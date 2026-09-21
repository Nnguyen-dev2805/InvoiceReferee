from pathlib import Path

from invoice_referee.domain import ClaimDraft, EvidenceRole, UploadPayload
from invoice_referee.storage import LocalCaseStore, LocalEvidenceRepository


def test_repository_reads_evidence_and_round_trips_ocr_result(tmp_path: Path) -> None:
    store = LocalCaseStore(tmp_path, id_factory=lambda: "CASE-OCR-001")
    claim = ClaimDraft(
        employee_name="Nguyễn Văn A",
        employee_email="a@example.com",
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
