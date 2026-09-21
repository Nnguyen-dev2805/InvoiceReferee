from pathlib import Path

import pytest

from invoice_referee.application import SubmitCaseService
from invoice_referee.domain import (
    ClaimDraft,
    EvidenceRole,
    SubmissionValidationError,
    UploadPayload,
)
from invoice_referee.storage import LocalCaseStore


def make_service(tmp_path: Path) -> SubmitCaseService:
    store = LocalCaseStore(tmp_path, id_factory=lambda: "CASE-TEST-001")
    return SubmitCaseService(store)


def valid_claim(body: str = "Tiếp khách công ty ABC cho dự án Phoenix") -> ClaimDraft:
    return ClaimDraft(
        subject="Đề nghị hoàn ứng",
        body=body,
    )


def upload(
    name: str = "bill.jpg",
    content: bytes = b"image-content",
    role: EvidenceRole = EvidenceRole.PRIMARY_DOCUMENT,
) -> UploadPayload:
    return UploadPayload(
        original_name=name,
        content=content,
        mime_type="image/jpeg",
        role=role,
    )


def test_accepts_description_without_evidence(tmp_path: Path) -> None:
    receipt = make_service(tmp_path).submit(valid_claim(), [])

    assert receipt.case_id == "CASE-TEST-001"
    assert receipt.primary_document_count == 0
    assert receipt.supporting_document_count == 0
    assert (tmp_path / receipt.case_id / "submission.json").exists()


def test_accepts_files_without_description(tmp_path: Path) -> None:
    receipt = make_service(tmp_path).submit(valid_claim(body=""), [upload()])

    assert receipt.primary_document_count == 1


def test_rejects_completely_empty_submission(tmp_path: Path) -> None:
    with pytest.raises(SubmissionValidationError) as exc_info:
        make_service(tmp_path).submit(valid_claim(body=""), [])

    assert "nội dung đề nghị" in str(exc_info.value)


def test_deduplicates_same_file_across_roles(tmp_path: Path) -> None:
    files = [
        upload(),
        upload(name="report-copy.jpg", role=EvidenceRole.SUPPORTING_DOCUMENT),
    ]

    receipt = make_service(tmp_path).submit(valid_claim(), files)

    assert receipt.primary_document_count == 1
    assert receipt.supporting_document_count == 0
    assert receipt.warnings == ["Đã bỏ qua tệp trùng: report-copy.jpg"]


def test_rejects_unsupported_primary_document(tmp_path: Path) -> None:
    with pytest.raises(SubmissionValidationError) as exc_info:
        make_service(tmp_path).submit(valid_claim(), [upload(name="script.exe")])

    assert "chưa được hỗ trợ" in str(exc_info.value)
