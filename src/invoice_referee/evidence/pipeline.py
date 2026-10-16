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
import hashlib
from dataclasses import dataclass
from pathlib import Path

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evaluation.models import Transcription, TranscriptionFact
from invoice_referee.evidence.trace import ProviderMode, RunBudget, stage_payload


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


def _trace_ref(ref: object) -> dict[str, object]:
    return {
        "source_id": getattr(ref, "source_id", None),
        "source_sha256": getattr(ref, "source_sha256", None),
        "page": getattr(ref, "page", None),
    }


def _trace_field(field: object) -> dict[str, object]:
    state = getattr(field, "state", "UNKNOWN")
    result: dict[str, object] = {
        "field": getattr(field, "field", ""),
        "state": state,
        "value": getattr(field, "value", None) if state == "FOUND" else None,
        "refs": [_trace_ref(ref) for ref in getattr(field, "refs", ())],
    }
    alternatives = getattr(field, "alternatives", ())
    if alternatives:
        result["alternatives"] = [
            {"value": item.value, "refs": [_trace_ref(ref) for ref in item.refs]}
            for item in alternatives
        ]
    return result


def _trace_profile_findings(findings: tuple[object, ...]) -> list[dict[str, object]]:
    return [
        {
            "code": getattr(finding, "code", "UNKNOWN"),
            "field": getattr(finding, "field", None),
            "status": getattr(finding, "status", "UNKNOWN"),
            "blocking": getattr(finding, "blocking", None),
            "reason": getattr(finding, "message", ""),
            "refs": [_trace_ref(ref) for ref in getattr(finding, "refs", ())],
        }
        for finding in findings
    ]


def _trace_document(classification: object) -> dict[str, object]:
    return {
        "document_id": getattr(classification, "document_id", None),
        "source_id": getattr(classification, "source_id", None),
        "document_type": getattr(classification, "document_type", None),
        "roles": list(getattr(classification, "roles", ())),
        "page_range": list(getattr(classification, "page_range", ())),
        "confidence": getattr(classification, "classification_confidence", None),
        "alternatives": list(getattr(classification, "alternative_document_types", ())),
        "refs": [_trace_ref(ref) for ref in getattr(classification, "refs", ())],
    }


def _trace_document_analysis(analysis: object) -> dict[str, object]:
    lines = getattr(analysis, "line_items", ())
    return {
        "document_id": getattr(analysis, "document_id", None),
        "document_type": getattr(analysis, "document_type", None),
        "source_id": getattr(analysis, "source_id", None),
        "page_range": list(getattr(analysis, "page_range", ())),
        "roles": list(getattr(analysis, "roles", ())),
        "fields": [_trace_field(field) for field in getattr(analysis, "fields", ())],
        "line_items": [
            {
                "item_id": line.id,
                "fields": [_trace_field(field) for field in line.fields],
                "refs": [_trace_ref(ref) for ref in line.refs],
            }
            for line in lines
        ],
        "refs": [_trace_ref(ref) for ref in getattr(analysis, "refs", ())],
    }


def _trace_matching(matching: object) -> dict[str, object]:
    links = getattr(matching, "links", ())
    rows = getattr(matching, "rows", ())
    findings = getattr(matching, "findings", ())
    return {
        "links": [
            {
                "item_id": link.item_id,
                "document_id": link.document_id,
                "source_id": link.source_id,
                "status": link.status,
                "method": link.method,
                "score": link.score,
                "allocated_amount": link.allocated_amount,
                "refs": [_trace_ref(ref) for ref in link.refs],
            }
            for link in links
        ],
        "rows": [
            {
                "item_id": row.item_id,
                "paper_amount": row.paper_amount,
                "category_candidate": row.category_candidate,
                "evidence_status": row.evidence_status,
                "alternative_evidence_type": row.alternative_evidence_type,
                "original_total": row.original_total,
                "allocated_total": row.allocated_total,
                "refs": [_trace_ref(ref) for ref in row.refs],
            }
            for row in rows
        ],
        "findings": [
            {
                "code": finding.code,
                "status": finding.status,
                "reason": finding.message,
                "refs": [_trace_ref(ref) for ref in finding.refs],
            }
            for finding in findings
        ],
    }


