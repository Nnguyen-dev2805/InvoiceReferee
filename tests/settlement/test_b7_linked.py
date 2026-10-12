"""B6→B7 linked settlement (b7-linked-intake-v1): draft, declarations, link.

These tests exercise the Service/Store path with the packet-literal context and
fake reader — no real DB, no LIVE providers, no .env. A linked child is a NEW
B7 case sharing the parent's employee/work; the B3 parent is never mutated.
"""
from __future__ import annotations

import pytest

from invoice_referee.shared.errors import DomainError
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3,
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401


def _linked_child(svc, parent):
    """Prepare (or reuse) the linked B7 child for a B3 parent."""
    return svc.prepare_linked_b7(
        parent.id, command("prepare", "NV-DEMO-01", "EMPLOYEE",
                           parent.case_version))


def test_link_keeps_employee_work_and_parent(approved_b3):
    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    assert child.job == "B7"
    assert child.submission.employee_ref == parent.submission.employee_ref
    assert child.submission.work_ref == parent.submission.work_ref
    assert child.linked_b7.origin.origin_case_id == parent.id
    assert svc.get_case(parent.id).job == "B3"
    assert child.submission.form["confirmed"] is False


def test_prepare_retry_does_not_create_second_child(approved_b3):
    svc, parent, decision = approved_b3
    cmd = command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version)
    first = svc.prepare_linked_b7(parent.id, cmd)
    second = svc.prepare_linked_b7(parent.id, cmd)
    assert first.id == second.id


def test_prepare_new_key_reuses_existing_child(approved_b3):
    svc, parent, decision = approved_b3
    first = svc.prepare_linked_b7(parent.id,
        command("prepare-a", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    second = svc.prepare_linked_b7(parent.id,
        command("prepare-b", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    assert first.id == second.id


def test_wrong_actor_cannot_prepare(approved_b3):
    svc, parent, decision = approved_b3
    with pytest.raises(DomainError) as exc:
        svc.prepare_linked_b7(parent.id,
            command("prepare", "ACC-DEMO-01", "ACCOUNTANT",
                    parent.case_version))
    assert exc.value.code == "BEYOND_AUTHORITY"


def test_generic_submit_rejects_spoofed_link(approved_b3):
    from invoice_referee.settlement.models import Submission

    svc, parent, decision = approved_b3
    spoof = Submission(
        employee_ref="NV-DEMO-01", work_ref="WORK-X", job="B7",
        money_as_of=parent.submission.money_as_of,
        knowledge_cutoff=parent.submission.knowledge_cutoff,
        form={"schema_version": "b7-linked-intake-v1", "confirmed": False,
              "expense_rows": [], "origin_link": {"origin_case_id": "FAKE"}})
    with pytest.raises(DomainError) as exc:
        svc.submit(spoof, command("spoof", "NV-DEMO-01", "EMPLOYEE", None))
    assert exc.value.code == "INVALID_PAYLOAD"


def test_generic_revise_cannot_wipe_link(approved_b3):
    from invoice_referee.settlement.models import Submission

    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    with pytest.raises(DomainError) as exc:
        svc.revise(child.id, child.submission.model_copy(
            update={"form": {"purpose": "x", "scope": "y"}}),
            command("wipe", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert exc.value.code == "INVALID_PAYLOAD"


def test_revise_linked_keeps_link_and_employee(approved_b3):
    from invoice_referee.settlement.models import B7ClaimRow, B7LinkedIntake

    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    intake = B7LinkedIntake(
        schema_version="b7-linked-intake-v1", confirmed=False,
        expense_rows=[B7ClaimRow(
            claim_id="CL-1", description="Khách sạn", purpose="BUSINESS",
            declared_amount_vnd=3_000_000, declared_payer="PERSONAL")])
    updated = svc.revise_linked_b7(child.id, intake,
        command("revise", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    assert updated.linked_b7.origin.origin_case_id == parent.id
    assert updated.submission.employee_ref == parent.submission.employee_ref
    assert updated.submission.work_ref == parent.submission.work_ref
    assert updated.submission.form["confirmed"] is False
    assert svc.get_case(parent.id).job == "B3"


def test_linked_b7_blocks_generic_financial_actions(approved_b3):
    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    # No generic decision/money/handoff/closure on a linked child.
    with pytest.raises(DomainError) as exc:
        svc.record_money(child.id, {
            "event_ref": "EV-X", "kind": "PAYMENT_TO_EMPLOYEE",
            "gross_vnd": 1, "payee_ref": "NV-DEMO-01",
            "event_at": "2026-10-11T00:00:00+07:00",
            "reported_status": "RECEIVED", "refs": []},
            command("m", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    assert exc.value.code == "LINKED_B7_REPORT_ONLY"
    with pytest.raises(DomainError) as exc2:
        svc.close_case(child.id, {"kind": "SETTLEMENT_COMPLETE", "basis": "x"},
                       command("c", "ACC-DEMO-01", "ACCOUNTANT",
                               child.case_version))
    assert exc2.value.code == "LINKED_B7_REPORT_ONLY"


def test_dependency_fingerprint_changes_with_parent(approved_b3):
    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    before = svc.store.linked_b7_dependency_fingerprint(child.id)
    # A parent receipt changes the dependency fingerprint.
    from tests.settlement.test_b3_funding import receipt_payload, upload_receipt
    parent = svc.get_case(parent.id)
    proof = upload_receipt(svc, parent, decision)
    svc.record_b3_advance(parent.id, receipt_payload(proof.id, decision),
        command("rec", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(parent.id).case_version))
    after = svc.store.linked_b7_dependency_fingerprint(child.id)
    assert before != after


def test_parent_stop_makes_child_context_not_current(approved_b3):
    from tests.settlement.test_b7_linked_context import _packet
    svc, parent, decision = approved_b3
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    child = svc.get_case(child.id)
    svc.record_b7_company_packet(child.id, _packet(),
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    assert child.linked_b7.context_current is True
    # Stop the parent: the child context is no longer current.
    svc.control(parent.id, "STOP",
                command("stop", "ACC-DEMO-01", "ACCOUNTANT",
                        svc.get_case(parent.id).case_version))
    child = svc.get_case(child.id)
    assert child.linked_b7.context_current is False


def test_delete_parent_with_linked_child_refused(approved_b3):
    svc, parent, decision = approved_b3
    svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    with pytest.raises(DomainError) as exc:
        svc.delete_case(parent.id)
    assert exc.value.code == "LINKED_CASE_EXISTS"


def test_linked_run_does_not_inherit_broad_demo_authority(approved_b3):
    """A linked B7 run uses B7 rights only — never the generic P-DEMO grant."""
    svc, parent, decision = approved_b3
    # Give the service a broad generic authority and no B7 config.
    from invoice_referee.settlement.models import AuthorityGrant
    svc.config = svc.config.model_copy(update={
        "authority": [AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                                     max_settlement_vnd=100_000_000)],
        "b7_context": None})
    child = svc.prepare_linked_b7(parent.id,
        command("prepare", "NV-DEMO-01", "EMPLOYEE", parent.case_version))
    run = svc.start(child.id, command("run", "NV-DEMO-01", "EMPLOYEE",
                                      child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    run_input = svc.store.get_run_input(run.id)
    # No broad P-DEMO grant leaked into the linked run.
    assert all(g.actor_ref != "P-DEMO" for g in run_input.authority)
