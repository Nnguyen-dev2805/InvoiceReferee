from pathlib import Path

import pytest

from invoice_referee.domain import ClaimDraft, EvidenceRole, UploadPayload
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository


def test_repository_reads_evidence_and_round_trips_ocr_result(tmp_path: Path) -> None:
    store = LocalCaseStore(tmp_path, id_factory=lambda: "CASE-OCR-001")
    claim = ClaimDraft(
        subject="Đề nghị kiểm tra OCR",
        body="Chi phí tiếp khách",
    )
    upload = UploadPayload(
        original_name="bill.jpg",
        content=b"image-content",
        mime_type="image/jpeg",
        role=EvidenceRole.PRIMARY_DOCUMENT,
    )
    store.save_submission(claim, [upload], [])
    repository = LocalEvidenceRepository(tmp_path)

    cases = repository.list_cases()
    evidence = cases[0].evidence[0]

    assert cases[0].case_id == "CASE-OCR-001"
    assert evidence.absolute_path.read_bytes() == b"image-content"

    result = {"provider": "mistral", "response": {"pages": []}}
    repository.save_ocr_result(evidence, result)

    assert repository.load_ocr_result(evidence) == result


def test_repository_deletes_one_case_and_all_artifacts(tmp_path: Path) -> None:
    store = LocalCaseStore(tmp_path, id_factory=lambda: "CASE-DELETE-001")
    store.save_submission(
        ClaimDraft(subject="Hồ sơ cần xóa", body="Chi phí thử nghiệm"),
        [
            UploadPayload(
                original_name="bill.jpg",
                content=b"image-content",
                mime_type="image/jpeg",
                role=EvidenceRole.PRIMARY_DOCUMENT,
            )
        ],
        [],
    )
    repository = LocalEvidenceRepository(tmp_path)
    evidence = repository.get_case("CASE-DELETE-001").evidence[0]
    repository.save_ocr_result(evidence, {"response": {"pages": []}})
    repository.save_processing_result(
        "CASE-DELETE-001",
        {"processed_at": "2026-09-21T10:00:00+07:00", "decision": "PASS"},
    )

    repository.delete_case("CASE-DELETE-001")

    assert not (tmp_path / "CASE-DELETE-001").exists()
    assert repository.list_cases() == []


def test_repository_rejects_unsafe_case_id_for_delete(tmp_path: Path) -> None:
    repository = LocalEvidenceRepository(tmp_path)

    with pytest.raises(ValueError, match="Case ID không hợp lệ"):
        repository.delete_case("../outside")
