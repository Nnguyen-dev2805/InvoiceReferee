"""Tests for Policy Engine (PolicyContext + deterministic resolution) and Decision Guard."""

import pytest

from invoice_referee.domain import models as m
from invoice_referee.policy import engine as policy_engine
from invoice_referee.policy import config as policy_config
from invoice_referee.decision.guard import guard


# --- PolicyContext: tri-state scope ------------------------------------------


def test_scope_in_scope_for_po_goods(routine_evidence, build_inputs):
    tx, checks = build_inputs(routine_evidence())
    ctx = policy_engine.build_policy_context(tx, checks)
    assert ctx.scope_status is m.ScopeStatus.IN_SCOPE
    assert ctx.authority_threshold_vnd == policy_config.AUTHORITY_THRESHOLD_VND


def test_scope_outside_policy_for_known_unsupported_type(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    assert ctx.scope_status is m.ScopeStatus.OUTSIDE_POLICY


def test_scope_unknown_when_type_undeterminable(routine_evidence, build_inputs):
    ev = routine_evidence()
    del ev["transaction_type"]
    del ev["purchase_order"]
    ev["invoice"]["po_id"] = None
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    assert ctx.scope_status is m.ScopeStatus.UNKNOWN


# --- Deterministic resolution (policy-correct action) ------------------------


def _resolve(build_inputs, evidence):
    tx, checks = build_inputs(evidence)
    ctx = policy_engine.build_policy_context(tx, checks)
    return policy_engine.resolve_action(tx, checks, ctx), tx, checks, ctx


def test_routine_resolves_auto_process(routine_evidence, build_inputs):
    outcome, *_ = _resolve(build_inputs, routine_evidence())
    assert outcome.action is m.DecisionAction.AUTO_PROCESS
    assert outcome.uncertainty_type is None


def test_unknown_type_resolves_request_info(routine_evidence, build_inputs):
    ev = routine_evidence()
    del ev["transaction_type"]
    del ev["purchase_order"]
    ev["invoice"]["po_id"] = None
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert outcome.uncertainty_type is m.UncertaintyType.FACTUAL_UNKNOWN


def test_outside_policy_resolves_escalate(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.ESCALATE
    assert outcome.uncertainty_type is m.UncertaintyType.OUTSIDE_POLICY
    assert outcome.target == policy_config.TARGET_ACCOUNTING_OWNER
    assert "P13" in outcome.policy_rule_ids


def test_missing_po_resolves_request_info_p01(routine_evidence, build_inputs):
    ev = routine_evidence()
    del ev["purchase_order"]
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert "P01" in outcome.policy_rule_ids


def test_missing_goods_receipt_resolves_request_info_p04(routine_evidence, build_inputs):
    ev = routine_evidence()
    del ev["goods_receipts"]
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert "P04" in outcome.policy_rule_ids


def test_flagged_input_resolves_request_info_p15(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = "45M hoặc 48M"
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert outcome.uncertainty_type is m.UncertaintyType.FACTUAL_UNKNOWN


def test_amount_mismatch_resolves_request_info_not_violation(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert outcome.primary_check_id == "CHECK_AMOUNT"


def test_evidence_issue_resolves_request_info_before_authority(routine_evidence, build_inputs):
    # A beyond-authority amount AND a wrong PO link: the structural issue wins
    # and routes to REQUEST_INFO (never AUTO_PROCESS, never straight ESCALATE).
    ev = routine_evidence()
    ev["purchase_order"]["approved_total"] = 120_000_000
    ev["purchase_order"]["items"][0]["unit_price"] = 12_000_000
    ev["purchase_order"]["items"][0]["line_total"] = 120_000_000
    ev["invoice"]["total_amount"] = 120_000_000
    ev["invoice"]["items"][0]["unit_price"] = 12_000_000
    ev["invoice"]["items"][0]["line_total"] = 120_000_000
    ev["goods_receipts"][0]["status"] = "PENDING"
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.REQUEST_INFO
    assert outcome.policy_rule_ids == ["P14"]


def test_beyond_authority_resolves_escalate(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["purchase_order"]["approved_total"] = 120_000_000
    ev["purchase_order"]["items"][0]["unit_price"] = 12_000_000
    ev["purchase_order"]["items"][0]["line_total"] = 120_000_000
    ev["invoice"]["total_amount"] = 120_000_000
    ev["invoice"]["items"][0]["unit_price"] = 12_000_000
    ev["invoice"]["items"][0]["line_total"] = 120_000_000
    outcome, *_ = _resolve(build_inputs, ev)
    assert outcome.action is m.DecisionAction.ESCALATE
    assert outcome.uncertainty_type is m.UncertaintyType.BEYOND_AUTHORITY
    assert outcome.target == policy_config.TARGET_FINANCE_MANAGER
    assert "P12" in outcome.policy_rule_ids


# --- Fallback question formatting --------------------------------------------


def test_fallback_question_formats_money_for_humans(routine_evidence, build_inputs):
    from invoice_referee.decision import fallback_questions

    ev = routine_evidence()
    ev["purchase_order"]["approved_total"] = 120_000_000
    ev["purchase_order"]["items"][0]["unit_price"] = 12_000_000
    ev["purchase_order"]["items"][0]["line_total"] = 120_000_000
    ev["invoice"]["total_amount"] = 120_000_000
    ev["invoice"]["items"][0]["unit_price"] = 12_000_000
    ev["invoice"]["items"][0]["line_total"] = 120_000_000
    outcome, tx, checks, _ctx = _resolve(build_inputs, ev)
    q = fallback_questions.build_question(outcome, tx, checks)
    # Money must be human-formatted (dot thousands + ₫), never a raw integer.
    assert "120.000.000 ₫" in q
    assert "50.000.000 ₫" in q
    assert "120000000" not in q


# --- Decision Guard: accepts matching, overrides unsafe proposals ------------


def _assessment(action, uncertainty=None, primary=None, question="Q?", target=None, refs=None, rules=None):
    return m.AgentAssessment(
        proposed_uncertainty_type=uncertainty,
        proposed_action=action,
        explanation="LLM explanation",
        primary_check_id=primary,
        question=question,
        target=target,
        policy_rule_ids=rules or [],
        evidence_refs=refs or [],
    )


def test_guard_accepts_matching_auto_process(routine_evidence, build_inputs):
    tx, checks = build_inputs(routine_evidence())
    ctx = policy_engine.build_policy_context(tx, checks)
    a = _assessment(m.DecisionAction.AUTO_PROCESS)
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.AUTO_PROCESS
    assert decision.question is None
    assert decision.target is None


def test_guard_overrides_unsafe_auto_process_on_factual_unknown(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000  # amount mismatch -> REQUEST_INFO
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    a = _assessment(m.DecisionAction.AUTO_PROCESS)  # unsafe proposal
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.REQUEST_INFO
    assert decision.question  # must carry a concrete question


def test_guard_overrides_unsafe_auto_process_beyond_authority(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["purchase_order"]["approved_total"] = 120_000_000
    ev["purchase_order"]["items"][0]["unit_price"] = 12_000_000
    ev["purchase_order"]["items"][0]["line_total"] = 120_000_000
    ev["invoice"]["total_amount"] = 120_000_000
    ev["invoice"]["items"][0]["unit_price"] = 12_000_000
    ev["invoice"]["items"][0]["line_total"] = 120_000_000
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    a = _assessment(m.DecisionAction.AUTO_PROCESS)
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.ESCALATE
    assert decision.target == policy_config.TARGET_FINANCE_MANAGER


def test_guard_overrides_auto_process_for_flagged_input(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = "45M hoặc 48M"
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    a = _assessment(m.DecisionAction.AUTO_PROCESS)
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.REQUEST_INFO


def test_guard_request_info_always_has_question(routine_evidence, build_inputs):
    ev = routine_evidence()
    del ev["goods_receipts"]
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    # LLM proposes a valid REQUEST_INFO but with an empty question -> guard must still fill one.
    a = _assessment(m.DecisionAction.REQUEST_INFO, uncertainty=m.UncertaintyType.FACTUAL_UNKNOWN, question="")
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.REQUEST_INFO
    assert decision.question


def test_guard_escalate_has_target(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["transaction_type"] = "SERVICE_INVOICE"
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    a = _assessment(m.DecisionAction.ESCALATE, uncertainty=m.UncertaintyType.OUTSIDE_POLICY)
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.ESCALATE
    assert decision.target == policy_config.TARGET_ACCOUNTING_OWNER


def test_guard_uses_valid_llm_question_when_matching(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    tx, checks = build_inputs(ev)
    ctx = policy_engine.build_policy_context(tx, checks)
    llm_q = "PO 30M nhưng invoice 35M. Có phê duyệt tăng thêm 5M không?"
    a = _assessment(
        m.DecisionAction.REQUEST_INFO,
        uncertainty=m.UncertaintyType.FACTUAL_UNKNOWN,
        primary="CHECK_AMOUNT",
        question=llm_q,
        refs=["PO-001", "INV-001"],
        rules=["P07"],
    )
    decision = guard(a, tx, checks, ctx)
    assert decision.action is m.DecisionAction.REQUEST_INFO
    assert decision.question == llm_q


def test_guard_records_decision_timestamp(routine_evidence, build_inputs):
    tx, checks = build_inputs(routine_evidence())
    ctx = policy_engine.build_policy_context(tx, checks)
    decision = guard(_assessment(m.DecisionAction.AUTO_PROCESS), tx, checks, ctx)
    assert decision.decided_at is not None
