"""Tests for the LLM Agent boundary and structured-output handling."""

import json

import pytest

from invoice_referee.domain import models as m
from invoice_referee.policy import engine as policy_engine
from invoice_referee.agent import service as agent_service
from invoice_referee.agent.llm_client import LLMClient, LLMError, LLMTimeout


class FakeClient(LLMClient):
    """Returns a canned response body regardless of prompt."""

    def __init__(self, body: str):
        self._body = body

    def complete(self, prompt: str) -> str:
        return self._body


class ErrorClient(LLMClient):
    def __init__(self, exc: Exception):
        self._exc = exc

    def complete(self, prompt: str) -> str:
        raise self._exc


def _amount_mismatch(routine_evidence):
    ev = routine_evidence()
    ev["invoice"]["total_amount"] = 35_000_000
    return ev


def _inputs(build_inputs, evidence):
    tx, checks = build_inputs(evidence)
    ctx = policy_engine.build_policy_context(tx, checks)
    return tx, checks, ctx


def test_valid_structured_output_is_parsed(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    body = json.dumps(
        {
            "proposed_uncertainty_type": "FACTUAL_UNKNOWN",
            "proposed_action": "REQUEST_INFO",
            "primary_check_id": "CHECK_AMOUNT",
            "explanation": "Invoice amount exceeds approved PO amount.",
            "question": "PO 30M nhưng invoice 35M. Có phê duyệt tăng 5M không?",
            "target": "Purchasing",
            "policy_rule_ids": ["P07"],
            "evidence_refs": ["PO-001", "INV-001"],
        }
    )
    a = agent_service.assess(tx, checks, ctx, client=FakeClient(body))
    assert a.fallback_used is False
    assert a.proposed_action is m.DecisionAction.REQUEST_INFO
    assert a.primary_check_id == "CHECK_AMOUNT"
    assert a.policy_rule_ids == ["P07"]


def test_provider_error_uses_audited_fallback(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    a = agent_service.assess(tx, checks, ctx, client=ErrorClient(LLMError("boom")))
    assert a.fallback_used is True
    # fallback still proposes the policy-correct action with a concrete question
    assert a.proposed_action is m.DecisionAction.REQUEST_INFO
    assert a.question


def test_provider_timeout_uses_fallback(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    a = agent_service.assess(tx, checks, ctx, client=ErrorClient(LLMTimeout("slow")))
    assert a.fallback_used is True


def test_invalid_json_uses_fallback(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    a = agent_service.assess(tx, checks, ctx, client=FakeClient("not json at all"))
    assert a.fallback_used is True


def test_invented_primary_check_is_invalid_and_falls_back(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    body = json.dumps(
        {
            "proposed_uncertainty_type": "FACTUAL_UNKNOWN",
            "proposed_action": "REQUEST_INFO",
            "primary_check_id": "CHECK_DOES_NOT_EXIST",
            "explanation": "made up",
            "question": "?",
            "policy_rule_ids": ["P07"],
            "evidence_refs": ["PO-001"],
        }
    )
    a = agent_service.assess(tx, checks, ctx, client=FakeClient(body))
    assert a.fallback_used is True


def test_invented_evidence_ref_is_invalid_and_falls_back(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    body = json.dumps(
        {
            "proposed_uncertainty_type": "FACTUAL_UNKNOWN",
            "proposed_action": "REQUEST_INFO",
            "primary_check_id": "CHECK_AMOUNT",
            "explanation": "x",
            "question": "?",
            "policy_rule_ids": ["P07"],
            "evidence_refs": ["GHOST-999"],
        }
    )
    a = agent_service.assess(tx, checks, ctx, client=FakeClient(body))
    assert a.fallback_used is True


def test_no_client_uses_fallback(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, _amount_mismatch(routine_evidence))
    a = agent_service.assess(tx, checks, ctx, client=None)
    assert a.fallback_used is True
    assert a.proposed_action is m.DecisionAction.REQUEST_INFO


def test_fallback_records_prompt_version(routine_evidence, build_inputs):
    tx, checks, ctx = _inputs(build_inputs, routine_evidence())
    a = agent_service.assess(tx, checks, ctx, client=None, prompt_version="v1")
    assert a.prompt_version == "v1"


def test_multi_issue_fallback_picks_a_real_unresolved_check(routine_evidence, build_inputs):
    ev = routine_evidence()
    ev["invoice"]["items"][0]["unit_price"] = 3_500_000  # price mismatch
    ev["invoice"]["total_amount"] = 35_000_000  # amount mismatch
    tx, checks, ctx = _inputs(build_inputs, ev)
    a = agent_service.assess(tx, checks, ctx, client=None)
    unresolved = {c.check_id for c in checks if c.status in (m.CheckStatus.FAIL, m.CheckStatus.UNKNOWN)}
    assert a.primary_check_id in unresolved
