"""E: two F01 flows converge — "chưa có bản ghi ứng" and "đã có bản ghi ứng".

Flow 1 (no advance record): the employee submits the settlement form + invoice.
The invoice is the employee-paid basis (demo policy); the printed declared advance
has no company record, so admission keeps A/S UNKNOWN and hands advance
verification to the accountant. The accountant records ADVANCE_RECEIVED from a
transfer receipt or a cash voucher; re-assessment then reaches COLLECT 760000.

Flow 2 (advance record already valid): the same advance exists in the ledger, so
the employee's submit alone reaches COLLECT 760000 without re-uploading anything.

Both branches (transfer/cash) record A=4m once; a retry does not double count.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    ConfirmCoverage,
    CreateDraft,
    Declaration,
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

PILOT = Path(__file__).resolve().parents[2] / "data" / "test-kit" / "uc03-pilot" / "f01-cong-tac-thu-lai-tien-thua"
TENANT = "tenant:uc03-pilot"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
ACTIVITY = "activity:uc03-f01"
SHA = "a" * 64
PILOT_CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _report(*, declared_advance: str | None = "4000000") -> ReadResult:
    fields = [_found("declared_name", "NGUYỄN MINH AN"), _found("printed_total", "3240000"),
              _found("purpose", "Làm việc với khách hàng tại Hà Nội")]
    if declared_advance is not None:
        fields.append(_found("declared_advance", declared_advance))
    paper = DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=tuple(fields),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Bữa ăn"), _found("amount", "3240000"), _found("invoice_refs", ("IR26101001",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR26101001"), _found("issuer_name", "An Bình"),
                _found("total_amount", "3240000"), _found("buyer_person_name", "NGUYỄN MINH AN")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


def _workflow(tmp_path: Path, *, advance: int) -> CaseWorkflow:
    import json

    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: PILOT_CLOCK)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "a")
    org = json.loads((PILOT / "input" / "organization.json").read_text(encoding="utf-8"))
    if advance:
        org["ledger"] = [e for e in org["ledger"] if e["kind"] == "ADVANCE_RECEIVED"]
    else:
        org["ledger"] = []
    from invoice_referee.domain.organization import OrganizationContext

    wf.import_company_context(
        OrganizationContext.model_validate_json(json.dumps(org)), origin="SIMULATED"
    )
    return wf


async def _seed(wf: CaseWorkflow, *, publish: bool = True, declared_advance: str | None = "4000000") -> str:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="a", occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:2", expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{TENANT}/{root}/hd.pdf"),)),
    )
    if publish:
        with wf.db.transaction() as cx:
            wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=_report(declared_advance=declared_advance))
    return root


async def _submit(wf: CaseWorkflow, root: str) -> None:
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    session_id = str(wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"])
    await wf.execute(
        CommandContext(session_id=session_id, actor_id=EMPLOYEE, command_id="cmd:submit", expected_case_version=int(version)),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="p")),
    )


async def _assess(wf: CaseWorkflow, root: str) -> None:
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())


async def _record_advance(wf: CaseWorkflow, root: str, *, method: str, status: str, key: str, command_id: str | None = None) -> None:
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    session = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACCOUNTANT, command_id=command_id or f"cmd:rec:{key}", expected_case_version=int(version)),
        RecordActual(root_id=root, money=RecordMoneyInput(
            external_key=key, claimed_kind="ADVANCE_RECEIVED", claimed_scope=ACTIVITY,
            payer="company:demo", payee=EMPLOYEE, amount=4_000_000,
            event_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
            completion_claim="Kế toán đã kiểm tra chứng từ ứng và xác nhận đã giao.",
            reason="Ghi nhận tiền ứng thực nhận",
            instrument_method=method, instrument_status=status,  # type: ignore[arg-type]
        )),
    )


async def _confirm_history_coverage(wf: CaseWorkflow, root: str) -> None:
    row = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))
    source = wf._query_one("SELECT source_id, digest FROM case_sources WHERE root_id = ?", (root,))
    session = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=ACCOUNTANT,
            command_id=f"cmd:coverage:{root}",
            expected_case_version=int(row["version"]),
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
                exact_quote="Sổ giao dịch đối chiếu đầy đủ",
            ),),
            reason="Đã đối chiếu toàn bộ lịch sử tiền của đúng hoạt động.",
        ),
    )


def _money(wf: CaseWorkflow, root: str) -> dict:
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        session = wf._system_session(TENANT)
        view = wf._case_view(cx, row)
    return {
        "state": view.state,
        "instructions": [(i.direction, i.amount) for i in view.instructions],
        "A": view.actual_money.A,
        "S": view.actual_money.S,
        "E": view.actual_money.E,
    }


async def test_flow1_no_record_blocks_then_transfer_records_and_collects(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, advance=0)
    root = await _seed(wf)
    await _submit(wf, root)
    await _assess(wf, root)
    blocked = _money(wf, root)
    assert blocked["instructions"] == [], "no advance record must not issue a wrong instruction"
    assert blocked["A"].state == "UNKNOWN"
    assert blocked["S"].state == "UNKNOWN"

    await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:ADV-F01")
    await _confirm_history_coverage(wf, root)
    done = _money(wf, root)
    assert done["instructions"] == [("COLLECT", 760_000)]
    assert done["A"].value == 4_000_000
    assert done["S"].value == -760_000


async def test_flow1_cash_voucher_also_records_and_collects(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, advance=0)
    root = await _seed(wf)
    await _submit(wf, root)
    await _assess(wf, root)
    await _record_advance(wf, root, method="CASH", status="COMPLETED", key="cash:PC-F01")
    await _confirm_history_coverage(wf, root)
    done = _money(wf, root)
    assert done["instructions"] == [("COLLECT", 760_000)]
    assert done["A"].value == 4_000_000


async def test_flow1_pending_transfer_does_not_record_received(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, advance=0)
    root = await _seed(wf)
    await _submit(wf, root)
    await _assess(wf, root)
    await _record_advance(wf, root, method="TRANSFER", status="PENDING", key="bank:ADV-pending")
    done = _money(wf, root)
    assert done["instructions"] == [], "a pending transfer must not establish A"
    assert done["A"].state == "UNKNOWN"


async def test_flow2_existing_record_collects_without_reupload(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, advance=4_000_000)
    root = await _seed(wf)
    await _submit(wf, root)
    await _assess(wf, root)
    done = _money(wf, root)
    assert done["instructions"] == [("COLLECT", 760_000)]
    assert done["A"].value == 4_000_000
    assert done["E"].value == 3_240_000


async def test_retry_does_not_double_count_the_advance(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, advance=0)
    root = await _seed(wf)
    await _submit(wf, root)
    await _assess(wf, root)
    await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:ADV-dup", command_id="cmd:rec:dup-1")
    # A retry with the SAME external key is idempotent: no second A.
    await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:ADV-dup", command_id="cmd:rec:dup-2")
    await _confirm_history_coverage(wf, root)
    done = _money(wf, root)
    assert done["A"].value == 4_000_000  # not 8m
