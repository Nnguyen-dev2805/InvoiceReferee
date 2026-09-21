"""Application service that validates and accepts employee submissions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRole,
    SubmissionReceipt,
    SubmissionValidationError,
    UploadPayload,
)
from invoice_referee.storage.base import CaseStore

PRIMARY_EXTENSIONS = {
    ".jpeg",
    ".jpg",
    ".json",
    ".pdf",
    ".png",
    ".webp",
    ".xml",
}
SUPPORTING_EXTENSIONS = PRIMARY_EXTENSIONS | {
    ".csv",
    ".doc",
    ".docx",
    ".txt",
    ".xls",
    ".xlsx",
}
@dataclass(frozen=True, slots=True)
class SubmissionLimits:
    max_files: int = 12
    max_file_size_bytes: int = 15 * 1024 * 1024
    max_total_size_bytes: int = 50 * 1024 * 1024


class SubmitCaseService:
    """Validate technical input and persist a new employee expense case."""

    def __init__(
        self,
        store: CaseStore,
        limits: SubmissionLimits | None = None,
        processor: Any | None = None,
    ) -> None:
        self.store = store
        self.limits = limits or SubmissionLimits()
        self.processor = processor

    def submit(
        self,
        claim: ClaimDraft,
        uploads: list[UploadPayload],
    ) -> SubmissionReceipt:
        issues = self._validate(claim, uploads)
        if issues:
            raise SubmissionValidationError(issues)

        unique_uploads, warnings = self._deduplicate(uploads)
        receipt = self.store.save_submission(claim, unique_uploads, warnings)
        if self.processor is None:
            return receipt
        result = self.processor.process_case(receipt.case_id)
        return receipt.model_copy(update={"status": result.decision.value})

    def _validate(
        self,
        claim: ClaimDraft,
        uploads: list[UploadPayload],
    ) -> list[str]:
        issues: list[str] = []
        if not claim.body and not uploads:
            issues.append("Nhập nội dung đề nghị hoặc đính kèm ít nhất một tệp.")

        if len(uploads) > self.limits.max_files:
            issues.append(f"Mỗi hồ sơ được đính kèm tối đa {self.limits.max_files} tệp.")

        total_size = sum(upload.size_bytes for upload in uploads)
        if total_size > self.limits.max_total_size_bytes:
            max_mb = self.limits.max_total_size_bytes // (1024 * 1024)
            issues.append(f"Tổng dung lượng tệp không được vượt quá {max_mb} MB.")

        for upload in uploads:
            extension = Path(upload.original_name).suffix.lower()
            allowed = (
                PRIMARY_EXTENSIONS
                if upload.role == EvidenceRole.PRIMARY_DOCUMENT
                else SUPPORTING_EXTENSIONS
            )
            if not upload.content:
                issues.append(f"Tệp {upload.original_name} đang rỗng.")
            elif upload.size_bytes > self.limits.max_file_size_bytes:
                max_mb = self.limits.max_file_size_bytes // (1024 * 1024)
                issues.append(
                    f"Tệp {upload.original_name} vượt giới hạn {max_mb} MB."
                )
            if extension not in allowed:
                issues.append(f"Định dạng {extension or 'không xác định'} chưa được hỗ trợ.")

        return issues

    @staticmethod
    def _deduplicate(
        uploads: list[UploadPayload],
    ) -> tuple[list[UploadPayload], list[str]]:
        seen_hashes: set[str] = set()
        unique_uploads: list[UploadPayload] = []
        warnings: list[str] = []
        for upload in uploads:
            digest = upload.sha256
            if digest in seen_hashes:
                warnings.append(f"Đã bỏ qua tệp trùng: {upload.original_name}")
                continue
            seen_hashes.add(digest)
            unique_uploads.append(upload)
        return unique_uploads, warnings
