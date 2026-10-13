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
# Order matters: a more specific cue (e.g. "công ty trả") is checked before a
# generic one so a line maps to the right field.
_FIELD_CUES: tuple[tuple[str, str], ...] = (
    ("công ty trả", "paid_company"),
    ("company paid", "paid_company"),
    ("nhân viên trả", "paid_employee"),
    ("employee paid", "paid_employee"),
    ("tổng chi", "incurred"),
    ("incurred", "incurred"),
    ("total", "incurred"),
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
    lines = text.splitlines()
    # A receipt names the payer ("Người thanh toán: <name>") and the amount
    # ("Đã thanh toán <amount>"). The payer decides whether the portion is the
    # employee-paid E candidate or the company-direct C portion.
    payer_line = next(
        (line for line in lines if "người thanh toán" in line.lower()), ""
    )
    amount_line = next(
        (line for line in lines if "đã thanh toán" in line.lower()), ""
    )
    if payer_line and amount_line:
        nums = _amounts(amount_line)
        payer_name = payer_line.split(":", 1)[-1].strip().lower()
        if nums:
            is_company = "công ty" in payer_name
            field = "paid_company" if is_company else "paid_employee"
            facts.append(
                TranscriptionFact(
                    field=field, value=nums[0], role="PAYMENT",
                    quote=amount_line.strip() or "payment",
                )
            )
            seen.add(field)
    for line in lines:
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
    merged: dict[str, TranscriptionFact] = {}
    for source in sources:
        for page in pages:
            text = await reader.ocr_page(source, page)
            if text and text.strip():
                read_pages += 1
            else:
                unread_pages += 1
            transcription = transcribe_text(text) if text else None
            if transcription is None:
                continue
            # Merge facts across the root's documents: each source carries a
            # different field set (invoice -> incurred, receipt -> paid, slip ->
            # advance). First writer wins so a field is not overwritten.
            for fact in transcription.facts:
                merged.setdefault(fact.field, fact)
    if not merged:
        return ReadOutcome(
            transcription=None,
            read_pages=read_pages,
            unread_pages=unread_pages,
            provider_mode=provider_mode,
        )
    origin = {
        "LIVE": "LIVE_READ",
        "RECORDED_REPLAY": "RECORDED_REPLAY",
    }.get(provider_mode, "STUB_TRANSCRIPTION")
    return ReadOutcome(
        transcription=Transcription(
            data_origin=origin,  # type: ignore[arg-type]
            facts=tuple(merged.values()),
        ),
        read_pages=read_pages,
        unread_pages=unread_pages,
        provider_mode=provider_mode,
    )
