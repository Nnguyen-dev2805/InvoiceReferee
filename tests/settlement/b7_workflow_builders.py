"""Test-only builders for B8 settlement-decision tests.

These build literal inputs (never call the code under test to produce expected
values). The unit builder only exercises ``settlement_target``; the integration
builder runs the REAL Service/pipeline with the fake reader so prerequisites are
proven by execution, not by a mocked report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from invoice_referee.settlement.models import (
    B7CompanyConfig,
    AuthorityGrant,
    CheckResult,
    ComponentSlot,
    Report,
    ReportComponents,
    Upload,
)

# The routine B7 checks a COMPLETE report must carry (Rulebook R7–R10).
ROUTINE_CHECKS = ("relation_status", "duplicate_events", "eligibility",
                  "payer_parts", "history_coverage", "budget", "authority")

SETTLEMENT_CLOCK = datetime(2026, 10, 14, 9, 0, tzinfo=timezone(timedelta(hours=7)))


def report_from_values(e, a, ra=0, p=0, rp=0, t=8_000_000, b=8_000_000):
    """Literal report for target unit tests (not source authenticity)."""
    amounts = dict(t=t, b=b, e=e, a=a, ra=ra, p=p, rp=rp)
    slots = {key: ComponentSlot(
        value=value, state="UNKNOWN" if value is None else "KNOWN",
        refs=[f"source:{key}"]) for key, value in amounts.items()}
    net = None if any(amounts[k] is None for k in ("e", "a", "ra", "p", "rp")) \
        else e - (a - ra) - (p - rp)
    return Report(
        run_id="R-unit", job="B7", mode="PIPELINE_FAKE_OR_REPLAY",
        generated_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        completion="INCOMPLETE" if net is None else "COMPLETE",
        components=ReportComponents(**slots), calculated_net_vnd=net,
        proposed_net_vnd=net,
        checks=[CheckResult(rule=rule, status="PASS",
                            reason="Unit input: sourced check",
                            refs=["source:unit"]) for rule in ROUTINE_CHECKS],
        source_refs=["source:unit"])


def b7_config(*, employee_cost_cap=8_000_000, net_cap=8_000_000,
              company_ref="COMPANY-INVREF"):
    """Explicit B7 authority config for the demo fixture (literal)."""
    return B7CompanyConfig(
        schema_version="b7-company-config-v1", version="b7-demo-v1",
        activated=True, synthetic=True, demo_clock=SETTLEMENT_CLOCK,
        ref="company:b7-config-demo", company_ref=company_ref,
        grants=[AuthorityGrant(
            actor_ref="APR-DEMO-01", employee_ref="NV-DEMO-01", work_ref=None,
            max_settlement_vnd=net_cap, max_employee_cost_vnd=employee_cost_cap,
            effective_from=datetime(2026, 10, 10, 0, 0,
                                    tzinfo=timezone(timedelta(hours=7))),
            effective_until=datetime(2026, 10, 31, 23, 59,
                                     tzinfo=timezone(timedelta(hours=7))))])


def _ledger_lines(rows):
    return "\n".join(rows) + "\n"


def make_ready_linked(svc, parent, monkeypatch, *,
                      employee_cost_vnd=5_000_000):
    """Drive the REAL Service/pipeline to a COMPLETE linked B7 report.

    Steps: record a B5 receipt2 on the parent, prepare the child, set the B7
    config (clock14Oct09h+07), upload employee expense/payment/claim sources and
    the company register, then run → wait → report. Returns (child_view, report).
    No mocked report is injected.
    """
    from invoice_referee.settlement.service import ServiceConfig
    from tests.settlement.test_b3_funding import (
        receipt_payload, upload_receipt,
    )
    from tests.settlement.test_b3_workflow import command
    from tests.settlement.test_b7_linked import _linked_child
    from tests.settlement.test_b7_linked_context import _event, _packet

    # 1. B5 actual receipt2 on the parent (canonical managed advance).
    parent = svc.get_case(parent.id)
    decision = svc.get_case(parent.id).b3_workflow.decision
    proof = upload_receipt(svc, parent, decision, amount=2_000_000)
    svc.record_b3_advance(parent.id, receipt_payload(proof.id, decision),
                          command("b5-rec", "ACC-DEMO-01", "ACCOUNTANT",
                                  svc.get_case(parent.id).case_version))

    # 2. Configure B7 rights + synthetic clock, then prepare the child. The
    #    child's server clocks are pinned to the synthetic settlement clock so
    #    a receipt at 14Oct08h+07 is inside the child's money_as_of window.
    svc.config = svc.config.model_copy(update={"b7_context": b7_config()})
    import invoice_referee.shared.clock as clock_module
    monkeypatch.setattr(clock_module, "utcnow", lambda: SETTLEMENT_CLOCK)
    child = _linked_child(svc, svc.get_case(parent.id))

    # 3. Employee declares the actual hotel expense (5M, BUSINESS, PERSONAL
    #    declared payer) and uploads the source ledger + claim link.
    from invoice_referee.settlement.models import B7ClaimRow, B7LinkedIntake
    intake = B7LinkedIntake(
        schema_version="b7-linked-intake-v1", confirmed=True,
        expense_rows=[B7ClaimRow(
            claim_id="CL-EMP", description="Khách sạn + đi lại",
            purpose="BUSINESS", declared_amount_vnd=employee_cost_vnd,
            declared_payer="PERSONAL")])
    child = svc.revise_linked_b7(child.id, intake,
        command("confirm", "NV-DEMO-01", "EMPLOYEE", child.case_version))
    lines = _ledger_lines([
        "fact EXP-EMP-amount expense.EXP-EMP.amount " + str(employee_cost_vnd),
        "fact EXP-EMP-purpose expense.EXP-EMP.purpose BUSINESS",
        "fact PAY-EMP-amount payment.PAY-EMP.amount " + str(employee_cost_vnd),
        "fact PAY-EMP-payer payment.PAY-EMP.payer EMPLOYEE",
        "fact PAY-EMP-status payment.PAY-EMP.status RECEIVED",
        "rel RX-EMP EXPENSE_PAYMENT EXP-EMP PAY-EMP",
        "rel RC-EMP CLAIM_EXPENSE CL-EMP EXP-EMP",
    ])
    svc.add_source(child.id,
        Upload(filename="employee-ledger.txt", content=lines.encode()),
        command("emp-src", "NV-DEMO-01", "EMPLOYEE",
                svc.get_case(child.id).case_version))

    # 4. Accountant records the company register: coverage to 14Oct, canonical
    #    advance2 (same identity as B5), company-direct flight3, no returns.
    flight_payment = _event(namespace="VENDOR:VNA", ref="PAY-F1",
                            kind="COMPANY_DIRECT", amount=3_000_000,
                            payee="VNA")
    flight_payment["employee_ref"] = "NV-DEMO-01"
    advance = _event(amount=2_000_000)
    advance["employee_ref"] = "NV-DEMO-01"
    packet = _packet(
        events=[advance, flight_payment],
        expenses=[{
            "expense_ref": "EXP-FLIGHT", "issuer_ref": "VNA",
            "document_ref": "INV-F", "amount_vnd": 3_000_000,
            "purpose": "BUSINESS", "expense_date": "2026-10-12",
            "refs": ["company:INV-F"],
            "payment_event_refs": ["VENDOR:VNA:PAY-F1"]}])
    packet["coverage"]["employee_ref"] = "NV-DEMO-01"
    packet["coverage"]["to"] = SETTLEMENT_CLOCK.isoformat()
    svc.record_b7_company_packet(child.id, packet,
        command("pkt", "ACC-DEMO-01", "ACCOUNTANT",
                svc.get_case(child.id).case_version))

    # 5. Run the real pipeline.
    child = svc.get_case(child.id)
    run = svc.start(child.id, command("run", "NV-DEMO-01", "EMPLOYEE",
                                      child.case_version))
    view = svc.wait(run.id)
    assert view.status == "SUCCEEDED", view
    report = svc.report(run.id)
    return svc.get_case(child.id), report
