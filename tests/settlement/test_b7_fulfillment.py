"""B9 settlement fulfillment: source-backed classifier + typed actual events.

Classifier tests use a REAL retained artifact (a temp source), and service
integration runs the REAL pipeline via ``ready_linked_b7``. No LIVE, no .env,
no mocked COMPLETE report. Evidence literals are synthetic human-source-review
inputs, not OCR/LLM output or gold.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Upload
from tests.settlement.test_b3_workflow import (  # noqa: F401 — fixture chain
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_workflow import ready_linked_b7  # noqa: F401


@pytest.fixture
def approved_linked_b7(ready_linked_b7):
    """A ready linked child with an APPROVE decision (B8) and no money yet."""
    svc, child, report = ready_linked_b7
    presentation = svc.present_b7(child.id, {
        "basis_report_id": report.run_id,
        "review": {"report_id": report.run_id, "note": "Đủ căn cứ",
                   "refs": report.source_refs}},
        command("b9-present", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    decision = svc.decide_b7(child.id, {
        "presentation_id": presentation.id, "outcome": "APPROVE",
        "reason": "Duyệt theo kết quả đã rà soát"},
        command("b9-approve", "APR-DEMO-01", "APPROVER",
                svc.get_case(child.id).case_version))
    return svc, svc.get_case(child.id), report, decision


def _money_text(*, amount, purpose, payee, payer, event_ref, method,
                event_at, namespace="BANK:DEMO-ACCOUNT", work=None,
                outcome="RECEIVED"):
    lines = [f"amount_vnd={amount}", "currency=VND", f"payer_ref={payer}",
             f"payee_ref={payee}", f"event_at={event_at}",
             f"receiver_outcome={outcome}", f"event_namespace={namespace}",
             f"event_ref={event_ref}", f"method={method}", f"purpose={purpose}"]
    if work is not None:
        lines.append(f"work_ref={work}")
    return "\n".join(lines) + "\n"


def upload_money_proof(svc, child, text, key="money-proof"):
    return svc.add_b7_settlement_proof(
        child.id, Upload(filename="settlement-proof.txt", content=text.encode()),
        command(key, "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(child.id).case_version))


def money_payload(source_id, decision_id, *, amount=2_000_000,
                  purpose="REIMBURSEMENT_RECEIVED", status="RECEIVED",
                  payee="NV-DEMO-01", payer="COMPANY", event_ref="TX-SET-01",
                  method="BANK_TRANSFER", event_at="2026-10-14T08:00:00+07:00",
                  namespace="BANK:DEMO-ACCOUNT", work=None):
    values = {
        "amount_vnd": amount, "currency": "VND", "payer_ref": payer,
        "payee_ref": payee, "event_at": event_at, "receiver_outcome": status,
        "event_namespace": namespace, "event_ref": event_ref, "method": method,
        "purpose": purpose,
    }
    if work is not None:
        values["work_ref"] = work
    return {
        "decision_id": decision_id, "event_namespace": namespace,
        "event_ref": event_ref, "method": method, "gross_vnd": amount,
        "payer_ref": payer, "payee_ref": payee, "event_at": event_at,
        "reported_status": status, "purpose": purpose,
        "allocation_note": "Đối chiếu giao dịch với đúng quyết định/công việc",
        "evidence": [{"field": k, "source_id": source_id, "locator": k,
                      "raw": str(v), "value": v, "read_state": "READ",
                      "origin": "HUMAN_SOURCE_REVIEW"}
                     for k, v in values.items()],
    }


def _record(svc, child, proof, payload, key="money"):
    return svc.record_b7_settlement_money(
        child.id, payload,
        command(key, "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(child.id).case_version))


def _records(svc, case_id):
    with svc.store._read() as conn:
        return svc.store._source_records(conn, case_id)


# --- classifier unit tests (real retained source) ---------------------------

def test_classifier_confirms_correct_receipt(approved_linked_b7):
    from datetime import datetime, timezone
    from invoice_referee.settlement.b7_fulfillment import classify_b7_money
    from invoice_referee.settlement.models import B7MoneyEventPayload
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    payload = B7MoneyEventPayload.model_validate(
        money_payload(proof.id, decision.id, event_ref="TX-1"))
    classification, incidents = classify_b7_money(
        payload, employee_ref="NV-DEMO-01", work_ref=child.submission.work_ref,
        company_ref="COMPANY-INVREF", sources=_records(svc, child.id),
        effective_at=datetime(2026, 10, 14, 9, 0, tzinfo=timezone(timedelta(hours=7))))
    assert classification == "CONFIRMED_RECEIPT", incidents


def test_classifier_collection_requires_company_ref(approved_linked_b7):
    from datetime import datetime, timezone
    from invoice_referee.settlement.b7_fulfillment import classify_b7_money
    from invoice_referee.settlement.models import B7MoneyEventPayload
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=700_000, purpose="ADVANCE_RETURN", payee="COMPANY-INVREF",
        payer="NV-DEMO-01", event_ref="TX-C1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    payload = B7MoneyEventPayload.model_validate(
        money_payload(proof.id, decision.id, amount=700_000, purpose="ADVANCE_RETURN",
                      payee="COMPANY-INVREF", payer="NV-DEMO-01", event_ref="TX-C1"))
    # Without company_ref, a return is unallocated — never normalized to company.
    classification, incidents = classify_b7_money(
        payload, employee_ref="NV-DEMO-01", work_ref=child.submission.work_ref,
        company_ref=None, sources=_records(svc, child.id),
        effective_at=datetime(2026, 10, 14, 9, 0, tzinfo=timezone(timedelta(hours=7))))
    assert classification == "INCIDENT"
    assert any(i.code == "UNALLOCATED" for i in incidents)


# --- service integration ----------------------------------------------------

def test_confirmed_receipt_fulfills_but_does_not_close(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    event = _record(svc, child, proof, money_payload(proof.id, decision.id,
                                                     event_ref="TX-1"))
    assert event.classification == "CONFIRMED_RECEIPT"
    view = svc.get_case(child.id)
    assert view.b7_workflow.decision.target.amount_vnd == 3_000_000
    assert view.b7_workflow.fulfillment.approved_vnd == 3_000_000
    assert view.b7_workflow.fulfillment.recorded_received_vnd == 2_000_000
    assert view.b7_workflow.fulfillment.remaining_vnd == 1_000_000
    assert view.b7_workflow.fulfillment.status == "PARTIAL"
    assert view.stage == "AWAITING_MONEY"
    assert not svc.closed(child.id)


def test_cash_receipt_confirmed_without_bank_source(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-CASH", method="CASH",
        event_at="2026-10-14T08:00:00+07:00"))
    event = _record(svc, child, proof, money_payload(
        proof.id, decision.id, event_ref="TX-CASH", method="CASH"))
    assert event.classification == "CONFIRMED_RECEIPT"


def test_pending_not_counted_as_received(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-P", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00", outcome="PENDING"))
    event = _record(svc, child, proof, money_payload(
        proof.id, decision.id, event_ref="TX-P", status="PENDING"))
    assert event.classification == "PENDING"
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.recorded_received_vnd is None
    assert view.b7_workflow.fulfillment.pending_count == 1


def test_wrong_recipient_keeps_raw_not_fulfilled(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-KHAC-99",
        payer="COMPANY", event_ref="TX-W", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    event = _record(svc, child, proof, money_payload(
        proof.id, decision.id, payee="NV-KHAC-99", event_ref="TX-W"))
    assert event.classification == "INCIDENT"
    assert any(i.code == "WRONG_RECIPIENT" for i in event.incidents)
    assert event.gross_vnd == 2_000_000  # raw preserved, never clipped


def test_unknown_purpose_keeps_unallocated(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="UNKNOWN", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-U", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    event = _record(svc, child, proof, money_payload(
        proof.id, decision.id, purpose="UNKNOWN", event_ref="TX-U"))
    assert event.classification == "INCIDENT"
    assert any(i.code == "UNALLOCATED" for i in event.incidents)


def test_after_cutoff_receipt_stored_not_fulfilled(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-LATE", method="BANK_TRANSFER",
        event_at="2026-11-01T08:00:00+07:00"))
    event = _record(svc, child, proof, money_payload(
        proof.id, decision.id, event_ref="TX-LATE",
        event_at="2026-11-01T08:00:00+07:00"))
    assert event.after_cutoff is True
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.recorded_received_vnd is None


def test_wrong_accountant_cannot_record(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    with pytest.raises(DomainError) as exc:
        svc.record_b7_settlement_money(
            child.id, money_payload(proof.id, decision.id, event_ref="TX-1"),
            command("bad", "NV-DEMO-01", "ACCOUNTANT",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_employee_cannot_record_event(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    with pytest.raises(DomainError) as exc:
        svc.record_b7_settlement_money(
            child.id, money_payload(proof.id, decision.id, event_ref="TX-1"),
            command("bad", "NV-DEMO-01", "EMPLOYEE",
                    svc.get_case(child.id).case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_zero_and_negative_amount_rejected(approved_linked_b7):
    from invoice_referee.settlement.models import B7MoneyEventPayload
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    for bad in (0, -5):
        payload = money_payload(proof.id, decision.id, event_ref="TX-1")
        payload["gross_vnd"] = bad
        with pytest.raises(DomainError) as exc:
            _record(svc, child, proof, payload, key=f"bad-{bad}")
        assert exc.value.code == "INVALID_PAYLOAD"


def test_evidence_source_must_belong_to_case(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    event = _record(svc, child, None,
                    money_payload("S-KHONG-THUOC", decision.id, event_ref="TX-X"))
    # An unresolved source is kept as an INCIDENT, never a receipt.
    assert event.classification == "INCIDENT"
    assert any(i.code == "SOURCE_UNRESOLVED" for i in event.incidents)
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.recorded_received_vnd is None


def test_same_event_ref_conflicts_not_double_counted(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    _record(svc, child, proof, money_payload(proof.id, decision.id, event_ref="TX-1"),
            key="r1")
    _record(svc, child, proof, money_payload(proof.id, decision.id, event_ref="TX-1"),
            key="r2")
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.recorded_received_vnd == 2_000_000
    assert any(i.code == "CONFLICTING_EVENT"
               for i in view.b7_workflow.fulfillment.incidents)


def test_stop_still_records_fact_without_advancing(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    svc.control(child.id, "STOP",
                command("stop", "ACC-DEMO-01", "ACCOUNTANT",
                        svc.get_case(child.id).case_version))
    event = _record(svc, child, proof, money_payload(proof.id, decision.id,
                                                     event_ref="TX-1"))
    assert event.classification == "CONFIRMED_RECEIPT"
    view = svc.get_case(child.id)
    assert view.b7_workflow.fulfillment.recorded_received_vnd == 2_000_000
    assert view.stage != "READY_TO_CLOSE"


def test_money_event_idempotent_same_key(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    payload = money_payload(proof.id, decision.id, event_ref="TX-1")
    first = _record(svc, child, proof, payload, key="same")
    replay = _record(svc, child, proof, payload, key="same")
    assert replay.id == first.id
    assert replay.idempotent_replay is True


def test_approval_not_leaked_into_generic_money_summary(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    proof = upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    _record(svc, child, proof, money_payload(proof.id, decision.id, event_ref="TX-1"))
    view = svc.get_case(child.id)
    # The B9 event kind never leaks into the generic money summary.
    assert view.money_summary["received_vnd"] is None
    assert view.money_summary["approved_vnd"] is None


def test_proof_upload_does_not_stale_decision(approved_linked_b7):
    svc, child, report, decision = approved_linked_b7
    before = svc.get_case(child.id)
    upload_money_proof(svc, child, _money_text(
        amount=2_000_000, purpose="REIMBURSEMENT_RECEIVED", payee="NV-DEMO-01",
        payer="COMPANY", event_ref="TX-1", method="BANK_TRANSFER",
        event_at="2026-10-14T08:00:00+07:00"))
    after = svc.get_case(child.id)
    assert after.input_revision == before.input_revision
    assert after.b7_workflow.status == "APPROVED"
    assert after.b7_workflow.basis_current is True


# --- Task 2: pure projection literals (no integration / no source auth) ------

def _receipt(event_id, canonical_id, amount, state="CONFIRMED", *,
             decision_id="D-1", qualifying=True, after_cutoff=False,
             incidents=None):
    from invoice_referee.settlement.models import B7FulfillmentReceipt
    return B7FulfillmentReceipt(
        event_id=event_id, canonical_id=canonical_id, decision_id=decision_id,
        amount_vnd=amount, state=state, qualifying=qualifying,
        after_cutoff=after_cutoff, incidents=incidents or [])


def _project(receipts, *, approved=3_000_000, direction="PAY_EMPLOYEE"):
    from datetime import datetime, timezone
    from invoice_referee.settlement.b7_fulfillment import project_b7_fulfillment
    at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    return project_b7_fulfillment("D-1", approved, direction, receipts,
                                  as_of=at, knowledge_cutoff=at)


def test_projection_partial_keeps_approved():
    result = _project([_receipt("M-1", "BANK:C:TX-1", 2_000_000)])
    assert result.approved_vnd == 3_000_000
    assert result.recorded_received_vnd == 2_000_000
    assert result.fulfilled_vnd == 2_000_000
    assert result.remaining_vnd == 1_000_000
    assert result.status == "PARTIAL"


def test_projection_pending_keeps_subtotal_not_remaining():
    result = _project([_receipt("M-1", "BANK:C:TX-1", 1_000_000, "PENDING")])
    assert result.recorded_received_vnd is None
    assert result.remaining_vnd is None
    assert result.pending_count == 1
    assert result.status == "BLOCKED"


def test_projection_overpay_caps_fulfilled_keeps_excess():
    result = _project([_receipt("M-1", "BANK:C:TX-1", 4_000_000)])
    assert result.recorded_received_vnd == 4_000_000  # raw kept
    assert result.fulfilled_vnd == 3_000_000  # capped
    assert any(i.code == "OVERPAY" and i.excess_vnd == 1_000_000
               for i in result.incidents)
    assert result.status == "BLOCKED"


def test_projection_other_decision_receipt_ignored():
    result = _project([_receipt("M-1", "BANK:C:TX-1", 2_000_000,
                                decision_id="D-OTHER")])
    assert result.recorded_received_vnd is None
    assert result.status == "WAITING"


def test_projection_canonical_duplicate_counted_once():
    result = _project([
        _receipt("M-1", "BANK:C:TX-1", 2_000_000),
        _receipt("M-2", "BANK:C:TX-1", 2_000_000, "PENDING")])
    # A later pending observation does not remove the confirmed receipt, and
    # the confirmed one counts once.
    assert result.recorded_received_vnd == 2_000_000


def test_projection_old_pending_superseded_by_final():
    result = _project([
        _receipt("M-1", "BANK:C:TX-1", 1_000_000, "PENDING"),
        _receipt("M-2", "BANK:C:TX-1", 1_000_000, "CONFIRMED")])
    assert result.recorded_received_vnd == 1_000_000
    assert result.pending_count == 0


def test_projection_failed_and_cancelled_not_receipt():
    result = _project([
        _receipt("M-1", "BANK:C:TX-1", 2_000_000, "FAILED"),
        _receipt("M-2", "BANK:C:TX-2", 1_000_000, "CANCELLED")])
    assert result.recorded_received_vnd is None
    assert result.status == "WAITING"


def test_projection_balanced_no_event_zero():
    result = _project([], approved=0, direction="BALANCED")
    assert result.approved_vnd == 0
    assert result.remaining_vnd == 0
    assert result.status == "BALANCED"
    assert result.recorded_received_vnd is None


def test_projection_future_receipt_excluded_keeps_blocker():
    result = _project([_receipt("M-1", "BANK:C:TX-1", 2_000_000,
                                after_cutoff=True)])
    assert result.recorded_received_vnd is None
    assert result.status == "BLOCKED"