def trace_read_report(
    report: object,
    *,
    status: str = "COMPLETED",
    state_after: str | None = None,
    version_after: int | None = None,
    draft: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return the bounded, privacy-filtered summary used by read-operation roots."""
    documents = []
    findings: list[dict[str, object]] = []
    for document in getattr(report, "documents", ()):
        summary = _trace_document_analysis(document)
        summary["profile_status"] = getattr(document, "profile_status", "UNKNOWN")
        summary["findings"] = _trace_profile_findings(
            tuple(getattr(document, "profile_findings", ()))
        )
        documents.append(summary)
        findings.extend(summary["findings"])
    for finding in getattr(report, "match_findings", ()):
        findings.append(
            {
                "code": finding.code,
                "status": finding.status,
                "reason": finding.message,
                "refs": [_trace_ref(ref) for ref in finding.refs],
            }
        )
    for problem in getattr(report, "problems", ()):
        findings.append(
            {
                "code": getattr(problem, "kind", "TECHNICAL"),
                "status": "BLOCKING" if getattr(problem, "blocking", False) else "OBSERVED",
                "affected_fields": list(getattr(problem, "affected_fields", ())),
                "next_action": getattr(problem, "next_action", None),
            }
        )
    return stage_payload(
        "read_root",
        {
            "status": status,
            "provider_mode": getattr(report, "provider_mode", None),
            "document_count": len(getattr(report, "documents", ())),
            "link_count": len(getattr(report, "links", ())),
            "row_match_count": len(getattr(report, "row_matches", ())),
            "problem_count": len(getattr(report, "problems", ())),
            "documents": documents,
            "findings": findings,
            "state_after": state_after,
            "version_after": version_after,
            "draft": draft,
        },
    )


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
    from invoice_referee.reconciliation.document_arithmetic import check_document_arithmetic

    from invoice_referee.domain.issues import ProcessingProblem
    from invoice_referee.evidence.prompts import evidence_reader_identity
    reader_identity = evidence_reader_identity(reader=reader, classifier=classifier,
                                               activity_profile=activity_profile)

    ocr_results = []
    confidence_candidates = []
    source_problems: list[ProcessingProblem] = []
    for source in sources:
        payload = source_bytes.get(source.id)
        provider_client = getattr(reader, "provider", None)
        configured_provider = (
            getattr(provider_client, "provider_name", None)
            or type(provider_client).__name__ if provider_client is not None else None
        )
        configured_model = getattr(provider_client, "model", None)
        expected_pages = None
        if payload is not None and source.media == "PDF":
            try:
                from invoice_referee.evidence.pdf import page_count_bytes

                expected_pages = page_count_bytes(payload)
            except Exception:
                expected_pages = None  # unreadable PDF: provider call reports the problem
        with step(
            f"ocr:{source.id}",
            metadata={"trace_stage": "ocr"},
            inputs=stage_payload(
                "ocr",
                {
                    "source_id": source.id,
                    "source_digest": source.digest,
                    "media": source.media,
                    "expected_pages": expected_pages,
                    "provider": configured_provider,
                    "model": configured_model,
                },
            ),
        ) as s:
            if payload is None:
                s.skipped = "missing_source_bytes"
                s.outputs.update(
                    stage_payload(
                        "ocr",
                        {
                            "pages_read": 0,
                            "coverage": {"expected_pages": expected_pages, "pages_read": 0},
                            "read_state": "NOT_READ",
                            "review_regions": 0,
                            "artifact_ref": None,
                            "complete": False,
                        },
                    )
                )
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
            result = await reader.read_source(
                source, budget=budget, artifacts=artifacts, source_bytes=payload,
                expected_pages=expected_pages, root_id=root_id,
            )
            s.inputs.update({"provider": result.provider, "model": result.model})
            source_candidates = collect_low_confidence_blocks(result)
            confidence_candidates.extend(source_candidates)
            artifact_ref = (
                f"local-artifact:{Path(result.raw_artifact_ref).name}"
                if result.raw_artifact_ref
                else None
            )
            pages_read = len(result.pages)
            s.outputs.update(
                stage_payload(
                    "ocr",
                    {
                        "provider": result.provider,
                        "model": result.model,
                        "pages_read": pages_read,
                        "coverage": {
                            "expected_pages": expected_pages,
                            "pages_read": pages_read,
                            "complete": result.complete,
                        },
                        "read_state": "READ" if pages_read and result.complete else (
                            "PARTIAL" if pages_read else "NOT_READ"
                        ),
                        "review_regions": len(source_candidates),
                        "artifact_ref": artifact_ref,
                        "complete": result.complete,
                    },
                )
            )
        ocr_results.append(result)
    ocr = tuple(ocr_results)

    # Confidence gate (one conditional batch).
    candidates = tuple(confidence_candidates)
    candidate_summaries = [
        {
            "candidate_id": candidate.candidate_id,
            "source_id": candidate.source_id,
            "page": candidate.page,
            "block_id": candidate.block_id,
            "low_word_count": len(candidate.low_words),
            "min_confidence": min(
                (word.confidence for word in candidate.low_words if word.confidence is not None),
                default=None,
            ),
        }
        for candidate in candidates
    ]
    with step(
        "confidence-review",
        metadata={"trace_stage": "confidence"},
        inputs=stage_payload(
            "confidence", {"candidate_count": len(candidates), "candidates": candidate_summaries}
        ),
    ) as s:
        if candidates:
            review = await review_ocr_quality(candidates, llm=classifier, budget=budget, sources=ocr)
            decisions = [
                {
                    "candidate_id": assessment.candidate_id,
                    "importance": assessment.importance,
                    "quality_state": assessment.quality_state,
                    "review_action": assessment.review_action,
                    "canonical_fields": list(assessment.canonical_fields),
                    "requires_verification": assessment.requires_verification,
                    "reason": assessment.reason,
                    "observed_text": assessment.observed_text,
                    "human_question": assessment.human_question,
                }
                for assessment in review.block_assessments
            ]
            s.outputs.update(
                stage_payload(
                    "confidence",
                    {
                        "status": review.status,
                        "candidate_count": len(candidates),
                        "decisions": decisions,
                        "findings": [
                            {
                                "candidate_id": item["candidate_id"],
                                "action": item["review_action"],
                                "requires_verification": item["requires_verification"],
                            }
                            for item in decisions
                            if item["review_action"] in ("ASK_HUMAN", "DEFER_TO_POLICY")
                            or item["requires_verification"] is True
                        ],
                    },
                )
            )
        else:
            # No numeric candidates: the model is not called; record the skip
            # honestly rather than as a successful review.
            from invoice_referee.domain.documents import ConfidenceReview

            review = ConfidenceReview(status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=())
            s.skipped = "no_low_confidence_candidates"
            s.outputs.update(
                stage_payload(
                    "confidence",
                    {
                        "status": review.status,
                        "candidate_count": 0,
                        "decisions": [],
                        "findings": [],
                        "skipped": "no_low_confidence_candidates",
                    },
                )
            )

    classification_inputs = [
        {
            "source_id": result.source_id,
            "source_digest": result.source_digest,
            "page_count": len(result.pages),
            "complete": result.complete,
        }
        for result in ocr
    ]
    with step(
        "classify",
        metadata={"trace_stage": "classification"},
        inputs=stage_payload(
            "classification", {"source_count": len(ocr), "sources": classification_inputs}
        ),
    ) as s:
        classifications = await classify_documents(ocr, llm=classifier, budget=budget)
        s.outputs.update(
            stage_payload(
                "classification",
                {
                    "status": "COMPLETED" if ocr else "SKIPPED_NO_SOURCES",
                    "skipped": None if ocr else "no_ocr_results",
                    "count": len(classifications),
                    "documents": [_trace_document(item) for item in classifications],
                },
            )
        )

    documents = []
    extraction_classes = [c for c in classifications if c.document_type != "UNKNOWN"]
    unresolved_classes = [c for c in classifications if c.document_type == "UNKNOWN"]
    unresolved_source_ids = {c.source_id for c in unresolved_classes}
    for classification in extraction_classes:
        source = next((r for r in ocr if r.source_id == classification.source_id), None)
        if source is None:
            continue
        with step(
            f"extract:{classification.document_type}",
            metadata={"trace_stage": "extraction"},
            inputs=stage_payload("extraction", {
                "document_id": classification.document_id,
                "document_type": classification.document_type,
                "source_id": source.source_id,
                "source_digest": source.source_digest,
                "page_range": list(classification.page_range),
                "confidence_status": review.status,
                "ocr_page_count": len(source.pages),
                "classification_confidence": classification.classification_confidence,
            }),
        ) as s:
            calls_before = budget.llm_attempts
            analysis = await extract_document(source, classification, llm=classifier, budget=budget)
            llm_attempts = max(0, budget.llm_attempts - calls_before)
            analysis_summary = _trace_document_analysis(analysis)
            fields, lines = analysis_summary["fields"], analysis_summary["line_items"]
            provenance_findings = [
                {"field": item["field"], "state": item["state"], "reason_code": "UNREADABLE_OR_UNRESOLVED"}
                for item in fields if item["state"] in ("UNREADABLE", "AMBIGUOUS")
            ]
            s.outputs.update(stage_payload("extraction", {
                "document_id": analysis.document_id,
                "document_type": analysis.document_type,
                "source_id": analysis.source_id,
                "source_digest": source.source_digest,
                "page_range": list(analysis.page_range),
                "parse_status": "PARSED" if fields or lines else "UNRESOLVED",
                "field_count": len(fields),
                "line_item_count": len(lines),
                "fields": fields,
                "line_items": lines,
                "source_refs": analysis_summary["refs"]
                    + [ref for line in lines for ref in line["refs"]]
                    + [ref for field in fields for ref in field["refs"]],
                "provenance_findings": provenance_findings,
                "repair_attempts": max(0, llm_attempts - 1),
                "llm_attempts": llm_attempts,
            }))
        with step(
            f"validate:{classification.document_type}",
            metadata={"trace_stage": "validation"},
            inputs=stage_payload("validation", {
                "document_id": analysis.document_id,
                "document_type": analysis.document_type,
                "source_id": source.source_id,
                "confidence_status": analysis.confidence_status,
                "input_fields": [_trace_field(field) for field in analysis.fields],
            }),
        ) as s:
            analysis = validate_document(analysis, source, review, activity_profile=activity_profile)
            arithmetic_findings = check_document_arithmetic(analysis)
            s.outputs.update(stage_payload("validation", {
                "document_id": analysis.document_id,
                "document_type": analysis.document_type,
                "profile_status": analysis.profile_status,
                "fields": [_trace_field(field) for field in analysis.fields],
                "findings": _trace_profile_findings(analysis.profile_findings),
                "blocking_count": sum(1 for finding in analysis.profile_findings if finding.blocking),
                "arithmetic_checks": {"state": "CHECKED_BY_SHARED_RULE", "findings": [
                    {"code": finding.code, "field_or_rule": finding.field_or_rule,
                     "basis": finding.basis, "refs": [_trace_ref(ref) for ref in finding.refs]}
                    for finding in arithmetic_findings]},
            }))
        documents.append(analysis)

    # UNKNOWN classifications are visible only when they carry a bounded set of
    # alternatives; unsupported cases remain source-scoped processing problems.
    if unresolved_classes:
        from invoice_referee.domain.documents import DocumentAnalysis
        for classification in unresolved_classes:
            source = next((r for r in ocr if r.source_id == classification.source_id), None)
            if source is None:
                continue
            if not any(p.kind == "UNSUPPORTED" and classification.source_id in p.affected_fields
                       for p in source_problems):
                source_problems.append(ProcessingProblem(
                    kind="UNSUPPORTED", affected_fields=(classification.source_id,),
                    message="loại tài liệu chưa được phân loại chắc chắn; cần xác minh",
                    relevance="MATERIAL", blocking=True, next_action="confirm_document_type",
                ))
            documents.append(DocumentAnalysis(
                source_id=source.source_id, document_id=classification.document_id,
                document_type="UNKNOWN", roles=("UNKNOWN",), page_range=classification.page_range,
                classification_confidence=classification.classification_confidence,
                alternative_document_types=classification.alternative_document_types,
                classification_refs=classification.refs, refs=classification.refs,
                confidence_status="UNRESOLVED", profile_status="UNKNOWN",
                warnings=("classification_unresolved",),
            ))
    if not documents and ocr and not source_problems:
        source_problems.append(ProcessingProblem(
            kind="UNSUPPORTED", affected_fields=tuple(r.source_id for r in ocr),
            message="no supported document type was classified", relevance="MATERIAL",
            blocking=True, next_action="confirm_document_type",
        ))
    if not sources:
        source_problems.append(ProcessingProblem(
            kind="UNSUPPORTED", affected_fields=(), message="no evidence sources provided",
            relevance="MATERIAL", blocking=True, next_action="attach_sources",
        ))

    paper = next((d for d in documents if d.document_type == "SETTLEMENT_FORM"), None)
    with step(
        "match",
        metadata={"trace_stage": "matching"},
        inputs=stage_payload("matching", {
            "paper_document_id": paper.document_id if paper else None,
            "document_count": len(documents),
            "row_count": len(paper.line_items) if paper else 0,
        }),
    ) as s:
        llm_attempts_before = budget.llm_attempts
        if paper is not None:
            matching = match_paper_evidence(paper, tuple(documents))
            suggestions_found = any(link.status == "SUGGEST_LINK" for link in matching.links)
            suggestion_count = sum(1 for link in matching.links if link.status == "SUGGEST_LINK")
            if suggestions_found:
                matching = await resolve_evidence_suggestions(
                    matching, tuple(documents), paper=paper, llm=classifier, budget=budget
                )
            else:
                s.skipped = "no_suggested_links"
        else:
            s.skipped = "no_settlement_form"
            from invoice_referee.domain.documents import EvidenceMatchFinding
            matching = EvidenceMatchingResult(findings=(EvidenceMatchFinding(
                code="SETTLEMENT_FORM_MISSING", status="UNRESOLVED",
                message="Không có giấy quyết toán (SETTLEMENT_FORM) để ghép chứng từ.", refs=(),
            ),))
            suggestions_found = False
            suggestion_count = 0
        actual_llm_calls = max(0, budget.llm_attempts - llm_attempts_before)
        matching_summary = _trace_matching(matching)
        s.outputs.update(stage_payload("matching", {
            "method": "rules+llm" if actual_llm_calls else "rules",
            "paper_document_id": paper.document_id if paper else None,
            "document_count": len(documents),
            "row_count": len(paper.line_items) if paper else 0,
            **matching_summary,
            "suggestions": suggestion_count,
            "llm_called": actual_llm_calls > 0,
            "resolved_suggestions": any(link.method == "LLM_RESOLVED" for link in matching.links),
        }))

    origin = {"LIVE": "LIVE_READ", "RECORDED_REPLAY": "RECORDED_REPLAY"}.get(
        provider_mode, "STUB_TRANSCRIPTION"
    )
    problems = tuple(source_problems) + tuple(p for result in ocr for p in result.problems)
    return ReadResult(
        provider_mode=provider_mode,
        data_origin=origin,
        reader_identity=reader_identity,
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
