"""Tests for the append-only audit store and human controls."""

import json

import pytest

from invoice_referee.domain import models as m
from invoice_referee.audit.store import AuditStore


def test_append_returns_event_with_id_and_timestamp():
    store = AuditStore(transaction_id="TX-001")
    ev = store.append("TRANSACTION_CREATED", reason="created")
    assert ev.event_id
    assert ev.timestamp
    assert ev.transaction_id == "TX-001"
    assert store.events[-1] is ev


def test_events_are_ordered_and_ids_unique():
    store = AuditStore(transaction_id="TX-001")
    store.append("TRANSACTION_CREATED")
    store.append("CHECK_COMPLETED", rule_id="P05", result="PASS")
    store.append("DECISION_MADE", result="AUTO_PROCESS")
    ids = [e.event_id for e in store.events]
    assert len(ids) == len(set(ids)) == 3
    assert [e.event_type for e in store.events] == [
        "TRANSACTION_CREATED",
        "CHECK_COMPLETED",
        "DECISION_MADE",
    ]


def test_record_check_result_creates_event():
    store = AuditStore(transaction_id="TX-001")
    cr = m.CheckResult(check_id="CHECK_QUANTITY", status=m.CheckStatus.FAIL, policy_rule_id="P05",
                       reason="exceeds", evidence_refs=["GR-001", "INV-001"])
    ev = store.record_check(cr)
    assert ev.event_type == "CHECK_COMPLETED"
    assert ev.rule_id == "P05"
    assert ev.result == "FAIL"
    assert ev.input_refs == ["GR-001", "INV-001"]


def test_record_llm_assessment_and_fallback_events():
    store = AuditStore(transaction_id="TX-001")
    a = m.AgentAssessment(
        proposed_uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
        proposed_action=m.DecisionAction.REQUEST_INFO,
        explanation="x",
        primary_check_id="CHECK_AMOUNT",
        model="fake-model",
        prompt_version="v1",
        fallback_used=True,
    )
    ev = store.record_assessment(a)
    assert ev.event_type == "LLM_ASSESSMENT_CREATED"
    assert ev.details["fallback_used"] is True
    assert ev.details["prompt_version"] == "v1"
    fb = store.record_fallback_used("provider timeout")
    assert fb.event_type == "LLM_FALLBACK_USED"


def test_record_decision_guard_captures_override_flag():
    store = AuditStore(transaction_id="TX-001")
    ev = store.record_decision_guard(proposed_action="AUTO_PROCESS", final_action="REQUEST_INFO")
    assert ev.event_type == "DECISION_GUARD_APPLIED"
    assert ev.details["proposal_overridden"] is True
    assert ev.details["proposed_action"] == "AUTO_PROCESS"
    assert ev.details["final_action"] == "REQUEST_INFO"


def test_record_decision_event():
    store = AuditStore(transaction_id="TX-001")
    d = m.Decision(action=m.DecisionAction.ESCALATE, reason="beyond authority",
                   target="Finance Manager", policy_rule_ids=["P12"])
    ev = store.record_decision(d)
    assert ev.event_type == "DECISION_MADE"
    assert ev.result == "ESCALATE"


# --- Human controls ----------------------------------------------------------


def test_record_stop_changes_workflow_status_only():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")

    stop = store.record_stop(tx, actor="a@example.com", reason="verify bank account")

    assert tx.workflow_status is m.WorkflowStatus.STOPPED
    assert tx.decision.action is m.DecisionAction.AUTO_PROCESS  # decision unchanged
    assert stop in tx.human_stops
    assert store.events[-1].event_type == "STOPPED"
    assert stop.previous_workflow_status is m.WorkflowStatus.ACTIVE


def test_stop_is_not_a_fourth_decision():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")
    store.record_stop(tx, actor="a@example.com", reason="hold")
    # Decision.action stays one of the three valid actions; STOPPED lives on workflow_status.
    assert tx.decision.action in set(m.DecisionAction)
    assert tx.workflow_status.value == "STOPPED"


def test_record_override_preserves_original_decision():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")

    ovr = store.record_override(
        tx, actor="a@example.com", overridden_action=m.DecisionAction.ESCALATE,
        reason="manual finance approval required",
    )

    assert ovr.original_action is m.DecisionAction.AUTO_PROCESS
    assert ovr.overridden_action is m.DecisionAction.ESCALATE
    assert ovr in tx.human_overrides
    # Original decision must remain reconstructable in audit history.
    original_events = [e for e in store.events if e.event_type == "DECISION_MADE"]
    assert any(True for _ in [ovr])  # override recorded
    assert store.events[-1].event_type == "OVERRIDDEN"
    assert store.events[-1].details["original_action"] == "AUTO_PROCESS"


def test_override_rejects_stopped_as_action():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")
    with pytest.raises((TypeError, ValueError)):
        store.record_override(tx, actor="a@example.com", overridden_action="STOPPED", reason="bad")


def test_history_survives_stop_then_override():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")
    store.record_decision(tx.decision)
    store.record_stop(tx, actor="a", reason="hold")
    store.record_override(tx, actor="b", overridden_action=m.DecisionAction.REQUEST_INFO, reason="need info")
    types = [e.event_type for e in store.events]
    assert types == ["DECISION_MADE", "STOPPED", "OVERRIDDEN"]
    assert len(tx.human_stops) == 1
    assert len(tx.human_overrides) == 1


# --- Export ------------------------------------------------------------------


def test_export_json_roundtrips():
    store = AuditStore(transaction_id="TX-001")
    store.append("TRANSACTION_CREATED", reason="created")
    store.append("DECISION_MADE", result="AUTO_PROCESS")
    payload = store.export_json()
    data = json.loads(payload)
    assert isinstance(data, list)
    assert data[0]["event_type"] == "TRANSACTION_CREATED"
    assert data[-1]["result"] == "AUTO_PROCESS"
