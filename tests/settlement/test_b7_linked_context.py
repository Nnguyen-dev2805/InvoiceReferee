"""B6→B7 linked context: coverage, actual vs approved, B7 rights (Task 2).

No real DB, no LIVE, no .env. Company packet/coverage are synthetic,
source-backed literals — not bank authentication or OCR success.
"""
from __future__ import annotations

import pytest

from invoice_referee.domain.models import DomainError
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3,  # noqa: F401 — fixture chain for approved_b3
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_linked import _linked_child
from tests.settlement.test_b7_workflow import ready_linked_b7  # noqa: F401


def _packet(*, events=None, expenses=None, complete=True, groups=None,
            missing=None, to="2026-10-14T23:59:59+07:00"):
    return {
        "schema_version": "b7-company-packet-v1",
        "coverage": {
            "employee_ref": "NV-DEMO-01", "work_ref": None,
            "from": "2026-10-01T00:00:00+07:00", "to": to,
            "complete_prior_history": complete,
            "groups": groups or ["ADVANCE", "ADVANCE_RETURN",
                                 "REIMBURSEMENT_RECEIVED",
                                 "REIMBURSEMENT_RETURN", "COMPANY_DIRECT",
                                 "DUPLICATE_CLAIMS"],
            "methods": ["CASH", "BANK_TRANSFER", "OTHER_COMPANY_CHANNELS"],
            "missing_ranges": missing or [],
            "owner_ref": "ACC-DEMO-01",
            "origin": "Synthetic company register for the linked test.",
            "ref": "company:coverage-linked",
        },
        "events": events or [],
        "expenses": expenses or [],
        "refs": ["company:coverage-linked"],
        "reading_note": "Kế toán đọc sổ công ty tới mốc quyết toán.",
    }


def _missing_opening():
    return [{"group": "opening", "from": "2026-10-01T00:00:00+07:00",
             "to": "2026-10-10T00:00:00+07:00",
             "reason": "Chưa có số dư đầu kỳ từ sổ công ty."}]


def _event(namespace="BANK:DEMO-ACCOUNT", ref="TX-ADV-01", kind="ADVANCE_RECEIVED",
           amount=2_000_000, outcome="RECEIVED", payee="NV-DEMO-01"):
    return {"event_namespace": namespace, "event_ref": ref, "kind": kind,
            "amount_vnd": amount, "payer_ref": "COMPANY", "payee_ref": payee,
            "outcome": outcome, "event_at": "2026-10-11T10:00:00+07:00",
            "refs": [f"company:{ref}"]}


def test_parent_approval2_actual1_imports_subtotal_not_approved(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    # Record one actual receipt of 1.0M in the parent.
    from tests.settlement.test_b3_funding import receipt_payload, upload_receipt
    parent = svc.get_case(parent.id)
    proof = upload_receipt(svc, parent, decision, amount=1_000_000)
    svc.record_b3_advance(parent.id,
        receipt_payload(proof.id, decision, amount=1_000_000),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT", svc.get_case(parent.id).case_version))
    view = svc.get_case(child.id)
    # Managed advance subtotal reflects actual 1M, never the approved 2M.
    assert view.linked_b7.managed_advance_subtotal_vnd == 1_000_000


def test_record_company_packet_requires_accountant(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    with pytest.raises(DomainError) as exc:
        svc.record_b7_company_packet(child.id, _packet(),
            command("pkt", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_full_coverage_with_receipt_sets_history(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    view = svc.record_b7_company_packet(child.id,
        _packet(events=[_event(amount=2_000_000)]),
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.history["history.advance.received"] == 2_000_000
    assert snap.history["history.advance.returned"] == 0
    assert snap.history["history.reimbursement.received"] == 0
    assert snap.history["history.reimbursement.returned"] == 0


def test_missing_coverage_keeps_history_unknown(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    view = svc.record_b7_company_packet(child.id,
        _packet(complete=False, missing=_missing_opening()),
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.history["history.advance.received"] is None
    assert view.linked_b7.context_current is True


def test_company_actual_expense_not_from_forecast(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    expense = {"expense_ref": "CE-flight", "issuer_ref": "VNA",
               "document_ref": "INV-1", "amount_vnd": 3_000_000,
               "purpose": "BUSINESS", "expense_date": "2026-10-12",
               "refs": ["company:INV-1"], "payment_event_refs": []}
    view = svc.record_b7_company_packet(child.id,
        _packet(expenses=[expense]),
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.company_expenses[0].amount_vnd == 3_000_000


def test_context_refresh_identical_hash_reuses(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    svc.record_b7_company_packet(child.id, _packet(),
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    before = svc.get_case(child.id)
    after = svc.refresh_linked_b7_context(child.id,
        command("ref", "ACC-DEMO-01", "ACCOUNTANT", before.case_version))
    # Identical packet: no new input_revision.
    assert after.input_revision == before.input_revision


# --- Task 1.3 negative prerequisites (assert slot/history, not HTTP only) ----

def _scoped_event(**over):
    event = _event(**{k: v for k, v in over.items()
                      if k in ("namespace", "ref", "kind", "amount", "outcome",
                               "payee")})
    event["employee_ref"] = over.get("employee_ref", "NV-DEMO-01")
    return event


def test_wrong_employee_coverage_keeps_history_unknown(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    packet = _packet(events=[_scoped_event(amount=2_000_000)])
    packet["coverage"]["employee_ref"] = "NV-KHAC-99"
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.history["history.advance.received"] is None


def test_missing_group_keeps_that_history_unknown(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    # Coverage present but the ADVANCE_RETURN group is not claimed.
    packet = _packet(events=[_scoped_event(amount=2_000_000)],
                     groups=["ADVANCE", "REIMBURSEMENT_RECEIVED",
                             "REIMBURSEMENT_RETURN", "COMPANY_DIRECT",
                             "DUPLICATE_CLAIMS"])
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.history["history.advance.received"] == 2_000_000
    assert snap.history["history.advance.returned"] is None  # group missing


def test_event_after_cutoff_not_counted(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    event = _scoped_event(amount=2_000_000)
    event["event_at"] = "2026-11-01T00:00:00+07:00"  # after settlement clock
    packet = _packet(events=[event])
    packet["coverage"]["to"] = "2026-10-14T09:00:00+07:00"
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    assert snap.history["history.advance.received"] == 0  # not counted


def test_pending_event_not_counted_as_received(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    packet = _packet(events=[_scoped_event(amount=2_000_000,
                                           outcome="PENDING")])
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    # A pending advance is not a received advance.
    assert snap.history["history.advance.received"] == 0


def test_same_event_ref_not_double_counted(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    # Two events with the SAME namespace+ref: the packet validator rejects.
    with pytest.raises(DomainError) as exc:
        svc.record_b7_company_packet(child.id,
            _packet(events=[_scoped_event(amount=2_000_000),
                            _scoped_event(amount=2_000_000)]),
            command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "INVALID_PAYLOAD"


def test_noop_context_key_is_bound_to_its_payload(ready_linked_b7):
    svc, child, _ = ready_linked_b7
    packet = svc.store.get_linked_b7_context(child.id).company_packet.model_dump(mode="json")
    cmd = command("noop-key", "ACC-DEMO-01", "ACCOUNTANT",
                  svc.get_case(child.id).case_version)
    first = svc.record_b7_company_packet(child.id, packet, cmd)
    changed = dict(packet)
    changed["reading_note"] += " Different request body."
    with pytest.raises(DomainError) as error:
        svc.record_b7_company_packet(child.id, changed, cmd)
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    assert svc.get_case(child.id).input_revision == first.input_revision
