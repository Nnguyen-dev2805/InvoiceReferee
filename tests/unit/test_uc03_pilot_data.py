"""Pilot artifact checks; these do not prove the finance runtime is wired."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/sinh_uc03_pilot.py"
CASES = {
    "f01-cong-tac-thu-lai-tien-thua": (3_240_000, 4_000_000),
    "f02-cong-tac-cong-ty-chi-them": (5_400_000, 5_000_000),
    "f03-cong-tac-can-bang": (4_320_000, 4_320_000),
}


def run_generator(output: Path):
    assert SCRIPT.is_file(), "pilot generator is not implemented"
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )


def test_pilot_sources_context_and_regeneration_are_independent_of_gold(tmp_path):
    output = tmp_path / "pilot"
    result = run_generator(output)
    assert result.returncode == 0, result.stderr
    for folder, (expense, advance) in CASES.items():
        inp = output / folder / "input"
        pdfs = sorted(inp.glob("*.pdf"))
        # F01 carries two extra alternative advance-basis documents (transfer +
        # cash) for the same 4m advance; F02/F03 carry the two base documents.
        assert len(pdfs) == (4 if folder.startswith("f01") else 2)
        text = "\n".join(PdfReader(p).pages[0].extract_text() for p in pdfs)
        assert "Hà Nội" in text and "06/10/2026" in text and "10/10/2026" in text
        assert f"{expense:,}".replace(",", ".") in text
        assert "máy in" not in text.casefold()
        # The demo-policy simplification: no printed payment-declaration sentence
        # and no attachment list line on the settlement form.
        assert "Tôi xác nhận đã trực tiếp thanh toán" not in text
        assert "Tài liệu kèm theo" not in text
        # The invoice names the buyer person (the employee-paid binding key).
        assert "Họ tên người mua: Nguyễn An" in text
        # The service-in-provision line is removed from the invoice.
        assert "Dịch vụ được cung cấp tại" not in text
        org = json.loads((inp / "organization.json").read_text())
        assert org["ledger"][0]["amount"] == advance
        assert org["ledger"][0]["kind"] == "ADVANCE_RECEIVED"
        assert org["coverage"]["opening_by_fund"] == {"company:bank-demo": 0}
        assert "expected_amounts" not in (inp / "organization.json").read_text()
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inp.iterdir()}
        gold = output / folder / "gold"
        gold.mkdir()
        (gold / "trap.json").write_text('{"expected": "999999999"}')
        result = run_generator(output)
        assert result.returncode == 0, result.stderr
        assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inp.iterdir()}
        assert (gold / "trap.json").exists()


def test_f01_carries_two_alternative_advance_basis_documents(tmp_path):
    # Two documents describe the SAME 4m advance; they are alternatives, not two
    # advances (4m + 4m would be wrong). Each carries the 4m amount exactly once.
    output = tmp_path / "pilot"
    assert run_generator(output).returncode == 0
    inp = output / "f01-cong-tac-thu-lai-tien-thua" / "input"
    transfer = PdfReader(inp / "03-bien-nhan-chuyen-khoan.pdf").pages[0].extract_text()
    cash = PdfReader(inp / "04-phieu-chi-tien-mat.pdf").pages[0].extract_text()
    for text in (transfer, cash):
        assert "4.000.000 đ" in text
        assert "Ứng" in text or "ứng" in text
    assert "BIÊN NHẬN CHUYỂN KHOẢN" in transfer
    assert "Hoàn tất" in transfer
    assert "PHIẾU CHI TIỀN MẶT" in cash
    assert "Người nhận tiền" in cash
    # Three signature positions on the cash voucher, all on one row.
    assert "Người phê duyệt" in cash and "Kế toán" in cash


def test_pilot_generator_refuses_unmanaged_output_without_deleting_files(tmp_path):
    output = tmp_path / "important"
    output.mkdir()
    sentinel = output / "notes.txt"
    sentinel.write_text("keep me")
    result = run_generator(output)
    assert result.returncode != 0
    assert sentinel.read_text() == "keep me"


def test_pilot_generator_does_not_follow_manifest_symlink(tmp_path):
    output = tmp_path / "pilot"
    assert run_generator(output).returncode == 0
    sentinel = tmp_path / "notes.txt"
    sentinel.write_text("keep me")
    (output / "manifest.json").unlink()
    (output / "manifest.json").symlink_to(sentinel)
    result = run_generator(output)
    assert result.returncode != 0
    assert sentinel.read_text() == "keep me"
