"""End-to-end integration tests for the production review() service."""

import json

import pytest

from invoice_referee.domain import models as m
from invoice_referee.services.reviewer import review
from invoice_referee.agent.llm_client import LLMClient, LLMError


class FakeClient(LLMClient):
    def __init__(self, body: str):
        self._body = body

    def complete(self, prompt: str) -> str:
        return self._body


class BoomClient(LLMClient):
    def complete(self, prompt: str) -> str:
        raise LLMError("provider down")


def _beyond_authority(routine_evidence):
    ev = routine_evidence()
    for coll in (ev["purchase_order"]["items"][0], ev["invoice"]["items"][0]):
        coll["unit_price"] = 12_000_000
        coll["line_total"] = 120_000_000
    ev["purchase_order"]["approved_total"] = 120_000_000
    ev["invoice"]["total_amount"] = 120_000_000
    return ev


# --- Happy path --------------------------------------------------------------


def test_tc01_auto_process_end_to_end(routine_evidence):
    result = review(routine_evidence())
    assert isinstance(result, m.ReviewResult)
    assert result.decision.action is m.DecisionAction.AUTO_PROCESS
    assert result.policy_context.scope_status is m.ScopeStatus.IN_SCOPE
    assert len(result.checks) == 8
    assert all(c.status is m.CheckStatus.PASS for c in result.checks)


def test_review_result_bundles_all_outputs(routine_evidence):
    result = review(routine_evidence())
    assert result.transaction.transaction_id
    assert result.agent_assessment is not None
    assert result.audit_events
    types = [e.event_type for e in result.audit_events]
    assert "TRANSACTION_CREATED" in types
    assert "CHECK_COMPLETED" in types
    assert "LLM_ASSESSMENT_CREATED" in types
    assert "DECISION_GUARD_APPLIED" in types
    assert "DECISION_MADE" in types


# --- Non-routine integration -------------------------------------------------


def test_tc09_amount_mismatch_request_info(routine_evidence):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    result = review(ev)
    assert result.decision.action is m.DecisionAction.REQUEST_INFO
    assert result.decision.question


def test_tc13_beyond_authority_escalate(routine_evidence):
    result = review(_beyond_authority(routine_evidence))
    assert result.decision.action is m.DecisionAction.ESCALATE
    assert result.decision.target == "Finance Manager"
    assert "P12" in result.decision.policy_rule_ids


def test_tc14_outside_policy_escalate(routine_evidence):
    ev = routine_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    result = review(ev)
    assert result.decision.action is m.DecisionAction.ESCALATE
    assert result.policy_context.scope_status is m.ScopeStatus.OUTSIDE_POLICY


# --- Fail-closed linkage/status safety (Task 3) ------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e["invoice"].update({"po_id": "PO-WRONG"}),
        lambda e: e["goods_receipts"][0].update({"po_id": "PO-WRONG"}),
        lambda e: e["purchase_order"].update({"status": "DRAFT"}),
        lambda e: e["goods_receipts"][0].update({"status": "PENDING"}),
    ],
)
def test_invalid_link_or_status_never_auto_processes(routine_evidence, mutate):
    evidence = routine_evidence()
    mutate(evidence)
    result = review(evidence)
    assert result.decision.action is m.DecisionAction.REQUEST_INFO
    assert result.transaction.evidence_issues


# --- LLM path variations -----------------------------------------------------


def test_normal_llm_execution_uses_valid_assessment(routine_evidence):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    body = json.dumps(
        {
            "proposed_uncertainty_type": "FACTUAL_UNKNOWN",
            "proposed_action": "REQUEST_INFO",
            "primary_check_id": "CHECK_AMOUNT",
            "explanation": "Invoice exceeds approved amount.",
            "question": "PO 30M nhưng invoice 35M. Có phê duyệt tăng 5M không?",
            "target": "Purchasing",
            "policy_rule_ids": ["P07"],
            "evidence_refs": ["PO-001", "INV-001"],
        }
    )
    result = review(ev, client=FakeClient(body))
    assert result.agent_assessment.fallback_used is False
    assert result.decision.action is m.DecisionAction.REQUEST_INFO
    assert result.decision.question == "PO 30M nhưng invoice 35M. Có phê duyệt tăng 5M không?"


