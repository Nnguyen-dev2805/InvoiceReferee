"""B5 receipt-method integration (P4.3): L01-style bank/cash confirmed path.

Exercises the Service/Store path with the packet-literal context (receipt
sources configured) and the fake reader — no real DB, no LIVE, no .env. These
pin the evidence-gated behavior the plan requires across both methods and the
missing-config / unknown-amount fail-safe cases.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import Upload
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3, _approve,  # noqa: F401
)
from tests.settlement.test_b3_funding import (  # noqa: F401
    approved_b3, receipt_payload, upload_receipt,
)


def _v(svc, case_id):
    return svc.get_case(case_id).case_version


def test_bank_receiver_confirmed_counts_toward_funding(approved_b3):
    """A fully-sourced bank RECEIVED fulfills exactly the approved advance."""
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("bank", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    funding = view.b3_workflow.funding
    assert funding.recorded_received_vnd == 2_000_000
    assert funding.fulfilled_vnd == 2_000_000
    assert funding.remaining_vnd == 0
    assert funding.status == "FULFILLED"
    assert view.stage == "AWAITING_WORK_SETTLEMENT"
    # B7 summary untouched by a B5 advance.
    assert view.money_summary["received_vnd"] is None


def test_cash_acknowledged_fulfills(approved_b3):
    svc, case, decision = approved_b3
    proof = svc.add_b3_advance_proof(case.id,
        Upload(filename="pc.txt", content=b"PC-L01-001"),
        command("cproof", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, method="CASH",
                        namespace="CASH:DEMO-QUY", event_ref="PC-L01-001",
                        receipt_details={"kind": "CASH",
                                         "voucher_number": "PC-L01-001",
                                         "acknowledgement": "ACKNOWLEDGED",
                                         "receiver_name": "Nguyễn An"}),
        command("cash", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.stage == "AWAITING_WORK_SETTLEMENT"


def test_cash_wrong_voucher_number_not_confirmed(approved_b3):
    """Cash voucher number must equal the event_ref of the voucher."""
    svc, case, decision = approved_b3
    proof = svc.add_b3_advance_proof(case.id,
        Upload(filename="pc2.txt", content=b"x"),
        command("cproof2", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    event = svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, method="CASH",
                        namespace="CASH:DEMO-QUY", event_ref="PC-999",
                        receipt_details={"kind": "CASH",
                                         "voucher_number": "PC-OTHER",
                                         "acknowledgement": "ACKNOWLEDGED",
                                         "receiver_name": "Nguyễn An"}),
        command("cashbad", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    assert event.classification == "UNCONFIRMED"
    assert svc.get_case(case.id).b3_workflow.funding.recorded_received_vnd is None


def test_partial_receipt_keeps_approved_and_remaining(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, amount=1_000_000)
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, amount=1_000_000),
        command("part", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.decision.advance_vnd == 2_000_000
    assert view.b3_workflow.funding.recorded_received_vnd == 1_000_000
    assert view.b3_workflow.funding.remaining_vnd == 1_000_000
    assert view.stage == "AWAITING_MONEY"


def test_wrong_recipient_keeps_raw_not_counted(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision, payee="NV-KHAC-99")
    svc.record_b3_advance(case.id,
        receipt_payload(proof.id, decision, payee="NV-KHAC-99"),
        command("wrong", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert any(i.kind == "WRONG_RECIPIENT"
               for i in view.b3_workflow.funding.incidents)
    assert view.stage == "RESOLVING_OBLIGATIONS"


def test_duplicate_same_event_not_double_counted(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("d1", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("d2", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert any(i.kind == "CONFLICTING_OUTCOME"
               for i in view.b3_workflow.funding.incidents)


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
        command("unk", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd is None
    assert view.b3_workflow.funding.remaining_vnd is None
    assert view.stage == "AWAITING_MONEY"


def test_receipt_under_stop_kept_without_stage_advance(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    svc.control(case.id, "STOP",
        command("stop", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    view = svc.get_case(case.id)
    assert view.b3_workflow.funding.recorded_received_vnd == 2_000_000
    assert view.stage != "AWAITING_WORK_SETTLEMENT"


def test_proof_upload_does_not_stale_decision(approved_b3):
    svc, case, decision = approved_b3
    upload_receipt(svc, case, decision)
    view = svc.get_case(case.id)
    assert view.input_revision == case.input_revision
    assert view.b3_workflow.basis_current is True


def test_wrong_actor_cannot_record(approved_b3):
    svc, case, decision = approved_b3
    proof = upload_receipt(svc, case, decision)
    with pytest.raises(DomainError) as exc:
        svc.record_b3_advance(case.id, receipt_payload(proof.id, decision),
            command("bad", "NV-DEMO-01", "ACCOUNTANT", _v(svc, case.id)))
    assert exc.value.code == "BEYOND_AUTHORITY"
