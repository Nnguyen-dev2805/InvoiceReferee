"""Tests for UI presentation helpers (pure functions, no Streamlit runtime)."""

import pytest

from invoice_referee.domain import models as m
from invoice_referee.transaction.builder import build_transaction
from app import presentation as p


def test_format_vnd_groups_thousands():
    assert p.format_vnd(30_000_000) == "30.000.000 ₫"


def test_format_vnd_none_is_dash():
    assert p.format_vnd(None) == "—"


def test_list_sample_cases_returns_all_17_sorted():
    cases = p.list_sample_cases()
    assert cases[0] == "TC01"
    assert cases[-1] == "TC17"
    assert len(cases) == 17


def test_load_sample_returns_evidence_dict():
    ev = p.load_sample("TC01")
    assert ev["transaction_id"] == "TX01"
    assert ev["invoice"]["total_amount"] == 30_000_000


def test_parse_json_input_valid():
    ev = p.parse_json_input('{"transaction_id": "X"}')
    assert ev["transaction_id"] == "X"


def test_parse_json_input_invalid_raises_value_error():
    with pytest.raises(ValueError):
        p.parse_json_input("{not valid json")


def test_parse_json_input_non_object_raises():
    with pytest.raises(ValueError):
        p.parse_json_input("[1, 2, 3]")


def test_evidence_summary_flags_presence():
    ev = p.load_sample("TC01")
    tx = build_transaction(ev)
    summary = p.evidence_summary(tx)
    assert summary["Purchase Order"] is True
    assert summary["Goods Receipt"] is True
    assert summary["Invoice"] is True
    assert summary["Payment History"] is True


def test_evidence_summary_missing_goods_receipt():
    ev = p.load_sample("TC04")
    tx = build_transaction(ev)
    summary = p.evidence_summary(tx)
    assert summary["Goods Receipt"] is False


def test_decision_actions_helper():
    assert set(p.decision_action_labels()) == {"AUTO_PROCESS", "REQUEST_INFO", "ESCALATE"}
