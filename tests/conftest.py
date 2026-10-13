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
    AnswerIssue,
    AttachSources,
    CommandResult,
    CreateDraft,
    Decide,
    Declaration,
    ReviseDeclaration,
    SourceUpload,
    Submit,
)
from invoice_referee.evaluation.models import TranscriptionFact
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_CONTEXT_PATH = PROJECT_ROOT / "data" / "demo" / "company-context.json"

TENANT_DEMO = "tenant:demo"
DEFAULT_ACTOR = "employee:employee-a"
DEFAULT_OCCURRED_AT = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def upload(name: str = "hoadon.pdf") -> SourceUpload:
    return SourceUpload(
        filename=name,
        media="PDF",
        digest="a" * 64,
        storage_key=f"{TENANT_DEMO}/root/{name}",
    )


# STUB packet transcriptions (test input only; never an app decision).
TEST_PACKETS: dict[str, dict[str, object]] = {
    # T8/E5/C3/A2/B8, S=3m -> one PAY instruction of 3m.
    "travel-clean": {
        "facts": [
            {"field": "incurred", "value": 8_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 5_000_000, "role": "PAYMENT"},
            {"field": "paid_company", "value": 3_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
        ],
        "relations": [("expense_activity", "expense:1", "activity:travel-clean", "SUPPORTED")],
    },
    # No payer on any document -> FACT issue, no instruction.
    "missing-payer": {
        "facts": [
            {"field": "incurred", "value": 5_000_000, "role": "INVOICE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
        ],
    },
    # No coverage -> A/P/R unknown, no balanced claim.
    "missing-history": {
        "facts": [
            {"field": "incurred", "value": 5_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 5_000_000, "role": "PAYMENT"},
        ],
    },
    # E6/A2 => S4 => one I4.
    "coverage-e6": {
        "facts": [
            {"field": "incurred", "value": 6_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 6_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:e6", "role": "INVOICE"},
        ],
    },
    # Same economic invoice, filed under a second activity in the same tenant.
    "dup-invoice": {
        "facts": [
            {"field": "incurred", "value": 6_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 6_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:dup", "role": "INVOICE"},
        ],
    },
    # Same root, basisX then a replacement basisY with the same S.
    "changed-basis": {
        "facts": [
            {"field": "incurred", "value": 6_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 6_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:basis-x", "role": "INVOICE"},
        ],
    },
    "changed-basis-v2": {
        "facts": [
            {"field": "incurred", "value": 6_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 6_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:basis-y", "role": "INVOICE"},
        ],
    },
    # E6/A2 => S4 => one I4, used by the money-execution tests.
    "money-i4": {
        "facts": [
            {"field": "incurred", "value": 6_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 6_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:money-i4", "role": "INVOICE"},
        ],
    },
    # E2/A2 => S0 with clean coverage => BALANCED/SETTLED, no instruction.
    "balanced-clean": {
        "facts": [
            {"field": "incurred", "value": 2_000_000, "role": "INVOICE"},
            {"field": "paid_employee", "value": 2_000_000, "role": "PAYMENT"},
            {"field": "advance", "value": 2_000_000, "role": "ADVANCE"},
            {"field": "coverage", "value": 1, "role": "LEDGER"},
            {"field": "economic_key", "value": "invoice:balanced", "role": "INVOICE"},
        ],
    },
}


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
        self.context_path = DEMO_CONTEXT_PATH
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

    # -- T6 submission helpers (contracts §9) --------------------------------
    async def submit_packet(
        self, name: str, *, mode: str = "STUB", activity: str = "activity:travel-a"
    ) -> CaseView:
        """Create a root from a named STUB packet and submit it.

        The packet name selects test input only; it never drives an app
        decision. A transcription is seeded for the root, a source is attached,
        and Submit runs the assessment. Re-submitting the same packet on the
        same activity targets the same root (one root per activity).
        """
        from invoice_referee.evaluation.models import Transcription

        spec = TEST_PACKETS[name]
        # File on the seeded authorized activity so the packet's scenario (not a
        # missing budget) drives the outcome; the packet name only selects input.
        created = await self.create(employee=DEFAULT_ACTOR, activity=activity)
        root = created.case_view.id
        self._last_root = root
        # Seed the STUB transcription (hand-transcribed literal reading).
        transcription = Transcription(
            facts=tuple(
                TranscriptionFact(**fact)  # type: ignore[arg-type]
                for fact in spec["facts"]
            ),
            relations=tuple(spec.get("relations", ())),
        )
        connection = self.db.connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO case_transcriptions (root_id, transcription_json, "
                "created_at) VALUES (?, ?, ?)",
                (root, transcription.model_dump_json(), DEFAULT_OCCURRED_AT.isoformat()),
            )
        finally:
            connection.close()
        if self._source_count(root) == 0:
            await self.attach(
                self.ctx(actor=DEFAULT_ACTOR, expected_case_version=self._version(root)),
                root,
                (upload(),),
            )
        submitted = await self.workflow.execute(
            self.ctx(actor=DEFAULT_ACTOR, expected_case_version=self._version(root)),
            Submit(
                root_id=root,
                declaration=Declaration(
                    activity_id=activity, declared_purpose="Công tác"
                ),
            ),
        )
        return submitted.case_view

    def _source_count(self, root_id: str) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM case_sources WHERE root_id = ?", (root_id,)
        )
        return int(row["n"])

    async def answer(self, root_id: str, answer, *, actor: str) -> CaseView:
        context = self.ctx(actor=actor, expected_case_version=self._version(root_id))
        result = await self.workflow.execute(context, AnswerIssue(root_id=root_id, answer=answer))
        return result.case_view

    async def decide(self, root_id: str, decision, *, actor: str) -> CaseView:
        context = self.ctx(actor=actor, expected_case_version=self._version(root_id))
        result = await self.workflow.execute(context, Decide(root_id=root_id, decision=decision))
        return result.case_view

    def question_card(self, root_id: str, issue_id: str):
        from invoice_referee.domain.issues import QuestionCard

        row = self.query_one(
            "SELECT payload_json FROM case_issues WHERE id = ? AND root_id = ?",
            (issue_id, root_id),
        )
        if row is None:
            raise KeyError(issue_id)
        from invoice_referee.domain.issues import BusinessIssue

        issue = BusinessIssue.model_validate_json(row["payload_json"])
        return QuestionCard(
            issue_id=issue.id,
            known_facts=(),
            excerpt_refs=issue.refs,
            required_answer=issue.question,
            effects=issue.basis,
            owner=issue.owner,
        )

    def _version(self, root_id: str) -> int:
        row = self.query_one("SELECT version FROM cases WHERE id = ?", (root_id,))
        return int(row["version"])

    # -- T9 evaluation helpers (contracts §9) --------------------------------
    def write_packet(self, base: Path, *, name: str) -> Path:
        """Write a packet on disk whose activity has a seeded demo transcription."""
        from tests.factories import write_test_packet

        # The packet's activity matches a demo activity that carries a
        # transcription, so the runner's submit has real input to assess.
        return write_test_packet(base, root_id=name, strata="routine")

    # -- T8 control helpers (contracts §9) -----------------------------------
    async def hold_reader(self) -> None:
        """Arm the gate a late worker waits on before it may commit."""
        import asyncio

        self._reader_gate = asyncio.Event()

    async def release_reader(self) -> None:
        if getattr(self, "_reader_gate", None) is not None:
            self._reader_gate.set()

    async def late_submit(self, root_id: str, activity: str) -> CaseView:
        """A worker that waits on the reader gate, then submits (may be stale)."""
        await self._reader_gate.wait()
        result = await self.workflow.execute(
            self.ctx(actor=DEFAULT_ACTOR, expected_case_version=self._version(root_id)),
            Submit(
                root_id=root_id,
                declaration=Declaration(activity_id=activity, declared_purpose="Công tác"),
            ),
        )
        return result.case_view

    async def stop(self) -> CaseView:
        from invoice_referee.domain.case import CommandContext
        from invoice_referee.domain.commands import Control

        root = self._last_root
        session = self.workflow.start_session(
            tenant=TENANT_DEMO, persona="accountant", actor_id="employee:accountant-demo"
        )
        ctx = CommandContext(
            session_id=session.session_id,
            actor_id="employee:accountant-demo",
            command_id=f"cmd:{uuid.uuid4().hex}",
            expected_case_version=0,
        )
        result = await self.workflow.execute(ctx, Control(root_id=root, action="STOP", reason="dừng"))
        return result.case_view

    def current_instructions(self) -> list[str]:
        rows = self.query_one(
            "SELECT COUNT(*) AS n FROM instructions WHERE status IN ('ISSUED','PARTIAL')"
        )
        count = int(rows["n"])
        return ["instruction"] * count

    # -- T7 money helpers (contracts §9) -------------------------------------
    async def record_received(
        self,
        *,
        instruction_amount: int,
        received: int,
        payee: str | None = None,
        external_key: str | None = None,
        kind: str = "REIMBURSEMENT_RECEIVED",
    ) -> CaseView:
        """Submit a routine root for `instruction_amount`, then record a receipt.

        Builds an instruction via the real submit path, then executes
        RecordActual (never a direct SQL write) as the accountant.
        """
        from invoice_referee.domain.finance import RecordMoneyInput
        from invoice_referee.domain.commands import RecordActual

        # E = instruction_amount + A(2m) so the derived instruction equals the
        # requested amount (E - A = instruction_amount).
        packet = "money-i4" if instruction_amount == 4_000_000 else "money-i4"
        v = await self.submit_packet(packet, mode="STUB")
        root = v.id
        money = RecordMoneyInput(
            external_key=external_key or f"bank:txn-{uuid.uuid4().hex[:8]}",
            claimed_kind=kind,
            claimed_scope="activity:travel-a",
            payer="company:demo" if kind == "REIMBURSEMENT_RECEIVED" else "employee:employee-a",
            payee=payee or DEFAULT_ACTOR,
            amount=received,
            event_at=DEFAULT_OCCURRED_AT,
            reason="Ghi nhận tiền thực tế",
        )
        context = self.ctx(
            actor="employee:accountant-demo",
            expected_case_version=self._version(root),
        )
        # The accountant persona is required by the handler.
        session = self.workflow.start_session(
            tenant=TENANT_DEMO, persona="accountant", actor_id="employee:accountant-demo"
        )
        context = CommandContext(
            session_id=session.session_id,
            actor_id="employee:accountant-demo",
            command_id=f"cmd:{uuid.uuid4().hex}",
            expected_case_version=self._version(root),
        )
        result = await self.workflow.execute(context, RecordActual(root_id=root, money=money))
        return result.case_view

    async def reverse_last_received(self, *, amount: int | None = None) -> CaseView:
        from invoice_referee.domain.finance import RecordMoneyInput
        from invoice_referee.domain.commands import RecordActual

        row = self.query_one(
            "SELECT root_id, id, amount, kind FROM money_events "
            "WHERE kind = 'REIMBURSEMENT_RECEIVED' ORDER BY recorded_at DESC LIMIT 1"
        )
        root = str(row["root_id"])
        money = RecordMoneyInput(
            external_key=f"bank:rev-{uuid.uuid4().hex[:8]}",
            claimed_kind="REVERSAL",
            claimed_scope="activity:travel-a",
            payer="employee:employee-a",
            payee="company:demo",
            amount=amount if amount is not None else int(row["amount"]),
            event_at=DEFAULT_OCCURRED_AT,
            reverses_event_id=str(row["id"]),
            reason="Đảo giao dịch",
        )
        session = self.workflow.start_session(
            tenant=TENANT_DEMO, persona="accountant", actor_id="employee:accountant-demo"
        )
        context = CommandContext(
            session_id=session.session_id,
            actor_id="employee:accountant-demo",
            command_id=f"cmd:{uuid.uuid4().hex}",
            expected_case_version=self._version(root),
        )
        result = await self.workflow.execute(context, RecordActual(root_id=root, money=money))
        return result.case_view

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


# -- reader fixture (contracts §9): read-only model proposals, no money ------

# Actions a model may propose; anything else (money/authority/policy) is
# rejected because the reader has no path to them.
_READ_ONLY_ACTIONS = frozenset({"READ_FIELDS", "CROSS_CHECK", "ASK_OWNER"})


class ReaderFixture:
    """A read-only proposal gate with a money side-effect spy (contracts §9)."""

    def __init__(self) -> None:
        self.money_side_effects: list[object] = []

    async def propose(self, *, model_action: str) -> "ProposalResult":
        rejected = model_action not in _READ_ONLY_ACTIONS
        return ProposalResult(action=model_action, rejected=rejected)


class ProposalResult:
    def __init__(self, *, action: str, rejected: bool) -> None:
        self.action = action
        self.rejected = rejected


@pytest.fixture
def reader_fixture() -> ReaderFixture:
    return ReaderFixture()