def test_provider_failure_falls_back_but_decision_is_policy_correct(routine_evidence):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    result = review(ev, client=BoomClient())
    assert result.agent_assessment.fallback_used is True
    assert result.decision.action is m.DecisionAction.REQUEST_INFO
    assert any(e.event_type == "LLM_FALLBACK_USED" for e in result.audit_events)


def test_invalid_structured_output_falls_back(routine_evidence):
    result = review(routine_evidence(), client=FakeClient("garbage not json"))
    assert result.agent_assessment.fallback_used is True
    # routine facts still auto-process
    assert result.decision.action is m.DecisionAction.AUTO_PROCESS


def test_unsafe_llm_auto_process_is_overridden_by_guard(routine_evidence):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000  # must be REQUEST_INFO
    body = json.dumps(
        {
            "proposed_uncertainty_type": None,
            "proposed_action": "AUTO_PROCESS",
            "primary_check_id": None,
            "explanation": "looks fine to me",
            "question": "",
            "policy_rule_ids": [],
            "evidence_refs": [],
        }
    )
    result = review(ev, client=FakeClient(body))
    assert result.decision.action is m.DecisionAction.REQUEST_INFO
    guard_events = [e for e in result.audit_events if e.event_type == "DECISION_GUARD_APPLIED"]
    assert guard_events and guard_events[-1].details["proposal_overridden"] is True


# --- Unseen input (mutation, no code change) ---------------------------------


def test_unseen_within_authority_auto_process(routine_evidence):
    ev = routine_evidence()
    ev["purchase_order"]["vendor_id"] = "V-NEW"
    ev["invoice"]["vendor_id"] = "V-NEW"
    ev["purchase_order"]["approved_total"] = 42_000_000
    ev["purchase_order"]["items"][0]["ordered_quantity"] = 14
    ev["purchase_order"]["items"][0]["line_total"] = 42_000_000
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 14
    ev["invoice"]["total_amount"] = 42_000_000
    ev["invoice"]["items"][0]["invoiced_quantity"] = 14
    ev["invoice"]["items"][0]["line_total"] = 42_000_000
    result = review(ev)
    assert result.decision.action is m.DecisionAction.AUTO_PROCESS


def test_unseen_beyond_authority_escalate(routine_evidence):
    ev = routine_evidence()
    for coll in (ev["purchase_order"]["items"][0], ev["invoice"]["items"][0]):
        coll["ordered_quantity"] = 25
        coll["invoiced_quantity"] = 25
        coll["unit_price"] = 3_000_000
        coll["line_total"] = 75_000_000
    ev["purchase_order"]["approved_total"] = 75_000_000
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 25
    ev["invoice"]["total_amount"] = 75_000_000
    result = review(ev)
    assert result.decision.action is m.DecisionAction.ESCALATE
    assert result.decision.uncertainty.type is m.UncertaintyType.BEYOND_AUTHORITY


def test_review_sets_effective_action_to_decision(routine_evidence):
    result = review(routine_evidence())
    assert result.transaction.effective_action is result.decision.action


def test_review_continues_existing_audit_sequence(routine_evidence):
    from invoice_referee.audit.store import AuditStore

    audit = AuditStore(transaction_id="TX-01")
    audit.append("DOCUMENT_UPLOADED")
    result = review(routine_evidence(), audit=audit)
    ids = [e.event_id for e in result.audit_events]
    assert ids == [f"AUD-{n:04d}" for n in range(1, len(ids) + 1)]
    assert len(ids) == len(set(ids))
    assert result.audit_events[0].event_type == "DOCUMENT_UPLOADED"


def test_review_rejects_mismatched_audit_transaction(routine_evidence):
    from invoice_referee.audit.store import AuditStore

    audit = AuditStore(transaction_id="TX-OTHER")
    with pytest.raises(ValueError):
        review(routine_evidence(), audit=audit)


def test_reviewer_source_has_no_case_id_branching():
    import inspect
    from invoice_referee.services import reviewer

    src = inspect.getsource(reviewer)
    for token in ("TC01", "TC07", "TC13", "TC14", "EV01", "EV05"):
        assert token not in src
