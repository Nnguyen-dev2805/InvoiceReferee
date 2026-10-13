"""Case workflow: canonical roots, draft/source/declaration commands, demo context.

This module owns the transaction boundary (contracts §6): a command, its version
bump and its audit row commit together. Provider I/O does not exist here yet; the
EvidenceReader arrives at T5 and the assessment pipeline at T6. Unsupported
command kinds fail loudly instead of pretending to work.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from zoneinfo import ZoneInfo

from invoice_referee.domain.case import (
    AssessmentResult,
    CaseView,
    CommandContext,
    Instruction,
    ReadSet,
    SettlementConclusion,
)
from invoice_referee.domain.commands import (
    AnswerIssue,
    AttachSources,
    CaseCommand,
    CommandResult,
    Control,
    CreateDraft,
    Decide,
    MarkExecution,
    Override,
    RecordActual,
    ReviseDeclaration,
    Submit,
)
from invoice_referee.domain.common import Fact, SignedVnd, Vnd
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.domain.finance import MoneyEvent, Projection
from invoice_referee.domain.issues import BusinessIssue
from invoice_referee.workflow.controls import (
    StaleControlError,
    assert_epoch_current,
    bump_epoch,
    context_version,
)
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.money import can_reverse, net_by_kind

DEFAULT_TENANT = "tenant:demo"
DEFAULT_PERSONA = "employee"
DEFAULT_ACTIVITY_PROFILE = "TRAVEL"
DEFAULT_MAX_SOURCE_BYTES = 20 * 1024 * 1024  # contracts §6 pilot ceiling per file
# Server-minted id prefix for a proposed (not yet authorized) activity (§10.4).
PROPOSED_ACTIVITY_PREFIX = "activity:proposed:"

PERSONAS: tuple[tuple[str, str], ...] = (
    ("employee", "Nhân viên"),
    ("accountant", "Kế toán"),
    ("approver", "Người quyết định"),
)

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class WorkflowError(Exception):
    """Base for server-side command errors the API maps to HTTP codes."""


class UnknownSessionError(WorkflowError):
    pass


class NotFoundError(WorkflowError):
    pass


class StaleCommandError(WorkflowError):
    pass


class CommandConflictError(WorkflowError):
    pass


class UnsupportedCommandError(WorkflowError):
    pass


@dataclass(frozen=True)
class DemoSession:
    session_id: str
    tenant: str
    persona: str
    actor_id: str


@dataclass(frozen=True)
class CatalogActivity:
    activity_id: str
    name: str
    occurred_at: datetime | None
    purpose: str
    status: str
    budget_amount: int | None

    @property
    def has_budget(self) -> bool:
        return self.budget_amount is not None


def default_actor(persona: str, tenant: str) -> str:
    """The demo actor a persona switches into (contracts §5: server-side)."""
    if tenant == DEFAULT_TENANT:
        return {
            "employee": "employee:employee-a",
            "accountant": "employee:accountant-demo",
            "approver": "employee:approver",
        }[persona]
    return f"employee:{persona}-{tenant.split(':')[-1]}"


def _root_id(tenant: str, employee: str, activity: str) -> str:
    digest = hashlib.sha256(f"{tenant}|{employee}|{activity}".encode("utf-8")).hexdigest()
    return f"case:{digest[:20]}"


def _unknown_projection() -> Projection:
    """No figures yet: every amount stays UNKNOWN, never a fabricated zero."""
    return Projection(
        T=Fact[Vnd](key="projection:T", state="UNKNOWN"),
        E=Fact[Vnd](key="projection:E", state="UNKNOWN"),
        C=Fact[Vnd](key="projection:C", state="UNKNOWN"),
        A=Fact[Vnd](key="projection:A", state="UNKNOWN"),
        P=Fact[Vnd](key="projection:P", state="UNKNOWN"),
        R=Fact[Vnd](key="projection:R", state="UNKNOWN"),
        unpaid=Fact[Vnd](key="projection:unpaid", state="UNKNOWN"),
        S=Fact[SignedVnd](key="projection:S", state="UNKNOWN"),
    )


def _context_issue(root_id: str) -> BusinessIssue:
    return BusinessIssue(
        id=f"issue:context:{root_id}",
        kind="FACT",
        field_or_rule="budget:B",
        owner="org-data",
        status="OPEN",
        basis=(
            "Context demo chưa có bản ghi ngân sách hoặc quyết định hoạt động "
            "cho hoạt động này."
        ),
        refs=(),
        question=(
            "Tìm bản ghi ngân sách/quyết định hoạt động; chưa có số 0 thay thế "
            "cho phần chưa xác minh."
        ),
    )


def _owner_persona(owner: str) -> str:
    """Which demo persona may answer an issue owned by `owner` (§5)."""
    return {
        "employee": "employee",
        "accountant": "accountant",
        "org-data": "accountant",
        "approver": "approver",
    }.get(owner, "any")


def _vn_date(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_VN_TZ).strftime("%d/%m/%Y")


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _meaningful_payload(command: CaseCommand) -> object:
    """The client-meaningful part of a command for the idempotency fingerprint.

    Server-minted fields are excluded so a retry with the same command id
    replays the stored result instead of conflicting (§10.3): an attachment
    `storage_key` is generated per attempt, and a new-activity `activity_id` is
    minted by the server (the client only chooses name/date/purpose).
    """
    if isinstance(command, AttachSources):
        return {
            "kind": command.kind,
            "root_id": command.root_id,
            "uploads": sorted(
                (upload.filename, upload.media, upload.digest)
                for upload in command.uploads
            ),
        }
    if isinstance(command, CreateDraft):
        activity = command.activity_data
        payload: dict[str, object] = {
            "kind": command.kind,
            "name": activity.name,
            "occurred_at": activity.occurred_at.isoformat(),
            "declared_purpose": activity.declared_purpose,
        }
        # Only a client-chosen existing activity id is meaningful; the server
        # mints `activity:proposed:<hex>` for a new activity, which must not
        # enter the fingerprint or a retry would look like a different command.
        if not activity.activity_id.startswith(PROPOSED_ACTIVITY_PREFIX):
            payload["activity_id"] = activity.activity_id
        return payload
    return json.loads(command.model_dump_json())


def _fingerprint(context: CommandContext, command: CaseCommand) -> str:
    payload = {
        "expected_case_version": context.expected_case_version,
        "command": _meaningful_payload(command),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# -- validated synthetic context models (contracts §10.4) --------------------


class _ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


Money = Annotated[int, Field(ge=0, strict=True)]


class _DemoBudget(_ContextModel):
    amount: Money
    effect_from: datetime | None = None
    record_key: str
    quote: str


class _DemoActivity(_ContextModel):
    id: str
    name: str
    occurred_at: datetime | None = None
    purpose: str
    status: Literal["AUTHORIZED", "PROPOSED"] = "AUTHORIZED"
    budget: _DemoBudget | None = None
    # Optional STUB hand-transcription for the dev/UI path (contracts §5).
    transcription: tuple[dict[str, object], ...] | None = None


class _DemoGrant(_ContextModel):
    id: str
    version: str
    actor: str
    actions: tuple[str, ...]
    scope: str
    max_amount: Money
    effective_from: datetime
    effective_to: datetime | None = None


class _DemoPerson(_ContextModel):
    id: str
    name: str


class _DemoWitness(_ContextModel):
    kind: Literal["LEDGER_OPENING", "LEDGER_COVERAGE", "BUDGET"]
    record_key: str
    quote: str


class _DemoOrganization(_ContextModel):
    id: str
    name: str


class _DemoContext(_ContextModel):
    data_origin: Literal["SIMULATED"]
    note: str
    organization: _DemoOrganization
    people: tuple[_DemoPerson, ...] = ()
    activities: tuple[_DemoActivity, ...] = ()
    grants: tuple[_DemoGrant, ...] = ()
    witnesses: tuple[_DemoWitness, ...] = ()


class CaseWorkflow:
    """Canonical roots, draft commands and the validated demo context."""

    def __init__(
        self,
        db: Database,
        *,
        uploads_dir: str | Path,
        max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.uploads_dir = Path(uploads_dir)
        self.max_source_bytes = max_source_bytes
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now_iso(self) -> str:
        return self._clock().isoformat()

    # -- demo sessions -------------------------------------------------------
    def start_session(
        self,
        *,
        tenant: str = DEFAULT_TENANT,
        persona: str = DEFAULT_PERSONA,
        actor_id: str | None = None,
    ) -> DemoSession:
        session_id = f"session:{uuid.uuid4().hex}"
        actor = actor_id or default_actor(persona, tenant)
        now = self._now_iso()
        with self.db.transaction() as cx:
            cx.execute(
                "INSERT INTO demo_sessions (session_id, tenant, persona, actor_id, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, tenant, persona, actor, now, now),
            )
            self._audit(
                cx,
                tenant=tenant,
                root_id=None,
                session_id=session_id,
                actor=actor,
                action="SESSION_START",
                detail=json.dumps({"persona": persona}, ensure_ascii=False),
            )
        return DemoSession(session_id=session_id, tenant=tenant, persona=persona, actor_id=actor)

    def session(self, session_id: str) -> DemoSession:
        row = self._query_one(
            "SELECT * FROM demo_sessions WHERE session_id = ?", (session_id,)
        )
        if row is None:
            raise UnknownSessionError("Phiên demo không tồn tại; hãy tải lại trang.")
        return DemoSession(
            session_id=row["session_id"],
            tenant=row["tenant"],
            persona=row["persona"],
            actor_id=row["actor_id"],
        )

    def switch_persona(self, session_id: str, persona: str) -> DemoSession:
        current = self.session(session_id)
        actor = default_actor(persona, current.tenant)
        with self.db.transaction() as cx:
            cx.execute(
                "UPDATE demo_sessions SET persona = ?, actor_id = ?, updated_at = ? "
                "WHERE session_id = ?",
                (persona, actor, self._now_iso(), session_id),
            )
            self._audit(
                cx,
                tenant=current.tenant,
                root_id=None,
                session_id=session_id,
                actor=actor,
                action="PERSONA_SWITCH",
                detail=json.dumps(
                    {"from": current.persona, "to": persona}, ensure_ascii=False
                ),
            )
        return DemoSession(
            session_id=session_id, tenant=current.tenant, persona=persona, actor_id=actor
        )

    # -- demo context --------------------------------------------------------
    def import_demo_context(
        self, context_path: str | Path, *, origin: str = "SIMULATED"
    ) -> str:
        raw = Path(context_path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        data = _DemoContext.model_validate_json(raw)
        tenant = data.organization.id
        with self.db.transaction() as cx:
            previous = cx.execute(
                "SELECT digest FROM context_imports WHERE tenant = ? "
                "ORDER BY id DESC LIMIT 1",
                (tenant,),
            ).fetchone()
            if previous is not None and previous["digest"] == digest:
                return digest

            for activity in data.activities:
                budget = activity.budget
                cx.execute(
                    "INSERT INTO context_activities (activity_id, tenant, name, "
                    "occurred_at, purpose, budget_amount, budget_effect_from, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant, activity_id) DO UPDATE SET name = excluded.name, "
                    "occurred_at = excluded.occurred_at, purpose = excluded.purpose, "
                    "budget_amount = excluded.budget_amount, "
                    "budget_effect_from = excluded.budget_effect_from, "
                    "status = excluded.status",
                    (
                        activity.id,
                        tenant,
                        activity.name,
                        activity.occurred_at.isoformat() if activity.occurred_at else None,
                        activity.purpose,
                        budget.amount if budget else None,
                        budget.effect_from.isoformat()
                        if budget and budget.effect_from
                        else None,
                        activity.status,
                    ),
                )
            # Seed a demo STUB transcription for activities that declare one, so
            # the STUB dev/UI path can assess without a provider (contracts §5).
            from invoice_referee.evaluation.models import Transcription, TranscriptionFact

            for activity in data.activities:
                if activity.transcription is None:
                    continue
                transcription = Transcription(
                    facts=tuple(
                        TranscriptionFact(**fact) for fact in activity.transcription
                    )
                )
                cx.execute(
                    "INSERT OR REPLACE INTO context_transcriptions (tenant, activity_id, "
                    "transcription_json) VALUES (?, ?, ?)",
                    (tenant, activity.id, transcription.model_dump_json()),
                )
            for grant in data.grants:
                cx.execute(
                    "INSERT OR REPLACE INTO context_grants (grant_id, tenant, version, "
                    "actor, actions_json, scope, max_amount, effective_from, "
                    "effective_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        grant.id,
                        tenant,
                        grant.version,
                        grant.actor,
                        json.dumps(list(grant.actions), ensure_ascii=False),
                        grant.scope,
                        grant.max_amount,
                        grant.effective_from.isoformat(),
                        grant.effective_to.isoformat() if grant.effective_to else None,
                    ),
                )
            for person in data.people:
                cx.execute(
                    "INSERT OR REPLACE INTO context_people (id, tenant, name) "
                    "VALUES (?, ?, ?)",
                    (person.id, tenant, person.name),
                )
            cx.execute("DELETE FROM context_witnesses WHERE tenant = ?", (tenant,))
            for witness in data.witnesses:
                cx.execute(
                    "INSERT INTO context_witnesses (tenant, kind, record_key, quote, "
                    "source_id, source_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        tenant,
                        witness.kind,
                        witness.record_key,
                        witness.quote,
                        "source:demo-context",
                        digest,
                    ),
                )
            cx.execute(
                "INSERT INTO context_imports (tenant, digest, origin, imported_at, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (tenant, digest, origin, self._now_iso(), data.note),
            )
            self._audit(
                cx,
                tenant=tenant,
                root_id=None,
                session_id=None,
                actor="system:context-import",
                action="CONTEXT_IMPORT",
                detail=json.dumps(
                    {"digest": digest, "origin": origin, "activities": len(data.activities)},
                    ensure_ascii=False,
                ),
                origin=origin,
            )
        return digest

    def catalog(self, tenant: str = DEFAULT_TENANT) -> tuple[CatalogActivity, ...]:
        # The selectable catalog is the authorized activity set: a PROPOSED
        # activity is a draft awaiting authorization, not an existing choice
        # (§10.4), so it is not offered here.
        connection = self.db.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM context_activities WHERE tenant = ? "
                "AND status = 'AUTHORIZED' ORDER BY activity_id",
                (tenant,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CatalogActivity(
                activity_id=row["activity_id"],
                name=row["name"],
                occurred_at=_parse_dt(row["occurred_at"]),
                purpose=row["purpose"],
                status=row["status"],
                budget_amount=row["budget_amount"],
            )
            for row in rows
        )

    def catalog_entry(self, tenant: str, activity_id: str) -> CatalogActivity | None:
        for entry in self.catalog(tenant):
            if entry.activity_id == activity_id:
                return entry
        return None

    def display_name(self, tenant: str, actor_id: str) -> str:
        row = self._query_one(
            "SELECT name FROM context_people WHERE id = ? AND tenant = ?",
            (actor_id, tenant),
        )
        return str(row["name"]) if row is not None else actor_id

    def last_context_import(self, tenant: str = DEFAULT_TENANT) -> dict[str, str] | None:
        row = self._query_one(
            "SELECT digest, origin, imported_at, note FROM context_imports "
            "WHERE tenant = ? ORDER BY id DESC LIMIT 1",
            (tenant,),
        )
        if row is None:
            return None
        return {
            "digest": str(row["digest"]),
            "origin": str(row["origin"]),
            "imported_at": str(row["imported_at"]),
            "note": str(row["note"]),
        }

    # -- commands ------------------------------------------------------------
    async def execute(self, context: CommandContext, command: CaseCommand) -> CommandResult:
        session = self.session(context.session_id)
        handlers: dict[str, Callable[..., CommandResult]] = {
            "CREATE_DRAFT": self._create_draft,
            "ATTACH_SOURCES": self._attach_sources,
            "REVISE_DECLARATION": self._revise_declaration,
            "SUBMIT": self._submit,
            "ANSWER_ISSUE": self._answer_issue,
            "DECIDE": self._decide,
            "RECORD_ACTUAL": self._record_actual,
            "MARK_EXECUTION": self._mark_execution,
            "CONTROL": self._control,
            "OVERRIDE": self._override,
        }
        handler = handlers.get(command.kind)
        if handler is None:
            raise UnsupportedCommandError(
                f"Lệnh {command.kind} chưa được triển khai trong phạm vi T2."
            )
        fingerprint = _fingerprint(context, command)
        with self.db.transaction() as cx:
            stored = cx.execute(
                "SELECT fingerprint, result_json FROM command_log WHERE tenant = ? "
                "AND actor_id = ? AND command_id = ?",
                (session.tenant, context.actor_id, context.command_id),
            ).fetchone()
            if stored is not None:
                if stored["fingerprint"] != fingerprint:
                    raise CommandConflictError(
                        "command_id đã được dùng cho một nội dung khác."
                    )
                previous = CommandResult.model_validate_json(stored["result_json"])
                return previous.model_copy(update={"duplicate_command": True})

            result = handler(cx, session, context, command)
            cx.execute(
                "INSERT INTO command_log (tenant, actor_id, command_id, fingerprint, "
                "result_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session.tenant,
                    context.actor_id,
                    context.command_id,
                    fingerprint,
                    result.model_dump_json(),
                    self._now_iso(),
                ),
            )
            return result

    def _create_draft(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: CreateDraft,
    ) -> CommandResult:
        activity = command.activity_data
        employee = session.actor_id
        known = cx.execute(
            "SELECT 1 FROM context_activities WHERE activity_id = ? AND tenant = ?",
            (activity.activity_id, session.tenant),
        ).fetchone()
        if known is None:
            # ProposedActivity: the draft grants no activity/B authority (§10.4).
            cx.execute(
                "INSERT INTO context_activities (activity_id, tenant, name, occurred_at, "
                "purpose, budget_amount, budget_effect_from, status) "
                "VALUES (?, ?, ?, ?, ?, NULL, NULL, 'PROPOSED') "
                "ON CONFLICT(tenant, activity_id) DO NOTHING",
                (
                    activity.activity_id,
                    session.tenant,
                    activity.name,
                    activity.occurred_at.isoformat(),
                    activity.declared_purpose,
                ),
            )

        root_id = _root_id(session.tenant, employee, activity.activity_id)
        now = self._now_iso()
        cx.execute(
            "INSERT INTO cases (id, tenant, employee, activity, profile, state, version, "
            "input_revision, control_epoch, activity_name, activity_occurred_at, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'DRAFT', 1, 1, 0, ?, ?, ?, ?) "
            "ON CONFLICT (tenant, employee, activity) DO NOTHING",
            (
                root_id,
                session.tenant,
                employee,
                activity.activity_id,
                DEFAULT_ACTIVITY_PROFILE,
                activity.name,
                activity.occurred_at.isoformat(),
                now,
                now,
            ),
        )
        row = cx.execute(
            "SELECT * FROM cases WHERE tenant = ? AND employee = ? AND activity = ?",
            (session.tenant, employee, activity.activity_id),
        ).fetchone()
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="CREATE_DRAFT",
            detail=json.dumps({"activity": activity.activity_id}, ensure_ascii=False),
        )
        return CommandResult(case_view=self._case_view(cx, row))

    def _attach_sources(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: AttachSources,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        self._require_version(row, context.expected_case_version)
        now = self._now_iso()
        for upload in command.uploads:
            cx.execute(
                "INSERT INTO case_sources (source_id, root_id, tenant, filename, media, "
                "digest, storage_key, attached_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"source:{uuid.uuid4().hex}",
                    str(row["id"]),
                    session.tenant,
                    upload.filename,
                    upload.media,
                    upload.digest,
                    upload.storage_key,
                    now,
                ),
            )
        self._bump(cx, row, now)
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="ATTACH_SOURCES",
            detail=json.dumps(
                {"files": [upload.filename for upload in command.uploads]},
                ensure_ascii=False,
            ),
        )
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _revise_declaration(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: ReviseDeclaration,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        self._require_version(row, context.expected_case_version)
        now = self._now_iso()
        revision = int(row["input_revision"]) + 1
        cx.execute(
            "INSERT INTO case_declarations (root_id, revision, purpose, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                str(row["id"]),
                revision,
                command.declaration.declared_purpose,
                command.declaration.notes,
                now,
            ),
        )
        self._bump(cx, row, now)
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="REVISE_DECLARATION",
            detail=json.dumps({"revision": revision}, ensure_ascii=False),
        )
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    # -- submission and assessment -------------------------------------------
    def _submit(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: Submit,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        self._require_version(row, context.expected_case_version)
        now = self._now_iso()
        self._assess_and_commit(cx, session, row, now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _answer_issue(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: AnswerIssue,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        # A stale answer is rejected (its history is kept in the command log but
        # it must not overwrite newer state) — contracts §6.
        self._require_version(row, context.expected_case_version)
        answer = command.answer
        issue = cx.execute(
            "SELECT * FROM case_issues WHERE id = ? AND root_id = ?",
            (answer.issue_id, str(row["id"])),
        ).fetchone()
        if issue is None:
            raise NotFoundError("Không tìm thấy việc cần xử lý này.")
        # Only the issue's owner may answer it (contracts §5).
        if issue["owner"] not in (context.actor_id, "employee", "accountant", "approver", "org-data"):
            raise UnsupportedCommandError("Bạn không phải người xử lý việc này.")
        if _owner_persona(issue["owner"]) not in ("any", session.persona):
            raise UnsupportedCommandError(
                "Việc này thuộc người xử lý khác; câu trả lời không được áp dụng."
            )
        now = self._now_iso()
        cx.execute(
            "UPDATE case_issues SET status = 'ANSWERED', updated_at = ? WHERE id = ?",
            (now, answer.issue_id),
        )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="ANSWER_ISSUE",
            detail=json.dumps({"issue": answer.issue_id}, ensure_ascii=False),
        )
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _decide(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: Decide,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        decision = command.decision
        # A decision needs a real grant for its actions at this scope and within
        # the grant's amount ceiling (contracts §5).
        for action in decision.actions:
            if not self._actor_has_grant(
                cx,
                session.tenant,
                context.actor_id,
                action,
                decision.effect_scope,
                decision.amount,
            ):
                raise UnsupportedCommandError(
                    f"Không có quyền thực hiện {action} trong phạm vi này."
                )
        now = self._now_iso()
        for issue_id in decision.issue_ids:
            cx.execute(
                "UPDATE case_issues SET status = 'RESOLVED', updated_at = ? WHERE id = ?",
                (now, issue_id),
            )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="DECIDE",
            detail=json.dumps(
                {"actions": list(decision.actions), "reason": decision.reason},
                ensure_ascii=False,
            ),
        )
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _record_actual(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: RecordActual,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        money = command.money
        # The accountant (or a granted actor) records actual money (§5).
        if session.persona not in ("accountant", "approver") and not self._actor_has_grant(
            cx, session.tenant, context.actor_id, "RECORD_ACTUAL", money.claimed_scope
        ):
            raise UnsupportedCommandError("Bạn không có quyền ghi nhận tiền thực tế.")
        now = self._now_iso()
        root_id = str(row["id"])
        # external_key is unique per tenant: a re-sent transaction is not counted
        # twice, and the same key with a different payload is a conflict (§4).
        existing = cx.execute(
            "SELECT * FROM money_events WHERE tenant = ? AND external_key = ?",
            (session.tenant, money.external_key),
        ).fetchone()
        if existing is not None:
            if (
                int(existing["amount"]) != money.amount
                or existing["kind"] != money.claimed_kind
            ):
                raise CommandConflictError(
                    "external_key đã dùng cho một giao dịch khác nội dung."
                )
            return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

        kind = money.claimed_kind
        event_id = f"money:{uuid.uuid4().hex}"
        # A recorded claim is verified only when it carries a responsible
        # completion confirmation or checked evidence (contracts §3–§4). A bare
        # statement is preserved as OBSERVED for audit, but it never fulfills an
        # instruction or settles a case (missing proof is not zero, and a
        # statement alone is not proof). A linked reversal is verified by its
        # binding to a real, unreversed original (§10.1).
        verified = (
            bool((money.completion_claim or "").strip())
            or bool(money.refs)
            or money.reverses_event_id is not None
        )
        event = MoneyEvent(
            id=event_id,
            external_key=money.external_key,
            kind=kind,  # type: ignore[arg-type]
            scope=money.claimed_scope,
            payer=money.payer,
            payee=money.payee,
            amount=money.amount,
            event_at=money.event_at,
            recorded_at=datetime.now(UTC),
            verification_state="CONFIRMED" if verified else "OBSERVED",
            allocation_state="ALLOCATED" if verified else "UNALLOCATED",
            reverses_event_id=money.reverses_event_id,
            refs=money.refs,
        )
        # A reversal must not exceed the unreversed original (§10.1).
        if money.reverses_event_id is not None:
            events = self._load_money_events(cx, session.tenant, root_id)
            if not can_reverse(events, money.reverses_event_id, money.amount):
                raise UnsupportedCommandError(
                    "Đảo giao dịch vượt quá số gốc chưa bị đảo."
                )
        cx.execute(
            "INSERT INTO money_events (id, tenant, root_id, external_key, kind, scope, "
            "payer, payee, amount, event_at, recorded_at, verification_state, "
            "allocation_state, reverses_event_id, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                session.tenant,
                root_id,
                event.external_key,
                event.kind,
                event.scope,
                event.payer,
                event.payee,
                event.amount,
                event.event_at.isoformat(),
                event.recorded_at.isoformat(),
                event.verification_state,
                event.allocation_state,
                event.reverses_event_id,
                event.model_dump_json(),
            ),
        )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=context.actor_id,
            action="RECORD_ACTUAL",
            detail=json.dumps(
                {"kind": event.kind, "amount": event.amount, "key": event.external_key},
                ensure_ascii=False,
            ),
        )
        # Re-assess so the projection reflects the new money and the active
        # instruction's fulfillment is re-derived (contracts §4).
        self._reconcile_money(cx, session, self._reload(cx, row), now)
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _mark_execution(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: MarkExecution,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        # MarkExecution belongs to the accountant with a grant on the root (§10.1).
        if session.persona not in ("accountant", "approver"):
            raise UnsupportedCommandError("Chỉ kế toán/người có quyền đánh dấu thực hiện.")
        now = self._now_iso()
        cx.execute(
            "UPDATE instructions SET execution_state = ?, updated_at = ? WHERE id = ? "
            "AND root_id = ?",
            (command.execution_state, now, command.instruction_id, str(row["id"])),
        )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="MARK_EXECUTION",
            detail=json.dumps(
                {"instruction": command.instruction_id, "state": command.execution_state},
                ensure_ascii=False,
            ),
        )
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _control(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: Control,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        # STOP is a control signal allowed on the newest version after the actor
        # and idempotency checks; it is not guarded by expected_case_version.
        if session.persona not in ("accountant", "approver"):
            raise UnsupportedCommandError("Chỉ kế toán/người có quyền dừng hồ sơ.")
        now = self._now_iso()
        root_id = str(row["id"])
        bump_epoch(cx, root_id, now)
        if command.action == "STOP":
            # Suspend pending instructions; a handed-off one becomes unknown
            # until its execution is checked (§6).
            cx.execute(
                "UPDATE instructions SET status = 'SUSPENDED', "
                "execution_state = CASE WHEN execution_state IN ('OPEN','UNKNOWN') "
                "THEN 'UNKNOWN' ELSE execution_state END, updated_at = ? "
                "WHERE root_id = ? AND status IN ('ISSUED','PARTIAL')",
                (now, root_id),
            )
            cx.execute(
                "UPDATE cases SET state = 'STOPPED', updated_at = ? WHERE id = ?",
                (now, root_id),
            )
        else:  # RESUME
            cx.execute(
                "UPDATE cases SET state = 'WAITING', updated_at = ? WHERE id = ?",
                (now, root_id),
            )
            self._assess_and_commit(cx, session, self._reload(cx, row), now)
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=context.actor_id,
            action=command.action,
            detail=json.dumps({"reason": command.reason}, ensure_ascii=False),
        )
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _override(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: Override,
    ) -> CommandResult:
        row = self._require_root(cx, session, command.root_id)
        decision = command.decision
        # An override needs the exact grant for its actions and amount (§5, §10.3).
        for action in decision.actions:
            if not self._actor_has_grant(
                cx,
                session.tenant,
                context.actor_id,
                action,
                decision.effect_scope,
                decision.amount,
            ):
                raise UnsupportedCommandError(
                    f"Không có quyền thực hiện {action} trong phạm vi này."
                )
        now = self._now_iso()
        root_id = str(row["id"])
        # A new scoped decision; the old decision is retained, facts and actual
        # money are never rewritten.
        for issue_id in decision.issue_ids:
            cx.execute(
                "UPDATE case_issues SET status = 'RESOLVED', updated_at = ? WHERE id = ?",
                (now, issue_id),
            )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=context.actor_id,
            action="OVERRIDE",
            detail=json.dumps(
                {
                    "supersedes": command.supersedes_decision_id,
                    "actions": list(decision.actions),
                    "reason": decision.reason,
                },
                ensure_ascii=False,
            ),
        )
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _load_money_events(
        self, cx: sqlite3.Connection, tenant: str, root_id: str
    ) -> tuple[MoneyEvent, ...]:
        return tuple(
            MoneyEvent.model_validate_json(row["payload_json"])
            for row in cx.execute(
                "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? "
                "ORDER BY recorded_at, id",
                (tenant, root_id),
            )
        )

    def _reconcile_money(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        now: str,
    ) -> None:
        """Re-derive fulfillment of active instructions from the ledger (§4).

        A payment fulfills only when received by the instruction's payee; an
        overpay is recorded and raises an incident, never clipped.
        """
        root_id = str(row["id"])
        # Only confirmed movements fulfill an instruction; an OBSERVED-only
        # claim is recorded for audit but grants no fulfillment (§3–§4).
        events = tuple(
            e
            for e in self._load_money_events(cx, session.tenant, root_id)
            if e.verification_state == "CONFIRMED"
        )
        employee = str(row["employee"])
        for inst in cx.execute(
            "SELECT * FROM instructions WHERE root_id = ? AND status IN ('ISSUED','PARTIAL')",
            (root_id,),
        ).fetchall():
            if inst["direction"] == "PAY":
                matching = tuple(
                    e
                    for e in events
                    if e.kind == "REIMBURSEMENT_RECEIVED" and e.payee == employee
                )
            else:
                matching = tuple(
                    e for e in events if e.kind == "EMPLOYEE_RETURN" and e.payee == "company:demo"
                )
            fulfilled = net_by_kind(matching, matching[0].kind) if matching else 0
            amount = int(inst["amount"])
            capped = min(fulfilled, amount)
            status = "FULFILLED" if capped >= amount and amount > 0 else (
                "PARTIAL" if capped > 0 else "ISSUED"
            )
            cx.execute(
                "UPDATE instructions SET fulfilled_amount = ?, status = ?, updated_at = ? "
                "WHERE id = ?",
                (capped, status, now, str(inst["id"])),
            )
            # An overpay beyond the instruction is an incident, not absorbed.
            if fulfilled > amount:
                over = fulfilled - amount
                recovery_key = f"incident:overpay:{inst['id']}"
                issue_id = f"issue:{hashlib.sha256((root_id + recovery_key).encode()).hexdigest()[:16]}"
                from invoice_referee.domain.issues import BusinessIssue

                issue = BusinessIssue(
                    id=issue_id,
                    kind="FACT",
                    field_or_rule=f"overpay:{inst['id']}",
                    owner="accountant",
                    basis=f"Chi vượt {over} so với yêu cầu {amount}.",
                    question="Xác minh khoản chi vượt và xử lý riêng (không tự thu bù).",
                )
                cx.execute(
                    "INSERT OR REPLACE INTO case_issues (id, tenant, root_id, kind, "
                    "field_or_rule, owner, status, recovery_key, payload_json, created_at, "
                    "updated_at) VALUES (?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)",
                    (
                        issue_id,
                        session.tenant,
                        root_id,
                        issue.kind,
                        issue.field_or_rule,
                        issue.owner,
                        recovery_key,
                        issue.model_dump_json(),
                        now,
                        now,
                    ),
                )

    def _actor_has_grant(
        self,
        cx: sqlite3.Connection,
        tenant: str,
        actor: str,
        action: str,
        scope: str,
        amount: int | None = None,
    ) -> bool:
        """A grant authorizes one action, one scope and an amount ceiling (§5).

        The scope must be the activity (or the tenant-wide convention); a grant
        scoped elsewhere never authorizes this action. When `amount` is given it
        must not exceed the grant's `max_amount` (per action, inclusive).
        """
        now = datetime.now(UTC)
        for grant in cx.execute(
            "SELECT * FROM context_grants WHERE tenant = ? AND actor = ?",
            (tenant, actor),
        ).fetchall():
            if action not in json.loads(grant["actions_json"]):
                continue
            # The grant's scope must cover the requested scope: an exact match,
            # or a tenant-wide grant (the demo's ``tenant:<id>`` convention).
            if str(grant["scope"]) not in (scope, tenant):
                continue
            if amount is not None and amount > int(grant["max_amount"]):
                continue
            eff_from = datetime.fromisoformat(grant["effective_from"])
            eff_to = (
                datetime.fromisoformat(grant["effective_to"])
                if grant["effective_to"]
                else None
            )
            if eff_from <= now and (eff_to is None or now <= eff_to):
                return True
        return False

    def _assess_and_commit(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        now: str,
    ) -> None:
        """Assess the current snapshot and commit issues/conclusion/instruction atomically."""
        from invoice_referee.reconciliation.service import Reconciler
        from invoice_referee.workflow.snapshots import build_assessment_input

        root_id = str(row["id"])
        # Stop is atomic with the commit: a worker whose snapshot predates a
        # Stop must not create a new instruction (contracts §6).
        if str(row["state"]) == "STOPPED":
            return
        transcription = self._transcription_for(cx, root_id)
        assessment_input = build_assessment_input(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            employee=str(row["employee"]),
            activity=str(row["activity"]),
            profile=str(row["profile"]),
            transcription=transcription,
        )
        result = Reconciler().assess(assessment_input)

        # Persist issues. The stable id is derived from the recovery key
        # (kind + field/rule), never from a model-authored name, and is stored
        # both as the row id and inside payload_json so view and lookup agree.
        # Reconciler-derived issues are recomputed each pass; incident issues
        # (e.g. an overpay) are preserved until their owner resolves them.
        cx.execute(
            "DELETE FROM case_issues WHERE root_id = ? AND recovery_key NOT LIKE 'incident:%'",
            (root_id,),
        )
        for issue in result.issues:
            recovery_key = f"{issue.kind}:{issue.field_or_rule}"
            issue_id = f"issue:{hashlib.sha256((root_id + recovery_key).encode()).hexdigest()[:16]}"
            stable_issue = issue.model_copy(update={"id": issue_id})
            cx.execute(
                "INSERT OR REPLACE INTO case_issues (id, tenant, root_id, kind, "
                "field_or_rule, owner, status, recovery_key, payload_json, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    issue_id,
                    session.tenant,
                    root_id,
                    issue.kind,
                    issue.field_or_rule,
                    issue.owner,
                    issue.status,
                    recovery_key,
                    stable_issue.model_dump_json(),
                    now,
                    now,
                ),
            )

        state = self._derive_state(result)
        conclusion_status = None
        open_incident = cx.execute(
            "SELECT 1 FROM case_issues WHERE root_id = ? AND recovery_key LIKE 'incident:%' "
            "AND status = 'OPEN' LIMIT 1",
            (root_id,),
        ).fetchone()
        if open_incident is not None:
            # An unresolved overpay/wrong-payee incident blocks any new action
            # until its owner resolves it (§10.1); actual money is retained.
            state = "WAITING"
            conclusion_status = "BLOCKED"
        elif result.allowed_effect is not None and self._obligation_owned_elsewhere(
            cx, session.tenant, root_id
        ):
            # The economic obligation already belongs to another root in this
            # tenant: do not issue a second instruction (§10.2). The canonical
            # owner keeps the actionable order.
            state = "WAITING"
            conclusion_status = "BLOCKED"
        elif result.allowed_effect is not None:
            state = self._apply_instruction_coverage(cx, session, row, result, now)
            conclusion_status = "OUTSTANDING" if state == "READY_TO_EXECUTE" else "BLOCKED"
        elif result.issues:
            state = "WAITING"
            conclusion_status = "BLOCKED"
        elif result.projection.S.state == "KNOWN" and int(result.projection.S.value or 0) == 0:
            # S=0 with every gate clean; only SETTLED if no execution is pending.
            pending = cx.execute(
                "SELECT 1 FROM instructions WHERE root_id = ? AND status IN ('ISSUED','PARTIAL') "
                "AND execution_state IN ('OPEN','UNKNOWN') LIMIT 1",
                (root_id,),
            ).fetchone()
            state = "WAITING" if pending is not None else "SETTLED"
            conclusion_status = "BALANCED"

        revision = int(row["input_revision"])
        cx.execute(
            "INSERT OR REPLACE INTO case_conclusions (id, tenant, root_id, revision, "
            "status, payload_json, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                f"conclusion:{root_id}:{revision}",
                session.tenant,
                root_id,
                revision,
                conclusion_status or "BLOCKED",
                result.model_dump_json(),
                now,
            ),
        )
        cx.execute(
            "UPDATE cases SET state = ?, version = version + 1, updated_at = ? WHERE id = ?",
            (state, now, root_id),
        )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=session.actor_id,
            action="ASSESS",
            detail=json.dumps({"state": state}, ensure_ascii=False),
        )

    def _apply_instruction_coverage(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        result,
        now: str,
    ) -> str:
        """Retain, supersede or issue the actionable instruction (§10.1).

        One actionable instruction per root. A pure confirmed receipt lowers S
        and the net remaining without changing the cost instruction basis, so
        the current instruction is retained. A changed cost basis (or a
        different direction) supersedes the old remainder and issues the full
        current abs(S). An OPEN/UNKNOWN execution that would be replaced is
        suspended pending external verification.
        """
        root_id = str(row["id"])
        effect = result.allowed_effect
        # A Stop suspends the actionable instruction; Resume must find it again
        # rather than treat it as absent and re-issue (which would reset its
        # unresolved execution, §6, §10.1).
        active = cx.execute(
            "SELECT * FROM instructions WHERE root_id = ? "
            "AND status IN ('ISSUED','PARTIAL','SUSPENDED','EXECUTION_UNKNOWN') "
            "ORDER BY created_at DESC LIMIT 1",
            (root_id,),
        ).fetchone()

        if active is not None:
            same_basis = active["cost_basis"] == result.cost_basis
            same_direction = active["direction"] == effect.direction
            remaining = max(int(active["amount"]) - int(active["fulfilled_amount"]), 0)
            same_amount = remaining == effect.amount
            if same_basis and same_direction and same_amount:
                # Nothing material changed: keep the same instruction. A suspended
                # remainder is reactivated, but a handed-off unresolved execution
                # stays UNKNOWN and keeps the case waiting for external proof.
                if active["status"] in ("SUSPENDED", "EXECUTION_UNKNOWN"):
                    reactivated = (
                        "PARTIAL" if int(active["fulfilled_amount"]) > 0 else "ISSUED"
                    )
                    cx.execute(
                        "UPDATE instructions SET status = ?, updated_at = ? WHERE id = ?",
                        (reactivated, now, str(active["id"])),
                    )
                    if active["execution_state"] in ("OPEN", "UNKNOWN"):
                        return "WAITING"
                return "READY_TO_EXECUTE"
            if active["execution_state"] in ("OPEN", "UNKNOWN"):
                # Cannot replace an instruction whose execution is unresolved.
                cx.execute(
                    "UPDATE instructions SET status = 'SUSPENDED', updated_at = ? WHERE id = ?",
                    (now, str(active["id"])),
                )
                return "WAITING"

        # Supersede any current actionable remainder, then issue the full abs(S).
        cx.execute(
            "UPDATE instructions SET status = 'SUPERSEDED', updated_at = ? "
            "WHERE root_id = ? AND status IN ('ISSUED','PARTIAL','SUSPENDED','EXECUTION_UNKNOWN')",
            (now, root_id),
        )
        self._issue_instruction(cx, session, row, result, now, active)
        return "READY_TO_EXECUTE"

    def _issue_instruction(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        result,
        now: str,
        supersedes: sqlite3.Row | None = None,
    ) -> None:
        effect = result.allowed_effect
        root_id = str(row["id"])
        # A distinct id per issuance event: a retained/superseded instruction is
        # never overwritten by a later order on the same cost basis (§10.1 keeps
        # old instructions and their fulfillment). Idempotency is provided by the
        # retain path, which reuses the existing row without re-issuing.
        basis_digest = hashlib.sha256((root_id + result.cost_basis).encode()).hexdigest()[:16]
        instruction_id = f"instruction:{basis_digest}:{uuid.uuid4().hex[:8]}"
        cx.execute(
            "INSERT INTO instructions (id, tenant, root_id, direction, amount, "
            "status, basis, cost_basis, supersedes_id, fulfilled_amount, execution_state, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'ISSUED', ?, ?, ?, 0, "
            "'NOT_STARTED', ?, ?)",
            (
                instruction_id,
                session.tenant,
                root_id,
                effect.direction,
                effect.amount,
                effect.basis,
                result.cost_basis,
                str(supersedes["id"]) if supersedes is not None else None,
                now,
                now,
            ),
        )
        # Record economic usage so a second root cannot claim the same obligation
        # (§10.2). The first writer becomes the canonical owner.
        for economic_key in self._economic_keys_for(cx, root_id):
            existing = cx.execute(
                "SELECT owner_root FROM usage_registry WHERE tenant = ? AND economic_key = ?",
                (session.tenant, economic_key),
            ).fetchone()
            if existing is None:
                cx.execute(
                    "INSERT INTO usage_registry (tenant, economic_key, owner_root, "
                    "expense_id, version) VALUES (?, ?, ?, ?, 1)",
                    (session.tenant, economic_key, root_id, "expense:1"),
                )

    def _obligation_owned_elsewhere(
        self, cx: sqlite3.Connection, tenant: str, root_id: str
    ) -> bool:
        """True if any of this root's economic keys is owned by another root."""
        for economic_key in self._economic_keys_for(cx, root_id):
            row = cx.execute(
                "SELECT owner_root FROM usage_registry WHERE tenant = ? AND economic_key = ?",
                (tenant, economic_key),
            ).fetchone()
            if row is not None and str(row["owner_root"]) != root_id:
                return True
        return False

    def _economic_keys_for(self, cx: sqlite3.Connection, root_id: str) -> tuple[str, ...]:
        row = cx.execute(
            "SELECT transcription_json FROM case_transcriptions WHERE root_id = ?",
            (root_id,),
        ).fetchone()
        if row is None or not row["transcription_json"]:
            return ()
        from invoice_referee.evaluation.models import Transcription

        transcription = Transcription.model_validate_json(row["transcription_json"])
        return tuple(
            str(fact.value) for fact in transcription.facts if fact.field == "economic_key"
        )

    def _transcription_for(self, cx: sqlite3.Connection, root_id: str):
        from invoice_referee.evaluation.models import Transcription

        row = cx.execute(
            "SELECT transcription_json FROM case_transcriptions WHERE root_id = ?",
            (root_id,),
        ).fetchone()
        if row is not None and row["transcription_json"]:
            return Transcription.model_validate_json(row["transcription_json"])
        # Fall back to the activity's demo STUB transcription (dev/UI path).
        case = cx.execute(
            "SELECT tenant, activity FROM cases WHERE id = ?", (root_id,)
        ).fetchone()
        if case is None:
            return None
        demo = cx.execute(
            "SELECT transcription_json FROM context_transcriptions "
            "WHERE tenant = ? AND activity_id = ?",
            (case["tenant"], case["activity"]),
        ).fetchone()
        if demo is None or not demo["transcription_json"]:
            return None
        return Transcription.model_validate_json(demo["transcription_json"])

    @staticmethod
    def _derive_state(result) -> str:
        if result.problems:
            return "TECHNICAL_ERROR"
        if result.issues:
            return "WAITING"
        if result.allowed_effect is not None:
            return "READY_TO_EXECUTE"
        if result.projection.S.state == "KNOWN" and int(result.projection.S.value or 0) == 0:
            return "SETTLED"
        return "WAITING"

    # -- reads ---------------------------------------------------------------
    def view(self, context: CommandContext, root_id: str) -> CaseView:
        session = self.session(context.session_id)
        connection = self.db.connect()
        try:
            row = connection.execute(
                "SELECT * FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
            if row is None or not self._session_can_see(session, row):
                raise NotFoundError("Không tìm thấy hồ sơ trong phạm vi phiên này.")
            return self._case_view(connection, row)
        finally:
            connection.close()

    def list_cases(self, context: CommandContext) -> tuple[CaseView, ...]:
        session = self.session(context.session_id)
        connection = self.db.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM cases WHERE tenant = ? ORDER BY created_at, id",
                (session.tenant,),
            ).fetchall()
            return tuple(
                self._case_view(connection, row)
                for row in rows
                if self._session_can_see(session, row)
            )
        finally:
            connection.close()

    # -- internals -----------------------------------------------------------
    @staticmethod
    def _session_can_see(session: DemoSession, row: sqlite3.Row) -> bool:
        # Employees act on their own scope (contracts §5); accountant/approver
        # tenant-scoped views arrive with their tasks.
        if session.persona == "employee" and row["employee"] != session.actor_id:
            return False
        return True

    def _require_root(
        self, cx: sqlite3.Connection, session: DemoSession, root_id: str
    ) -> sqlite3.Row:
        row = cx.execute(
            "SELECT * FROM cases WHERE id = ? AND tenant = ?", (root_id, session.tenant)
        ).fetchone()
        if row is None or not self._session_can_see(session, row):
            raise NotFoundError("Không tìm thấy hồ sơ trong phạm vi phiên này.")
        return row

    @staticmethod
    def _require_version(row: sqlite3.Row, expected: int) -> None:
        if int(row["version"]) != expected:
            raise StaleCommandError(
                "Hồ sơ đã thay đổi sau khi bạn tải: "
                f"bạn gửi theo version {expected}, hiện tại là {row['version']}. "
                "Hãy tải lại hồ sơ rồi gửi lại."
            )

    @staticmethod
    def _bump(cx: sqlite3.Connection, row: sqlite3.Row, now: str) -> None:
        cx.execute(
            "UPDATE cases SET version = version + 1, input_revision = input_revision + 1, "
            "updated_at = ? WHERE id = ?",
            (now, str(row["id"])),
        )

    @staticmethod
    def _reload(cx: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
        return cx.execute("SELECT * FROM cases WHERE id = ?", (str(row["id"]),)).fetchone()

    @staticmethod
    def _audit(
        cx: sqlite3.Connection,
        *,
        tenant: str,
        root_id: str | None,
        session_id: str | None,
        actor: str,
        action: str,
        detail: str,
        origin: str = "APP",
    ) -> None:
        cx.execute(
            "INSERT INTO audit_events (tenant, root_id, session_id, actor, action, "
            "detail, origin, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tenant,
                root_id,
                session_id,
                actor,
                action,
                detail,
                origin,
                datetime.now(UTC).isoformat(),
            ),
        )

    def _query_one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        connection = self.db.connect()
        try:
            return connection.execute(sql, params).fetchone()
        finally:
            connection.close()

    def _case_view(self, cx: sqlite3.Connection, row: sqlite3.Row) -> CaseView:
        activity = cx.execute(
            "SELECT name, budget_amount FROM context_activities "
            "WHERE activity_id = ? AND tenant = ?",
            (row["activity"], row["tenant"]),
        ).fetchone()
        person = cx.execute(
            "SELECT name FROM context_people WHERE id = ? AND tenant = ?",
            (row["employee"], row["tenant"]),
        ).fetchone()
        sources = tuple(
            SourceRef(
                id=source["source_id"],
                digest=source["digest"],
                tenant=source["tenant"],
                media=source["media"],
                storage_key=source["storage_key"],
            )
            for source in cx.execute(
                "SELECT * FROM case_sources WHERE root_id = ? "
                "ORDER BY attached_at, source_id",
                (str(row["id"]),),
            )
        )
        audit_rows = cx.execute(
            "SELECT action, actor, occurred_at FROM audit_events WHERE root_id = ? "
            "ORDER BY id DESC LIMIT 10",
            (str(row["id"]),),
        ).fetchall()
        activity_name = activity["name"] if activity is not None else row["activity_name"]
        employee_name = person["name"] if person is not None else row["employee"]

        # Persisted issues, conclusion and instructions (contracts §10.3).
        issues = tuple(
            BusinessIssue.model_validate_json(issue_row["payload_json"])
            for issue_row in cx.execute(
                "SELECT payload_json FROM case_issues WHERE root_id = ? "
                "AND status IN ('OPEN','ANSWERED') ORDER BY created_at, id",
                (str(row["id"]),),
            )
        )
        if not issues and (activity is None or activity["budget_amount"] is None) \
                and row["state"] == "DRAFT":
            issues = (_context_issue(str(row["id"])),)

        conclusion_row = cx.execute(
            "SELECT payload_json, decided_at FROM case_conclusions WHERE root_id = ? "
            "ORDER BY revision DESC LIMIT 1",
            (str(row["id"]),),
        ).fetchone()
        conclusion = None
        actual_money = _unknown_projection()
        if conclusion_row is not None:
            from invoice_referee.domain.case import SettlementConclusion

            result = AssessmentResult.model_validate_json(conclusion_row["payload_json"])
            actual_money = result.projection
            if result.issues:
                status = "BLOCKED"
            elif result.projection.S.state == "KNOWN" and int(result.projection.S.value or 0) == 0:
                status = "BALANCED"
            else:
                status = "OUTSTANDING"
            conclusion = SettlementConclusion(
                status=status,
                projection=result.projection,
                expense_dispositions=(),
                read_set=ReadSet(
                    input_revision=int(row["input_revision"]),
                    control_epoch=int(row["control_epoch"]),
                    context_version=1,
                    ledger_version=1,
                    usage_version=1,
                ),
                basis=result.cost_basis,
                actor_or_system="system:referee",
                decided_at=datetime.fromisoformat(conclusion_row["decided_at"]),
            )

        instructions = tuple(
            Instruction(
                id=inst["id"],
                root_id=inst["root_id"],
                direction=inst["direction"],
                amount=int(inst["amount"]),
                status=inst["status"],
                basis=inst["basis"],
                supersedes_id=inst["supersedes_id"],
                fulfilled_amount=int(inst["fulfilled_amount"]),
                remaining=max(int(inst["amount"]) - int(inst["fulfilled_amount"]), 0),
                execution_state=inst["execution_state"],
            )
            for inst in cx.execute(
                "SELECT * FROM instructions WHERE root_id = ? "
                "AND status IN ('ISSUED','PARTIAL','FULFILLED') ORDER BY created_at",
                (str(row["id"]),),
            )
        )
        return CaseView(
            id=row["id"],
            version=int(row["version"]),
            state=row["state"],
            summary=(
                f"{activity_name} · {_vn_date(row['activity_occurred_at'])} · {employee_name}"
            ),
            sources=sources,
            issues=issues,
            problems=(),
            conclusion=conclusion,
            instructions=instructions,
            actual_money=actual_money,
            audit=tuple(
                f"{entry['occurred_at']} · {entry['actor']} · {entry['action']}"
                for entry in audit_rows
            ),
        )
