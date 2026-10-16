"""Shared S6 workflow seeding (contexts, workflow, seeded cases)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, CreateDraft
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow
from tests.tc18_shapes import (
    _acceptance,
    _acceptance as acc,
    _invoice,
    _paper,
    _transfer,
    _transfer as trf,
)

TENANT = "tenant:t"
EMPLOYEE = "employee:a"
ACCOUNTANT = "employee:accountant"
ACTIVITY = "activity:1"
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _context(
    *,
    except_max: int | None = 2_000_000,
    except_to: str | None = "2026-12-31T23:59:59+07:00",
) -> dict:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    grants = [
        {
            "id": "g:r",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["RECOGNIZE_COST"],
            "scope": ACTIVITY,
            "max_amount": 8_000_000,
            "effective_from": interval[0],
            "effective_to": interval[1],
        },
        {
            "id": "g:i",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
            "scope": ACTIVITY,
            "max_amount": 4_000_000,
            "effective_from": interval[0],
            "effective_to": interval[1],
        },
    ]
    if except_max is not None:
        grants.append(
            {
                "id": "g:except-sim",
                "version": "v1",
                "actor": ACCOUNTANT,
                "actions": ["EXCEPT_POLICY"],
                "scope": ACTIVITY,
                "max_amount": except_max,
                "effective_from": interval[0],
                "effective_to": except_to,
            }
        )
    return {
        "organization_id": TENANT,
        "profile": "WORK_EXPENSE",
        "activity": {
            "activity_id": ACTIVITY,
            "name": "a",
            "occurred_at": "2026-10-06T09:00:00+07:00",
            "purpose": "p",
            "profile": "WORK_EXPENSE",
            "authorization": {"id": "auth:1"},
        },
        "people": ({"id": EMPLOYEE, "name": "NV"}, {"id": ACCOUNTANT, "name": "KT"}),
        "budgets": (),
        "grants": tuple(grants),
        "ledger": (
            {
                "id": "adv:1",
                "external_key": "bank:ADV-1",
                "kind": "ADVANCE_RECEIVED",
                "scope": ACTIVITY,
                "payer": "company:demo",
                "payee": EMPLOYEE,
                "amount": 5_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "recorded_at": "2026-10-05T10:00:00+07:00",
                "verification_state": "CONFIRMED",
                "allocation_state": "ALLOCATED",
            },
        ),
        "coverage": {
            "activity": ACTIVITY,
            "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-10-10T18:00:00+07:00",
            "fund_ids": ["company:bank"],
            "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
            "opening_by_fund": {"company:bank": 0},
            "ledger_version": "l:v1",
            "witness_keys": ["cov:1"],
        },
    }


def _report(*, consistent: bool = True) -> ReadResult:
    issuer = "Công ty An Thịnh" if consistent else "Trung tâm Kỹ thuật Phúc An"
    payee = "Công ty An Thịnh"
    paper = _paper(labor_reason="Nhà cung cấp không xuất hóa đơn")
    return ReadResult(
        provider_mode="LIVE",
        data_origin="LIVE_READ",
        documents=(
            paper,
            _invoice(),
            acc(issuer=issuer),
            trf(payee=payee, status="Thành công"),
        ),
    )


def _workflow(tmp_path: Path, **ctx_kw) -> CaseWorkflow:
    import json

    from invoice_referee.domain.organization import OrganizationContext

    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: AS_OF)
    wf.enable_evidence_read(
        reader=object(), classifier=object(), artifacts_root=tmp_path / "artifacts"
    )
    wf.import_company_context(
        OrganizationContext.model_validate_json(json.dumps(_context(**ctx_kw))),
        origin="SIMULATED",
    )
    return wf


async def _seed(wf: CaseWorkflow, *, consistent: bool = True) -> tuple[str, object]:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id="cmd:1",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=ACTIVITY,
                name="a",
                occurred_at="2026-10-06T09:00:00+07:00",
                declared_purpose="p",
            )
        ),
    )
    root = created.case_view.id
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(
            cx, tenant=TENANT, root_id=root, report=_report(consistent=consistent)
        )
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, session, row, wf._now_iso())
    return root, session


def _issues(wf: CaseWorkflow, root: str):
    with wf.db.connect() as cx:
        return cx.execute(
            "SELECT * FROM case_issues WHERE root_id = ?", (root,)
        ).fetchall()
