"""Synchronous case processing for the first two accounting rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from invoice_referee.domain import (
    CaseProcessingResult,
    EvidenceRole,
    ProcessingDecision,
    RuleFinding,
)
from invoice_referee.storage import LocalEvidenceRepository, StoredCase, StoredEvidence

VIETNAM_TZ = timezone(timedelta(hours=7))
OCR_SUFFIXES = {".jpeg", ".jpg", ".pdf", ".png", ".webp"}


def _ocr_markdown(response: dict[str, Any]) -> str:
    pages = response.get("pages") or []
    return "\n\n".join(
        str(page.get("markdown") or "").strip()
        for page in pages
        if str(page.get("markdown") or "").strip()
    )


class CaseProcessingService:
    """Run missing checks, independent OCR calls, and one Kimi analysis."""

    def __init__(
        self,
        repository: LocalEvidenceRepository,
        ocr_adapter: Any | None,
        reasoning_adapter: Any | None,
    ) -> None:
        self.repository = repository
        self.ocr_adapter = ocr_adapter
        self.reasoning_adapter = reasoning_adapter

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

        missing_findings = self._missing_source_findings(case, primary, supporting)
        if missing_findings:
            return self._save_result(
                case,
                decision=ProcessingDecision.NEEDS_HUMAN,
                summary="Hồ sơ thiếu nguồn dữ liệu bắt buộc.",
                reasoning=" ".join(finding.message for finding in missing_findings),
                findings=missing_findings,
            )

        if self.ocr_adapter is None:
            return self._technical_failure(
                case,
                "OCR_NOT_CONFIGURED",
                "Mistral OCR chưa được cấu hình nên chưa thể đọc evidence.",
            )

        documents: list[dict[str, Any]] = []
        ocr_evidence_ids: list[str] = []
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
                documents.append(
                    {
                        "evidence_id": evidence.evidence_id,
                        "role": evidence.role,
                        "filename": evidence.original_name,
                        "ocr_text": _ocr_markdown(execution.response),
                    }
                )
            except Exception as exc:
                processing_errors.append(
                    f"OCR thất bại với {evidence.original_name}: {exc}"
                )

        primary_ids = {evidence.evidence_id for evidence in primary}
        supporting_ids = {evidence.evidence_id for evidence in supporting}
        successful_primary = primary_ids.intersection(ocr_evidence_ids)
        successful_supporting = supporting_ids.intersection(ocr_evidence_ids)

        findings: list[RuleFinding] = []
        if not successful_primary:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BILL_EVIDENCE",
                    status="FAIL",
                    message="Không có bill evidence đọc được bằng OCR.",
                    source_refs=[evidence.evidence_id for evidence in primary],
                )
            )
        if not case.body.strip() and not successful_supporting:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BUSINESS_CONTEXT",
                    status="FAIL",
                    message="Không có business context đọc được từ nội dung hoặc tài liệu bổ sung.",
                    source_refs=[evidence.evidence_id for evidence in supporting],
                )
            )
        if processing_errors:
            findings.append(
                RuleFinding(
                    rule_id="PROCESSING_ERROR",
                    status="ERROR",
                    message="Một hoặc nhiều tài liệu không xử lý được.",
                )
            )
        if findings:
            return self._save_result(
                case,
                decision=ProcessingDecision.NEEDS_HUMAN,
                summary="Hồ sơ cần kế toán kiểm tra do nguồn dữ liệu chưa xử lý đầy đủ.",
                reasoning=" ".join(finding.message for finding in findings),
                findings=findings,
                ocr_evidence_ids=ocr_evidence_ids,
                processing_errors=processing_errors,
            )

        if self.reasoning_adapter is None:
            return self._technical_failure(
                case,
                "KIMI_NOT_CONFIGURED",
                "Kimi chưa được cấu hình nên chưa thể đánh giá hồ sơ.",
                ocr_evidence_ids=ocr_evidence_ids,
            )

        try:
            analysis = self.reasoning_adapter.analyze(
                {
                    "case_id": case.case_id,
                    "business_context": {
                        "subject": case.subject,
                        "description": case.body,
                    },
                    "documents": documents,
                }
            )
        except Exception as exc:
            return self._technical_failure(
                case,
                "KIMI_PROCESSING_ERROR",
                "Kimi không trả về kết quả hợp lệ; cần kế toán kiểm tra.",
                ocr_evidence_ids=ocr_evidence_ids,
                processing_errors=[str(exc)],
            )

        if not analysis.business_context_present:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BUSINESS_CONTEXT",
                    status="FAIL",
                    message="Kimi không xác định được mục đích kinh doanh từ context đã cung cấp.",
                    source_refs=[
                        evidence.evidence_id for evidence in supporting
                    ],
                )
            )
        else:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BUSINESS_CONTEXT",
                    status="PASS",
                    message="Đã xác định được business context.",
                )
            )

        if analysis.conflict_detected:
            findings.append(
                RuleFinding(
                    rule_id="BILL_CONTEXT_CONFLICT",
                    status="FAIL",
                    message="Kimi phát hiện bill và business context có dữ kiện mâu thuẫn.",
                    source_refs=ocr_evidence_ids,
                )
            )
        else:
            findings.append(
                RuleFinding(
                    rule_id="BILL_CONTEXT_CONFLICT",
                    status="PASS",
                    message="Không phát hiện mâu thuẫn giữa bill và business context.",
                )
            )

        decision = (
            ProcessingDecision.NEEDS_HUMAN
            if any(finding.status != "PASS" for finding in findings)
            else ProcessingDecision.PASS
        )
        return self._save_result(
            case,
            decision=decision,
            summary=analysis.summary,
            reasoning=analysis.reasoning,
            findings=findings,
            ocr_evidence_ids=ocr_evidence_ids,
            kimi_analysis=analysis,
        )

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
                    message="Hồ sơ không có bill hoặc chứng từ chính.",
                )
            )
        if not case.body.strip() and not supporting:
            findings.append(
                RuleFinding(
                    rule_id="MISSING_BUSINESS_CONTEXT",
                    status="FAIL",
                    message="Hồ sơ không có nội dung hoặc tài liệu business context.",
                )
            )
        return findings

    def _technical_failure(
        self,
        case: StoredCase,
        rule_id: str,
        message: str,
        *,
        ocr_evidence_ids: list[str] | None = None,
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
        kimi_analysis: Any | None = None,
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
            kimi_analysis=kimi_analysis,
            processing_errors=processing_errors or [],
        )
        self.repository.save_processing_result(
            case.case_id,
            result.model_dump(mode="json"),
        )
        return result
