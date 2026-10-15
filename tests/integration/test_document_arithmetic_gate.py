"""Core arithmetic gate blocks the commit for TC06/TC11 (not just a UI warning).

The document's own numbers do not close, so no affirmative financial effect may
be issued: the gate is enforced by the Reconciler (allowed_effect is None) and by
the workflow commit (the case ends WAITING with no instruction). The printed
source numbers are preserved. TC01's internally consistent invoice still admits
and still reaches COLLECT 760000.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CaseScope, CommandContext, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.reconciliation.service import Reconciler
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))
TENANT = "tenant:arith"
EMPLOYEE = "employee:employee-a"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _tc06_paper() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Chi phí tiếp khách"),
                _found("declared_advance", "4000000"), _found("printed_total", "3240000"),
                _found("printed_return", "700000")),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Chi phí tiếp khách"), _found("amount", "3240000"),
            _found("invoice_refs", ("00000601",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _tc06_invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00000601"), _found("issuer_name", "MINH PHÁT"),
                _found("buyer_name", COMPANY), _found("subtotal", "3000000"),
                _found("tax", "240000"), _found("total_amount", "3240000"),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _tc11_paper() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Mua thiết bị"),
                _found("declared_advance", "6000000"), _found("printed_total", "5500000"),
                _found("printed_return", "500000")),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Máy in văn phòng"), _found("amount", "5500000"),
            _found("invoice_refs", ("00001101",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _tc05_paper() -> DocumentAnalysis:
    def sourced(field: str, value: object, quote: str) -> FieldCandidate:
        return FieldCandidate(
            field=field, state="FOUND", value=value,
            refs=(EvidenceRef(source_id="s1", source_sha256=SHA, page=1, exact_quote=quote),),
        )

    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            sourced("declared_name", "NGUYỄN MINH AN", "NGUYỄN MINH AN"),
            sourced("declared_advance", "4000000", "Ứng kê khai: 4.000.000 đ"),
            sourced("printed_total", "3500000", "Tổng cộng: 3.500.000 đ"),
            sourced("printed_return", "500000", "Hoàn kê khai: 500.000 đ"),
        ),
        line_items=(
            DocumentLine(id="r1", fields=(
                sourced("description", "Chi phí tiếp khách", "Tiếp khách"),
                sourced("amount", "2000000", "2.000.000 đ"),
                sourced("invoice_refs", ("00000501",), "Hóa đơn 00000501"),
            )),
            DocumentLine(id="r2", fields=(
                sourced("description", "Chi phí phòng họp", "Phòng họp"),
                sourced("amount", "1000000", "1.000.000 đ"),
                sourced("invoice_refs", ("00000501",), "Hóa đơn 00000501"),
            )),
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _tc05_invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(
            _found("document_number", "00000501"), _found("issuer_name", "MINH PHÁT"),
            _found("buyer_name", COMPANY), _found("subtotal", "3000000"),
            _found("tax", "240000"), _found("total_amount", "3240000"),
            _found("document_date", "10/10/2026"),
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _tc11_invoice() -> DocumentAnalysis:
    # subtotal 5m + tax 400k = 5.4m, but the printed total is 5.5m (off by 100k).
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00001101"), _found("issuer_name", "MINH PHÁT"),
                _found("buyer_name", COMPANY), _found("subtotal", "5000000"),
                _found("tax", "400000"), _found("total_amount", "5500000"),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org(*, advance: int) -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": EMPLOYEE, "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000, "effective_from": interval[0],
             "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:1",
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": "activity:1", "payer": "company:demo", "payee": EMPLOYEE,
                    "amount": advance, "event_at": "2026-10-05T09:00:00+07:00",
                    "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"employee": EMPLOYEE, "activity": "activity:1",
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _report(paper: DocumentAnalysis, invoice: DocumentAnalysis) -> ReadResult:
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


def _admit(report: ReadResult, *, advance: int):
    return admit_evidence(
        report, scope=CaseScope(tenant=TENANT, employee=EMPLOYEE, activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(advance=advance), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_tc06_reconciler_blocks_the_effect_on_the_refund_contradiction() -> None:
    inp = _admit(_report(_tc06_paper(), _tc06_invoice()), advance=4_000_000)
    result = Reconciler().assess(inp)
    assert result.allowed_effect is None, "a refund contradiction must not issue money"
    facts = [i for i in result.issues if i.kind == "FACT" and "arithmetic" in i.field_or_rule]
    assert facts, "the refund contradiction must be a FACT"
    assert "60000" in facts[0].basis and "700000" in facts[0].basis


def test_tc11_reconciler_blocks_the_effect_on_the_total_contradiction() -> None:
    inp = _admit(_report(_tc11_paper(), _tc11_invoice()), advance=6_000_000)
    result = Reconciler().assess(inp)
    assert result.allowed_effect is None, "an invoice total contradiction must not issue money"
    facts = [i for i in result.issues if i.kind == "FACT" and "arithmetic" in i.field_or_rule]
    assert facts
    assert "100000" in facts[0].basis and "5500000" in facts[0].basis


def test_tc01_consistent_invoice_has_no_arithmetic_fact() -> None:
    # TC01's invoice is internally consistent; the paper's refund matches too.
    paper = _tc06_paper().model_copy(update={"fields": (
        _found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Chi phí tiếp khách"),
        _found("declared_advance", "4000000"), _found("printed_total", "3240000"),
        _found("printed_return", "760000"),
    )})
    inp = _admit(_report(paper, _tc06_invoice()), advance=4_000_000)
    result = Reconciler().assess(inp)
    assert not [i for i in inp.admission_issues if "arithmetic" in i.field_or_rule]
    # With consistent documents and a full context, TC01 reaches COLLECT 760000.
    assert result.allowed_effect is not None
    assert result.allowed_effect.direction == "COLLECT"
    assert result.allowed_effect.amount == 760_000


def test_tc05_row_total_contradiction_is_employee_fact_and_cost_stays_unknown() -> None:
    inp = _admit(_report(_tc05_paper(), _tc05_invoice()), advance=4_000_000)

    result = Reconciler().assess(inp)
    facts = [issue for issue in result.issues if issue.field_or_rule == "expense:arithmetic:line_total"]

    assert len(facts) == 1
    assert facts[0].kind == "FACT" and facts[0].owner == "employee"
    assert "3.000.000" in facts[0].basis and "3.500.000" in facts[0].basis and "500.000" in facts[0].basis
    assert "3.000.000" in facts[0].question and "3.500.000" in facts[0].question
    assert {ref.exact_quote for ref in facts[0].refs} >= {
        "Tổng cộng: 3.500.000 đ", "Tiếp khách", "2.000.000 đ", "Phòng họp", "1.000.000 đ",
    }
    assert inp.expense_set_complete is False
    assert all(expense.incurred.state == "UNKNOWN" for expense in inp.expense_facts)
    assert not any(expense.payments for expense in inp.expense_facts)
    assert result.projection.T.state == "UNKNOWN"
    assert result.projection.E.state == "UNKNOWN"
    assert result.allowed_effect is None
    assert not any(issue.field_or_rule == "expense:T" for issue in result.issues)
    assert not any(issue.field_or_rule == "expense:payer" for issue in result.issues)


def test_summary_row_is_not_admitted_or_counted_as_a_second_cost() -> None:
    paper = _tc05_paper().model_copy(update={
        "fields": (
            _found("declared_name", "NGUYỄN MINH AN"),
            _found("declared_advance", "4000000"),
            _found("printed_total", "3000000"),
            _found("printed_return", "1000000"),
        ),
        "line_items": _tc05_paper().line_items + (DocumentLine(id="sum", fields=(
            _found("description", "Tổng cộng"), _found("amount", "3000000"),
        )),),
    })
    inp = _admit(_report(paper, _tc05_invoice()), advance=4_000_000)

    result = Reconciler().assess(inp)

    assert len(inp.expense_facts) == 2
    assert not any(issue.field_or_rule.endswith(":missing_evidence") for issue in inp.admission_issues)
    assert not any(issue.field_or_rule == "expense:arithmetic:line_total" for issue in result.issues)
    assert result.allowed_effect is not None and result.allowed_effect.amount == 1_000_000


async def test_tc05_workflow_commit_keeps_issue_and_emits_no_instruction(tmp_path: Path) -> None:
    wf, root = await _seed_workflow(tmp_path, _report(_tc05_paper(), _tc05_invoice()))
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        view = wf._case_view(cx, row)
    assert view.state == "WAITING"
    assert view.instructions == ()
    assert view.actual_money.T.state == "UNKNOWN"
    assert view.actual_money.E.state == "UNKNOWN"
    assert any(
        issue.kind == "FACT" and issue.field_or_rule == "expense:arithmetic:line_total"
        for issue in view.issues
    )


# --- workflow commit boundary -----------------------------------------------


async def _seed_workflow(tmp_path: Path, report: ReadResult) -> tuple[CaseWorkflow, str]:
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    db = Database(tmp_path / "a.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.import_company_context(_org(advance=4_000_000), origin="SIMULATED")
    # Evidence mode: the typed admission mapper consumes the published report.
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "art")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE,
                       command_id="cmd:1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(
            activity_id="activity:1", name="a",
            occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=report)
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    return wf, root


async def test_tc06_commit_ends_waiting_with_no_instruction(tmp_path: Path) -> None:
    wf, root = await _seed_workflow(tmp_path, _report(_tc06_paper(), _tc06_invoice()))
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        view = wf._case_view(cx, row)
    assert view.state == "WAITING"
    assert not view.instructions
    assert any(i.kind == "FACT" and "arithmetic" in i.field_or_rule for i in view.issues)
