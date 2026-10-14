"""TC01 with no confirmed advance record: A/S UNKNOWN, accountant verification.

The paper still declares a 4.000.000 đ advance, but the company has no
ADVANCE_RECEIVED record. Coverage alone must not assert A=0 (which would issue a
wrong PAY for the full cost): A/S stay UNKNOWN, no instruction is issued, and the
accountant is asked to verify/record the advance. After the accountant records
the actual 4m through the existing granted path, re-assessment reaches COLLECT
760000 without double counting; a pending/failed record must NOT become A.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
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

TENANT = "tenant:tc01-no-adv"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
ACTIVITY = "activity:tc01"
SHA = "a" * 64
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _report() -> ReadResult:
    paper = DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("purpose", "Chi phí tiếp khách"),
                _found("printed_total", "3240000"), _found("declared_advance", "4000000"),
                _found("printed_return", "760000")),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Chi phí tiếp khách"), _found("amount", "3240000"),
            _found("invoice_refs", ("00000101",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00000101"), _found("issuer_name", "An Bình"),
                _found("buyer_person_name", "Nguyễn An"), _found("subtotal", "3000000"),
                _found("tax", "240000"), _found("total_amount", "3240000"),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


def _org(*, advance: int) -> object:
    from invoice_referee.domain.organization import OrganizationContext

    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    ledger = []
    if advance:
        ledger.append({"id": "adv:tc01", "external_key": "company:bank:ADV-TC01",
                       "kind": "ADVANCE_RECEIVED", "scope": ACTIVITY, "payer": "company:demo",
                       "payee": EMPLOYEE, "amount": advance,
                       "event_at": "2026-10-05T09:00:00+07:00",
                       "recorded_at": "2026-10-05T10:00:00+07:00",
                       "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"})
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "tenant": TENANT, "profile": "WORK_EXPENSE",
        "activity": {"activity_id": ACTIVITY, "name": "Tiếp khách", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "Chi phí tiếp khách", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": EMPLOYEE, "name": "Nguyễn An"},),
        "budgets": ({"id": "b:1", "activity": ACTIVITY, "amount": 8_000_000, "effect_range": interval,
                     "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": ACTIVITY, "max_amount": 8_000_000, "effective_from": interval[0],
             "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": ACTIVITY,
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": tuple(ledger),
        "coverage": {"employee": EMPLOYEE, "activity": ACTIVITY,
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


async def _seed(tmp_path: Path, *, advance: int) -> tuple[CaseWorkflow, str]:
    db = Database(tmp_path / "a.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "art")
    wf.import_company_context(_org(advance=advance), origin="SIMULATED")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="Tiếp khách",
                                               occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:2",
                       expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(
            filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{TENANT}/{root}/hd.pdf"),)),
    )
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=_report())
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    return wf, root


def _money(wf: CaseWorkflow, root: str) -> dict:
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        view = wf._case_view(cx, row)
    return {
        "state": view.state,
        "instructions": [(i.direction, i.amount) for i in view.instructions],
        "A": view.actual_money.A, "S": view.actual_money.S, "E": view.actual_money.E,
        "issues": [(i.kind, i.field_or_rule, i.owner) for i in view.issues],
    }


async def _record(wf: CaseWorkflow, root: str, *, method: str, status: str) -> None:
    with wf.db.transaction() as cx:
        version = int(cx.execute("SELECT version FROM cases WHERE id = ?", (root,)).fetchone()["version"])
    session = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACCOUNTANT,
                       command_id=f"cmd:rec:{method}:{status}", expected_case_version=version),
        RecordActual(root_id=root, money=RecordMoneyInput(
            external_key=f"bank:ADV-{method}-{status}", claimed_kind="ADVANCE_RECEIVED",
            claimed_scope=ACTIVITY, payer="company:demo", payee=EMPLOYEE, amount=4_000_000,
            event_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
            completion_claim="Kế toán đã kiểm tra chứng từ ứng và xác nhận đã giao.",
            reason="Ghi nhận tiền ứng thực nhận",
            instrument_method=method, instrument_status=status)),  # type: ignore[arg-type]
    )


async def test_tc01_without_advance_record_is_unknown_and_asks_accountant(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path, advance=0)
    state = _money(wf, root)
    assert state["instructions"] == [], "no advance record must not issue money from the printed number"
    assert state["A"].state == "UNKNOWN"
    assert state["S"].state == "UNKNOWN"
    assert any(rule == "ledger:advance" and owner == "accountant" for _, rule, owner in state["issues"]), \
        "the accountant must be asked to verify/record the advance"


async def test_tc01_recording_the_advance_then_collects(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path, advance=0)
    await _record(wf, root, method="TRANSFER", status="COMPLETED")
    done = _money(wf, root)
    assert done["instructions"] == [("COLLECT", 760_000)]
    assert done["A"].value == 4_000_000
    assert done["S"].value == -760_000


async def test_tc01_pending_record_does_not_establish_a(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path, advance=0)
    await _record(wf, root, method="TRANSFER", status="PENDING")
    state = _money(wf, root)
    assert state["instructions"] == []
    assert state["A"].state == "UNKNOWN"


async def test_tc01_existing_record_still_collects(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path, advance=4_000_000)
    done = _money(wf, root)
    assert done["instructions"] == [("COLLECT", 760_000)]
    assert done["A"].value == 4_000_000
