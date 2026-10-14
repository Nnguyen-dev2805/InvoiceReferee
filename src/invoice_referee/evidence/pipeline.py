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


async def read_root(
    *,
    sources: tuple[SourceRef, ...],
    reader,
    classifier,
    artifacts,
    source_bytes: dict[str, bytes],
    budget: RunBudget,
    provider_mode: ProviderMode,
    root_id: str = "",
    activity_profile: str | None = None,
) -> "ReadResult":
    """Run the evidence pipeline: OCR -> confidence -> classify -> extract ->
    validate -> match. Stops before reconciliation/policy/finance (plan E7).

    The returned ReadResult is a typed evidence report only; nothing here has a
    financial effect.
    """
    from invoice_referee.domain.documents import EvidenceMatchingResult
    from invoice_referee.domain.evidence import ReadResult
    from invoice_referee.evidence.classification import classify_documents
    from invoice_referee.evidence.extraction import extract_document
    from invoice_referee.evidence.matching import match_paper_evidence, resolve_evidence_suggestions
    from invoice_referee.evidence.ocr_quality import collect_low_confidence_blocks, review_ocr_quality
    from invoice_referee.evidence.document_validity import validate_document
    from invoice_referee.evidence.telemetry import step

    from invoice_referee.domain.issues import ProcessingProblem

    ocr_results = []
    source_problems: list[ProcessingProblem] = []
    for source in sources:
        payload = source_bytes.get(source.id)
        if payload is None:
            # A missing source is NOT silently dropped: it is a material
            # technical problem, never a reduced source set (plan E7).
            source_problems.append(
                ProcessingProblem(
                    kind="TECHNICAL",
                    affected_fields=(source.id,),
                    message=f"nguồn {source.id} không đọc được bytes",
                    relevance="MATERIAL",
                    blocking=True,
                    next_action="reupload_source",
                )
            )
            continue
        expected_pages = None
        if source.media == "PDF":
            try:
                from invoice_referee.evidence.pdf import page_count_bytes

                expected_pages = page_count_bytes(payload)
            except Exception:
                expected_pages = None  # unreadable PDF: provider call reports the problem
        with step(
            f"ocr:{source.filename or source.id}",
            metadata={"source_id": source.id, "media": source.media},
        ) as s:
            result = await reader.read_source(
                source, budget=budget, artifacts=artifacts, source_bytes=payload,
                expected_pages=expected_pages, root_id=root_id,
            )
            s.outputs["pages"] = len(result.pages)
            s.outputs["complete"] = result.complete
        ocr_results.append(result)
    ocr = tuple(ocr_results)

    # Confidence gate (one conditional batch).
    candidates = tuple(c for result in ocr for c in collect_low_confidence_blocks(result))
    with step("confidence-review", metadata={"candidates": len(candidates)}) as s:
        if candidates:
            review = await review_ocr_quality(candidates, llm=classifier, budget=budget)
            s.outputs["status"] = review.status
        else:
            # No numeric candidates: the model is not called; record the skip
            # honestly rather than as a successful review.
            from invoice_referee.domain.documents import ConfidenceReview

            review = ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=())
            s.skipped = "no_low_confidence_candidates"
            s.outputs["status"] = review.status

    with step("classify", metadata={"documents": len(ocr)}) as s:
        classifications = await classify_documents(ocr, llm=classifier, budget=budget)
        s.outputs["count"] = len(classifications)

    documents = []
    for classification in classifications:
        source = next((r for r in ocr if r.source_id == classification.source_id), None)
        if source is None:
            continue
        with step(
            f"extract:{classification.document_type}",
            metadata={"document_id": classification.document_id, "document_type": classification.document_type},
        ) as s:
            analysis = await extract_document(source, classification, llm=classifier, budget=budget)
            s.outputs["profile_status"] = analysis.profile_status
        with step(
            f"validate:{classification.document_type}",
            metadata={"document_id": classification.document_id},
        ) as s:
            analysis = validate_document(
                analysis, source, review, activity_profile=activity_profile
            )
            s.outputs["profile_status"] = analysis.profile_status
            s.outputs["findings"] = len(analysis.profile_findings)
        documents.append(analysis)

    paper = next((d for d in documents if d.document_type == "SETTLEMENT_FORM"), None)
    with step("match", metadata={"has_paper": paper is not None}) as s:
        if paper is not None:
            matching = match_paper_evidence(paper, tuple(documents))
            s.outputs["links"] = len(matching.links)
            # One bounded suggestion-resolution batch, only when suggestions exist.
            if any(link.status == "SUGGEST_LINK" for link in matching.links):
                matching = await resolve_evidence_suggestions(
                    matching, tuple(documents), llm=classifier, budget=budget
                )
                s.outputs["resolved_suggestions"] = True
            else:
                s.outputs["resolved_suggestions"] = False
        else:
            s.skipped = "no_settlement_form"
            matching = EvidenceMatchingResult(
                findings=(
                    __import__("invoice_referee.domain.documents", fromlist=["EvidenceMatchFinding"]).EvidenceMatchFinding(
                        code="SETTLEMENT_FORM_MISSING",
                        status="UNRESOLVED",
                        message="Không có giấy quyết toán (SETTLEMENT_FORM) để ghép chứng từ.",
                        refs=(),
                    ),
                )
            )

    origin = {"LIVE": "LIVE_READ", "RECORDED_REPLAY": "RECORDED_REPLAY"}.get(
        provider_mode, "STUB_TRANSCRIPTION"
    )
    problems = tuple(source_problems) + tuple(p for result in ocr for p in result.problems)
    return ReadResult(
        provider_mode=provider_mode,
        data_origin=origin,
        documents=tuple(documents),
        links=matching.links,
        row_matches=matching.rows,
        match_findings=matching.findings,
        page_coverage_detail=tuple(
            __import__("invoice_referee.domain.documents", fromlist=["PageCoverage"]).PageCoverage(
                source_id=result.source_id, page=page.page, state="OCR_COMPLETE",
                artifact_ref=result.raw_artifact_ref,
            )
            for result in ocr
            for page in result.pages
        ),
        problems=problems,
    )
