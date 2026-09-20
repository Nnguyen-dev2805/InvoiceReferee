"""Verify harness tests: fixtures + suites run through production review()."""

import json

import pytest

from invoice_referee.domain import models as m
from invoice_referee.agent.llm_client import LLMClient
from verify import harness


ALL_CASES = [f"TC{n:02d}" for n in range(1, 18)]


def test_all_17_fixtures_exist():
    for cid in ALL_CASES:
        assert harness.fixture_path(cid).exists(), f"missing fixture {cid}"


@pytest.mark.parametrize("case_id", ALL_CASES)
def test_each_fixture_matches_expected(case_id):
    results = harness.run_verify([case_id])
    assert len(results) == 1
    r = results[0]
    assert r.actual == r.expected, f"{case_id}: expected {r.expected}, got {r.actual}"
    assert r.passed is True


def test_core_suite_all_pass():
    results = harness.run_suite("core")
    assert [r.case_id for r in results] == ["TC01", "TC07", "TC13", "TC14"]
    assert all(r.passed for r in results)


def test_escalation_suite_three_routine_two_human():
    results = harness.run_suite("escalation")
    actions = [r.actual for r in results]
    assert actions.count("AUTO_PROCESS") == 3
    assert actions.count("AUTO_PROCESS") + sum(a in ("REQUEST_INFO", "ESCALATE") for a in actions) == 5
    assert all(r.passed for r in results)


def test_escalation_human_cases_have_specific_question_and_target():
    results = {r.case_id: r for r in harness.run_suite("escalation")}
    req = results["TC07"]
    assert req.actual == "REQUEST_INFO"
    assert req.question and "Please review" not in req.question
    esc = results["TC13"]
    assert esc.actual == "ESCALATE"
    assert esc.target == "Finance Manager"
    assert esc.uncertainty_type == "BEYOND_AUTHORITY"


def test_suite_all_exposes_both_suites():
    combined = harness.run_suite("all")
    case_ids = {r.case_id for r in combined}
    suites = {r.suite for r in combined}
    assert {"core", "escalation"}.issubset(suites)
    assert {"TC01", "TC07", "TC13", "TC14", "TC02", "TC03"}.issubset(case_ids)
    assert all(r.passed for r in combined)


def test_results_carry_timestamp_and_fallback_status():
    r = harness.run_verify(["TC01"])[0]
    assert r.timestamp
    assert isinstance(r.fallback_used, bool)


def test_unseen_mutation_without_code_change():
    # Change amounts on a routine fixture at runtime; still auto-processes.
    ev = harness.load_case("TC01")
    ev["purchase_order"]["approved_total"] = 42_000_000
    ev["purchase_order"]["items"][0]["unit_price"] = 3_000_000
    ev["purchase_order"]["items"][0]["ordered_quantity"] = 14
    ev["purchase_order"]["items"][0]["line_total"] = 42_000_000
    ev["goods_receipts"][0]["items"][0]["received_quantity"] = 14
    ev["invoice"]["items"][0]["invoiced_quantity"] = 14
    ev["invoice"]["items"][0]["unit_price"] = 3_000_000
    ev["invoice"]["items"][0]["line_total"] = 42_000_000
    ev["invoice"]["total_amount"] = 42_000_000
    r = harness.verify_evidence("UNSEEN-1", ev, expected="AUTO_PROCESS")
    assert r.actual == "AUTO_PROCESS"
    assert r.passed


class UnsafeClient(LLMClient):
    """Always proposes AUTO_PROCESS regardless of facts."""

    def complete(self, prompt: str) -> str:
        return json.dumps(
            {
                "proposed_uncertainty_type": None,
                "proposed_action": "AUTO_PROCESS",
                "primary_check_id": None,
                "explanation": "looks fine",
                "question": "",
                "policy_rule_ids": [],
                "evidence_refs": [],
            }
        )


def test_unsafe_llm_proposal_does_not_pass_a_human_case():
    # TC13 must ESCALATE even if the LLM says AUTO_PROCESS.
    r = harness.run_verify(["TC13"], client=UnsafeClient())[0]
    assert r.actual == "ESCALATE"
    assert r.passed
