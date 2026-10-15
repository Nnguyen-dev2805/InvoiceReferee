"""A6 actual-execution / loop-closure tests (plan A6; contracts §4, §10.1).

An issued instruction is NOT money received. F01 employee returns require a
source-bound employee draft before accountant confirmation; F02 completed
reimbursement makes P=400000/S=0; F03 never issues a zero instruction. A
duplicate external key does not double count.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    ConfirmCoverage,
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
from invoice_referee.domain.finance import COVERAGE_REQUIRED_FLOW_KINDS, RecordMoneyInput
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
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("printed_total", amount)),
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
    direction = "PAY" if kind == "REIMBURSEMENT_RECEIVED" else "COLLECT"
    external_key = f"bank:txn-{kind}-{amount}"
    instruction = wf._query_one(
        "SELECT id FROM instructions WHERE tenant = ? AND root_id = ? "
        "AND direction = ? AND status IN ('ISSUED','PARTIAL') ORDER BY created_at DESC LIMIT 1",
        (tenant, root, direction),
    )
    if instruction is None:
        existing = wf._query_one(
            "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? AND external_key = ?",
            (tenant, root, external_key),
        )
        assert existing is not None
        instruction_id = json.loads(existing["payload_json"])["instruction_id"]
    else:
        instruction_id = str(instruction["id"])
    source = wf._query_one(
        "SELECT source_id, digest FROM case_sources WHERE tenant = ? AND root_id = ? "
        "ORDER BY attached_at LIMIT 1",
        (tenant, root),
    )
    assert source is not None
    money = RecordMoneyInput(
        external_key=external_key, claimed_kind=kind, claimed_scope=str(wf._query_one("SELECT activity FROM cases WHERE id = ?", (root,))["activity"]),
        payer=payer, payee=payee, amount=amount,
        event_at=datetime(2026, 10, 10, 17, tzinfo=timezone(timedelta(hours=7))),
        completion_claim="Đã hoàn tất, đối chiếu sao kê", reason="ghi nhận",
        instruction_id=instruction_id,
        refs=(EvidenceRef(
            source_id=str(source["source_id"]),
            source_sha256=str(source["digest"]),
            page=1,
            exact_quote="Chứng từ đã đối chiếu",
        ),),
    )
    return (await wf.execute(ctx, RecordActual(root_id=root, money=money))).case_view


async def _confirm_history_coverage(wf: CaseWorkflow, tenant: str, root: str) -> None:
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    source = wf._query_one("SELECT source_id, digest FROM case_sources WHERE root_id = ?", (root,))
    session = wf.start_session(
        tenant=tenant, persona="accountant", actor_id="employee:accountant-demo"
    )
    await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id="employee:accountant-demo",
            command_id=f"cmd:coverage:{root}",
            expected_case_version=version,
        ),
        ConfirmCoverage(
            root_id=root,
            start=datetime(2026, 10, 1, tzinfo=timezone(timedelta(hours=7))),
            funds=("Tài khoản ngân hàng công ty",),
            flow_kinds=COVERAGE_REQUIRED_FLOW_KINDS,
            opening_balance=0,
            witness_refs=(EvidenceRef(
                source_id=source["source_id"],
                source_sha256=source["digest"],
                page=1,
                exact_quote="Sao kê đối chiếu sổ tiền công ty",
            ),),
            reason="Đã đối chiếu toàn bộ lịch sử tiền của đúng hoạt động.",
        ),
    )


async def test_f01_direct_return_claim_requires_source_bound_employee_draft(tmp_path: Path) -> None:
    wf, tenant, root = await _typed_case(
        tmp_path, folder="f01-cong-tac-thu-lai-tien-thua", invoice="IR26101001", amount=3_240_000, claim=3_240_000
    )
    v = wf.view(wf.start_session(tenant=tenant, persona="employee", actor_id="employee:employee-a"), root)
    assert [(i.direction, i.amount) for i in v.instructions] == [("COLLECT", 760_000)]
    # A client-authored R event without an employee-uploaded, source-bound
    # draft is inadmissible. The API regression covers the upload/OCR/confirm path.
    from invoice_referee.workflow.service import UnsupportedCommandError

    with pytest.raises(UnsupportedCommandError, match="chứng từ hoàn trả đã lưu"):
        await _record(
            wf, tenant, root, kind="EMPLOYEE_RETURN", amount=760_000,
            payer="employee:employee-a", payee="company:demo",
        )
    unchanged = wf.view(
        wf.start_session(tenant=tenant, persona="accountant", actor_id="employee:accountant-demo"),
        root,
    )
    assert unchanged.actual_money.R.value == 0
    assert unchanged.actual_money.S.value == -760_000


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
    await _confirm_history_coverage(wf, tenant, root)
    closed = wf.view(
        wf.start_session(tenant=tenant, persona="accountant", actor_id="employee:accountant-demo"),
        root,
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
        tmp_path, folder="f02-cong-tac-cong-ty-chi-them", invoice="IR26101002", amount=5_400_000, claim=5_400_000
    )
    await _record(wf, tenant, root, kind="REIMBURSEMENT_RECEIVED", amount=400_000, payer="company:demo", payee="employee:employee-a")
    again = await _record(wf, tenant, root, kind="REIMBURSEMENT_RECEIVED", amount=400_000, payer="company:demo", payee="employee:employee-a")
    await _confirm_history_coverage(wf, tenant, root)
    again = wf.view(
        wf.start_session(tenant=tenant, persona="accountant", actor_id="employee:accountant-demo"),
        root,
    )
    assert again.actual_money.P.value == 400_000  # not 800_000
