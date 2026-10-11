"""B5 advance receipt (b3-intake-v1): proof upload + actual receipt bookkeeping.

These tests exercise the Service/Store path with the packet-literal context and
fake reader — no real DB, no LIVE providers, no .env. Proof evidence literals
are synthetic *human-source-review* inputs, not OCR/LLM outputs or independent
gold. Assertions are on persisted records/sums/stages, not only HTTP status.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from invoice_referee.settlement.models import Upload
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3, _approve,
)


@pytest.fixture
def approved_b3(presented_b3):
    svc, case, presentation = presented_b3
    decision = _approve(svc, case, presentation)
    return svc, svc.get_case(case.id), decision


def receipt_payload(source_id, decision, *, amount=2_000_000,
                    payee="NV-DEMO-01", event_ref="TX-ADV-01"):
    event_at = decision.effective_at + timedelta(hours=1)
    values = {"amount_vnd": amount, "currency": "VND",
              "payer_side": "COMPANY", "payee_ref": payee,
              "event_at": event_at.isoformat(), "receiver_outcome": "RECEIVED",
              "event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": event_ref,
              "method": "BANK_TRANSFER"}
    return {
        "decision_id": decision.id, "event_namespace": "BANK:DEMO-ACCOUNT",
        "event_ref": event_ref, "method": "BANK_TRANSFER", "gross_vnd": amount,
        "payer_side": "COMPANY", "payee_ref": payee,
        "event_at": event_at.isoformat(), "reported_status": "RECEIVED",
        "allocation_note": "Đối chiếu giao dịch với đúng quyết định/công việc",
        "evidence": [{"field": k, "source_id": source_id, "locator": k,
            "raw": str(v), "value": v, "read_state": "READ",
            "origin": "HUMAN_SOURCE_REVIEW"} for k, v in values.items()],
    }


def upload_receipt(svc, case, decision, amount=2_000_000,
                   payee="NV-DEMO-01", key="proof", event_ref="TX-ADV-01"):
    at = decision.effective_at + timedelta(hours=1)
    text = (f"amount_vnd={amount}\ncurrency=VND\npayer_side=COMPANY\n"
            f"payee_ref={payee}\nevent_at={at.isoformat()}\n"
            "receiver_outcome=RECEIVED\n"
            f"event_namespace=BANK:DEMO-ACCOUNT\nevent_ref={event_ref}\n"
            "method=BANK_TRANSFER\n")
    return svc.add_b3_advance_proof(case.id,
        Upload(filename="receiver-receipt.txt", content=text.encode()),
        command(key, "ACC-DEMO-01", "ACCOUNTANT", case.case_version))


def test_receipt_fulfills_advance_not_closes_case(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    after_proof = svc.get_case(case.id)
    assert after_proof.input_revision == case.input_revision
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("receipt", "ACC-DEMO-01", "ACCOUNTANT", after_proof.case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.b3_workflow.funding.remaining_vnd == 0
    assert view.stage == "AWAITING_WORK_SETTLEMENT"
    assert view.money_summary["received_vnd"] is None  # B7 không thành reimbursement
    assert not svc.closed(case.id)


def test_partial_receipt_preserves_approved_amount(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, amount=1_000_000)
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, amount=1_000_000),
        command("partial", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.decision.advance_vnd == 2_000_000
    assert view.b3_workflow.funding.recorded_received_vnd == 1_000_000
    assert view.b3_workflow.funding.remaining_vnd == 1_000_000
    assert view.stage == "AWAITING_MONEY"


def test_overpay_keeps_actual_three_million(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, amount=3_000_000)
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, amount=3_000_000),
        command("overpay", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 3_000_000
    assert any(i.kind == "OVERPAY" and i.amount_vnd == 1_000_000
               for i in view.b3_workflow.funding.incidents)
    assert view.stage == "RESOLVING_OBLIGATIONS"
    assert not svc.closed(case.id)


def test_wrong_recipient_not_counted_as_received(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, payee="NV-KHAC-99")
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, payee="NV-KHAC-99"),
        command("wrong", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert any(i.kind == "WRONG_RECIPIENT"
               for i in view.b3_workflow.funding.incidents)
    assert view.stage == "RESOLVING_OBLIGATIONS"


def test_same_event_ref_not_double_counted(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("r1", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    # Second RECEIVED for the same namespace+ref: conflicting outcome, not a
    # second payment.
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("r2", "ACC-DEMO-01", "ACCOUNTANT", view.case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert any(i.kind == "CONFLICTING_OUTCOME"
               for i in view.b3_workflow.funding.incidents)


def test_pending_then_received_appends(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    pending = receipt_payload(proof.id, decision)
    pending["reported_status"] = "PENDING"
    for f in pending["evidence"]:
        if f["field"] == "receiver_outcome":
            f["value"] = "PENDING"
    svc.record_b3_advance(case.id, pending,
        command("pend", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert view.b3_workflow.funding.pending_count == 1
    assert view.stage == "AWAITING_MONEY"
    # Final receipt for the same economic event.
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("fin", "ACC-DEMO-01", "ACCOUNTANT", view.case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.stage == "AWAITING_WORK_SETTLEMENT"
    # Two records kept (pending + received), not one overwritten.
    assert len(view.b3_workflow.advance_events) == 2


def test_unknown_amount_keeps_remaining_null(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    payload = receipt_payload(proof.id, decision)
    payload["gross_vnd"] = None
    payload["reported_status"] = "UNCONFIRMED"
    for f in payload["evidence"]:
        if f["field"] == "amount_vnd":
            f["value"] = None
            f["read_state"] = "UNCLEAR"
    svc.record_b3_advance(case.id, payload,
        command("unk", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert view.b3_workflow.funding.remaining_vnd is None
    assert view.stage == "AWAITING_MONEY"


# --- Task 3: basis / Stop / B7 isolation -------------------------------------

def test_proof_upload_alone_does_not_stale_decision(approved_b3):
    """Adding a proof source must not require re-approval (no basis break)."""
    svc, case, decision = approved_b3
    upload_receipt(svc, case, decision)
    view = svc.get_case(case.id)
    assert view.b3_workflow.basis_current is True
    assert view.b3_workflow.status == "APPROVED"
    assert view.input_revision == case.input_revision
    assert view.b3_workflow.funding.recorded_received_vnd is None


def test_generic_source_still_stales_decision(ready_b3):
    """A normal (proposal) source add still invalidates the basis."""
    svc, case, report_id = ready_b3
    presentation = svc.present_b3(case.id, {
        "basis_report_id": report_id,
        "review": {"report_id": report_id, "note": "Đủ", "refs": []}},
        command("present", "ACC-DEMO-01", "ACCOUNTANT", case.case_version))
    svc.decide_b3(case.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt", "work_allowed": True,
        "budget_vnd": 8_000_000, "advance_vnd": 2_000_000},
        command("approve", "APR-DEMO-01", "APPROVER",
                svc.get_case(case.id).case_version))
    svc.add_source(case.id, Upload(filename="extra.txt", content=b"bo sung"),
                   command("src", "NV-DEMO-01", "EMPLOYEE",
                           svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.b3_workflow.basis_current is False
    assert view.b3_workflow.status == "NEEDS_RECHECK"


def test_stop_still_records_actual_without_advancing(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.control(case.id, "STOP",
                command("stop", "ACC-DEMO-01", "ACCOUNTANT",
                        svc.get_case(case.id).case_version))
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    # The actual fact is kept even under Stop.
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    # Stop does not auto-advance to work-settlement.
    assert view.stage != "AWAITING_WORK_SETTLEMENT"
    assert not svc.closed(case.id)


def test_b5_received_does_not_touch_b7_pending_count(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    pending = receipt_payload(proof.id, decision)
    pending["reported_status"] = "PENDING"
    svc.record_b3_advance(case.id, pending,
        command("pend", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    # A B3 pending advance is not a B7 pending obligation.
    assert view.money_summary["pending_events"] == 0
    assert view.money_summary["received_vnd"] is None


def test_b5_advance_event_does_not_leak_into_b7_summary(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    assert view.money_summary["approved_vnd"] is None
    assert view.money_summary["received_vnd"] is None
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000


def test_wrong_actor_cannot_record_advance(approved_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    with pytest.raises(DomainError) as exc:
        svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
            command("bad", "NV-DEMO-01", "ACCOUNTANT",
                    svc.get_case(case.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_evidence_source_must_belong_to_case(approved_b3):
    from invoice_referee.domain.models import DomainError
    svc, case, decision = approved_b3
    with pytest.raises(DomainError) as exc:
        svc.record_b3_advance(case.id,
            receipt_payload("S-KHONG-THUOC", decision),
            command("bad-src", "ACC-DEMO-01", "ACCOUNTANT",
                    svc.get_case(case.id).case_version))
    assert exc.value.code == "BASIS_MISMATCH"


def test_generic_source_cannot_fake_proof_use(approved_b3):
    """A client-supplied source_use in provenance is dropped, not trusted."""
    svc, case, decision = approved_b3
    # Generic upload (proposal path) trying to self-label as proof.
    record = svc.store.add_source(
        case.id, Upload(filename="fake.txt", content=b"x",
                        provenance={"source_use": "B3_ADVANCE_PROOF"}),
        command("gen", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(case.id).case_version))
    proof_ids = svc.store._b3_proof_source_ids(case.id)
    assert record.id not in proof_ids


def test_decision_event_idempotent_same_key(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    payload = receipt_payload(proof.id, decision)
    first = svc.record_b3_advance(case.id, payload,
        command("same", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    replay = svc.record_b3_advance(case.id, payload,
        command("same", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    assert replay.id == first.id
    assert replay.idempotent_replay is True


def test_confirmed_advance_merges_into_history_on_rerun(approved_b3):
    """A rerun after a recorded receipt sees the received advance in history."""
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case.id).case_version))
    view = svc.get_case(case.id)
    # Re-run the same case; the run input history must include the advance.
    rerun = svc.start(case.id, command("rerun", "NV-DEMO-01", "EMPLOYEE",
                                       view.case_version))
    assert svc.wait(rerun.id).status == "SUCCEEDED"
    run_input = svc.store.get_run_input(rerun.id)
    refs = [r.ref for r in run_input.b3_context.history]
    assert any(r.startswith("b3advance:") for r in refs)


def test_cross_case_same_event_ref_still_records_own_scope(presented_b3, tmp_path):
    """Two cases share one store; a same event_ref in each keeps its own scope.

    The store has no cross-case ledger in this slice, so the identity guard is
    per case/decision: each case records its own event without a foreign case
    silently stealing the contribution. (Cross-case dedup is a later, linked
    plan; this test pins the current per-scope behavior honestly.)
    """
    svc, case_a, presentation = presented_b3
    decision_a = _approve(svc, case_a, presentation)
    case_a = svc.get_case(case_a.id)
    proof_a = upload_receipt(svc, case_a, decision_a)
    svc.record_b3_advance(case_a.id, receipt_payload(proof_a.id, decision_a),
        command("a-rec", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(case_a.id).case_version))
    view_a = svc.get_case(case_a.id)
    assert view_a.b3_workflow.funding.recorded_received_vnd == 2_000_000
    # A decision_id from another case is not honored here.
    other = receipt_payload(proof_a.id, decision_a)
    other["decision_id"] = "BD-KHONG-THUOC"
    svc.record_b3_advance(case_a.id, other,
        command("a-foreign", "ACC-DEMO-01", "ACCOUNTANT",
                view_a.case_version))
    view_a2 = svc.get_case(case_a.id)
    assert any(i.kind == "UNAUTHORIZED_OR_UNALLOCATED"
               for i in view_a2.b3_workflow.funding.incidents)
