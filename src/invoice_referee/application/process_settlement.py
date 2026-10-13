"""Durable UC-03 worker: source gate, quality, extraction, policy, decision."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from invoice_referee.application.decision_guard import build_settlement_decision
from invoice_referee.application.paper_evidence_matching import match_paper_evidence
from invoice_referee.application.process_case import (
    SETTLEMENT_BLOCKING_FIELDS,
    CaseProcessingService,
)
from invoice_referee.application.settlement_summary import (
    build_settlement_success_reason,
)
from invoice_referee.domain import (
    DecisionTarget,
    DocumentValidityResult,
    DocumentValidityStatus,
    DocumentFieldImportance,
    ExpenseDocumentType,
    ExpenseDocumentFacts,
    ExpenseEvidenceStatus,
    ExpenseItemDraft,
    ORIGINAL_EXPENSE_DOCUMENT_TYPES,
    PaperSettlementFacts,
    SettlementDocumentRole,
    SettlementDraft,
    SettlementFinding,
    SettlementType,
    SubmissionSourceType,
    UncertaintyType,
)
from invoice_referee.extraction import (
    DEFAULT_WORD_REVIEW_THRESHOLD,
    ExternalServiceUnavailableError,
    collect_low_confidence_blocks,
    restructure_mistral_ocr,
)
from invoice_referee.policy import (
    SettlementPolicyConfig,
    evaluate_settlement_policy,
    field_importance,
    validate_expense_document,
    validate_paper_settlement_document,
)
from invoice_referee.storage import SQLiteSettlementRepository

OCR_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png", ".webp"}
SOURCE_GATE_RULES = {
    "SET_CONTEXT_001",
    "SET_INPUT_001",
    "SET_ADV_001",
    "SET_DOC_001",
}

VALIDITY_TO_CONFIDENCE_FIELDS = {
    "issuer_name": {"seller_name"},
    "issuer_tax_code": {"seller_tax_code"},
    "buyer_name": {"buyer_name"},
    "buyer_tax_code": {"buyer_tax_code"},
    "document_number": {"invoice_number", "transaction_reference"},
    "template_number": {"template_number"},
    "serial_number": {"serial_number"},
    "document_date": {"invoice_date"},
    "total_amount": {"total_amount"},
    "line_items": {"item_name", "quantity", "unit_price", "line_amount"},
    "payer_name": {"buyer_name"},
    "payee_name": {"seller_name"},
    "transaction_reference": {"transaction_reference"},
    "transaction_status": {"transaction_status"},
    "confirmation_present": {"receipt_status"},
    "purpose": {"business_purpose"},
    "advance_amount": {"total_amount"},
}


def _required_confidence_fields(
    validity: DocumentValidityResult,
) -> set[str]:
    fields: set[str] = set()
    for field_name in validity.required_fields:
        try:
            document_type = ExpenseDocumentType(validity.document_type)
        except ValueError:
            continue
        if field_importance(document_type, field_name) != DocumentFieldImportance.CRITICAL:
            continue
        fields.update(VALIDITY_TO_CONFIDENCE_FIELDS.get(field_name, set()))
    return fields.intersection(SETTLEMENT_BLOCKING_FIELDS)


def _usable_confidence_fields(validity: DocumentValidityResult) -> set[str]:
    """Canonical fields already extracted safely from this same document."""

    fields: set[str] = set()
    for field_name in validity.present_fields:
        fields.update(VALIDITY_TO_CONFIDENCE_FIELDS.get(field_name, set()))
    return fields


def _ocr_markdown(response: dict[str, Any]) -> str:
    return "\n\n".join(
        str(page.get("markdown") or "").strip()
        for page in response.get("pages") or []
        if str(page.get("markdown") or "").strip()
    )


def _validity_findings(
    result: DocumentValidityResult,
    *,
    filename: str,
) -> list[SettlementFinding]:
    source_refs = result.source_refs or [f"DOC:{result.document_id}"]
    findings: list[SettlementFinding] = []
    for issue in result.issues:
        unresolved_invoice_identity = (
            result.document_type == ExpenseDocumentType.E_INVOICE.value
            and issue.code in {"REQUIRED_FIELD_UNCLEAR", "REQUIRED_FIELD_GROUP_UNCLEAR"}
            and issue.importance == DocumentFieldImportance.CRITICAL
        )
        if issue.code.startswith("DOCUMENT_TYPE"):
            rule_id = "SET_DOCUMENT_CLASSIFICATION_001"
        elif issue.code == "BUYER_TAX_CODE_MISMATCH":
            rule_id = "SET_BUYER_IDENTITY_001"
        elif issue.code == "PAPER_FORM_DATA_WARNING":
            rule_id = "SET_PAPER_CONSISTENCY_001"
        elif issue.code == "DOCUMENT_DATA_WARNING":
            rule_id = "SET_DOCUMENT_CONSISTENCY_001"
        elif result.document_type == "PAPER_SETTLEMENT_REQUEST":
            rule_id = "SET_PAPER_FORM_VALIDITY_001"
        else:
            rule_id = "SET_DOCUMENT_REQUIRED_FIELDS_001"
        outside_policy = issue.code == "BUYER_TAX_CODE_MISMATCH"
        status = "FAIL" if issue.blocking or unresolved_invoice_identity else "WARN"
        findings.append(
            SettlementFinding(
                rule_id=rule_id,
                status=status,
                message=f"Chứng từ '{filename}': {issue.message}",
                uncertainty_type=(
                    UncertaintyType.OUTSIDE_POLICY
                    if outside_policy or unresolved_invoice_identity
                    else UncertaintyType.NONE
                    if status != "FAIL"
                    else UncertaintyType.FACTUAL_UNKNOWN
                ),
                target=DecisionTarget.ACCOUNTANT,
                question=issue.question if status == "FAIL" else None,
                source_refs=source_refs,
            )
        )
    if result.status == DocumentValidityStatus.CLEAR:
        findings.append(
            SettlementFinding(
                rule_id="SET_DOCUMENT_VALIDITY_001",
                status="PASS",
                message=(
                    f"Chứng từ '{filename}' được phân loại là "
                    f"{result.document_type} và đủ dữ kiện bắt buộc."
                ),
                source_refs=source_refs,
            )
        )
    return findings


class SettlementProcessingService:
    """Process one queued settlement independently from an HTTP request."""

    def __init__(
        self,
        repository: SQLiteSettlementRepository,
        *,
        policy: SettlementPolicyConfig | None = None,
        ocr_adapter: Any | None = None,
        reasoning_adapter: Any | None = None,
        enable_document_pipeline: bool = False,
        word_confidence_threshold: float = DEFAULT_WORD_REVIEW_THRESHOLD,
    ) -> None:
        self.repository = repository
        self.policy = policy or SettlementPolicyConfig()
        self.ocr_adapter = ocr_adapter
        self.reasoning_adapter = reasoning_adapter
        self.enable_document_pipeline = enable_document_pipeline
        self.word_confidence_threshold = word_confidence_threshold

    def run_once(self) -> bool:
        job = self.repository.claim_next_job()
        if job is None:
            return False
        case_id = str(job["case_id"])
        job_id = str(job["job_id"])
        try:
            processing_input = self.repository.load_processing_input(case_id)
            draft = SettlementDraft.model_validate(processing_input["canonical"])
            documents = processing_input["documents"]
            has_paper_form = any(
                document["role"]
                == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
                for document in documents
            )

            preliminary = evaluate_settlement_policy(
                draft,
                has_paper_form=has_paper_form,
                config=self.policy,
            )
            source_findings = [
                finding
                for finding in preliminary
                if finding.rule_id in SOURCE_GATE_RULES
            ]
            if any(finding.status == "FAIL" for finding in source_findings):
                self._finish(job_id, case_id, source_findings)
                return True

            quality_findings: list[SettlementFinding] = []
            document_facts: list[ExpenseDocumentFacts] = []
            if self.enable_document_pipeline:
                quality_findings, document_facts, paper_facts = self._process_documents(
                    case_id,
                    documents,
                    draft,
                )
                if any(finding.status == "FAIL" for finding in quality_findings):
                    self._finish(
                        job_id,
                        case_id,
                        [*source_findings, *quality_findings],
                    )
                    return True
            else:
                paper_facts = None

            if draft.source_type == SubmissionSourceType.PAPER_SCAN:
                self._finish_paper_case(
                    job_id=job_id,
                    case_id=case_id,
                    draft=draft,
                    documents=documents,
                    quality_findings=quality_findings,
                    document_facts=document_facts,
                    paper_facts=paper_facts,
                    has_paper_form=has_paper_form,
                )
                return True
            findings = evaluate_settlement_policy(
                draft,
                has_paper_form=has_paper_form,
                config=self.policy,
            )
            findings.extend(quality_findings)
            if self.enable_document_pipeline:
                findings.extend(
                    self._reconciliation_findings(
                        draft,
                        documents,
                        document_facts,
                    )
                )

            self._finish(job_id, case_id, findings)
        except Exception as exc:
            self.repository.fail_job(job_id, case_id, str(exc))
        return True

    def _finish(
        self,
        job_id: str,
        case_id: str,
        findings: list[SettlementFinding],
    ) -> None:
        decision = build_settlement_decision(
            findings,
            success_reason=build_settlement_success_reason(
                self.repository.get_case(case_id)
            ),
        )
        self.repository.complete_job(job_id, case_id, findings, decision)

    def _process_documents(
        self,
        case_id: str,
        documents: list[dict[str, Any]],
        draft: SettlementDraft,
    ) -> tuple[
        list[SettlementFinding],
        list[ExpenseDocumentFacts],
        PaperSettlementFacts | None,
    ]:
        findings: list[SettlementFinding] = []
        facts: list[ExpenseDocumentFacts] = []
        paper_facts: PaperSettlementFacts | None = None
        if self.ocr_adapter is None:
            return [
                SettlementFinding(
                    rule_id="SET_QUALITY_001",
                    status="FAIL",
                    message="Dịch vụ OCR chưa được cấu hình cho hồ sơ UC-03.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question="Vui lòng cấu hình OCR hoặc kiểm tra chứng từ thủ công.",
                )
            ], [], None
        if self.reasoning_adapter is None:
            return [
                SettlementFinding(
                    rule_id="SET_EXTRACTION_001",
                    status="FAIL",
                    message="Extraction Agent chưa được cấu hình cho hồ sơ UC-03.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question=(
                        "Vui lòng cấu hình Extraction Agent hoặc nhập dữ kiện "
                        "chứng từ thủ công."
                    ),
                )
            ], [], None

        for document in documents:
            document_id = str(document["document_id"])
            path = self.repository.document_path(case_id, document_id)
            if path.suffix.lower() not in OCR_SUFFIXES:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_QUALITY_001",
                        status="FAIL",
                        message=(
                            f"Chưa hỗ trợ đọc tự động file "
                            f"'{document['original_name']}'."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        source_refs=[f"DOC:{document_id}"],
                    )
                )
                continue
            try:
                execution = self.ocr_adapter.process(path, document["mime_type"])
                stored_ocr = {
                    "schema_version": "1.0",
                    "case_id": case_id,
                    "document_id": document_id,
                    "source_file": document["original_name"],
                    **execution.to_dict(),
                }
                self.repository.save_json_artifact(
                    case_id,
                    "ocr",
                    f"{document_id}.json",
                    stored_ocr,
                )
                hierarchy = restructure_mistral_ocr(stored_ocr)
                candidates = collect_low_confidence_blocks(
                    hierarchy,
                    evidence_id=document_id,
                    threshold=self.word_confidence_threshold,
                )
                for candidate in candidates:
                    candidate["source_file"] = document["original_name"]

                extraction_payload = {
                    "case_id": case_id,
                    "document_id": document_id,
                    "filename": document["original_name"],
                    "role": document["role"],
                    "ocr_text": _ocr_markdown(execution.response),
                }
                if (
                    document["role"]
                    == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
                ):
                    extracted_paper = self.reasoning_adapter.extract_paper_settlement(
                        extraction_payload
                    )
                    if extracted_paper.document_id != document_id:
                        raise ValueError(
                            "Paper Extraction Agent trả document_id không khớp nguồn."
                        )
                    artifact_payload = extracted_paper.model_dump(mode="json")
                    validity = validate_paper_settlement_document(
                        extracted_paper,
                        advance_amount_required=(
                            draft.settlement_type
                            == SettlementType.ADVANCE_SETTLEMENT
                        ),
                    )
                else:
                    extracted = self.reasoning_adapter.extract_expense_document(
                        extraction_payload
                    )
                    if extracted.document_id != document_id:
                        raise ValueError(
                            "Extraction Agent trả document_id không khớp nguồn."
                        )
                    artifact_payload = extracted.model_dump(mode="json")
                    validity = validate_expense_document(
                        extracted,
                        company_tax_codes=self.policy.company_tax_codes,
                    )
                self.repository.save_json_artifact(
                    case_id,
                    "facts",
                    f"{document_id}.json",
                    artifact_payload,
                )
                self.repository.save_json_artifact(
                    case_id,
                    "validity",
                    f"{document_id}.json",
                    validity.model_dump(mode="json"),
                )
                confidence_blocking_fields = _required_confidence_fields(validity)
                usable_confidence_fields = _usable_confidence_fields(validity)

                if candidates:
                    confidence = self.reasoning_adapter.analyze_confidence(
                        {
                            "case_id": case_id,
                            "ocr_word_review_threshold": self.word_confidence_threshold,
                            "evidence": {
                                "evidence_id": document_id,
                                "role": document["role"],
                                "filename": document["original_name"],
                                "document_type": validity.document_type,
                                "required_fields": validity.required_fields,
                                "extracted_usable_fields": sorted(
                                    usable_confidence_fields
                                ),
                                "ocr_text": _ocr_markdown(execution.response),
                                "candidate_blocks": candidates,
                            },
                        }
                    )
                    legacy_findings = CaseProcessingService._confidence_findings(
                        candidates,
                        confidence,
                        blocking_fields=confidence_blocking_fields,
                        usable_fields=usable_confidence_fields,
                    )
                    for finding in legacy_findings:
                        detailed_source_refs = [
                            (
                                f"DOC:{source_ref}"
                                if source_ref.startswith(f"{document_id}:")
                                else f"DOC:{document_id}"
                            )
                            for source_ref in finding.source_refs
                        ] or [f"DOC:{document_id}"]
                        findings.append(
                            SettlementFinding(
                                rule_id="SET_QUALITY_001",
                                status=(
                                    "FAIL"
                                    if finding.status in {"FAIL", "ERROR"}
                                    else finding.status
                                ),
                                message=finding.message,
                                uncertainty_type=(
                                    UncertaintyType.FACTUAL_UNKNOWN
                                    if finding.status in {"FAIL", "ERROR"}
                                    else UncertaintyType.NONE
                                ),
                                target=DecisionTarget.ACCOUNTANT,
                                question=(
                                    finding.message
                                    if finding.status in {"FAIL", "ERROR"}
                                    else None
                                ),
                                source_refs=list(dict.fromkeys(detailed_source_refs)),
                            )
                        )
                else:
                    findings.append(
                        SettlementFinding(
                            rule_id="SET_QUALITY_001",
                            status="PASS",
                            message=(
                                f"Chứng từ '{document['original_name']}' vượt "
                                "qua ngưỡng chất lượng OCR."
                            ),
                            source_refs=[f"DOC:{document_id}"],
                        )
                    )

                findings.extend(
                    _validity_findings(
                        validity,
                        filename=document["original_name"],
                    )
                )
                if any(
                    finding.status == "FAIL"
                    and any(
                        source_ref == f"DOC:{document_id}"
                        or source_ref.startswith(f"DOC:{document_id}:")
                        for source_ref in finding.source_refs
                    )
                    for finding in findings
                ):
                    continue
                if validity.eligible_for_matching:
                    if (
                        document["role"]
                        == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
                    ):
                        paper_facts = extracted_paper
                    else:
                        facts.append(extracted)
            except ExternalServiceUnavailableError:
                raise
            except Exception as exc:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_EXTRACTION_001",
                        status="FAIL",
                        message=(
                            f"Chưa đọc xong chứng từ "
                            f"'{document['original_name']}': {exc}"
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question=(
                            f"Vui lòng kiểm tra '{document['original_name']}' "
                            "hoặc chạy lại hồ sơ."
                        ),
                        source_refs=[f"DOC:{document_id}"],
                    )
                )
        return findings, facts, paper_facts

    def _finish_paper_case(
        self,
        *,
        job_id: str,
        case_id: str,
        draft: SettlementDraft,
        documents: list[dict[str, Any]],
        quality_findings: list[SettlementFinding],
        document_facts: list[ExpenseDocumentFacts],
        paper_facts: PaperSettlementFacts | None,
        has_paper_form: bool,
    ) -> None:
        base_findings = evaluate_settlement_policy(
            draft,
            has_paper_form=has_paper_form,
            config=self.policy,
        )
        base_findings = [
            finding for finding in base_findings if finding.rule_id != "SET_AUTH_001"
        ]
        if paper_facts is None or not paper_facts.lines:
            base_findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_LINES_001",
                    status="FAIL",
                    message="Chưa trích xuất được các dòng chi phí từ đơn giấy.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question="Vui lòng kiểm tra bảng khoản chi trên đơn giấy.",
                    source_refs=[
                        f"DOC:{document['document_id']}"
                        for document in documents
                        if document["role"]
                        == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
                    ],
                )
            )
            self._finish(job_id, case_id, [*base_findings, *quality_findings])
            return

        evidence_documents = [
            document
            for document in documents
            if document["role"] == SettlementDocumentRole.EXPENSE_EVIDENCE.value
        ]
        items, links, matching_findings = match_paper_evidence(
            paper_facts,
            document_facts,
            evidence_documents,
            fallback_no_evidence_reason=draft.paper_no_evidence_reason,
        )
        items, links, matching_findings = self._resolve_suggested_paper_links(
            case_id=case_id,
            items=items,
            links=links,
            findings=matching_findings,
            facts=document_facts,
        )
        for warning in paper_facts.extraction_warnings:
            matching_findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_CONSISTENCY_001",
                    status="FAIL",
                    message=f"Đơn giấy có dữ liệu chưa nhất quán: {warning}",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question=(
                        "Vui lòng đối chiếu bản gốc và xác nhận giá trị đúng "
                        "trên đơn giấy."
                    ),
                    source_refs=paper_facts.source_refs,
                )
            )
        line_amounts = [line.amount for line in paper_facts.lines]
        if paper_facts.total_amount is None:
            matching_findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_TOTAL_001",
                    status="FAIL",
                    message="Chưa đọc được tổng cộng trên đơn giấy.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question="Vui lòng xác nhận tổng cộng trên đơn giấy.",
                    source_refs=paper_facts.source_refs,
                )
            )
        elif all(amount is not None for amount in line_amounts):
            line_total = sum(
                (amount for amount in line_amounts if amount is not None),
                start=Decimal("0"),
            )
            if abs(line_total - paper_facts.total_amount) > Decimal("1"):
                matching_findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_TOTAL_001",
                        status="FAIL",
                        message=(
                            f"Tổng các dòng là {line_total:,.0f} VND nhưng tổng "
                            f"trên đơn là {paper_facts.total_amount:,.0f} VND."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question=(
                            "Vui lòng xác nhận tổng cộng hoặc số tiền của từng "
                            "dòng trên đơn giấy."
                        ),
                        source_refs=paper_facts.source_refs,
                    )
                )
            else:
                matching_findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_TOTAL_001",
                        status="PASS",
                        message="Tổng các dòng khớp tổng cộng trên đơn giấy.",
                        source_refs=paper_facts.source_refs,
                    )
                )
        claimed_total = paper_facts.total_amount or sum(
            (Decimal(str(item["claimed_amount"])) for item in items),
            start=Decimal("0"),
        )
        if draft.settlement_type == SettlementType.ADVANCE_SETTLEMENT:
            if paper_facts.advance_amount is None or paper_facts.advance_amount <= 0:
                matching_findings.append(
                    SettlementFinding(
                        rule_id="SET_ADV_AMOUNT_001",
                        status="FAIL",
                        message="Chưa đọc được số tiền đã tạm ứng hợp lệ trên đơn giấy.",
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question="Vui lòng xác nhận số tiền đã tạm ứng ghi trên đơn.",
                        source_refs=paper_facts.source_refs,
                    )
                )
            else:
                matching_findings.append(
                    SettlementFinding(
                        rule_id="SET_ADV_AMOUNT_001",
                        status="PASS",
                        message=(
                            f"Đơn khai số tiền đã tạm ứng "
                            f"{paper_facts.advance_amount:,.0f} VND; MVP không đối "
                            "chiếu với lịch sử giải ngân."
                        ),
                        source_refs=paper_facts.source_refs,
                    )
                )
                expected_difference = abs(
                    paper_facts.advance_amount - claimed_total
                )
                if paper_facts.reimbursement_amount is not None:
                    if (
                        abs(
                            paper_facts.reimbursement_amount
                            - expected_difference
                        )
                        > Decimal("1")
                    ):
                        matching_findings.append(
                            SettlementFinding(
                                rule_id="SET_SETTLEMENT_DIFF_001",
                                status="FAIL",
                                message=(
                                    f"Chênh lệch tính lại là "
                                    f"{expected_difference:,.0f} VND nhưng đơn ghi "
                                    f"{paper_facts.reimbursement_amount:,.0f} VND."
                                ),
                                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                                target=DecisionTarget.ACCOUNTANT,
                                question=(
                                    "Vui lòng xác nhận số tiền quyết toán chênh lệch "
                                    "đúng trên đơn."
                                ),
                                source_refs=paper_facts.source_refs,
                            )
                        )
                    else:
                        if paper_facts.advance_amount > claimed_total:
                            direction = "nhân viên hoàn trả công ty"
                        elif paper_facts.advance_amount < claimed_total:
                            direction = "công ty thanh toán thêm cho nhân viên"
                        else:
                            direction = "không phát sinh thanh toán thêm hoặc hoàn trả"
                        matching_findings.append(
                            SettlementFinding(
                                rule_id="SET_SETTLEMENT_DIFF_001",
                                status="PASS",
                                message=(
                                    f"Chênh lệch {expected_difference:,.0f} VND khớp "
                                    f"phép tính; chiều tiền: {direction}."
                                ),
                                source_refs=paper_facts.source_refs,
                            )
                        )
        self.repository.replace_paper_items(
            case_id,
            purpose=paper_facts.purpose,
            items=items,
            links=links,
            claimed_total=str(claimed_total),
            allocated_advance_amount=(
                str(paper_facts.advance_amount)
                if draft.settlement_type == SettlementType.ADVANCE_SETTLEMENT
                and paper_facts.advance_amount is not None
                else None
            ),
            beneficiary_name=paper_facts.beneficiary_name,
            bank_account_number=paper_facts.bank_account_number,
            bank_name=paper_facts.bank_name,
        )
        # The paper path is normalized into the same item contract as the
        # electronic form, then evaluated by the same deterministic policy.
        # This prevents paper-only gaps for limits, prohibited categories and
        # late submissions.
        try:
            normalized_items = [ExpenseItemDraft.model_validate(item) for item in items]
        except ValueError:
            normalized_items = []
        normalized_draft = draft.model_copy(
            update={
                "expense_items": normalized_items,
                "allocated_advance_amount": paper_facts.advance_amount or Decimal("0"),
            }
        )
        common_policy_findings = evaluate_settlement_policy(
            normalized_draft,
            has_paper_form=has_paper_form,
            config=self.policy,
        )
        approval_finding = SettlementFinding(
            rule_id="SET_APPROVAL_001",
            status="PENDING_APPROVAL",
            message=(
                "Hồ sơ đã qua bước kiểm tra tự động và đang chờ kế toán "
                "xác nhận hoặc ký theo quy trình phê duyệt."
            ),
            uncertainty_type=UncertaintyType.NONE,
            target=DecisionTarget.ACCOUNTANT,
            question=(
                "Kế toán kiểm tra bản gốc và thực hiện bước xác nhận/chữ ký; "
                "sau đó hồ sơ được chuyển tiếp đến cấp phê duyệt kế tiếp."
            ),
            source_refs=[
                f"DOC:{document['document_id']}"
                for document in documents
                if document["role"]
                == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
            ],
        )
        findings = [
            *common_policy_findings,
            *quality_findings,
            *matching_findings,
        ]
        if not any(finding.status == "FAIL" for finding in findings):
            findings.append(approval_finding)
        self._finish(job_id, case_id, findings)

    def _resolve_suggested_paper_links(
        self,
        *,
        case_id: str,
        items: list[dict[str, Any]],
        links: list[dict[str, Any]],
        findings: list[SettlementFinding],
        facts: list[ExpenseDocumentFacts],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[SettlementFinding]]:
        """Use one bounded LLM call only for deterministic-match grey areas."""

        suggested = [link for link in links if link["link_status"] == "SUGGEST_LINK"]
        resolver = getattr(self.reasoning_adapter, "analyze_evidence_reconciliation", None)
        if not suggested or not callable(resolver):
            return items, links, findings

        facts_by_id = {fact.document_id: fact for fact in facts}
        payload = {
            "case_id": case_id,
            "workflow": "EVIDENCE_RECONCILIATION",
            "candidate_links": [
                {
                    "item_id": link["item_id"],
                    "document_id": link["document_id"],
                    "score": link["score"],
                    "method": link["link_method"],
                    "line_amount": str(next(
                        (item["claimed_amount"] for item in items if item["item_id"] == link["item_id"]),
                        "",
                    )),
                    "document_number": link.get("document_number"),
                    "document_total": str(link["total_amount"]) if link.get("total_amount") is not None else None,
                    "document_type": str(link["document_type"]),
                    "explanation": link["explanation"],
                }
                for link in suggested
            ],
            "documents": [
                {
                    "document_id": fact.document_id,
                    "issuer_name": fact.issuer_name,
                    "document_number": fact.document_number,
                    "document_date": str(fact.document_date) if fact.document_date else None,
                    "total_amount": str(fact.total_amount) if fact.total_amount is not None else None,
                    "line_items": [line.description for line in fact.line_items],
                }
                for fact in facts
            ],
        }
        try:
            analysis = resolver(payload)
        except Exception:
            # The deterministic matcher already produces an accountant-facing
            # request for this uncertainty.  A temporary LLM outage must not
            # hide it or turn it into a technical false pass.
            return items, links, findings

        self.repository.save_json_artifact(
            case_id,
            "reconciliation",
            "paper-link-resolution.json",
            analysis.model_dump(mode="json"),
        )
        candidates = {(link["item_id"], link["document_id"]): link for link in suggested}
        auto_document_ids = {
            link["document_id"] for link in links if link["link_status"] == "AUTO_LINK"
        }
        promoted: list[dict[str, Any]] = []
        for accepted in analysis.accepted_links:
            key = (accepted.item_id, accepted.document_id)
            link = candidates.get(key)
            if link is None or accepted.confidence < 0.90 or accepted.document_id in auto_document_ids:
                continue
            link["link_status"] = "AUTO_LINK"
            link["link_method"] = "LLM_RECONCILIATION"
            link["score"] = float(accepted.confidence)
            link["explanation"] = accepted.rationale
            promoted.append(link)
            auto_document_ids.add(accepted.document_id)

        if not promoted:
            return items, links, findings

        item_by_id = {item["item_id"]: item for item in items}
        promoted_document_ids = {link["document_id"] for link in promoted}
        for link in promoted:
            item = item_by_id[link["item_id"]]
            fact = facts_by_id.get(link["document_id"])
            item["evidence_names"] = list(dict.fromkeys([
                *item.get("evidence_names", []), link["filename"]
            ]))
            if fact and fact.document_type in ORIGINAL_EXPENSE_DOCUMENT_TYPES:
                item["evidence_status"] = "ORIGINAL_EVIDENCE"
                item["alternative_evidence_type"] = None
            elif fact:
                item["evidence_status"] = "ALTERNATIVE_EVIDENCE"
                item["alternative_evidence_type"] = "PAYMENT_PROOF" if fact.document_type == ExpenseDocumentType.PAYMENT_PROOF else "OTHER"
            if fact and fact.document_date and not item.get("expense_date"):
                item["expense_date"] = fact.document_date.isoformat()

        findings = [
            finding
            for finding in findings
            if not (
                finding.rule_id == "SET_PAPER_MATCH_001"
                and finding.status == "FAIL"
                and any(ref == f"DOC:{document_id}" for document_id in promoted_document_ids for ref in finding.source_refs)
            )
        ]
        findings.extend(
            SettlementFinding(
                rule_id="SET_PAPER_MATCH_001",
                status="PASS",
                message=(
                    f"Đã xác nhận ghép evidence cho khoản '{item_by_id[link['item_id']]['description']}' "
                    "sau bước đối chiếu có kiểm soát."
                ),
                source_refs=[f"DOC:{link['document_id']}"],
            )
            for link in promoted
        )
        return items, links, findings

    @staticmethod
    def _reconciliation_findings(
        draft: SettlementDraft,
        documents: list[dict[str, Any]],
        facts: list[ExpenseDocumentFacts],
    ) -> list[SettlementFinding]:
        findings: list[SettlementFinding] = []
        facts_by_id = {fact.document_id: fact for fact in facts}
        for item in draft.expense_items:
            if (
                item.evidence_status == ExpenseEvidenceStatus.NO_EVIDENCE
                or item.policy_exception_code
            ):
                continue
            item_documents = [
                document
                for document in documents
                if document["role"]
                == SettlementDocumentRole.EXPENSE_EVIDENCE.value
                and document["linked_item_id"] == item.item_id
            ]
            item_facts = [
                facts_by_id[document["document_id"]]
                for document in item_documents
                if document["document_id"] in facts_by_id
            ]
            source_refs = [
                f"DOC:{document['document_id']}"
                for document in item_documents
            ]
            if len(item_facts) != len(item_documents) or any(
                fact.total_amount is None for fact in item_facts
            ):
                findings.append(
                    SettlementFinding(
                        rule_id="SET_TOTAL_001",
                        status="FAIL",
                        message=(
                            f"Chưa đủ tổng tiền chứng từ để đối chiếu khoản "
                            f"'{item.description}'."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question=(
                            f"Vui lòng xác nhận tổng chứng từ của khoản "
                            f"'{item.description}'."
                        ),
                        source_refs=source_refs,
                    )
                )
                continue
            document_total = sum(
                (fact.total_amount or Decimal("0") for fact in item_facts),
                start=Decimal("0"),
            )
            if abs(document_total - item.claimed_amount) > Decimal("1"):
                findings.append(
                    SettlementFinding(
                        rule_id="SET_TOTAL_001",
                        status="FAIL",
                        message=(
                            f"Khoản '{item.description}' khai "
                            f"{item.claimed_amount:,.0f} VND nhưng tổng chứng từ "
                            f"là {document_total:,.0f} VND."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.EMPLOYEE,
                        question=(
                            f"Vui lòng xác nhận số tiền của khoản "
                            f"'{item.description}'."
                        ),
                        source_refs=source_refs,
                    )
                )
            else:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_TOTAL_001",
                        status="PASS",
                        message=(
                            f"Khoản '{item.description}' khớp tổng tiền chứng từ."
                        ),
                        source_refs=source_refs,
                    )
                )
        return findings

    def drain(self, max_jobs: int = 100) -> int:
        processed = 0
        while processed < max_jobs and self.run_once():
            processed += 1
        return processed
