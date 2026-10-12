"""B6→B7 claim↔expense matching (Task 3).

Structured fake reader: employee sources carry expense/payment observations and
CLAIM_EXPENSE relations; company context supplies the actual company facts.
Gold literals are source-first, independent of production output. No expected
labels are fed into any prompt/input.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import (
    B7ClaimRow, B7LinkedIntake, Observation, Relation,
)
from tests.settlement.test_b3_workflow import (
    command, ready_b3, presented_b3,  # noqa: F401 — fixture chain
)
from tests.settlement.test_b3_funding import approved_b3  # noqa: F401
from tests.settlement.test_b7_linked import _linked_child
from tests.settlement.test_b7_linked_context import _packet, _event


def _confirm(svc, child, rows):
    intake = B7LinkedIntake(schema_version="b7-linked-intake-v1",
                            confirmed=True, expense_rows=rows)
    return svc.revise_linked_b7(child.id, intake,
        command("confirm", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))


def test_claim_expense_relation_establishes_comparison(approved_b3):
    """A claim matched to an actual expense yields a MATCHED comparison."""
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    rows = [B7ClaimRow(claim_id="CL-hotel", description="Khách sạn",
                       purpose="BUSINESS", declared_amount_vnd=3_000_000,
                       declared_payer="PERSONAL")]
    _confirm(svc, child, rows)
    # Company packet: actual employee hotel expense of 3.0M.
    packet = _packet(expenses=[{
        "expense_ref": "EXP-hotel", "issuer_ref": "HOTEL",
        "document_ref": "INV-H", "amount_vnd": 3_000_000,
        "purpose": "BUSINESS", "expense_date": "2026-10-12",
        "refs": ["company:INV-H"], "payment_event_refs": []}])
    child = svc.get_case(child.id)
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    # Build context observations + relations, then evaluate.
    snap = svc.store.get_linked_b7_context(child.id)
    from invoice_referee.settlement.linked_context import linked_context_observations
    obs, rels, issues = linked_context_observations(snap, "S-ctx")
    # A CLAIM_EXPENSE relation links the claim to the company expense.
    rels.append(Relation(relation_id="RX-1", kind="CLAIM_EXPENSE",
                         from_id="CL-hotel", to_id="EXP-hotel",
                         supporting_refs=["company:INV-H"],
                         status="ESTABLISHED", reason="claim↔expense"))
    # Claim comparison should be computed by the evaluator.
    from invoice_referee.settlement.rules import evaluate
    run_input = svc.store.get_run_input  # noqa: F841
    # Use a synthetic run input carrying the confirmed form.
    from invoice_referee.settlement.models import RunInput
    child_view = svc.get_case(child.id)
    ri = RunInput(
        case_id=child.id, case_version=child_view.case_version,
        input_revision=child_view.input_revision, control_epoch=1,
        submission=child_view.submission, sources=[],
        policy={}, authority=[], response_refs=[], config={},
        snapshot_hash="snap")
    report = evaluate(ri, obs, rels, run_id="R-test", mode="FAKE")
    comps = report.claim_comparisons
    assert any(c.claim_id == "CL-hotel" and c.status == "MATCHED"
               for c in comps), comps


def test_claim_mismatch_is_conflict_not_forecast(approved_b3):
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    rows = [B7ClaimRow(claim_id="CL-hotel", description="Khách sạn",
                       purpose="BUSINESS", declared_amount_vnd=3_000_000,
                       declared_payer="PERSONAL")]
    _confirm(svc, child, rows)
    packet = _packet(expenses=[{
        "expense_ref": "EXP-hotel", "issuer_ref": "HOTEL",
        "document_ref": "INV-H", "amount_vnd": 2_500_000,
        "purpose": "BUSINESS", "expense_date": "2026-10-12",
        "refs": ["company:INV-H"], "payment_event_refs": []}])
    child = svc.get_case(child.id)
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    snap = svc.store.get_linked_b7_context(child.id)
    from invoice_referee.settlement.linked_context import linked_context_observations
    obs, rels, issues = linked_context_observations(snap, "S-ctx")
    rels.append(Relation(relation_id="RX-1", kind="CLAIM_EXPENSE",
                         from_id="CL-hotel", to_id="EXP-hotel",
                         supporting_refs=["company:INV-H"],
                         status="ESTABLISHED", reason="claim↔expense"))
    from invoice_referee.settlement.rules import evaluate
    from invoice_referee.settlement.models import RunInput
    child_view = svc.get_case(child.id)
    ri = RunInput(case_id=child.id, case_version=child_view.case_version,
                  input_revision=child_view.input_revision, control_epoch=1,
                  submission=child_view.submission, sources=[], policy={},
                  authority=[], response_refs=[], config={},
                  snapshot_hash="snap")
    report = evaluate(ri, obs, rels, run_id="R-test", mode="FAKE")
    comps = report.claim_comparisons
    assert any(c.claim_id == "CL-hotel" and c.status == "CONFLICT"
               for c in comps), comps


def test_linked_run_computes_T_from_source_facts(approved_b3):
    """End-to-end: company flight3 + employee hotel3 → T8/E5 (source-first)."""
    svc, parent, decision = approved_b3
    child = _linked_child(svc, parent)
    rows = [B7ClaimRow(claim_id="CL-hotel", description="Khách sạn",
                       purpose="BUSINESS", declared_amount_vnd=3_000_000,
                       declared_payer="PERSONAL")]
    _confirm(svc, child, rows)
    # Company context: actual flight3 paid by company (vendor payment) plus the
    # canonical advance2 event.
    flight_payment = _event(namespace="VENDOR:VNA", ref="PAY-F1",
                            kind="COMPANY_DIRECT", amount=3_000_000,
                            payee="VNA")
    packet = _packet(
        events=[_event(amount=2_000_000), flight_payment],
        expenses=[{
            "expense_ref": "EXP-flight", "issuer_ref": "VNA",
            "document_ref": "INV-F", "amount_vnd": 3_000_000,
            "purpose": "BUSINESS", "expense_date": "2026-10-12",
            "refs": ["company:INV-F"],
            "payment_event_refs": ["VENDOR:VNA:PAY-F1"]}])
    child = svc.get_case(child.id)
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT", child.case_version))
    child = svc.get_case(child.id)
    run = svc.start(child.id, command("run", "NV-DEMO-01", "EMPLOYEE",
                                      child.case_version))
    assert svc.wait(run.id).status == "SUCCEEDED"
    report = svc.report(run.id)
    # Company-direct flight3 is T (company expense); B is the approved budget.
    assert report.components.t.value == 3_000_000
    assert report.components.b.value == 8_000_000
    # Whole-work A from the canonical company advance event.
    assert report.components.a.value == 2_000_000
