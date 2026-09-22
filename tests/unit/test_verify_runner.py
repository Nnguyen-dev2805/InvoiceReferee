from pathlib import Path

from invoice_referee.domain import EvidenceRole
from app.views.verify_runner import discover_testcases, load_testcase


def _write(path: Path, content: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_load_testcase_reads_subject_body_and_primary_evidence(tmp_path: Path) -> None:
    case_dir = tmp_path / "happy_case"
    _write(
        case_dir / "content" / "content.txt",
        "Hóa đơn Phong Vũ\nEm gửi hóa đơn hôm trước nhé chị.".encode("utf-8"),
    )
    _write(case_dir / "evidence" / "bill.png", b"fake-image-bytes")

    loaded = load_testcase(case_dir)

    assert loaded is not None
    claim, uploads = loaded
    assert claim.subject == "Hóa đơn Phong Vũ"
    assert claim.body == "Em gửi hóa đơn hôm trước nhé chị."
    assert len(uploads) == 1
    assert uploads[0].original_name == "bill.png"
    assert uploads[0].role == EvidenceRole.PRIMARY_DOCUMENT


def test_load_testcase_includes_supporting_attach_file(tmp_path: Path) -> None:
    case_dir = tmp_path / "conflict_case"
    _write(case_dir / "content" / "content.txt", "Đối chiếu nhiên liệu\nNội dung.".encode("utf-8"))
    _write(case_dir / "evidence" / "bill.pdf", b"bill")
    _write(case_dir / "content" / "attach_file" / "kiem_ke.pdf", b"kiem-ke")

    loaded = load_testcase(case_dir)

    assert loaded is not None
    _, uploads = loaded
    roles_by_name = {upload.original_name: upload.role for upload in uploads}
    assert roles_by_name["bill.pdf"] == EvidenceRole.PRIMARY_DOCUMENT
    assert roles_by_name["kiem_ke.pdf"] == EvidenceRole.SUPPORTING_DOCUMENT


def test_load_testcase_returns_none_for_empty_folder(tmp_path: Path) -> None:
    case_dir = tmp_path / "empty_case"
    case_dir.mkdir()
    (case_dir / ".DS_Store").write_bytes(b"junk")

    assert load_testcase(case_dir) is None


def test_discover_testcases_lists_only_directories_sorted(tmp_path: Path) -> None:
    (tmp_path / "b_case").mkdir()
    (tmp_path / "a_case").mkdir()
    (tmp_path / "stray_file.txt").write_bytes(b"x")

    folders = discover_testcases(tmp_path)

    assert [folder.name for folder in folders] == ["a_case", "b_case"]
