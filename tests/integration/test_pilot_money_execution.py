"""A6 actual-execution / loop-closure tests (plan A6; contracts §4, §10.1).

An issued instruction is NOT money received. A responsible completed money event
bound to the original instruction closes the loop: F01 a completed return makes
R=760000/S=0; F02 a completed reimbursement makes P=400000/S=0; F03 never issues
a zero instruction. A duplicate external key does not double count.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    EmployeePaidClaim,
    RecordActual,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PILOT_ROOT = Path(__file__).resolve().parents[2] / "data" / "test-kit" / "uc03-pilot"
SHA = "a" * 64


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(
        field=name, state="FOUND", value=value,
        refs=(EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote="x"),),
    )  # type: ignore[arg-type]


def _report(invoice: str, amount: str) -> ReadResult:
    paper = DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("printed_total", amount)),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "x"), _found("amount", amount), _found("invoice_refs", (invoice,)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    doc = DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", invoice), _found("issuer_name", "An Bình"), _found("total_amount", amount)),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, doc))


async def _typed_case(
    tmp_path: Path, *, folder: str, invoice: str, amount: int, claim: int
) -> tuple[CaseWorkflow, str, str]:
    org_path = PILOT_ROOT / folder / "input" / "organization.json"
    from invoice_referee.domain.organization import OrganizationContext

    org = OrganizationContext.model_validate_json(org_path.read_text(encoding="utf-8"))
    tenant = org.organization_id or org.tenant
    activity = str((org.activity or {}).get("activity_id"))
    employee = "employee:employee-a"

    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    # Pin the harness clock to the pilot's historical decision instant so the
    # context coverage (through 10/10) is valid (plan A3/C: controlled clock).
    pilot_clock = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: pilot_clock)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "a")
    wf.import_company_context(org, origin="SIMULATED")

    session = wf.start_session(tenant=tenant, persona="employee", actor_id=employee)
    ctx = CommandContext(session_id=session.session_id, actor_id=employee, command_id="cmd:1", expected_case_version=0)
    created = await wf.execute(ctx, CreateDraft(activity_data=ActivityData(
        activity_id=activity, name="a", occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="p",
    )))
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=employee, command_id="cmd:2", expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{tenant}/{root}/hd.pdf"),)),
    )
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=tenant, root_id=root, report=_report(invoice, str(amount)))
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=employee, command_id="cmd:3", expected_case_version=int(version)),
        Submit(
            root_id=root,
            declaration=Declaration(activity_id=activity, declared_purpose="p"),
            employee_paid_claims=(EmployeePaidClaim(
                invoice_reference=invoice, amount=claim,
                refs=(EvidenceRef(source_id="file:hd.pdf", source_sha256=digest, page=1, exact_quote="x"),),
                reason="đã trả",
            ),),
        ),
    )
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(tenant), row, wf._now_iso())
    return wf, tenant, root


async def _record(wf: CaseWorkflow, tenant: str, root: str, *, kind: str, amount: int, payer: str, payee: str):
    import uuid

    session = wf.start_session(tenant=tenant, persona="accountant", actor_id="employee:accountant-demo")
    ctx = CommandContext(
        session_id=session.session_id, actor_id="employee:accountant-demo",
        command_id=f"cmd:rec:{uuid.uuid4().hex}", expected_case_version=wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"],
    )
    money = RecordMoneyInput(
        external_key=f"bank:txn-{kind}-{amount}", claimed_kind=kind, claimed_scope=str(wf._query_one("SELECT activity FROM cases WHERE id = ?", (root,))["activity"]),
        payer=payer, payee=payee, amount=amount, event_at=datetime(2026, 10, 12, tzinfo=UTC),
        completion_claim="Đã hoàn tất, đối chiếu sao kê", reason="ghi nhận",
    )
    return (await wf.execute(ctx, RecordActual(root_id=root, money=money))).case_view


async def test_f01_completed_return_closes_the_loop(tmp_path: Path) -> None:
    wf, tenant, root = await _typed_case(
        tmp_path, folder="f01-cong-tac-thu-lai-tien-thua", invoice="IR26101001", amount=3_240_000, claim=3_240_000
    )
    v = wf.view(wf.start_session(tenant=tenant, persona="employee", actor_id="employee:employee-a"), root)
    assert [(i.direction, i.amount) for i in v.instructions] == [("COLLECT", 760_000)]
    closed = await _record(
        wf, tenant, root, kind="EMPLOYEE_RETURN", amount=760_000,
        payer="employee:employee-a", payee="company:demo",
    )
    assert closed.actual_money.R.value == 760_000
    assert closed.actual_money.S.value == 0
    assert closed.state == "SETTLED"


async def test_f02_completed_reimbursement_closes_the_loop(tmp_path: Path) -> None:
    wf, tenant, root = await _typed_case(
        tmp_path, folder="f02-cong-tac-cong-ty-chi-them", invoice="IR26101002", amount=5_400_000, claim=5_400_000
    )
    v = wf.view(wf.start_session(tenant=tenant, persona="employee", actor_id="employee:employee-a"), root)
    assert [(i.direction, i.amount) for i in v.instructions] == [("PAY", 400_000)]
    closed = await _record(
        wf, tenant, root, kind="REIMBURSEMENT_RECEIVED", amount=400_000,
        payer="company:demo", payee="employee:employee-a",
    )
    assert closed.actual_money.P.value == 400_000
    assert closed.actual_money.S.value == 0
    assert closed.state == "SETTLED"


async def test_f03_never_issues_a_zero_instruction(tmp_path: Path) -> None:
    wf, tenant, root = await _typed_case(
        tmp_path, folder="f03-cong-tac-can-bang", invoice="IR26101003", amount=4_320_000, claim=4_320_000
    )
    v = wf.view(wf.start_session(tenant=tenant, persona="employee", actor_id="employee:employee-a"), root)
    assert v.actual_money.S.value == 0
    assert v.instructions == ()
    assert v.state == "SETTLED"


async def test_duplicate_external_key_does_not_double_count(tmp_path: Path) -> None:
    wf, tenant, root = await _typed_case(
        tmp_path, folder="f01-cong-tac-thu-lai-tien-thua", invoice="IR26101001", amount=3_240_000, claim=3_240_000
    )
    await _record(wf, tenant, root, kind="EMPLOYEE_RETURN", amount=760_000, payer="employee:employee-a", payee="company:demo")
    again = await _record(wf, tenant, root, kind="EMPLOYEE_RETURN", amount=760_000, payer="employee:employee-a", payee="company:demo")
    assert again.actual_money.R.value == 760_000  # not 1_520_000
