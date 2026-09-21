import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain import ClaimDraft, EvidenceRole, UploadPayload
from invoice_referee.storage import LocalCaseStore


def test_store_persists_metadata_file_and_audit_log(tmp_path: Path) -> None:
    fixed_time = datetime(2026, 9, 21, 10, 0, tzinfo=timezone(timedelta(hours=7)))
    store = LocalCaseStore(
        tmp_path,
        clock=lambda: fixed_time,
        id_factory=lambda: "CASE-TEST-STORE",
    )
    claim = ClaimDraft(
        employee_name="Trần Thị B",
        employee_email="b@example.com",
        subject="Chi phí văn phòng phẩm",
        body="Mua dây cáp cho dự án Orion",
    )
    evidence = UploadPayload(
        original_name="hóa đơn.jpg",
        content=b"test-image",
        mime_type="image/jpeg",
        role=EvidenceRole.PRIMARY_DOCUMENT,
    )

    receipt = store.save_submission(claim, [evidence], [])

    case_dir = tmp_path / receipt.case_id
    metadata = json.loads((case_dir / "submission.json").read_text(encoding="utf-8"))
    audit_lines = (case_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()

    assert metadata["employee_claim"]["body"] == "Mua dây cáp cho dự án Orion"
    assert metadata["evidence"][0]["role"] == "PRIMARY_DOCUMENT"
    assert (case_dir / metadata["evidence"][0]["relative_path"]).exists()
    assert [json.loads(line)["event_type"] for line in audit_lines] == [
        "CASE_CREATED",
        "EVIDENCE_ATTACHED",
    ]
