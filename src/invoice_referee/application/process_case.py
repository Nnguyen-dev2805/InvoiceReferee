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
                summary="Không có block confidence thấp cần xem xét.",
                reasoning="Hồ sơ chỉ hoàn thành Confidence Quality Gate; chưa được kiểm tra missing value, policy hoặc tính hợp lệ nghiệp vụ.",
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
                "Confidence Quality Agent không trả về kết quả hợp lệ; cần người kiểm tra.",
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
            summary = "Có block OCR quan trọng cần người xác minh."
            reasoning = self._confidence_questions(
                confidence_analysis,
                confidence_findings,
            )
        else:
            policy_signal_count = sum(
                item.review_action == "DEFER_TO_POLICY"
                for item in confidence_analysis.block_assessments
            )
            if policy_signal_count:
                summary = (
                    "Confidence Quality Gate hoàn thành; có "
                    f"{policy_signal_count} tín hiệu được chuyển sang Policy Agent."
                )
                reasoning = (
                    "Không cần hỏi người ở bước OCR. Tín hiệu policy được giữ lại "
                    "để kiểm tra ở giai đoạn nghiệp vụ sau."
                )
            else:
                summary = "Các block confidence thấp không cần người xác minh."
                reasoning = "Hồ sơ chỉ hoàn thành Confidence Quality Gate; chưa được kiểm tra missing value, policy hoặc tính hợp lệ nghiệp vụ."

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
                findings.append(
                    RuleFinding(
                        rule_id="LOW_CONFIDENCE_BLOCK_UNKNOWN",
                        status="FAIL",
                        message=f"Vui lòng kiểm tra {candidate_id}; block chưa được đánh giá duy nhất một lần.",
                        source_refs=[candidate_id],
                    )
                )
                continue

            if assessment.review_action == "ASK_HUMAN":
                question = assessment.human_question or (
                    f"Vui lòng kiểm tra {candidate_id} và xác nhận "
                    f"{', '.join(assessment.canonical_fields) or 'nội dung OCR'}."
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
                findings.append(
                    RuleFinding(
                        rule_id="OCR_POLICY_SIGNAL",
                        status="WARN",
                        message=(
                            f"Chuyển Policy Agent xem xét nhóm {category}: "
                            f"{assessment.reason}"
                        ),
                        source_refs=[candidate_id],
                    )
                )

        if not findings:
            findings.append(
                RuleFinding(
                    rule_id="OCR_CONFIDENCE_REVIEW",
                    status="PASS",
                    message="Các block confidence thấp không cần người xác minh.",
                    source_refs=sorted(expected_ids),
                )
            )
        return findings

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
    def _confidence_questions(
        cls,
        analysis: ConfidenceAnalysis,
        findings: list[RuleFinding],
    ) -> str:
        questions = [
            item.human_question
            for item in analysis.block_assessments
            if item.human_question and item.review_action == "ASK_HUMAN"
        ]
        return " ".join(questions) or cls._finding_questions(findings)

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
