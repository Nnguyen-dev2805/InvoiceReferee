"""UC-03 submission service."""

from __future__ import annotations

from pathlib import Path

from invoice_referee.domain import (
    SettlementDocumentRole,
    SettlementDraft,
    SettlementReceipt,
    SettlementUpload,
    SubmissionValidationError,
)
from invoice_referee.policy import SettlementPolicyConfig
from invoice_referee.storage import SQLiteSettlementRepository

SUPPORTED_EXTENSIONS = {
    ".jpeg",
    ".jpg",
    ".json",
    ".pdf",
    ".png",
    ".txt",
    ".webp",
    ".xml",
}


class SubmitSettlementService:
    def __init__(
        self,
        repository: SQLiteSettlementRepository,
        *,
        policy: SettlementPolicyConfig | None = None,
        max_files: int = 20,
        max_file_size_bytes: int = 15 * 1024 * 1024,
        max_total_size_bytes: int = 60 * 1024 * 1024,
    ) -> None:
        self.repository = repository
        self.policy = policy or SettlementPolicyConfig()
        self.max_files = max_files
        self.max_file_size_bytes = max_file_size_bytes
        self.max_total_size_bytes = max_total_size_bytes

    def submit(
        self,
        draft: SettlementDraft,
        uploads: list[SettlementUpload],
    ) -> SettlementReceipt:
        issues = self._validate(draft, uploads)
        if issues:
            raise SubmissionValidationError(issues)
        return self.repository.create_case(
            draft,
            uploads,
            policy_id=self.policy.policy_id,
            policy_version=self.policy.policy_version,
        )

    def _validate(
        self,
        draft: SettlementDraft,
        uploads: list[SettlementUpload],
    ) -> list[str]:
        issues: list[str] = []
        if len(uploads) > self.max_files:
            issues.append(f"Mỗi hồ sơ được tải tối đa {self.max_files} file.")
        if sum(upload.size_bytes for upload in uploads) > self.max_total_size_bytes:
            issues.append("Tổng dung lượng hồ sơ vượt quá 60 MB.")

        item_ids = {item.item_id for item in draft.expense_items}
        item_by_id = {item.item_id: item for item in draft.expense_items}
        seen_names: set[str] = set()
        seen_hashes: set[str] = set()
        for upload in uploads:
            normalized_name = upload.original_name.casefold()
            if normalized_name in seen_names:
                issues.append(
                    f"Tên file '{upload.original_name}' bị lặp; hãy đổi tên để liên kết chính xác."
                )
            seen_names.add(normalized_name)
            if upload.sha256 in seen_hashes:
                issues.append(f"File '{upload.original_name}' trùng nội dung trong hồ sơ.")
            seen_hashes.add(upload.sha256)

            extension = Path(upload.original_name).suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                issues.append(
                    f"Định dạng {extension or 'không xác định'} chưa được hỗ trợ."
                )
            if not upload.content:
                issues.append(f"File '{upload.original_name}' đang rỗng.")
            if upload.size_bytes > self.max_file_size_bytes:
                issues.append(f"File '{upload.original_name}' vượt quá 15 MB.")
            if (
                upload.role == SettlementDocumentRole.EXPENSE_EVIDENCE
                and upload.linked_item_id not in item_ids
            ):
                issues.append(
                    f"File '{upload.original_name}' chưa được gắn vào khoản chi hợp lệ."
                )
            if upload.linked_item_id in item_by_id:
                declared_names = {
                    name.casefold()
                    for name in item_by_id[upload.linked_item_id].evidence_names
                }
                if normalized_name not in declared_names:
                    issues.append(
                        f"Liên kết file '{upload.original_name}' không khớp dữ liệu khoản chi."
                    )

        uploaded_evidence_names = {
            upload.original_name.casefold()
            for upload in uploads
            if upload.role == SettlementDocumentRole.EXPENSE_EVIDENCE
        }
        for item in draft.expense_items:
            missing = [
                name
                for name in item.evidence_names
                if name.casefold() not in uploaded_evidence_names
            ]
            if missing:
                issues.append(
                    f"Khoản '{item.description}' tham chiếu file không tồn tại: "
                    + ", ".join(missing)
                )
        return issues

