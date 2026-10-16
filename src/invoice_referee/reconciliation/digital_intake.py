"""Digital web-form intake: validation + declaration->paper adapter (S6).

A DIGITAL_FORM declaration becomes a synthetic SETTLEMENT_FORM whose refs
point at the declaration itself (real digest of the stored declaration +
record_key per line) — never fake OCR. Evidence mapping resolves by attached
source id; after the evidence files are read, mapped document numbers become
the row's invoice_refs so the SAME match/admission/policy/money core runs.
"""

from __future__ import annotations

import hashlib
from datetime import date

from invoice_referee.domain.commands import Declaration
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentAnalysis,
    DocumentLine,
    FieldCandidate,
)


def canonical_digest(declaration: Declaration) -> str:
    """Hash the digital-intake subset only (S6, fixed 18/10/2026).

    The save-time and submit-time Declaration envelopes legitimately differ
    (notes/incurred_total/paper corrections ride along at submit), so the
    read/submit match must cover exactly the declared rows + kind + purpose +
    no-advance assertion — never the whole envelope.
    """
    import json as _json

    payload = {
        "declared_purpose": declaration.declared_purpose,
        "settlement_type": declaration.settlement_type,
        "digital_lines": [
            line.model_dump(mode="json") for line in declaration.digital_lines
        ],
        "no_advance_asserted": declaration.no_advance_asserted,
        "no_advance_reason": declaration.no_advance_reason,
    }
    return hashlib.sha256(
        _json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def validate_digital_declaration(
    declaration: Declaration, *, attached_source_ids: set[str]
) -> Declaration:
    """Server-side validation of a DIGITAL_FORM declaration (pure).

    Raises ValueError on anything the client must fix. Never trusts the
    frontend: source mapping, reason/note separation, dates and the
    self-expense/advance exclusions are all re-checked here.
    """
    if declaration.submission_source != "DIGITAL_FORM":
        raise ValueError("digital validation requires submission_source=DIGITAL_FORM")
    if not declaration.digital_lines:
        raise ValueError("DIGITAL_FORM requires at least one declared line")
    if declaration.settlement_type == "EMPLOYEE_REIMBURSEMENT":
        if declaration.declared_advance is not None:
            raise ValueError("self-expense must not declare an advance amount")
        if not declaration.no_advance_asserted:
            raise ValueError("self-expense requires an explicit no-advance assertion")
    seen: set[str] = set()
    for line in declaration.digital_lines:
        if line.item_id in seen:
            raise ValueError(f"duplicate declared item_id {line.item_id}")
        seen.add(line.item_id)
        try:
            parsed = date.fromisoformat(line.expense_date)
        except ValueError:
            raise ValueError(f"invalid expense_date for {line.item_id}") from None
        if parsed > date.today():
            raise ValueError(f"expense_date in the future for {line.item_id}")
        unknown = [s for s in line.source_ids if s not in attached_source_ids]
        if unknown:
            raise ValueError(
                f"line {line.item_id} maps unattached sources: {', '.join(unknown)}"
            )
        if line.evidence_status == "NO_EVIDENCE" and line.source_ids:
            raise ValueError(f"NO_EVIDENCE line {line.item_id} must not map sources")
    return declaration


def digital_to_paper(
    declaration: Declaration,
    *,
    root_id: str,
    evidence_numbers: dict[str, str],
) -> DocumentAnalysis:
    """Build the synthetic settlement paper from a validated declaration."""
    validate_digital_declaration(declaration, attached_source_ids=set(evidence_numbers))
    digest = canonical_digest(declaration)
    declaration_source = f"declaration:{root_id}"

    def _ref(item_id: str, quote: str) -> EvidenceRef:
        return EvidenceRef(
            source_id=declaration_source,
            source_sha256=digest,
            page=None,
            record_key=f"digital-line:{item_id}",
            exact_quote=quote,
        )

    lines: list[DocumentLine] = []
    total = 0
    for line in declaration.digital_lines:
        numbers = []
        for source_id in line.source_ids:
            number = evidence_numbers.get(source_id)
            if number is None:
                raise ValueError(
                    f"line {line.item_id} maps source {source_id} "
                    "with no read document number"
                )
            numbers.append(number)
        total += int(line.amount)
        quote = line.description
        fields = [
            FieldCandidate(
                field="description",
                state="FOUND",
                value=line.description,
                refs=(_ref(line.item_id, quote),),
            ),
            FieldCandidate(
                field="amount",
                state="FOUND",
                value=int(line.amount),
                refs=(_ref(line.item_id, quote),),
            ),
        ]
        if numbers:
            fields.append(
                FieldCandidate(
                    field="invoice_refs",
                    state="FOUND",
                    value=tuple(numbers),
                    refs=(_ref(line.item_id, quote),),
                )
            )
        if line.exception_reason:
            fields.append(
                FieldCandidate(
                    field="no_evidence_reason",
                    state="FOUND",
                    value=line.exception_reason,
                    refs=(_ref(line.item_id, line.exception_reason),),
                )
            )
        if line.note:
            fields.append(
                FieldCandidate(
                    field="note",
                    state="FOUND",
                    value=line.note,
                    refs=(_ref(line.item_id, line.note),),
                )
            )
        lines.append(DocumentLine(id=f"digital:{line.item_id}", fields=tuple(fields)))

    purpose_quote = declaration.declared_purpose
    return DocumentAnalysis(
        source_id=declaration_source,
        document_id=f"{declaration_source}:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(
            FieldCandidate(
                field="purpose",
                state="FOUND",
                value=declaration.declared_purpose,
                refs=(_ref("header", purpose_quote),),
            ),
            FieldCandidate(
                field="printed_total",
                state="FOUND",
                value=total,
                refs=(_ref("header", purpose_quote),),
            ),
        ),
        line_items=tuple(lines),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _evidence_numbers(documents: list) -> dict[str, str]:
    """source_id -> document_number for read evidence (server-resolved)."""
    out: dict[str, str] = {}
    for document in documents:
        for candidate in document.fields:
            if candidate.field == "document_number" and candidate.state == "FOUND":
                out[document.source_id] = str(candidate.value)
    return out


async def read_digital_report(
    *,
    declaration: Declaration,
    root_id: str,
    sources: tuple,
    reader: object,
    classifier: object,
    artifacts: object,
    source_bytes: dict[str, bytes],
    budget,
    provider_mode: str,
    activity_profile: str | None = None,
):
    """Read evidence files + declared rows into one typed report (S6).

    Same stage functions as the paper pipeline (OCR -> confidence -> extract ->
    validate -> match); only the paper differs — it is synthesized from the
    validated declaration (provenance DECLARATION) instead of OCR. Evidence
    mapping resolves by attached source id; document numbers read from the
    evidence become the synthetic rows' invoice_refs so matching stays
    content-bound.
    """
    from invoice_referee.domain.documents import PageCoverage
    from invoice_referee.domain.evidence import ReadResult
    from invoice_referee.domain.issues import ProcessingProblem
    from invoice_referee.evidence.document_validity import validate_document
    from invoice_referee.evidence.extraction import extract_evidence_document
    from invoice_referee.evidence.matching import match_paper_evidence
    from invoice_referee.evidence.ocr_quality import (
        collect_low_confidence_blocks,
        review_ocr_quality,
    )
    from invoice_referee.evidence.prompts import role_aware_reader_identity
    from invoice_referee.evidence.telemetry import step
    from invoice_referee.evidence.trace import stage_payload
    from invoice_referee.reconciliation.document_arithmetic import (
        check_document_arithmetic,
    )

    validate_digital_declaration(
        declaration, attached_source_ids={s.id for s in sources}
    )
    reader_identity = role_aware_reader_identity(
        reader=reader, classifier=classifier, activity_profile=activity_profile
    )
    ocr_results, confidence_candidates, source_problems = [], [], []
    ocr_by_id: dict[str, object] = {}
    for source in sources:
        payload = source_bytes.get(source.id)
        if payload is None:
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
        result = await reader.read_source(  # type: ignore[attr-defined]
            source,
            budget=budget,
            artifacts=artifacts,
            source_bytes=payload,
            expected_pages=None,
            root_id=root_id,
        )
        ocr_results.append(result)
        ocr_by_id[source.id] = result
        source_candidates = collect_low_confidence_blocks(result)
        confidence_candidates.extend(source_candidates)
    ocr = tuple(ocr_results)
    if confidence_candidates:
        review = await review_ocr_quality(
            tuple(confidence_candidates), llm=classifier, budget=budget, sources=ocr
        )
    else:
        from invoice_referee.domain.documents import ConfidenceReview

        review = ConfidenceReview(
            status="SKIPPED_NO_NUMERIC_CANDIDATES", block_assessments=()
        )
    documents = []
    for source in sources:
        ocr_result = ocr_by_id.get(source.id)
        if ocr_result is None or not budget.can_call_llm():
            continue
        with step(
            f"extract:evidence:{source.id}", metadata={"trace_stage": "extraction"}
        ) as s:
            analysis = await extract_evidence_document(
                ocr_result, llm=classifier, budget=budget
            )
            if analysis.document_type == "SETTLEMENT_FORM":
                source_problems.append(
                    ProcessingProblem(
                        kind="UNSUPPORTED",
                        affected_fields=(source.id,),
                        message="file vai trò evidence nhưng nội dung là đơn quyết toán",
                        relevance="MATERIAL",
                        blocking=True,
                        next_action="fix_upload_role",
                    )
                )
            s.outputs.update(
                stage_payload(
                    "extraction",
                    {
                        "document_id": analysis.document_id,
                        "document_type": analysis.document_type,
                    },
                )
            )
        analysis = validate_document(
            analysis, ocr_result, review, activity_profile=activity_profile
        )
        check_document_arithmetic(analysis)
        documents.append(analysis)
    numbers = _evidence_numbers(documents)
    paper = digital_to_paper(declaration, root_id=root_id, evidence_numbers=numbers)
    with step("match", metadata={"trace_stage": "matching"}):
        matching = match_paper_evidence(paper, tuple(documents))
    origin = {"LIVE": "LIVE_READ", "RECORDED_REPLAY": "RECORDED_REPLAY"}.get(
        provider_mode, "STUB_TRANSCRIPTION"
    )
    problems = tuple(source_problems) + tuple(p for r in ocr for p in r.problems)
    return ReadResult(
        provider_mode=provider_mode,
        data_origin=origin,
        reader_identity=reader_identity,
        documents=(paper, *documents),
        links=matching.links,
        row_matches=matching.rows,
        match_findings=matching.findings,
        page_coverage_detail=tuple(
            PageCoverage(
                source_id=r.source_id,
                page=p.page,
                state="OCR_COMPLETE",
                artifact_ref=r.raw_artifact_ref,
            )
            for r in ocr
            for p in r.pages
        ),
        problems=problems,
    )
