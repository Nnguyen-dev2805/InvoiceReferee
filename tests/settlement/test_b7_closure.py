"""B9 closure & handoff: only a fully-fulfilled, revalidated settlement closes.

Integration over the REAL pipeline (fake reader). No LIVE, no .env, no mocked
COMPLETE report. Asserts on persisted records/stage, not only status.
"""
from __future__ import annotations

import pytest

from invoice_referee.shared.errors import DomainError
from tests.settlement.test_b3_workflow import (  # noqa: F401 — fixture chain
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_workflow import ready_linked_b7  # noqa: F401
from tests.settlement.test_b7_fulfillment import (  # noqa: F401
    approved_linked_b7, _money_text, money_payload, upload_money_proof, _record,
)
from tests.settlement.b7_workflow_builders import report_from_values


def test_zero_net_alone_cannot_close():
    from invoice_referee.settlement.settlement_reconciliation import b7_closure_blockers
    report = report_from_values(2_000_000, 2_000_000)
    blockers = b7_closure_blockers(
        report=report, decision=None, fulfillment=None, revalidation=None,
        scope_current=True, coverage_current=True, stop_active=False,
        open_question_count=0)
    assert blockers
    assert any("quyết định" in reason.lower() for reason in blockers)


def _receipt(svc, child, decision, amount, ref, key, purpose="REIMBURSEMENT_RECEIVED",
             payee="NV-DEMO-01", payer="COMPANY"):
    proof = upload_money_proof(svc, child, _money_text(
        amount=amount, purpose=purpose, payee=payee, payer=payer, event_ref=ref,
        method="BANK_TRANSFER", event_at="2026-10-14T08:00:00+07:00"), key=f"pf-{key}")
    return _record(svc, child, proof, money_payload(
        proof.id, decision.id, amount=amount, purpose=purpose, payee=payee,
        payer=payer, event_ref=ref), key=f"ev-{key}")


def _refresh_rerun_revalidate(svc, child_id, key):
    child = svc.get_case(child_id)
    svc.refresh_b7_money_context(child_id,
        command(f"ctx-{key}", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child_id)
    run = svc.start(child_id,
        command(f"run-{key}", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    child = svc.get_case(child_id)
    svc.revalidate_b7(child_id,
        command(f"reval-{key}", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    return svc.report(run.id)


def _close(svc, child_id, report_id, key, decision_id):
    child = svc.get_case(child_id)
    return svc.close_b7(child_id, {
        "decision_id": decision_id, "current_report_id": report_id,
        "reason": "Đủ căn cứ, hết nghĩa vụ"},
        command(f"close-{key}", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))


def test_two_receipts_then_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    assert final.calculated_net_vnd == 0
    closure = _close(svc, child.id, final.run_id, "1", decision.id)
    assert closure.kind == "SETTLEMENT_COMPLETE"
    assert closure.original_decision_id == decision.id
    view = svc.get_case(child.id)
    assert view.stage == "SETTLEMENT_CLOSED"
    assert view.b7_workflow.closure.id == closure.id
    assert svc.closed(child.id) is True


def test_collection_close(approved_b3, monkeypatch):
    """E1.3/A2 → collect 0.7; company receives RA0.7 → S0 → close."""
    svc, parent, decision = approved_b3
    from tests.settlement.b7_workflow_builders import make_ready_linked
    child, report = make_ready_linked(svc, parent, monkeypatch,
                                      employee_cost_vnd=1_300_000)
    assert report.calculated_net_vnd == -700_000
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("cp", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE", "reason": "Duyệt"},
        command("cd", "APR-DEMO-01", "APPROVER", child.case_version))
    assert decision.target.direction == "COLLECT_FROM_EMPLOYEE"
    assert decision.target.amount_vnd == 700_000
    _receipt(svc, child, decision, 700_000, "TX-C1", "c1",
             purpose="ADVANCE_RETURN", payee="COMPANY-INVREF", payer="NV-DEMO-01")
    final = _refresh_rerun_revalidate(svc, child.id, "c1")
    assert final.calculated_net_vnd == 0
    closure = _close(svc, child.id, final.run_id, "c1", decision.id)
    assert svc.get_case(child.id).stage == "SETTLEMENT_CLOSED"


def test_balanced_closes_without_money_events(approved_b3, monkeypatch):
    from tests.settlement.b7_workflow_builders import make_ready_linked
    svc, parent, decision = approved_b3
    child, report = make_ready_linked(svc, parent, monkeypatch,
                                      employee_cost_vnd=2_000_000)
    assert report.calculated_net_vnd == 0
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("bp", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE", "reason": "Duyệt"},
        command("bd", "APR-DEMO-01", "APPROVER", child.case_version))
    assert decision.target.direction == "BALANCED"
    assert svc.get_case(child.id).stage == "READY_TO_CLOSE"
    # No money event is created by a BALANCED approval.
    assert svc.get_case(child.id).b7_workflow.fulfillment.recorded_received_vnd is None
    child = svc.get_case(child.id)
    svc.revalidate_b7(child.id,
        command("br", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    closure = _close(svc, child.id, report.run_id, "b", decision.id)
    assert svc.get_case(child.id).stage == "SETTLEMENT_CLOSED"
    # BALANCED closure did not create a zero money event.
    assert svc.get_case(child.id).b7_workflow.fulfillment.recorded_received_vnd is None


def test_partial_receipt_cannot_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    with pytest.raises(DomainError) as exc:
        _close(svc, child.id, final.run_id, "1", decision.id)
    assert exc.value.code == "B7_CLOSURE_BLOCKED"
    assert not svc.closed(child.id)


def test_refuse_with_obligation_cannot_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("rp", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "REFUSE", "reason": "Không"},
        command("rd", "APR-DEMO-01", "APPROVER", child.case_version))
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.close_b7(child.id, {
            "decision_id": decision.id, "current_report_id": report.run_id,
            "reason": "x"},
            command("cl", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code in ("B7_CLOSURE_BLOCKED", "B7_WORKFLOW_BLOCKED")
    assert not svc.closed(child.id)


def test_pending_blocks_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 3_000_000, "TX-1", "1")
    # A pending event on top keeps remaining unknown.
    proof = upload_money_proof(svc, child, _money_text(
        amount=1_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-P", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00", outcome="PENDING"), key="pf-p")
    _record(svc, child, proof, money_payload(
        proof.id, decision.id, amount=1_000_000, event_ref="TX-P", status="PENDING"),
        key="ev-p")
    final = _refresh_rerun_revalidate(svc, child.id, "p")
    with pytest.raises(DomainError) as exc:
        _close(svc, child.id, final.run_id, "p", decision.id)
    assert exc.value.code == "B7_CLOSURE_BLOCKED"
    assert not svc.closed(child.id)


def test_parent_stop_blocks_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    parent_id = child.linked_b7.origin.origin_case_id
    svc.control(parent_id, "STOP",
        command("stop", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(parent_id).case_version))
    with pytest.raises(DomainError) as exc:
        _close(svc, child.id, final.run_id, "1", decision.id)
    assert exc.value.code == "B7_CLOSURE_BLOCKED"
    assert not svc.closed(child.id)


def test_wrong_actor_cannot_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.close_b7(child.id, {
            "decision_id": decision.id, "current_report_id": final.run_id,
            "reason": "x"},
            command("bad", "NV-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_close_same_key_replays(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    first = _close(svc, child.id, final.run_id, "same", decision.id)
    replay = _close(svc, child.id, final.run_id, "same", decision.id)
    assert replay.id == first.id


def test_closed_case_rejects_new_money_event(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    _close(svc, child.id, final.run_id, "1", decision.id)
    child = svc.get_case(child.id)
    # A closed child rejects new proof/money; the fix is an adjustment child.
    with pytest.raises(DomainError) as exc:
        upload_money_proof(svc, child, _money_text(
            amount=100_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
            payer="COMPANY", event_ref="TX-Z", method="BANK_TRANSFER",
            event_at="2026-10-14T08:00:00+07:00"), key="pf-z")
    assert exc.value.code in ("CASE_CLOSED", "B7_CLOSED_ADJUSTMENT_REQUIRED")


# --- handoff -----------------------------------------------------------------

def test_handoff_for_remaining_then_receipt_reduces(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    child = svc.get_case(child.id)
    handoff = svc.handoff_b7(child.id, {
        "decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
        command("ho1", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert handoff.remaining_vnd == 1_000_000
    assert handoff.direction == "PAY_EMPLOYEE"
    # A further receipt reduces the remaining; the old handoff stays history.
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.remaining_vnd == 0
    assert view.b7_workflow.current_handoff.remaining_vnd == 1_000_000  # history kept


def test_handoff_balanced_blocked(approved_b3, monkeypatch):
    from tests.settlement.b7_workflow_builders import make_ready_linked
    svc, parent, decision = approved_b3
    child, report = make_ready_linked(svc, parent, monkeypatch,
                                      employee_cost_vnd=2_000_000)
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ", "refs": []}},
        command("bp", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE", "reason": "Duyệt"},
        command("bd", "APR-DEMO-01", "APPROVER", child.case_version))
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.handoff_b7(child.id, {"decision_id": decision.id, "reason": "x"},
            command("ho", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "B7_WORKFLOW_BLOCKED"


def test_handoff_same_key_replays(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    child = svc.get_case(child.id)
    body = {"decision_id": decision.id, "reason": "Bàn giao"}
    first = svc.handoff_b7(child.id, body,
        command("same", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    replay = svc.handoff_b7(child.id, body,
        command("same", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert replay.id == first.id
    assert replay.idempotent_replay is True


def test_handoff_blocks_material_source_added_after_approval(approved_linked_b7):
    from invoice_referee.settlement.models import Upload
    svc, child, report, decision = approved_linked_b7
    expense_id = report.expense_rows[0].expense_id
    svc.add_source(child.id, Upload(filename="changed-cost.txt",
        content=f"fact CHANGED expense.{expense_id}.amount 6000000\n".encode()),
        command("changed", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))
    view = svc.get_case(child.id)
    assert view.b7_workflow.basis_current is False
    with pytest.raises(DomainError) as error:
        svc.handoff_b7(child.id, {"decision_id": decision.id, "reason": "Bàn giao"},
            command("handoff-new", "ACC-DEMO-01", "ACCOUNTANT", view.case_version))
    assert error.value.code == "BASIS_STALE"


# --- regression: generic guard stays blocked, races, history parsing ---------

def test_generic_close_and_handoff_remain_blocked_linked(approved_linked_b7):
    """Dedicated B9 routes do NOT open the generic W05 lifecycle for linked B7."""
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 3_000_000, "TX-1", "1")
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.close_case(child.id, {"kind": "SETTLEMENT_COMPLETE", "basis": "x"},
            command("gc", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "LINKED_B7_REPORT_ONLY"
    with pytest.raises(DomainError) as exc2:
        svc.handoff(child.id, {"decision_id": decision.id},
            command("gh", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc2.value.code == "LINKED_B7_REPORT_ONLY"
    with pytest.raises(DomainError) as exc3:
        svc.record_money(child.id, {
            "event_ref": "EV", "kind": "PAYMENT_TO_EMPLOYEE", "gross_vnd": 1,
            "payee_ref": "NV-DEMO-01", "event_at": "2026-10-14T00:00:00+07:00",
            "reported_status": "RECEIVED", "refs": []},
            command("gm", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc3.value.code == "LINKED_B7_REPORT_ONLY"


def test_second_close_after_closed_is_idempotent_or_blocked(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    first = _close(svc, child.id, final.run_id, "1", decision.id)
    # A different payload on an already-closed case is rejected, not re-closed.
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.close_b7(child.id, {
            "decision_id": decision.id, "current_report_id": final.run_id,
            "reason": "lý do khác"},
            command("close-2", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code in ("CASE_CLOSED", "STALE_VERSION")


def test_history_parses_after_closure(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 2_000_000, "TX-1", "1")
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    final = _refresh_rerun_revalidate(svc, child.id, "1")
    _close(svc, child.id, final.run_id, "1", decision.id)
    # get_case/history still parse the new typed kind + closure audit.
    view = svc.get_case(child.id)
    assert view.stage == "SETTLEMENT_CLOSED"
    entries = svc.store.history(child.id)
    assert any(e.operation == "B7_CLOSE" for e in entries)
    assert any(e.operation == "B7_RECORD_MONEY" for e in entries)



# --- R1.4 regression matrix ---------------------------------------------------

def test_same_totals_but_changed_cost_source_needs_recheck(approved_linked_b7):
    """Same E/T/B numbers but a changed cost source/relations → NEEDS_RECHECK.

    The cost basis is compared by the full signature, not by totals, so an
    equal total must not waive a changed cost evidence/relations.
    """
    svc, child, report, decision = approved_linked_b7
    expense_id = report.expense_rows[0].expense_id
    # A new cost fact for the same expense changes the cost signature while the
    # employee total stays 5.0M (the original amount is superseded by the doc).
    svc.add_source(child.id,
        __import__("invoice_referee.settlement.models", fromlist=["Upload"]).Upload(
            filename="restated-cost.txt",
            content=f"fact CHANGED expense.{expense_id}.amount 5000000\n".encode()),
        command("restate", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))
    child = svc.get_case(child.id)
    run = svc.start(child.id,
        command("run-restate", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    child = svc.get_case(child.id)
    reval = svc.revalidate_b7(child.id,
        command("reval-restate", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert reval.status == "NEEDS_RECHECK"


def test_handoff_reuse_requires_same_receipt_history(approved_linked_b7):
    """Same remaining amount with a different receipt history is a new handoff.

    The obligation signature binds cost basis + receipt history, so a new
    receipt that keeps the same remaining is not a silent reuse.
    """
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 1_000_000, "TX-1", "1")
    child = svc.get_case(child.id)
    first = svc.handoff_b7(child.id,
        {"decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
        command("ho-a", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert first.remaining_vnd == 2_000_000
    # A different, additional receipt changes the receipt history.
    _receipt(svc, child, decision, 1_000_000, "TX-2", "2")
    child = svc.get_case(child.id)
    second = svc.handoff_b7(child.id,
        {"decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
        command("ho-b", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert second.id != first.id
    assert second.remaining_vnd == 1_000_000
    assert second.receipt_history_signature != first.receipt_history_signature


def test_noop_handoff_key_replay_then_conflict(approved_linked_b7):
    """A no-op handoff registers its command: same key replays, other body 409."""
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 1_000_000, "TX-1", "1")
    child = svc.get_case(child.id)
    body = {"decision_id": decision.id, "reason": "Bàn giao phần còn lại"}
    first = svc.handoff_b7(child.id, body,
        command("noop-ho", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    # Same key + same body → idempotent replay.
    replay = svc.handoff_b7(child.id, body,
        command("noop-ho", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert replay.id == first.id
    assert replay.idempotent_replay is True
    # Same key + different body → IDEMPOTENCY_CONFLICT (registry bound it).
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.handoff_b7(child.id,
            {"decision_id": decision.id, "reason": "Lý do khác"},
            command("noop-ho", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_handoff_after_revalidation_valid_when_basis_moved(approved_linked_b7):
    """Duyệt3→receipt1→refresh/rerun/revalidate VALID → handoff remaining2."""
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 1_000_000, "TX-1", "1")
    _refresh_rerun_revalidate(svc, child.id, "1")
    child = svc.get_case(child.id)
    handoff = svc.handoff_b7(child.id,
        {"decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
        command("ho-valid", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert handoff.remaining_vnd == 2_000_000
    assert handoff.direction == "PAY_EMPLOYEE"
    # The original approval is unchanged (still 3.0M, same decision).
    view = svc.get_case(child.id)
    assert view.b7_workflow.decision.id == decision.id
    assert view.b7_workflow.decision.target.amount_vnd == 3_000_000


def test_old_revalidation_badge_does_not_authorize_after_source_change(
        approved_linked_b7):
    """A VALID revalidation is not enough once a material source changes later."""
    from invoice_referee.settlement.models import Upload
    svc, child, report, decision = approved_linked_b7
    _receipt(svc, child, decision, 1_000_000, "TX-1", "1")
    _refresh_rerun_revalidate(svc, child.id, "1")
    # Material cost source changes after the revalidation.
    expense_id = report.expense_rows[0].expense_id
    svc.add_source(child.id, Upload(filename="post-reval.txt",
        content=f"fact LATE expense.{expense_id}.amount 6000000\n".encode()),
        command("late", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))
    child = svc.get_case(child.id)
    with pytest.raises(DomainError) as exc:
        svc.handoff_b7(child.id,
            {"decision_id": decision.id, "reason": "Bàn giao phần còn lại"},
            command("ho-late", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "BASIS_STALE"
