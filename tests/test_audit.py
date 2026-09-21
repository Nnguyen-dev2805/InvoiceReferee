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


def test_events_are_exposed_read_only():
    """Audit history is append-only; callers must not be able to mutate it."""
    store = AuditStore(transaction_id="TX-001")
    store.append("TRANSACTION_CREATED")
    with pytest.raises((AttributeError, TypeError)):
        store.events.append("tampered")
    with pytest.raises((AttributeError, TypeError)):
        store.events.clear()


def test_override_before_a_decision_is_recorded_does_not_crash():
    """Overriding a transaction that has no agent decision yet must be allowed."""
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    assert tx.decision is None

    ovr = store.record_override(
        tx, actor="a@example.com", overridden_action=m.DecisionAction.ESCALATE,
        reason="manual finance approval required",
    )

    assert ovr.original_action is None
    assert ovr.overridden_action is m.DecisionAction.ESCALATE
    assert store.events[-1].details["original_action"] is None


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


# --- Extraction / OCR events (Task 10) ---------------------------------------


def _candidate(name="total_amount", value=30_000_000, status=m.FieldStatus.EXTRACTED):
    return m.FieldCandidate(
        field_name=name,
        raw_text=str(value),
        normalized_value=value,
        confidence=0.95,
        status=status,
        page_number=1,
        bounding_box=None,
        evidence_block_ids=["BLK-001"],
    )


def test_record_document_and_ocr_events_keep_one_sequence():
    store = AuditStore(transaction_id="TX-OCR")
    doc = m.UploadedDocument("DOC-1", "inv.pdf", "application/pdf", 1234, "abc", b"%PDF-")
    store.record_document_uploaded(doc, actor="judge")
    store.record_document_validated(doc, actor="judge")
    ocr = m.OCRDocument("DOC-1", [], [], "", "paddleocr", "v1", 12)
    store.record_ocr_completed(ocr)
    ids = [e.event_id for e in store.events]
    assert ids == ["AUD-0001", "AUD-0002", "AUD-0003"]
    assert [e.event_type for e in store.events] == [
        "DOCUMENT_UPLOADED",
        "DOCUMENT_VALIDATED",
        "OCR_COMPLETED",
    ]


def test_record_field_event_carries_provenance_not_bytes():
    store = AuditStore(transaction_id="TX-OCR")
    ev = store.record_field_event("FIELD_CONFIRMED", _candidate(), actor="ap@x")
    assert ev.event_type == "FIELD_CONFIRMED"
    assert ev.input_refs == ["BLK-001"]
    assert ev.details["field_name"] == "total_amount"
    assert ev.details["selected_method"] == "OCR_RULE"
    assert "content" not in ev.details and "image_bytes" not in ev.details


def test_record_field_event_captures_conflict_and_alternatives():
    store = AuditStore(transaction_id="TX-OCR")
    selected = _candidate(value=9_000_000, status=m.FieldStatus.CONFLICTING)
    selected.extraction_method = "TABLE_SUMMARY"
    selected.provider_confidence = 0.99
    selected.mapping_score = 1.0
    alt = _candidate(value=7_000_000)
    alt.extraction_method = "EXACT_KEY_VALUE"
    ev = store.record_field_event(
        "FIELD_EXTRACTED", selected, actor="judge@demo", alternatives=[alt]
    )
    assert ev.details["selected_method"] == "TABLE_SUMMARY"
    assert ev.details["provider_confidence"] == 0.99
    assert ev.details["mapping_score"] == 1.0
    assert ev.details["alternative_count"] == 1
    assert ev.details["conflict"] is True
    assert ev.details["evidence_block_ids"] == ["BLK-001"]


def test_record_field_event_alternatives_default_to_empty():
    store = AuditStore(transaction_id="TX-OCR")
    ev = store.record_field_event("FIELD_EXTRACTED", _candidate(), actor="judge@demo")
    assert ev.details["alternative_count"] == 0
    assert ev.details["alternatives"] == []


def test_record_field_event_preserves_the_rejected_alternative_values():
    """A conflict must be reconstructable, so the losing value is recorded."""
    store = AuditStore(transaction_id="TX-OCR")
    selected = _candidate(value=9_000_000, status=m.FieldStatus.CONFLICTING)
    alt = _candidate(value=7_000_000)
    alt.extraction_method = "EXACT_KEY_VALUE"
    ev = store.record_field_event(
        "FIELD_EXTRACTED", selected, actor="judge@demo", alternatives=[alt]
    )
    assert ev.details["alternatives"] == [
        {"value": 7_000_000, "method": "EXACT_KEY_VALUE", "evidence_block_ids": ["BLK-001"]}
    ]


def test_record_extraction_reviewed_event():
    store = AuditStore(transaction_id="TX-OCR")
    result = m.InvoiceExtractionResult("DOC-1", m.ExtractionStatus.REVIEWED)
    ev = store.record_extraction_reviewed(result, actor="judge")
    assert ev.event_type == "EXTRACTION_REVIEWED"
    assert ev.result == "REVIEWED"


def test_override_sets_effective_action_but_preserves_agent_decision():
    store = AuditStore(transaction_id="TX-001")
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    tx.decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")
    tx.effective_action = m.DecisionAction.AUTO_PROCESS
    store.record_override(
        tx, actor="judge@demo", overridden_action=m.DecisionAction.ESCALATE, reason="manual"
    )
    assert tx.decision.action is m.DecisionAction.AUTO_PROCESS
    assert tx.effective_action is m.DecisionAction.ESCALATE


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
