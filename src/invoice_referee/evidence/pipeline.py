"""Read -> transcribe pipeline (contracts §5, §8; plan T5).

This is the seam that makes a LIVE submit actually read the uploaded sources:
it runs the reader over the root's sources and turns the page text into a
`Transcription` (the literal fields the Reconciler assesses). A page that was
not read produces no fact — never a fabricated zero — so an unreadable document
leaves the case unresolved instead of settling on nothing.

No provider credential, model name or source instruction lives here; the reader
is injected (a real Mistral-backed reader in LIVE, a fake in tests).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evaluation.models import Transcription, TranscriptionFact
from invoice_referee.evidence.trace import ProviderMode, RunBudget


@dataclass
class ReadOutcome:
    """What one read pass produced, plus the honest failure signal."""

    transcription: Transcription | None
    read_pages: int
    unread_pages: int
    provider_mode: ProviderMode


# Literal field cues for the demo extractor (bounded, no model, no confidence).
_FIELD_CUES: tuple[tuple[str, str], ...] = (
    ("incurred", "incurred"),
    ("tổng chi", "incurred"),
    ("total", "incurred"),
    ("nhân viên trả", "paid_employee"),
    ("employee paid", "paid_employee"),
    ("công ty trả", "paid_company"),
    ("company paid", "paid_company"),
    ("ứng", "advance"),
    ("advance", "advance"),
    ("hoàn trả", "returned"),
    ("đối chiếu", "coverage"),
    ("coverage", "coverage"),
)

_AMOUNT = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)")
_INVOICE = re.compile(r"(invoice:[A-Za-z0-9:_\-]+)")


def _amounts(text: str) -> list[int]:
    out: list[int] = []
    for match in _AMOUNT.finditer(text):
        try:
            out.append(int(match.group(1).replace(".", "")))
        except ValueError:
            continue
    return out


def transcribe_text(text: str) -> Transcription | None:
    """Turn one page's literal text into a transcription, or None if unreadable.

    The extractor is deliberately literal: it maps a small set of cue phrases to
    fields and reads the first amount on the matching line. It never invents a
    field that is absent, so a blank/unreadable page yields None (not zeros).
    """
    if not text or not text.strip():
        return None
    facts: list[TranscriptionFact] = []
    seen: set[str] = set()
    lowered = text.lower()
    for line in text.splitlines():
        line_lower = line.lower()
        for cue, field in _FIELD_CUES:
            if cue in line_lower and field not in seen:
                if field == "coverage":
                    facts.append(
                        TranscriptionFact(
                            field="coverage", value=1, role="LEDGER", quote=line.strip() or cue
                        )
                    )
                    seen.add(field)
                    break
                nums = _amounts(line)
                if nums:
                    facts.append(
                        TranscriptionFact(
                            field=field,
                            value=nums[0],
                            role="INVOICE" if field == "incurred" else "PAYMENT",
                            quote=line.strip() or cue,
                        )
                    )
                    seen.add(field)
                    break
    invoice = _INVOICE.search(text)
    if invoice is not None:
        facts.append(
            TranscriptionFact(
                field="economic_key", value=invoice.group(1), role="INVOICE", quote=invoice.group(1)
            )
        )
    if not facts:
        # Text present but no recognisable field: not a readable business doc.
        return None
    # A required incurred cost with no coverage is still a valid (partial) read;
    # the Reconciler decides what is unresolved.
    _ = lowered
    return Transcription(facts=tuple(facts))


async def transcribe_root(
    *,
    reader,
    sources: tuple[SourceRef, ...],
    budget: RunBudget,
    provider_mode: ProviderMode,
    pages: tuple[int, ...] = (1,),
) -> ReadOutcome:
    """Read the root's sources and produce one transcription (contracts §5).

    Every source is read; the first page with recognisable fields wins. Pages
    that return no text are counted as unread, and a run with no readable page
    yields ``transcription=None`` so the workflow keeps the case unresolved.
    """
    read_pages = 0
    unread_pages = 0
    for source in sources:
        for page in pages:
            text = await reader.ocr_page(source, page)
            if text and text.strip():
                read_pages += 1
            else:
                unread_pages += 1
            transcription = transcribe_text(text) if text else None
            if transcription is not None:
                return ReadOutcome(
                    transcription=transcription,
                    read_pages=read_pages,
                    unread_pages=unread_pages,
                    provider_mode=provider_mode,
                )
    return ReadOutcome(
        transcription=None,
        read_pages=read_pages,
        unread_pages=unread_pages,
        provider_mode=provider_mode,
    )
