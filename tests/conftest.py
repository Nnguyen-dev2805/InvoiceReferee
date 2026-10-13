"""Shared app fixture for integration tests (contracts §9).

One tmp DB + one CaseWorkflow + create_app(workflow): the same boundary the
HTTP tests exercise. Commands always run through CaseWorkflow.execute and
views through CaseWorkflow.view; the fixture never writes SQL for behaviour
under test, only to observe stored state.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.domain.case import CaseView, CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CommandResult,
    CreateDraft,
    Declaration,
    ReviseDeclaration,
    SourceUpload,
)
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONTEXT_PATH = PROJECT_ROOT / "data" / "demo" / "company-context.json"

TENANT_DEMO = "tenant:demo"
DEFAULT_ACTOR = "employee:employee-a"
DEFAULT_OCCURRED_AT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


class AppFixture:
    """Drives the real workflow/app for integration tests."""

    FINANCIAL_TABLE_HINTS = ("money", "expense", "instruction", "ledger", "actual")

    def __init__(self, tmp_path: Path) -> None:
        self.db = Database(tmp_path / "app.sqlite")
        self.db.migrate()
        self.workflow = CaseWorkflow(
            self.db,
            uploads_dir=tmp_path / "uploads",
            # A small cap keeps the oversize-upload check fast; the real
            # 20 MiB pilot ceiling is pinned in test_root_session.py.
            max_source_bytes=4096,
        )
        self.workflow.import_demo_context(DEMO_CONTEXT_PATH, origin="SIMULATED")
        self.app = create_app(self.workflow, mode="STUB", frontend_dir=None)
        self._transport = ASGITransport(app=self.app)
        self._clients: list[AsyncClient] = []
        self._sessions: dict[tuple[str, str], str] = {}
        self.client = self.fresh_client()
        self.client.cookies.set(SESSION_COOKIE, self.session_for(TENANT_DEMO))

    # -- sessions and contexts ---------------------------------------------
    def session_for(
        self,
        tenant: str = TENANT_DEMO,
        *,
        actor: str | None = None,
        persona: str = "employee",
    ) -> str:
        actor_id = actor or self.default_actor(tenant)
        key = (tenant, actor_id)
        if key not in self._sessions:
            session = self.workflow.start_session(
                tenant=tenant, persona=persona, actor_id=actor_id
            )
            self._sessions[key] = session.session_id
        return self._sessions[key]

    @staticmethod
    def default_actor(tenant: str) -> str:
        if tenant == TENANT_DEMO:
            return DEFAULT_ACTOR
        return f"employee:{tenant.split(':')[-1]}"

    def fresh_client(self) -> AsyncClient:
        client = AsyncClient(transport=self._transport, base_url="http://testserver")
        self._clients.append(client)
        return client

    def client_for(self, *, tenant: str, persona: str = "employee") -> AsyncClient:
        client = self.fresh_client()
        client.cookies.set(SESSION_COOKIE, self.session_for(tenant, persona=persona))
        return client

    def new_command_id(self) -> str:
        return f"cmd:{uuid.uuid4().hex}"

    def ctx(
        self,
        *,
        tenant: str = TENANT_DEMO,
        actor: str | None = None,
        session_id: str | None = None,
        expected_case_version: int = 0,
        command_id: str | None = None,
    ) -> CommandContext:
        actor_id = actor or self.default_actor(tenant)
        return CommandContext(
            session_id=session_id or self.session_for(tenant, actor=actor_id),
            actor_id=actor_id,
            command_id=command_id or self.new_command_id(),
            expected_case_version=expected_case_version,
        )

    # -- commands ------------------------------------------------------------
    async def create(
        self,
        *,
        employee: str,
        activity: str,
        tenant: str = TENANT_DEMO,
        activity_name: str | None = None,
        occurred_at: datetime | None = None,
        declared_purpose: str = "Công tác",
        expected_case_version: int = 0,
    ) -> CommandResult:
        command = CreateDraft(
            activity_data=ActivityData(
                activity_id=activity,
                name=activity_name or activity,
                occurred_at=occurred_at or DEFAULT_OCCURRED_AT,
                declared_purpose=declared_purpose,
            )
        )
        context = self.ctx(
            tenant=tenant, actor=employee, expected_case_version=expected_case_version
        )
        return await self.workflow.execute(context, command)

    async def attach(
        self, context: CommandContext, root_id: str, uploads: tuple[SourceUpload, ...]
    ) -> CommandResult:
        return await self.workflow.execute(
            context, AttachSources(root_id=root_id, uploads=uploads)
        )

    async def revise(
        self, context: CommandContext, root_id: str, declaration: Declaration
    ) -> CommandResult:
        return await self.workflow.execute(
            context, ReviseDeclaration(root_id=root_id, declaration=declaration)
        )

    def view(self, context: CommandContext, root_id: str) -> CaseView:
        return self.workflow.view(context, root_id)

    # -- stored-state observation -------------------------------------------
    def query_one(self, sql: str, params: tuple[object, ...] = ()):
        connection = self.db.connect()
        try:
            return connection.execute(sql, params).fetchone()
        finally:
            connection.close()

    def case_count(self, tenant: str = TENANT_DEMO) -> int:
        row = self.query_one("SELECT COUNT(*) AS n FROM cases WHERE tenant = ?", (tenant,))
        return int(row["n"])

    def input_revision(self, root_id: str) -> int:
        row = self.query_one("SELECT input_revision AS n FROM cases WHERE id = ?", (root_id,))
        return int(row["n"])

    def audit_actions(self) -> list[str]:
        connection = self.db.connect()
        try:
            rows = connection.execute(
                "SELECT action FROM audit_events ORDER BY id"
            ).fetchall()
            return [str(row["action"]) for row in rows]
        finally:
            connection.close()

    def budget_amount(
        self, activity_id: str, tenant: str = TENANT_DEMO
    ) -> int | None:
        row = self.query_one(
            "SELECT budget_amount AS amount FROM context_activities "
            "WHERE activity_id = ? AND tenant = ?",
            (activity_id, tenant),
        )
        return None if row is None else row["amount"]

    def financial_row_count(self) -> int:
        connection = self.db.connect()
        try:
            names = [
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ]
            total = 0
            for name in names:
                if any(hint in name for hint in self.FINANCIAL_TABLE_HINTS):
                    total += int(
                        connection.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"]
                    )
            return total
        finally:
            connection.close()

    async def close(self) -> None:
        for client in self._clients:
            await client.aclose()


@pytest.fixture
async def app_fixture(tmp_path: Path):
    fixture = AppFixture(tmp_path)
    try:
        yield fixture
    finally:
        await fixture.close()
