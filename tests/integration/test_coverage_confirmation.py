"""Accountant coverage confirmation enters typed admission, not a text answer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, CreateDraft
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:coverage-test"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
NOW = datetime.fromisoformat("2026-10-15T12:00:00+07:00")
STATEMENT = b"%PDF-1.4\nSao ke cong ty\n%%EOF\n"
FLOW_KINDS = [
    "ADVANCE_RECEIVED",
    "REIMBURSEMENT_RECEIVED",
    "EMPLOYEE_RETURN",
    "REVERSAL",
    "OBSERVED_UNALLOCATED",
]


@pytest.fixture
async def workspace(tmp_path: Path):
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    workflow = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: NOW)
    workflow.import_company_context(
        OrganizationContext(
            tenant=TENANT,
            organization_id=TENANT,
            company_name="Công ty Coverage Demo",
            people=(
                {"id": EMPLOYEE, "name": "Nguyễn An"},
                {"id": ACCOUNTANT, "name": "Kế toán Demo"},
            ),
        ),
        origin="SIMULATED",
    )
    employee_session = workflow.start_session(
        tenant=TENANT, persona="employee", actor_id=EMPLOYEE
    )
    created = await workflow.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id=EMPLOYEE,
            command_id="cmd:create-coverage-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:coverage-test",
                name="Tiếp khách đối tác",
                occurred_at=NOW,
                declared_purpose="Làm việc với đối tác",
            )
        ),
    )
    account_session = workflow.start_session(
        tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT
    )
    app = create_app(workflow, mode="STUB", frontend_dir=None)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    client.cookies.set(SESSION_COOKIE, account_session.session_id)
    yield client, workflow, created.case_view.id
    await client.aclose()


async def test_accountant_coverage_is_structured_and_used_by_admission(workspace) -> None:
    client, workflow, root = workspace
    case = await client.get(f"/api/cases/{root}")
    attached = await client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("so-giao-dich.pdf", STATEMENT, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:attach-ledger-statement",
            "X-Expected-Version": str(case.json()["version"]),
        },
    )
    assert attached.status_code == 200, attached.text
    case_view = attached.json()["case_view"]
    statement = case_view["sources"][0]
    response = await client.post(
        f"/api/cases/{root}/coverage",
        headers={
            "X-Command-Id": "cmd:confirm-history",
            "X-Expected-Version": str(case_view["version"]),
        },
        json={
            "start": "2026-10-01T00:00:00+07:00",
            "funds": ["company:bank-demo"],
            "flow_kinds": FLOW_KINDS,
            "opening_balance": 0,
            "unallocated_event_ids": [],
            "witness_refs": [
                {
                    "source_id": statement["id"],
                    "source_sha256": statement["digest"],
                    "page": 1,
                    "exact_quote": "Sao ke cong ty",
                }
            ],
            "reason": "Đã đối chiếu sổ ngân hàng của công ty trong toàn bộ kỳ và đúng hoạt động này.",
        },
    )

    assert response.status_code == 200, response.text
    updated = response.json()["case_view"]
    assert updated["coverage_record"]["scope"] == updated["activity"]
    assert updated["coverage_record"]["employee"] == EMPLOYEE
    assert updated["coverage_record"]["actor"] == ACCOUNTANT
    assert updated["coverage_record"]["opening_balance"]["value"] == 0
    assert updated["coverage_record"]["ledger_version"] == "0"
    assert updated["coverage_current"] is True
    with workflow.db.connect() as cx:
        from invoice_referee.domain.evidence import ReadResult
        from invoice_referee.workflow.evidence_assessment import build_evidence_assessment_input

        assessment = build_evidence_assessment_input(
            cx,
            tenant=TENANT,
            root_id=root,
            report=ReadResult(),
            as_of=NOW,
        )
    assert assessment.coverage is not None
    assert set(assessment.coverage.flow_kinds) == set(FLOW_KINDS)


async def test_initial_history_confirmation_needs_no_fabricated_pdf_or_fund(workspace):
    client, workflow, root = workspace
    view = (await client.get(f"/api/cases/{root}")).json()
    response = await client.post(
        f"/api/cases/{root}/money-history/confirm",
        headers={"X-Command-Id": "cmd:initial-history", "X-Expected-Version": str(view["version"])},
        json={"all_prior_money_recorded": True},
    )
    assert response.status_code == 200, response.text
    view = response.json()["case_view"]
    assert view["coverage_current"] is True
    record = view["coverage_record"]
    assert record["source"] == "MANAGED_HISTORY"
    assert record["actor"] == ACCOUNTANT
    assert record["employee"] == EMPLOYEE
    assert record["witness_refs"] == []  # Never invent a quote proving absence.
    assert record["ledger_version"] == "0"
    assert workflow._query_one("SELECT COUNT(*) AS n FROM money_events")["n"] == 0

    # An unchanged checkpoint remains usable after a restart and another day.
    restarted = CaseWorkflow(workflow.db, uploads_dir=workflow.uploads_dir,
                             clock=lambda: datetime.fromisoformat("2026-10-16T12:00:00+07:00"))
    session = restarted.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    assert restarted.view(session, root).coverage_current is True


async def test_initial_history_requires_explicit_confirmation_and_current_version(workspace):
    client, workflow, root = workspace
    view = (await client.get(f"/api/cases/{root}")).json()
    for statement in (False, True):
        response = await client.post(
            f"/api/cases/{root}/money-history/confirm",
            headers={"X-Command-Id": f"cmd:bad-history:{statement}",
                     "X-Expected-Version": str(view["version"] - 1 if statement else view["version"])},
            json={"all_prior_money_recorded": statement},
        )
        assert response.status_code in (400, 409), response.text
    assert workflow._query_one("SELECT COUNT(*) AS n FROM case_coverage_records")["n"] == 0


async def test_employee_cannot_establish_initial_history(workspace):
    client, workflow, root = workspace
    employee = workflow.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    client.cookies.set(SESSION_COOKIE, employee.session_id)
    response = await client.post(
        f"/api/cases/{root}/money-history/confirm",
        headers={"X-Command-Id": "cmd:employee-initial", "X-Expected-Version": "1"},
        json={"all_prior_money_recorded": True},
    )
    assert response.status_code == 403, response.text


async def test_employee_cannot_confirm_money_history(workspace) -> None:
    _, workflow, root = workspace
    from httpx import ASGITransport, AsyncClient
    from invoice_referee.api.app import create_app

    employee = workflow.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    app = create_app(workflow, mode="STUB", frontend_dir=None)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    client.cookies.set(SESSION_COOKIE, employee.session_id)
    try:
            response = await client.post(
                f"/api/cases/{root}/coverage",
                headers={"X-Command-Id": "cmd:employee-coverage"},
                json={
                    "start": "2026-10-01T00:00:00+07:00",
                    "funds": ["Tài khoản ngân hàng công ty"],
                    "flow_kinds": FLOW_KINDS,
                    "opening_balance": 0,
                    "reason": "Đã đối chiếu đầy đủ trong kỳ.",
                },
        )
    finally:
        await client.aclose()
    assert response.status_code == 403
    assert workflow._query_one("SELECT COUNT(*) AS n FROM case_coverage_records")["n"] == 0


async def test_coverage_cannot_use_a_future_as_of_or_start_date(workspace) -> None:
    client, workflow, root = workspace
    case = await client.get(f"/api/cases/{root}")
    response = await client.post(
        f"/api/cases/{root}/coverage",
        headers={
            "X-Command-Id": "cmd:future-coverage",
            "X-Expected-Version": str(case.json()["version"]),
        },
        json={
            "start": "2026-10-16T00:00:00+07:00",
            "funds": ["Tài khoản ngân hàng công ty"],
            "flow_kinds": FLOW_KINDS,
            "opening_balance": 0,
            "unallocated_event_ids": [],
            "witness_refs": [],
            "reason": "Ngày bắt đầu nằm trong tương lai.",
        },
    )
    assert response.status_code == 400
    assert workflow._query_one("SELECT COUNT(*) AS n FROM case_coverage_records")["n"] == 0


async def test_backdated_event_invalidates_only_its_root_coverage(workspace) -> None:
    from invoice_referee.domain.common import EvidenceRef
    from invoice_referee.domain.commands import RecordActual
    from invoice_referee.domain.finance import RecordMoneyInput
    from invoice_referee.domain.evidence import ReadResult
    from invoice_referee.workflow.evidence_assessment import build_evidence_assessment_input

    client, workflow, root = workspace
    other_employee = "employee:employee-b"
    employee_session = workflow.start_session(
        tenant=TENANT, persona="employee", actor_id=other_employee
    )
    other_created = await workflow.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id=other_employee,
            command_id="cmd:create-other-history-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:other-coverage-test",
                name="Công việc khác",
                occurred_at=NOW,
                declared_purpose="Công việc khác",
            )
        ),
    )
    other_attachment = await client.post(
        f"/api/cases/{other_created.case_view.id}/sources",
        files={"files": ("other-so-giao-dich.pdf", STATEMENT, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:attach-other-statement",
            "X-Expected-Version": str(other_created.case_view.version),
        },
    )
    other_case = other_attachment.json()["case_view"]
    other_statement = other_case["sources"][0]
    case = (await client.get(f"/api/cases/{root}")).json()
    statement_response = await client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("so-giao-dich.pdf", STATEMENT, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:attach-statement-isolation",
            "X-Expected-Version": str(case["version"]),
        },
    )
    statement = statement_response.json()["case_view"]["sources"][0]
    confirmed = await client.post(
        f"/api/cases/{root}/coverage",
        headers={
            "X-Command-Id": "cmd:confirm-history-isolation",
            "X-Expected-Version": str(statement_response.json()["case_view"]["version"]),
        },
        json={
            "start": "2026-10-01T00:00:00+07:00",
            "funds": ["Tài khoản ngân hàng công ty"],
            "flow_kinds": FLOW_KINDS,
            "opening_balance": 0,
            "unallocated_event_ids": [],
            "witness_refs": [{
                "source_id": statement["id"],
                "source_sha256": statement["digest"],
                "page": 1,
                "exact_quote": "Sao ke cong ty",
            }],
            "reason": "Đã đối chiếu đủ toàn bộ sổ tiền của công việc đang mở.",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    # A backdated event on another root does not change the covered root's
    # ledger version or its admitted coverage.
    accountant_session = workflow.start_session(
        tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT
    )
    await workflow.execute(
        CommandContext(
            session_id=accountant_session.session_id,
            actor_id=ACCOUNTANT,
            command_id="cmd:other-root-return",
            expected_case_version=other_case["version"],
        ),
        RecordActual(
            root_id=other_created.case_view.id,
            money=RecordMoneyInput(
                external_key="bank:OTHER-ADVANCE-1",
                claimed_kind="ADVANCE_RECEIVED",
                claimed_scope="activity:proposed:other-coverage-test",
                payer="company:demo",
                payee=other_employee,
                amount=10,
                event_at="2026-10-02T09:00:00+07:00",
                completion_claim="Kế toán đã đối chiếu giao dịch hoàn tiền.",
                refs=(EvidenceRef(
                    source_id=other_statement["id"],
                    source_sha256=other_statement["digest"],
                    page=1,
                    exact_quote="Sao ke cong ty",
                ),),
                reason="Giao dịch ở hồ sơ khác.",
            ),
        ),
    )

    with workflow.db.connect() as cx:
        still_valid = build_evidence_assessment_input(
            cx,
            tenant=TENANT,
            root_id=root,
            report=ReadResult(),
            as_of=NOW,
        )
    assert still_valid.coverage is not None

    # A backdated unallocated movement written into the covered root advances
    # its root-local ledger version and makes coverage unusable.
    current = await client.get(f"/api/cases/{root}")
    witness = current.json()["sources"][0]
    await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:root-backdated-payment",
            "X-Expected-Version": str(current.json()["version"]),
        },
        json={
            "money": {
                "external_key": "bank:BACKDATED-UNALLOCATED-1",
                "claimed_kind": "OBSERVED_UNALLOCATED",
                "claimed_scope": current.json()["activity"],
                "payer": "company:demo",
                "payee": EMPLOYEE,
                "amount": 50_000,
                "event_at": "2026-10-02T09:00:00+07:00",
                "completion_claim": "Kế toán đã đối chiếu khoản chi bổ sung.",
                "instrument_status": "UNKNOWN",
                "reason": "Bổ sung giao dịch đã phát sinh trong kỳ.",
                "refs": [{
                    "source_id": witness["id"],
                    "source_sha256": witness["digest"],
                    "page": 1,
                    "exact_quote": "Sao ke cong ty",
                }],
            }
        },
    )
    with workflow.db.connect() as cx:
        stale = build_evidence_assessment_input(
            cx,
            tenant=TENANT,
            root_id=root,
            report=ReadResult(),
            as_of=NOW,
        )
    assert stale.coverage is None
    assert any(issue.field_or_rule == "ledger:coverage" for issue in stale.admission_issues)
