"""R1: the generated 15-case corpus carries real facts in the sources (plan R1).

The review (PDF_DATA_REVIEW) found the old evaluation PDFs shared one body and
carried none of the facts their gold demanded. This suite pins the replacement:
15 named cases whose sources actually contain the fields, staged so a future
proof is absent from the initial input, with literal gold that never leaks into
input.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from du_lieu_kiem_thu.ho_so import (  # noqa: E402
    CASES,
    CASE_IDS,
    CASE_SLUGS,
    build_case,
)
from invoice_referee.evaluation.packets import load_gold, load_input  # noqa: E402


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("kiem-thu")
    for spec in CASES:
        build_case(spec, out)
    return out


@pytest.fixture(scope="module")
def generated_d04(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("d04")
    spec = next(c for c in CASES if c.case_id == "D04")
    build_case(spec, out)
    return out / spec.slug


def test_exactly_15_named_cases() -> None:
    assert len(CASES) == 15
    assert CASE_IDS == [f"D{i:02d}" for i in range(1, 16)]


def test_slugs_are_vietnamese_free_lowercase_hyphen() -> None:
    for slug in CASE_SLUGS:
        assert slug == slug.lower()
        assert " " not in slug and "_" not in slug
        assert slug.startswith("case-")
        # no accented Vietnamese characters in the folder name
        assert all(ord(ch) < 128 for ch in slug)


def test_initial_stage_excludes_future_proof(generated_d04: Path) -> None:
    p = load_input(generated_d04, stage_id="ban-dau")
    assert all("xac-nhan-nguoi-tra" not in s.filename for s in p.sources)
    assert "ban-doc-stub" not in p.model_dump_json()


def test_initial_stage_present_after_proof_stage(generated_d04: Path) -> None:
    later = load_input(generated_d04, stage_id="bo-sung-payer")
    assert any("xac-nhan-nguoi-tra" in s.filename for s in later.sources)


def test_d01_source_carries_its_money_fields(generated: Path) -> None:
    # The source text must actually contain the amounts the gold asserts, so a
    # reader (not the transcription) can derive them.
    import pypdf

    packet = generated / "case-01-cong-ty-chi-them"
    text = _all_text(packet / "dau-vao" / "01-nop-ban-dau")
    assert "8.000.000" in text  # incurred
    assert "5.000.000" in text  # employee paid
    assert "3.000.000" in text  # company direct
    assert "2.000.000" in text  # advance


def test_input_never_contains_gold(generated: Path) -> None:
    packet = generated / "case-01-cong-ty-chi-them"
    p = load_input(packet, stage_id="ban-dau")
    dumped = p.model_dump_json()
    assert "latent" not in dumped
    assert "expected" not in dumped
    # No file inside dau-vao/ references the answer folder.
    for path in (packet / "dau-vao").rglob("*"):
        if path.is_file():
            assert "dap-an" not in path.read_text(encoding="utf-8", errors="ignore")


def test_gold_reads_for_a_stage(generated: Path) -> None:
    gold = load_gold(generated / "case-04-chua-ro-nguoi-thanh-toan", stage_id="ban-dau")
    assert gold.allowed.route == "FACT"


def test_native_date_is_not_read_as_amount(generated: Path) -> None:
    # A date like 05/10/2026 must not be parsed as a money amount.
    import pypdf

    packet = generated / "case-01-cong-ty-chi-them"
    text = _all_text(packet / "dau-vao" / "01-nop-ban-dau")
    assert "2026" in text  # the date is present
    # The extractor must not turn the date into a fact; that is asserted at the
    # pipeline layer, here we just ensure the date is not written as an amount.
    assert "20.260" not in text and "2.026" not in text


def test_partial_build_is_not_claimed_as_15(tmp_path: Path) -> None:
    from du_lieu_kiem_thu.ho_so import build_case

    # Building a single case produces one case dir, not a claimed-15 manifest.
    spec = CASES[0]
    build_case(spec, tmp_path)
    dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(dirs) == 1


def test_source_filename_does_not_leak_the_slug(generated: Path) -> None:
    import pypdf

    for spec in CASES:
        packet = generated / spec.slug
        for source in (packet / "dau-vao").rglob("*.pdf"):
            assert spec.slug not in source.name
            text = " ".join(
                (page.extract_text() or "") for page in pypdf.PdfReader(str(source)).pages
            )
            assert spec.slug not in text


def _all_text(directory: Path) -> str:
    import pypdf

    parts: list[str] = []
    for pdf in sorted(directory.rglob("*.pdf")):
        for page in pypdf.PdfReader(str(pdf)).pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def test_cli_check_and_generate(tmp_path: Path) -> None:
    import sinh_du_lieu_kiem_thu as cli

    out = tmp_path / "corpus"
    code = cli.main(["--output", str(out), "--cases", "all"])
    assert code == 0
    assert (out / "manifest.json").is_file()
    assert (out / "case-01-cong-ty-chi-them").is_dir()
    assert cli.main(["--output", str(out), "--check"]) == 0


def test_cli_check_fails_when_unmanaged(tmp_path: Path) -> None:
    import sinh_du_lieu_kiem_thu as cli

    out = tmp_path / "empty"
    assert cli.main(["--output", str(out), "--check"]) == 2


def test_cli_partial_cases(tmp_path: Path) -> None:
    import sinh_du_lieu_kiem_thu as cli

    out = tmp_path / "partial"
    code = cli.main(["--output", str(out), "--cases", "01,02"])
    assert code == 0
    assert (out / "case-01-cong-ty-chi-them").is_dir()
    assert (out / "case-02-nhan-vien-hoan-tien").is_dir()
    assert not (out / "case-03-quyet-toan-can-bang").exists()


def test_cli_refuses_nonempty_unmanaged(tmp_path: Path) -> None:
    import sinh_du_lieu_kiem_thu as cli

    out = tmp_path / "busy"
    out.mkdir()
    (out / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["--output", str(out), "--cases", "all"])


def test_gold_change_changes_the_digest(tmp_path: Path) -> None:
    from du_lieu_kiem_thu import dap_an

    spec = next(c for c in CASES if c.case_id == "D01")
    case_dir = tmp_path / "d01"
    build_case(spec, tmp_path)
    before = dap_an.gold_digest(tmp_path / spec.slug / "dap-an")
    allowed = tmp_path / spec.slug / "dap-an" / "ket-qua-hop-le.json"
    data = json.loads(allowed.read_text(encoding="utf-8"))
    data["stages"]["ban-dau"]["expected_amounts"] = {"PAY": 9_000_000}
    allowed.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    after = dap_an.gold_digest(tmp_path / spec.slug / "dap-an")
    assert before != after, "changing allowed gold must change the digest"


def test_two_builds_same_spec_have_same_source_hashes(tmp_path: Path) -> None:
    import hashlib

    spec = next(c for c in CASES if c.case_id == "D01")
    a = tmp_path / "a"
    b = tmp_path / "b"
    build_case(spec, a)
    build_case(spec, b)
    pa = sorted((a / spec.slug / "dau-vao" / "01-nop-ban-dau").glob("*.pdf"))
    pb = sorted((b / spec.slug / "dau-vao" / "01-nop-ban-dau").glob("*.pdf"))
    assert [p.name for p in pa] == [p.name for p in pb]
    for left, right in zip(pa, pb):
        assert hashlib.sha256(left.read_bytes()).hexdigest() == hashlib.sha256(
            right.read_bytes()
        ).hexdigest()


def test_resolver_materializes_exact_bytes(generated: Path) -> None:
    import hashlib

    from invoice_referee.evaluation.packets import bind_sources

    packet = generated / "case-01-cong-ty-chi-them"
    p = load_input(packet, stage_id="ban-dau")
    resolve = bind_sources(packet, p, stage_id="ban-dau")
    for source in p.sources:
        data = resolve(source)
        assert hashlib.sha256(data).hexdigest() == source.sha256


def test_resolver_rejects_unbound_source(generated: Path) -> None:
    from invoice_referee.evaluation.models import PacketSource
    from invoice_referee.evaluation.packets import PacketError, bind_sources

    packet = generated / "case-01-cong-ty-chi-them"
    p = load_input(packet, stage_id="ban-dau")
    resolve = bind_sources(packet, p, stage_id="ban-dau")
    rogue = PacketSource(filename="rogue.pdf", media="PDF", sha256="0" * 64)
    with pytest.raises(PacketError):
        resolve(rogue)


def test_future_source_edit_keeps_initial_basis(generated_d04: Path) -> None:
    from invoice_referee.evaluation.packets import digest_packet_input

    before = digest_packet_input(generated_d04, stage_id="ban-dau")
    proof = generated_d04 / "dau-vao" / "02-bo-sung" / "01-xac-nhan-nguoi-tra.pdf"
    proof.write_bytes(proof.read_bytes() + b"% edited\n")
    after = digest_packet_input(generated_d04, stage_id="ban-dau")
    assert before == after, "editing a later-stage proof must not change the initial basis"

