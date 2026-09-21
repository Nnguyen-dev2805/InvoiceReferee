"""Synchronous extraction-quality workflow for submitted expense evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from invoice_referee.domain import (
    CaseProcessingResult,
    ConfidenceAnalysis,
    EvidenceRole,
    ProcessingDecision,
    RuleFinding,
)
from invoice_referee.extraction import (
    DEFAULT_WORD_REVIEW_THRESHOLD,
    collect_low_confidence_blocks,
    restructure_mistral_ocr,
)
from invoice_referee.storage import LocalEvidenceRepository, StoredCase, StoredEvidence

VIETNAM_TZ = timezone(timedelta(hours=7))
OCR_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png", ".webp"}
BLOCKING_FINDING_STATUSES = {"FAIL", "ERROR"}
ACCOUNTING_FIELD_LABELS = {
    "seller_name": "tên người bán",
    "seller_tax_code": "mã số thuế người bán",
    "buyer_name": "tên người mua",
    "buyer_tax_code": "mã số thuế người mua",
    "invoice_date": "ngày chứng từ",
    "invoice_number": "số hóa đơn",
    "template_number": "mẫu số hóa đơn",
    "serial_number": "ký hiệu hóa đơn",
    "item_name": "tên hàng hóa hoặc dịch vụ",
    "quantity": "số lượng",
    "unit_price": "đơn giá",
    "line_amount": "thành tiền",
    "tax_amount": "tiền thuế",
    "total_amount": "tổng thanh toán",
    "payment_method": "phương thức thanh toán",
    "transaction_reference": "mã giao dịch",
}
TECHNICAL_QUESTION_MARKERS = (
    "candidate",
    "block",
    "page-",
    "confidence",
    "ocr",
    "ev-",
)


def _ocr_markdown(response: dict[str, Any]) -> str:
    pages = response.get("pages") or []
    return "\n\n".join(
        str(page.get("markdown") or "").strip()
        for page in pages
        if str(page.get("markdown") or "").strip()
    )


class CaseProcessingService:
    """Run source gates, OCR, then confidence-quality review."""

    def __init__(
        self,
        repository: LocalEvidenceRepository,
        ocr_adapter: Any | None,
        reasoning_adapter: Any | None,
        word_confidence_threshold: float = DEFAULT_WORD_REVIEW_THRESHOLD,
    ) -> None:
        self.repository = repository
        self.ocr_adapter = ocr_adapter
        self.reasoning_adapter = reasoning_adapter
        self.word_confidence_threshold = word_confidence_threshold

    def process_case(self, case_id: str) -> CaseProcessingResult:
        case = self.repository.get_case(case_id)
        primary = [
            evidence
            for evidence in case.evidence
            if evidence.role == EvidenceRole.PRIMARY_DOCUMENT.value
        ]
        supporting = [
            evidence
            for evidence in case.evidence
            if evidence.role == EvidenceRole.SUPPORTING_DOCUMENT.value
        ]

        source_findings = self._missing_source_findings(case, primary, supporting)
        if source_findings:
            return self._save_result(
                case,
                decision=ProcessingDecision.NEEDS_HUMAN,
                summary="Hồ sơ cần bổ sung nguồn dữ liệu.",
                reasoning=self._finding_questions(source_findings),
                findings=source_findings,
            )

        if self.ocr_adapter is None:
            return self._technical_failure(
                case,
                "OCR_NOT_CONFIGURED",
                "Mistral OCR chưa được cấu hình nên chưa thể đọc evidence.",
            )

        documents: list[dict[str, Any]] = []
        ocr_evidence_ids: list[str] = []
        low_confidence_candidates: list[dict[str, Any]] = []
        processing_errors: list[str] = []
        for evidence in case.evidence:
            if evidence.absolute_path.suffix.lower() not in OCR_SUFFIXES:
                processing_errors.append(
                    f"Định dạng chưa hỗ trợ OCR: {evidence.original_name}"
                )
                continue
            try:
                execution = self.ocr_adapter.process(
                    evidence.absolute_path,
                    evidence.mime_type,
                )
                stored_result = {
                    "schema_version": "1.0",
                    "case_id": case.case_id,
                    "evidence_id": evidence.evidence_id,
                    "source_file": evidence.original_name,
                    **execution.to_dict(),
                }
                self.repository.save_ocr_result(evidence, stored_result)
                ocr_evidence_ids.append(evidence.evidence_id)
                hierarchy = restructure_mistral_ocr(stored_result)
                evidence_candidates = collect_low_confidence_blocks(
                    hierarchy,
                    evidence_id=evidence.evidence_id,
                    threshold=self.word_confidence_threshold,
                )
                for candidate in evidence_candidates:
                    candidate["source_file"] = evidence.original_name
                low_confidence_candidates.extend(evidence_candidates)
                documents.append(
                    {
                        "evidence_id": evidence.evidence_id,
                        "role": evidence.role,
                        "filename": evidence.original_name,
                        "ocr_text": _ocr_markdown(execution.response),
                        "pages": self._page_context(hierarchy),
                        "candidate_blocks": evidence_candidates,
                    }
                )
            except Exception as exc:
                processing_errors.append(
                    f"OCR thất bại với {evidence.original_name}: {exc}"
                )

        post_ocr_findings = self._post_ocr_findings(
            case,
            primary,
            supporting,
            ocr_evidence_ids,
            processing_errors,
        )
        if post_ocr_findings:
            return self._save_result(
                case,
                decision=ProcessingDecision.NEEDS_HUMAN,
                summary="Một hoặc nhiều evidence chưa đọc được bằng OCR.",
                reasoning=self._finding_questions(post_ocr_findings),
                findings=post_ocr_findings,
                ocr_evidence_ids=ocr_evidence_ids,
                low_confidence_candidates=low_confidence_candidates,
                processing_errors=processing_errors,
            )

        if not low_confidence_candidates:
            findings = [
                RuleFinding(
                    rule_id="OCR_CONFIDENCE_REVIEW",
                    status="PASS",
                    message="Không có meaningful word dưới ngưỡng confidence.",
                )
            ]
            return self._save_result(
                case,
                decision=ProcessingDecision.PASS,
                summary="Chứng từ không có thông tin nào cần kiểm tra thêm về độ rõ.",
                reasoning="Không có thông tin nào cần kế toán xác nhận ở bước này.",
                findings=findings,
                ocr_evidence_ids=ocr_evidence_ids,
                low_confidence_candidates=low_confidence_candidates,
            )

        if self.reasoning_adapter is None:
            return self._technical_failure(
                case,
                "KIMI_NOT_CONFIGURED",
                "Kimi chưa được cấu hình nên chưa thể kiểm tra confidence OCR.",
                ocr_evidence_ids=ocr_evidence_ids,
                low_confidence_candidates=low_confidence_candidates,
            )

        try:
            confidence_analysis = self.reasoning_adapter.analyze_confidence(
                {
                    "case_id": case.case_id,
                    "ocr_word_review_threshold": self.word_confidence_threshold,
                    "business_context": {
                        "subject": case.subject,
                        "description": case.body,
                    },
                    "documents": [
                        {
                            "evidence_id": document["evidence_id"],
                            "role": document["role"],
                            "filename": document["filename"],
                            "ocr_text": document["ocr_text"],
                            "candidate_blocks": document["candidate_blocks"],
                        }
                        for document in documents
                        if document["candidate_blocks"]
                    ],
                }
            )
        except Exception as exc:
            return self._technical_failure(
                case,
                "CONFIDENCE_AGENT_ERROR",
                "Hệ thống chưa hoàn tất kiểm tra độ rõ của chứng từ; cần kế toán kiểm tra lại.",
                ocr_evidence_ids=ocr_evidence_ids,
                low_confidence_candidates=low_confidence_candidates,
                processing_errors=[str(exc)],
            )

        confidence_findings = self._confidence_findings(
            low_confidence_candidates,
            confidence_analysis,
        )
        findings = confidence_findings
        decision = (
            ProcessingDecision.NEEDS_HUMAN
            if self._has_blocking_findings(findings)
            else ProcessingDecision.PASS
        )
        if decision == ProcessingDecision.NEEDS_HUMAN:
            summary = "Chứng từ có thông tin quan trọng cần kế toán xác nhận."
            reasoning = self._confidence_questions(confidence_findings)
        else:
            policy_signal_count = sum(
                item.review_action == "DEFER_TO_POLICY"
                for item in confidence_analysis.block_assessments
            )
            if policy_signal_count:
                summary = (
                    f"Có {policy_signal_count} nội dung cần được kiểm tra theo "
                    "chính sách chi phí."
                )
                reasoning = (
                    "Chứng từ vẫn có thể tiếp tục xử lý; các nội dung này sẽ được "
                    "xem xét ở bước kiểm tra chính sách."
                )
            else:
                summary = "Các thông tin chưa rõ không ảnh hưởng đến việc đọc chứng từ."
                reasoning = "Không có thông tin nào cần kế toán xác nhận ở bước này."

        return self._save_result(
            case,
            decision=decision,
            summary=summary,
            reasoning=reasoning,
            findings=findings,
            ocr_evidence_ids=ocr_evidence_ids,
            low_confidence_candidates=low_confidence_candidates,
            confidence_analysis=confidence_analysis,
        )

    @staticmethod
    def _page_context(hierarchy: dict[str, Any]) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for page in hierarchy.get("pages") or []:
            pages.append(
                {
                    "page_index": page.get("page_index"),
                    "blocks": [
                        {
                            "block_id": block.get("block_id"),
                            "block_type": block.get("block_type"),
                            "content": block.get("content"),
                        }
                        for block in page.get("blocks") or []
                    ],
                }
            )
        return pages

    @staticmethod
    def _confidence_findings(
        candidates: list[dict[str, Any]],
        analysis: ConfidenceAnalysis,
    ) -> list[RuleFinding]:
        expected_ids = {candidate["candidate_id"] for candidate in candidates}
        assessment_counts: dict[str, int] = {}
        assessment_by_id: dict[str, Any] = {}
        for assessment in analysis.block_assessments:
            assessment_counts[assessment.candidate_id] = (
                assessment_counts.get(assessment.candidate_id, 0) + 1
            )
            assessment_by_id[assessment.candidate_id] = assessment

        findings: list[RuleFinding] = []
        unexpected_ids = set(assessment_by_id).difference(expected_ids)
        if unexpected_ids:
            findings.append(
                RuleFinding(
                    rule_id="OCR_CONFIDENCE_ASSESSMENT_INVALID",
                    status="ERROR",
                    message="Confidence Agent trả candidate_id không tồn tại.",
                    source_refs=sorted(unexpected_ids),
                )
            )

        for candidate in candidates:
            candidate_id = candidate["candidate_id"]
            assessment = assessment_by_id.get(candidate_id)
            if assessment is None or assessment_counts.get(candidate_id) != 1:
                source_file = candidate.get("source_file") or "chứng từ"
                findings.append(
                    RuleFinding(
                        rule_id="LOW_CONFIDENCE_BLOCK_UNKNOWN",
                        status="FAIL",
                        message=(
                            f"Chưa thể hoàn tất kiểm tra chất lượng cho {source_file}. "
                            "Vui lòng kiểm tra lại chứng từ."
                        ),
                        source_refs=[candidate_id],
                    )
                )
                continue

            if assessment.review_action == "ASK_HUMAN":
                question = CaseProcessingService._accountant_question(
                    assessment,
                    candidate,
                )
                findings.append(
                    RuleFinding(
                        rule_id="LOW_CONFIDENCE_ASK_HUMAN",
                        status="FAIL",
                        message=question,
                        source_refs=[candidate_id],
                    )
                )
            elif assessment.review_action == "DEFER_TO_POLICY":
                category = assessment.semantic_category or "chưa phân loại"
                source_file = candidate.get("source_file") or "chứng từ"
                findings.append(
                    RuleFinding(
                        rule_id="OCR_POLICY_SIGNAL",
                        status="WARN",
                        message=(
                            f"{source_file} có nội dung thuộc nhóm {category}; "
                            "cần xem xét ở bước kiểm tra chính sách chi phí."
                        ),
                        source_refs=[candidate_id],
                    )
                )

        if not findings:
            findings.append(
                RuleFinding(
                    rule_id="OCR_CONFIDENCE_REVIEW",
                    status="PASS",
                    message="Không có thông tin nào cần kế toán xác nhận ở bước này.",
                    source_refs=sorted(expected_ids),
                )
            )
        return findings

    @staticmethod
    def _accountant_question(
        assessment: Any,
        candidate: dict[str, Any],
    ) -> str:
        question = (assessment.human_question or "").strip()
        if question and not any(
            marker in question.lower() for marker in TECHNICAL_QUESTION_MARKERS
        ):
            return question

        source_file = candidate.get("source_file") or "chứng từ"
        labels = [
            ACCOUNTING_FIELD_LABELS.get(field, field.replace("_", " "))
            for field in assessment.canonical_fields
        ]
        if not labels:
            labels = ["thông tin chưa rõ"]
        if len(labels) == 1:
            field_text = labels[0]
        else:
            field_text = ", ".join(labels[:-1]) + f" và {labels[-1]}"

        observed_text = assessment.observed_text.strip()
        if observed_text and len(observed_text) <= 80:
            return (
                f"Vui lòng kiểm tra {source_file} và xác nhận {field_text} "
                f"có phải là '{observed_text}' không."
            )
        return f"Vui lòng kiểm tra {source_file} và xác nhận {field_text}."

    @staticmethod
    def _missing_source_findings(
        case: StoredCase,
        primary: list[StoredEvidence],
        supporting: list[StoredEvidence],
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        if not primary:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BILL_EVIDENCE",
                    status="FAIL",
                    message="Vui lòng bổ sung bill hoặc chứng từ chính cho khoản chi.",
                )
            )
        if not case.body.strip() and not supporting:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BUSINESS_CONTEXT",
                    status="FAIL",
                    message="Vui lòng bổ sung mô tả hoặc tài liệu thể hiện business context.",
                )
            )
        return findings

    @staticmethod
    def _post_ocr_findings(
        case: StoredCase,
        primary: list[StoredEvidence],
        supporting: list[StoredEvidence],
        ocr_evidence_ids: list[str],
        processing_errors: list[str],
    ) -> list[RuleFinding]:
        primary_ids = {evidence.evidence_id for evidence in primary}
        supporting_ids = {evidence.evidence_id for evidence in supporting}
        successful_ids = set(ocr_evidence_ids)
        findings: list[RuleFinding] = []

        if not primary_ids.intersection(successful_ids):
            findings.append(
                RuleFinding(
                    rule_id="BILL_EVIDENCE_NOT_READABLE",
                    status="FAIL",
                    message="Vui lòng cung cấp bill/chứng từ chính có thể đọc được.",
                    source_refs=sorted(primary_ids),
                )
            )
        if not case.body.strip() and not supporting_ids.intersection(successful_ids):
            findings.append(
                RuleFinding(
                    rule_id="BUSINESS_CONTEXT_NOT_READABLE",
                    status="FAIL",
                    message="Vui lòng cung cấp business context có thể đọc được.",
                    source_refs=sorted(supporting_ids),
                )
            )
        if processing_errors:
            findings.append(
                RuleFinding(
                    rule_id="OCR_PROCESSING_ERROR",
                    status="ERROR",
                    message="Vui lòng kiểm tra các evidence không xử lý được bằng OCR.",
                )
            )
        return findings

    @staticmethod
    def _finding_questions(findings: list[RuleFinding]) -> str:
        return " ".join(
            finding.message
            for finding in findings
            if finding.status in BLOCKING_FINDING_STATUSES
        )

    @staticmethod
    def _has_blocking_findings(findings: list[RuleFinding]) -> bool:
        return any(
            finding.status in BLOCKING_FINDING_STATUSES for finding in findings
        )

    @classmethod
    def _confidence_questions(cls, findings: list[RuleFinding]) -> str:
        return cls._finding_questions(findings)

    def _technical_failure(
        self,
        case: StoredCase,
        rule_id: str,
        message: str,
        *,
        ocr_evidence_ids: list[str] | None = None,
        low_confidence_candidates: list[dict[str, Any]] | None = None,
        processing_errors: list[str] | None = None,
    ) -> CaseProcessingResult:
        return self._save_result(
            case,
            decision=ProcessingDecision.NEEDS_HUMAN,
            summary=message,
            reasoning=message,
            findings=[
                RuleFinding(
                    rule_id=rule_id,
                    status="ERROR",
                    message=message,
                )
            ],
            ocr_evidence_ids=ocr_evidence_ids,
            low_confidence_candidates=low_confidence_candidates,
            processing_errors=processing_errors,
        )

    def _save_result(
        self,
        case: StoredCase,
        *,
        decision: ProcessingDecision,
        summary: str,
        reasoning: str,
        findings: list[RuleFinding],
        ocr_evidence_ids: list[str] | None = None,
        low_confidence_candidates: list[dict[str, Any]] | None = None,
        confidence_analysis: ConfidenceAnalysis | None = None,
        processing_errors: list[str] | None = None,
    ) -> CaseProcessingResult:
        result = CaseProcessingResult(
            case_id=case.case_id,
            decision=decision,
            processed_at=datetime.now(tz=VIETNAM_TZ).isoformat(),
            summary=summary,
            reasoning=reasoning,
            findings=findings,
            ocr_evidence_ids=ocr_evidence_ids or [],
            low_confidence_candidates=low_confidence_candidates or [],
            confidence_analysis=confidence_analysis,
            processing_errors=processing_errors or [],
        )
        self.repository.save_processing_result(
            case.case_id,
            result.model_dump(mode="json"),
        )
        return result
