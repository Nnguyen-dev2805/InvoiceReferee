"""Travel demo recipe: generator correctness and partition separation.

The demo is synthetic and fake/replay only. These tests build it into a tmp dir
(never touching data/) and assert the manifest separates input/company/followup
from expected, the oracle is not an input, and the ledger is a valid structured
source the fake reader parses.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "build_travel_demo", REPO / "scripts" / "build_travel_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def demo(tmp_path):
    gen = _load_generator()
    out = tmp_path / "data" / "settlement" / "travel-demo-v1"
    manifest = gen.build("WORK-DEMO-TRAVEL", out,
                         "2026-10-14T23:59:59+07:00")
    return out, manifest, gen


def test_manifest_separates_expected_from_inputs(demo):
    out, manifest, _ = demo
    roles = {f["path"]: f["role"] for f in manifest["files"]}
    assert roles["employee-input/employee-ledger.txt"] == "employee-actual-expenses"
    assert roles["company-input/company-packet-template.json"] \
        == "company-register-template"
    assert roles["followup/reimbursement-note.md"] == "followup"
    assert roles["expected/oracle.json"] == "expected-oracle"
    # Expected is excluded from model inputs.
    assert "expected" in manifest["excluded_from_model"]
    # No expected artifact lives inside the input partition.
    assert not any(p.startswith("employee-input/expected") for p in roles)


def test_oracle_is_not_an_input_file(demo):
    out, _, _ = demo
    # The employee input directory contains only the ledger, no oracle.
    employee_files = list((out / "employee-input").rglob("*"))
    assert [f.name for f in employee_files if f.is_file()] \
        == ["employee-ledger.txt"]


def test_ledger_is_valid_structured_source(demo):
    out, _, _ = demo
    from invoice_referee.settlement.reader import (
        StructuredLedgerReader, looks_like_ledger,
    )
    text = (out / "employee-input" / "employee-ledger.txt").read_text()
    assert looks_like_ledger(text)
    # Parse the ledger text directly (no Store/budget needed for text sources).
    reader = StructuredLedgerReader(out)
    observations = reader.parse_text(text, "S-demo", [
        "expense.EXP-HOTEL.amount", "payment.PAY-HOTEL.payer",
        "payment.PAY-HOTEL.status"])
    by_key = {o.key: o.value for o in observations}
    assert by_key["expense.EXP-HOTEL.amount"] == 3_000_000
    assert by_key["payment.PAY-HOTEL.payer"] == "EMPLOYEE"
    assert by_key["payment.PAY-HOTEL.status"] == "RECEIVED"


def test_oracle_matches_declared_identity(demo):
    out, manifest, gen = demo
    oracle = json.loads((out / "expected" / "oracle.json").read_text())
    assert oracle["employee_cost_vnd"] == gen.EMPLOYEE_TOTAL == 5_000_000
    assert oracle["company_direct_vnd"] == 3_000_000
    assert oracle["total_work_cost_vnd"] == 8_000_000
    assert oracle["advance_received_vnd"] == 2_000_000
    assert oracle["settlement_net_vnd"] == 3_000_000
    assert oracle["after_receipt_3m_net_vnd"] == 0
    # Company identity present so collection classification is unambiguous.
    config = json.loads((out / "company-input" / "b7-config.json").read_text())
    assert config["company_ref"] == manifest["company_ref"]


def test_generator_refuses_frozen_dataset_name(tmp_path):
    gen = _load_generator()
    with pytest.raises(SystemExit):
        gen.build("WORK", tmp_path / "data" / "worked-example-v1",
                  "2026-10-14T23:59:59+07:00")


def test_manifest_hash_is_reproducible(tmp_path):
    gen = _load_generator()
    a = gen.build("WORK", tmp_path / "a" / "travel-demo-v1",
                  "2026-10-14T23:59:59+07:00")
    b = gen.build("WORK", tmp_path / "b" / "travel-demo-v1",
                  "2026-10-14T23:59:59+07:00")
    hashes_a = {f["path"]: f["sha256"] for f in a["files"]}
    hashes_b = {f["path"]: f["sha256"] for f in b["files"]}
    assert hashes_a == hashes_b
