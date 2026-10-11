"""B9 revalidation: a correct fulfillment keeps the original decision valid.

Integration trace over the REAL pipeline (fake reader): approved3 → actual2 →
context refresh/rerun S1 → revalidation VALID remaining1 → actual1 → refresh/
rerun S0 → revalidation VALID, same original decision. No LIVE, no .env.
"""
from __future__ import annotations

import pytest

from tests.settlement.test_b3_workflow import (  # noqa: F401 — fixture chain
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_workflow import ready_linked_b7  # noqa: F401
from tests.settlement.test_b7_fulfillment import (  # noqa: F401
    approved_linked_b7, _money_text, money_payload, upload_money_proof, _record,
)


def _refresh_and_rerun(svc, child_id, key):
    child = svc.get_case(child_id)
    svc.refresh_b7_money_context(child_id,
        command(f"ctx-{key}", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child_id)
    run = svc.start(child_id,
        command(f"run-{key}", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    return svc.report(run.id)


def _revalidate(svc, child_id, key):
    child = svc.get_case(child_id)
    return svc.revalidate_b7(child_id,
        command(f"reval-{key}", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))


def test_correct_receipts_keep_original_decision_valid(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    _record(svc, child, proof, money_payload(proof.id, decision.id, event_ref="TX-1"))
    # Whole-work report now shows P=2 → S=1.
    new_report = _refresh_and_rerun(svc, child.id, "1")
    assert new_report.components.p.value == 2_000_000
    assert new_report.calculated_net_vnd == 1_000_000
    reval = _revalidate(svc, child.id, "1")
    assert reval.status == "VALID", reval.blocked_reasons
    assert reval.original_decision_id == decision.id
    view = svc.get_case(child.id)
    # The original decision is unchanged; remaining is 1, not a new approval.
    assert view.b7_workflow.decision.target.amount_vnd == 3_000_000
    assert view.b7_workflow.fulfillment.remaining_vnd == 1_000_000
    assert view.b7_workflow.fulfillment.recorded_received_vnd == 2_000_000


def test_second_receipt_reaches_zero_keeps_same_decision(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    for amount, ref in ((2_000_000, "TX-1"), (1_000_000, "TX-2")):
        proof = upload_money_proof(svc, child, _money_text(
            amount=amount, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
            payer="COMPANY", event_ref=ref, method="BANK_TRANSFER",
            event_at="2026-10-14T08:00:00+07:00"), key=f"pf-{ref}")
        _record(svc, child, proof,
                money_payload(proof.id, decision.id, amount=amount, event_ref=ref),
                key=f"ev-{ref}")
    new_report = _refresh_and_rerun(svc, child.id, "2")
    assert new_report.calculated_net_vnd == 0
    reval = _revalidate(svc, child.id, "2")
    assert reval.status == "VALID", reval.blocked_reasons
    view = svc.get_case(child.id)
    assert view.b7_workflow.decision.id == decision.id
    assert view.b7_workflow.fulfillment.remaining_vnd == 0
    assert view.b7_workflow.fulfillment.status == "FULFILLED"
    assert view.stage == "READY_TO_CLOSE"


def test_extra_advance_delta_needs_recheck(approved_linked_b7):
    """A change to A (advance) outside fulfillment is material → NEEDS_RECHECK."""
    from tests.settlement.test_b7_linked_context import _event, _packet
    svc, child, report, decision = approved_linked_b7
    # A new company packet adds a second advance (A=4) not matched by receipts.
    child = svc.get_case(child.id)
    new_event = _event(namespace="BANK:DEMO-ACCOUNT", ref="TX-ADV-02",
                       amount=2_000_000)
    new_event["employee_ref"] = "NV-DEMO-01"
    packet = _packet(events=[new_event])
    packet["coverage"]["employee_ref"] = "NV-DEMO-01"
    packet["coverage"]["to"] = "2026-10-14T09:00:00+07:00"
    svc.record_b7_company_packet(child.id, packet,
        command("pkt2", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    run = svc.start(child.id,
        command("run-x", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    reval = _revalidate(svc, child.id, "x")
    assert reval.status == "NEEDS_RECHECK"
    assert reval.blocked_reasons
