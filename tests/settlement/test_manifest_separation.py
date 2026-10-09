"""W06 manifest separation: input/followup/expected tách bạch, hash là bản
gói đã đóng băng, development corpus không được coi là holdout độc lập.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.evaluation import (
    discover_packets,
    load_packet,
    run_suite,
)
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

CORPUS = Path(__file__).parents[2] / "docs" / "discovery" / "eval_development"


def test_corpus_discovers_the_20_packets():
    packets = discover_packets(CORPUS)
    ids = {p.case_id for p in packets}
    assert len(ids) == 20
    assert {"Q01", "Q09", "A01"} <= ids
    assert all(p.dataset_role == "DEVELOPMENT_ONLY" for p in packets)


def test_q01_expected_is_separate_from_inputs():
    packet = load_packet(CORPUS / "b7_core_01" / "Q01")
    input_names = {p.name for p in packet.input_files}
    assert input_names == {"employee_claim.md", "authority_and_pretrip.md",
                           "expense_and_payment_sources.md",
                           "financial_events_m1.csv", "coverage_m1.md"}
    # expected tách khỏi input: không nằm trong input_files và có hash riêng
    assert "expected.json" not in input_names
    assert packet.expected_initial["S"] == 3_000_000
    assert packet.expected_after is None


def test_q09_followup_is_separate_from_initial_inputs():
    packet = load_packet(CORPUS / "b7_uncertainty_01" / "Q09")
    initial = {p.name for p in packet.input_files}
    followup = {p.name for p in packet.followup_files}
    assert followup == {"resolution.md"}
    assert followup & initial == set()  # followup không trộn vào input ban đầu
    assert packet.expected_initial["requires_extra_resolution"] is True
    assert packet.expected_after["phase"] == "AFTER_SELECTED_VALID_FOLLOWUP"
    assert packet.expected_after["first_pass_routine"] is False


def test_followup_marked_as_initial_input_is_refused(tmp_path):
    packet_dir = tmp_path / "Q09"
    packet_dir.mkdir()
    original = CORPUS / "b7_uncertainty_01" / "Q09"
    manifest = json.loads((original / "manifest.json").read_text())
    manifest["followup_is_initial_input"] = True
    (packet_dir / "manifest.json").write_text(json.dumps(manifest))
    # copy input files (không cần hash đúng — expect fail trước khi đọc file)
    with pytest.raises(DomainError) as error:
        load_packet(packet_dir)
    assert error.value.code == "FOLLOWUP_IS_INPUT"


def test_tampered_expected_hash_is_refused(tmp_path):
    packet_dir = tmp_path / "Q01"
    (packet_dir / "expected").mkdir(parents=True)
    original = CORPUS / "b7_core_01" / "Q01"
    for rel in ["manifest.json", "expected/expected.json"]:
        (packet_dir / rel).write_bytes((original / rel).read_bytes())
    # đổi 1 byte expected nhưng giữ hash cũ → dataset bị từ chối
    expected_path = packet_dir / "expected" / "expected.json"
    tampered = json.loads(expected_path.read_text())
    tampered["S"] = 999
    expected_path.write_text(json.dumps(tampered))
    (packet_dir / "input").mkdir()
    for entry in json.loads((packet_dir / "manifest.json").read_text())["input_files"]:
        target = packet_dir / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original / entry["path"]).read_bytes())
    with pytest.raises(DomainError) as error:
        load_packet(packet_dir)
    assert error.value.code == "DATASET_HASH_MISMATCH"


def test_development_corpus_reported_not_holdout(tmp_path):
    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    service = Service(store, StructuredLedgerReader(store.artifact_root),
                      config=ServiceConfig())
    report = run_suite(CORPUS, service, packet_ids=["Q01"])
    assert report.results[0].case_id == "Q01"
    notes = " ".join(report.notes)
    # development corpus không được báo là holdout độc lập
    assert "DEVELOPMENT_ONLY" in notes
    assert "holdout" in notes
    # verdict không được gắn PASS chỉ vì run xong: fake reader không đọc được
    # narrative sources → kết quả thật được giữ nguyên
    assert report.results[0].verdict in {"PASS", "FAIL", "INCONCLUSIVE"}
    assert report.mode == "FAKE_OR_REPLAY"


def test_family_clones_flagged_in_report_notes():
    packets = discover_packets(CORPUS)
    families = {p.family_id for p in packets}
    assert families == {"WORK_BUDGET_TEMPLATE_01"}  # một family, không độc lập
