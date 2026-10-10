"""Durable UC-03 worker: source gate, quality, extraction, policy, decision."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from invoice_referee.application.decision_guard import build_settlement_decision
from invoice_referee.application.process_case import CaseProcessingService
from invoice_referee.domain import (
    DecisionTarget,
    ExpenseDocumentFacts,
    SettlementDocumentRole,
    SettlementDraft,
    SettlementFinding,
    SubmissionSourceType,
    UncertaintyType,
)
from invoice_referee.extraction import (
    DEFAULT_WORD_REVIEW_THRESHOLD,
    collect_low_confidence_blocks,
    restructure_mistral_ocr,
)
from invoice_referee.policy import SettlementPolicyConfig, evaluate_settlement_policy
from invoice_referee.storage import SQLiteSettlementRepository

OCR_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png", ".webp"}
SOURCE_GATE_RULES = {
    "SET_CONTEXT_001",
    "SET_INPUT_001",
    "SET_ADV_001",
    "SET_DOC_001",
}


def _ocr_markdown(response: dict[str, Any]) -> str:
    return "\n\n".join(
        str(page.get("markdown") or "").strip()
        for page in response.get("pages") or []
        if str(page.get("markdown") or "").strip()
    )


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
                quality_findings, document_facts = self._process_documents(
                    case_id,
                    documents,
                )
                if any(finding.status == "FAIL" for finding in quality_findings):
                    self._finish(
                        job_id,
                        case_id,
                        [*source_findings, *quality_findings],
                    )
                    return True

            duplicates = self.repository.find_case_duplicate_documents(case_id)
            findings = evaluate_settlement_policy(
                draft,
                has_paper_form=has_paper_form,
                duplicate_document_names=duplicates,
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

            if draft.source_type == SubmissionSourceType.PAPER_SCAN and has_paper_form:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_SIGNATURE_001",
                        status="FAIL",
                        message=(
                            "Giấy đề nghị đã được tiếp nhận nhưng chữ ký tay "
                            "chưa được xác nhận."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question=(
                            "Vui lòng kiểm tra giấy đề nghị và xác nhận đủ chữ ký "
                            "theo chuỗi phê duyệt."
                        ),
                        source_refs=[
                            f"DOC:{document['document_id']}"
                            for document in documents
                            if document["role"]
                            == SettlementDocumentRole.SETTLEMENT_REQUEST_FORM.value
                        ],
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
        decision = build_settlement_decision(findings)
        self.repository.complete_job(job_id, case_id, findings, decision)

    def _process_documents(
        self,
        case_id: str,
        documents: list[dict[str, Any]],
    ) -> tuple[list[SettlementFinding], list[ExpenseDocumentFacts]]:
        findings: list[SettlementFinding] = []
        facts: list[ExpenseDocumentFacts] = []
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
            ], []
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
            ], []

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

                if candidates:
                    confidence = self.reasoning_adapter.analyze_confidence(
                        {
                            "case_id": case_id,
                            "ocr_word_review_threshold": self.word_confidence_threshold,
                            "evidence": {
                                "evidence_id": document_id,
                                "role": document["role"],
                                "filename": document["original_name"],
                                "ocr_text": _ocr_markdown(execution.response),
                                "candidate_blocks": candidates,
                            },
                        }
                    )
                    legacy_findings = CaseProcessingService._confidence_findings(
                        candidates,
                        confidence,
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

                if any(
                    finding.status == "FAIL"
                    and f"DOC:{document_id}" in finding.source_refs
                    for finding in findings
                ):
                    continue

                extracted = self.reasoning_adapter.extract_expense_document(
                    {
                        "case_id": case_id,
                        "document_id": document_id,
                        "filename": document["original_name"],
                        "role": document["role"],
                        "ocr_text": _ocr_markdown(execution.response),
                    }
                )
                if extracted.document_id != document_id:
                    raise ValueError(
                        "Extraction Agent trả document_id không khớp nguồn."
                    )
                self.repository.save_json_artifact(
                    case_id,
                    "facts",
                    f"{document_id}.json",
                    extracted.model_dump(mode="json"),
                )
                facts.append(extracted)
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
        return findings, facts

    @staticmethod
    def _reconciliation_findings(
        draft: SettlementDraft,
        documents: list[dict[str, Any]],
        facts: list[ExpenseDocumentFacts],
    ) -> list[SettlementFinding]:
        findings: list[SettlementFinding] = []
        facts_by_id = {fact.document_id: fact for fact in facts}
        for item in draft.expense_items:
            if item.policy_exception_code:
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
