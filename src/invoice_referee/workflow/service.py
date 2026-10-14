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
from invoice_referee.workflow.money import can_reverse, net_by_kind, verify_money_claim
from invoice_referee.workflow.instructions import InstructionState, reconcile_instruction

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
    # Server-owned business profile (T1): TRAVEL or WORK_EXPENSE.
    profile: str = "TRAVEL"

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


def _budget_for(budgets: tuple[dict[str, object], ...], activity_id: str) -> dict[str, object] | None:
    for budget in budgets:
        if str(budget.get("activity")) == activity_id:
            return budget
    return None


def _instruction_state(row: sqlite3.Row) -> "InstructionState":
    """Build the pure InstructionState the reconcile decision reads (§10.1)."""
    from invoice_referee.workflow.instructions import InstructionState

    return InstructionState(
        id=str(row["id"]),
        direction=str(row["direction"]),
        amount=int(row["amount"]),
        cost_basis=str(row["cost_basis"]),
        fulfilled_amount=int(row["fulfilled_amount"]),
        execution_state=str(row["execution_state"]),
        status=str(row["status"]),
    )


def _profile_allowed(grant: sqlite3.Row, profile: str | None) -> bool:
    """A grant with an explicit allowed_profiles list only covers those profiles.

    An empty list means the grant is profile-agnostic (plan R3). A grant for a
    different profile never authorizes this activity.
    """
    if profile is None:
        return True
    try:
        allowed = json.loads(grant["allowed_profiles_json"] or "[]")
    except (KeyError, IndexError):
        return True
    if not allowed:
        return True
    return profile in allowed


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
    # Server-owned business profile (T1); defaults to TRAVEL for older contexts.
    profile: str = "TRAVEL"
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
    # Profiles this grant is valid for; empty means all (plan R3).
    allowed_profiles: tuple[str, ...] = ()


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
        # The LIVE read seam (contracts §5, §8). Unset => the STUB/dev path reads
        # a seeded transcription. When set, submit reads the uploaded sources.
        self._transcriber: Callable[..., object] | None = None
        self._provider_mode: str = "STUB"
        # The §12 evidence pipeline seam (E7). Unset => the STUB/finance path.
        self._evidence_reader: object | None = None
        self._evidence_classifier: object | None = None
        self._evidence_artifacts: object | None = None
        self._evidence_source_bytes: dict[str, bytes] = {}
        self._evidence_provider_mode: str = "STUB"
        # The operation/step trace recorder (contracts §9; LangSmith wiring). It
        # is always present (a local no-op sink when tracing is disabled), so a
        # command can open an operation root without a None check. It never
        # affects business state and its export runs outside any txn.
        from invoice_referee.evidence.telemetry import TraceRecorder

        self._trace: TraceRecorder = TraceRecorder()
        # The last operation trace ref per root (persisted to the view/report so a
        # technical user can find the trace). Never a business field.
        self._last_trace_ref: dict[str, str] = {}

    def enable_live_read(self, transcriber: Callable[..., object], *, provider_mode: str) -> None:
        """Wire a read->transcription callable so submit reads real sources.

        The callable receives keyword args (sources, budget, provider_mode) and
        returns a ``ReadOutcome``. It runs outside the DB transaction (§6).
        """
        self._transcriber = transcriber
        self._provider_mode = provider_mode

    def enable_evidence_read(
        self,
        *,
        reader: object,
        classifier: object,
        artifacts_root: str | Path,
        source_bytes: dict[str, bytes] | None = None,
        provider_mode: str = "LIVE",
    ) -> None:
        """Wire the §12 evidence pipeline (OCR -> classify -> extract -> match).

        The pipeline is evidence-only: it produces a typed `ReadResult` and never
        reaches the finance consumer. Provider I/O runs outside the transaction.
        """
        from invoice_referee.evidence.artifacts import ArtifactStore

        self._evidence_reader = reader
        self._evidence_classifier = classifier
        self._evidence_artifacts = ArtifactStore(root=artifacts_root)
        self._evidence_source_bytes = source_bytes or {}
        self._evidence_provider_mode = provider_mode
        self._provider_mode = provider_mode

    def enable_trace(self, recorder) -> None:
        """Wire the operation/step trace recorder (composition root only)."""
        self._trace = recorder

    @property
    def trace(self):
        return self._trace

    def _trace_operation(
        self,
        name: str,
        *,
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
        tags: tuple[str, ...] = (),
    ):
        """Open a root span for one real operation (flush on exit, no txn)."""
        return self._trace.operation(name, run_id=run_id, metadata=metadata, tags=tags)

    def _record_trace_ref(self, root_id, operation) -> None:
        """Remember the operation trace ref for a root (debug reference only)."""
        if operation is None or root_id is None:
            return
        ref = self._trace.trace_ref(operation)
        if ref:
            self._last_trace_ref[str(root_id)] = ref

    def _evidence_wiring(self):
        return (
            self._evidence_reader,
            self._evidence_classifier,
            self._evidence_artifacts,
            self._evidence_provider_mode,
        )

    def _evidence_context(self, job_id: str):
        """Return (tenant, root_id, sources, source_bytes, profile) for a job, or None."""
        from invoice_referee.domain.evidence import SourceRef

        connection = self.db.connect()
        try:
            job = connection.execute(
                "SELECT tenant, root_id FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if job is None:
                return None
            tenant = str(job["tenant"])
            root_id = str(job["root_id"])
            case_row = connection.execute(
                "SELECT profile FROM cases WHERE id = ?", (root_id,)
            ).fetchone()
            profile = str(case_row["profile"]) if case_row is not None else None
            sources = tuple(
                SourceRef(
                    id=row["source_id"],
                    digest=row["digest"],
                    tenant=row["tenant"],
                    media=row["media"],
                    storage_key=row["storage_key"],
                    filename=row["filename"],
                )
                for row in connection.execute(
                    "SELECT * FROM case_sources WHERE root_id = ? ORDER BY attached_at, source_id",
                    (root_id,),
                )
            )
        finally:
            connection.close()
        source_bytes: dict[str, bytes] = {}
        for source in sources:
            payload = self._evidence_source_bytes.get(source.id)
            if payload is None:
                path = self.uploads_dir / source.storage_key
                if path.is_file():
                    payload = path.read_bytes()
            if payload is not None:
                source_bytes[source.id] = payload
        return tenant, root_id, sources, source_bytes, profile

    def _evidence_basis(self, cx: sqlite3.Connection, tenant: str, root_id: str) -> dict:
        """The input basis (source digest set + case version) for a job (§6)."""
        sources = [
            str(row["digest"])
            for row in cx.execute(
                "SELECT digest FROM case_sources WHERE root_id = ? ORDER BY source_id",
                (root_id,),
            )
        ]
        case = cx.execute("SELECT version FROM cases WHERE id = ?", (root_id,)).fetchone()
        return {
            "tenant": tenant,
            "root_id": root_id,
            "sources": sources,
            "case_version": int(case["version"]) if case is not None else None,
        }

    def _evidence_basis_current(self, cx: sqlite3.Connection, job: sqlite3.Row) -> bool:
        stored = job["input_basis_json"] if "input_basis_json" in job.keys() else None
        if not stored:
            return True
        try:
            basis = json.loads(stored)
        except (TypeError, ValueError):
            return True
        current = self._evidence_basis(cx, str(job["tenant"]), str(job["root_id"]))
        return basis.get("sources") == current.get("sources")

    def _mark_evidence_job(
        self, cx: sqlite3.Connection, job_id: str, *, phase: str, status: str
    ) -> None:
        cx.execute(
            "UPDATE jobs SET phase = ?, status = ?, updated_at = ? WHERE id = ?",
            (phase, status, self._now_iso(), job_id),
        )

    def _fail_evidence_job(self, cx: sqlite3.Connection, job_id: str, message: str) -> None:
        # A provider/artifact/OCR failure is visible: the case becomes
        # TECHNICAL_ERROR with a typed problem, never a silent PROCESSING (E7).
        cx.execute(
            "UPDATE jobs SET phase = 'DONE', status = 'FAILED', updated_at = ? WHERE id = ?",
            (self._now_iso(), job_id),
        )
        row = cx.execute("SELECT tenant, root_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        from invoice_referee.domain.evidence import ReadResult
        from invoice_referee.domain.issues import ProcessingProblem

        root_id = str(row["root_id"])
        cx.execute(
            "UPDATE cases SET state = 'TECHNICAL_ERROR', updated_at = ? WHERE id = ?",
            (self._now_iso(), root_id),
        )
        # Keep the provider error class + a short message so a failure is
        # diagnosable, without leaking secrets (redacted to a bounded length).
        detail = f"{type(message).__name__}: {message}" if not isinstance(message, str) else message
        detail = (detail or "").strip().replace("\n", " ")[:300]
        problem = ProcessingProblem(
            kind="TECHNICAL",
            affected_fields=(),
            message=f"đọc chứng cứ thất bại (lỗi kỹ thuật): {detail or 'không rõ'}",
            relevance="MATERIAL",
            blocking=True,
            next_action="retry_or_report_technical",
        )
        cx.execute(
            "INSERT OR REPLACE INTO case_evidence_reports (root_id, tenant, report_json, "
            "created_at) VALUES (?, ?, ?, ?)",
            (
                root_id,
                str(row["tenant"]),
                ReadResult(problems=(problem,)).model_dump_json(),
                self._now_iso(),
            ),
        )

    def _store_evidence_report(
        self, cx, *, tenant: str, root_id: str, report, basis: dict | None = None
    ) -> None:
        """Persist the typed report with its input basis (no state change)."""
        cx.execute(
            "INSERT OR REPLACE INTO case_evidence_reports (root_id, tenant, report_json, "
            "input_basis_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                root_id, tenant, report.model_dump_json(),
                json.dumps(basis or {}, ensure_ascii=False), self._now_iso(),
            ),
        )

    def _publish_evidence_report(
        self, cx, *, tenant: str, root_id: str, report, session=None
    ) -> None:
        self._store_evidence_report(cx, tenant=tenant, root_id=root_id, report=report)
        # The typed report is published; the case becomes EVIDENCE_READY. The
        # finance consumer then assesses the typed admission input from the
        # CURRENT stored state (plan A5). A Stop/changed basis before this point
        # is caught by the caller's re-check, so a stale report is not assessed.
        cx.execute(
            "UPDATE cases SET state = 'EVIDENCE_READY', updated_at = ? WHERE id = ?",
            (self._now_iso(), root_id),
        )

    def _reusable_report(self, cx: sqlite3.Connection, tenant: str, root_id: str):
        """A stored report whose input basis still matches the case, or None.

        A preview draft persists the report + the source digest set it was read
        from. On submit, if the case still has exactly those sources, the read is
        reused so OCR/LLM is not called again just because the employee confirmed
        (report P1-1/W3). A changed source set invalidates it.
        """
        from invoice_referee.domain.evidence import ReadResult

        row = cx.execute(
            "SELECT report_json, input_basis_json FROM case_evidence_reports WHERE root_id = ?",
            (root_id,),
        ).fetchone()
        if row is None or not row["report_json"]:
            return None
        try:
            basis = json.loads(row["input_basis_json"] or "{}")
        except (TypeError, ValueError):
            return None
        current = sorted(
            str(r["digest"])
            for r in cx.execute(
                "SELECT digest FROM case_sources WHERE root_id = ?", (root_id,)
            )
        )
        if basis.get("sources") != current:
            return None
        report = ReadResult.model_validate_json(row["report_json"])
        # A failed/empty read is not a reusable report.
        if not any(f.state == "FOUND" for d in report.documents for f in d.fields):
            return None
        return report

    def _claim_next_evidence_job(self) -> str | None:
        with self.db.transaction() as cx:
            row = cx.execute(
                "SELECT id FROM jobs WHERE status = 'QUEUED' AND kind = 'SUBMIT' "
                "ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = str(row["id"])
            cx.execute(
                "UPDATE jobs SET status = 'RUNNING', updated_at = ? WHERE id = ?",
                (self._now_iso(), job_id),
            )
            return job_id

    async def run_evidence_job_for(self, root_id: str) -> None:
        """Test/CLI helper: run the newest QUEUED evidence job for a root."""
        from invoice_referee.workflow.evidence_jobs import run_evidence_job

        with self.db.transaction() as cx:
            row = cx.execute(
                "SELECT id FROM jobs WHERE root_id = ? AND status = 'QUEUED' "
                "ORDER BY created_at DESC LIMIT 1",
                (root_id,),
            ).fetchone()
        if row is None:
            return
        await run_evidence_job(self, str(row["id"]))

    @property
    def provider_mode(self) -> str:
        return self._provider_mode

    @provider_mode.setter
    def provider_mode(self, value: str) -> None:
        self._provider_mode = value

    def _now_iso(self) -> str:
        return self._clock().isoformat()

    def _system_session(self, tenant: str) -> DemoSession:
        """A server-owned session for the evidence worker's typed assessment.

        The worker assesses with the system referee identity; it is not a user
        command, so no client session/actor is required (plan A5).
        """
        return DemoSession(
            session_id="session:evidence-worker",
            tenant=tenant,
            persona="system",
            actor_id="system:referee",
        )

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
                    "occurred_at, purpose, budget_amount, budget_effect_from, status, profile) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant, activity_id) DO UPDATE SET name = excluded.name, "
                    "occurred_at = excluded.occurred_at, purpose = excluded.purpose, "
                    "budget_amount = excluded.budget_amount, "
                    "budget_effect_from = excluded.budget_effect_from, "
                    "status = excluded.status, profile = excluded.profile",
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
                        activity.profile,
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
                    "actor, actions_json, scope, allowed_profiles_json, max_amount, "
                    "effective_from, effective_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        grant.id,
                        tenant,
                        grant.version,
                        grant.actor,
                        json.dumps(list(grant.actions), ensure_ascii=False),
                        grant.scope,
                        json.dumps(list(grant.allowed_profiles), ensure_ascii=False),
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
            # Store a typed snapshot the admission consumer reads, built from the
            # SAME demo data (plan A5/D): one source of truth. Budgets/grants/
            # witnesses are projected so the catalog and the typed consumer agree.
            self._store_demo_snapshot(cx, data, tenant=tenant, origin=origin, digest=digest)
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

    def _store_demo_snapshot(
        self, cx: sqlite3.Connection, data, *, tenant: str, origin: str, digest: str
    ) -> None:
        """Store a typed OrganizationContext snapshot from the demo context.

        The demo schema and the typed schema are different, so this maps the
        demo records (activities/budgets/grants/people/witnesses) into ONE
        OrganizationContext payload that the admission consumer reads. It does
        NOT invent money, budgets or history the demo context does not declare;
        an activity with no budget simply carries no budget.
        """
        from invoice_referee.domain.organization import OrganizationContext
        from invoice_referee.workflow.context_records import store_snapshot

        activities = tuple(
            {
                "id": activity.id,
                "activity_id": activity.id,
                "name": activity.name,
                "occurred_at": activity.occurred_at.isoformat() if activity.occurred_at else None,
                "purpose": activity.purpose,
                "status": activity.status,
                "profile": activity.profile,
            }
            for activity in data.activities
        )
        budgets = tuple(
            {
                "id": activity.budget.record_key if activity.budget else f"budget:{activity.id}",
                "activity": activity.id,
                "amount": activity.budget.amount,
                "effect_range": [
                    activity.budget.effect_from.isoformat() if activity.budget.effect_from else None,
                    None,
                ],
                "actor": "employee:approver",
            }
            for activity in data.activities
            if activity.budget is not None
        )
        grants = tuple(
            {
                "id": grant.id,
                "version": grant.version,
                "actor": grant.actor,
                "actions": list(grant.actions),
                "scope": grant.scope,
                "max_amount": grant.max_amount,
                "effective_from": grant.effective_from.isoformat(),
                "effective_to": grant.effective_to.isoformat() if grant.effective_to else None,
                "allowed_profiles": list(grant.allowed_profiles),
            }
            for grant in data.grants
        )
        context = OrganizationContext.model_validate(
            {
                "organization_id": tenant,
                "tenant": tenant,
                "profile": "TRAVEL",
                "data_origin": "SIMULATED",
                "activity": None,
                "activities": activities,
                "people": tuple({"id": p.id, "name": p.name} for p in data.people),
                "budgets": budgets,
                "grants": grants,
                "witnesses": tuple(
                    {"record_key": w.record_key, "quote": w.quote, "kind": w.kind}
                    for w in data.witnesses
                ),
            }
        )
        store_snapshot(cx, context, origin, imported_at=self._now_iso())

    def import_company_context(
        self, context: "object", *, origin: str = "SIMULATED"
    ) -> str:
        """Import a typed OrganizationContext through the same validated path.

        Persists the full validated payload as an immutable snapshot (so
        policies/budgets/ledger/coverage survive restart) AND projects the
        activity/people/grants/witnesses rows the existing commands read
        (plan A1). No expected/route value is stored; the ledger is trusted
        server fixture.
        """
        import json as _json

        from invoice_referee.domain.organization import OrganizationContext
        from invoice_referee.workflow.context_records import persist_context

        data = (
            context
            if isinstance(context, OrganizationContext)
            else OrganizationContext.model_validate(context)
        )
        tenant = data.organization_id or data.tenant
        now = self._now_iso()
        with self.db.transaction() as cx:
            digest = persist_context(cx, data, origin, imported_at=now)
            cx.execute(
                "INSERT INTO context_imports (tenant, digest, origin, imported_at, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (tenant, digest, origin, now, "typed company context"),
            )
            self._audit(
                cx, tenant=tenant, root_id=None, session_id=None,
                actor="system:context-import", action="CONTEXT_IMPORT",
                detail=_json.dumps({"digest": digest, "origin": origin}, ensure_ascii=False),
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
                profile=row["profile"] if "profile" in row.keys() else "TRAVEL",
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
        # The LIVE read happens outside the mutation transaction (§6): a submit
        # in LIVE reads the uploaded sources and persists the resulting
        # transcription before assessment. Provider I/O never runs inside the
        # BEGIN IMMEDIATE block.
        if command.kind == "SUBMIT" and self._transcriber is not None:
            await self._read_sources_for_submit(session, command.root_id)
        fingerprint = _fingerprint(context, command)
        # One operation root per command, flushed AFTER the transaction commits
        # (the context manager exits outside the BEGIN IMMEDIATE block). Child
        # steps run inside the handler and only BUFFER spans; no network I/O
        # happens inside the transaction (§4/§9).
        op_name = f"command:{command.kind.lower()}"
        command_root = getattr(command, "root_id", None)
        from invoice_referee.evidence.telemetry import code_revision

        with self._trace_operation(
            op_name,
            metadata={
                "command_id": context.command_id,
                "root_id": command_root,
                "actor": context.actor_id,
                "tenant": session.tenant,
                "provider_mode": self._provider_mode,
                "code_revision": code_revision(),
            },
            tags=("operation", command.kind.lower()),
        ) as operation:
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
                    operation.outputs["duplicate_command"] = True
                    return previous.model_copy(update={"duplicate_command": True})

                with self._trace.step("handler", operation=operation) as step:
                    result = handler(cx, session, context, command)
                    step.outputs["state"] = result.case_view.state
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
                self._record_trace_ref(command_root, operation)
                return result

    async def _read_sources_for_submit(self, session: DemoSession, root_id: str) -> None:
        """Read the root's sources (LIVE) and persist the transcription (§5, §6).

        Runs outside the mutation transaction. A run with no readable page
        persists nothing, so the assessment keeps the case unresolved rather
        than settling on a fabricated zero.
        """
        from invoice_referee.domain.evidence import SourceRef
        from invoice_referee.evidence.trace import RunBudget

        connection = self.db.connect()
        try:
            row = connection.execute(
                "SELECT * FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
            if row is None:
                return
            sources = tuple(
                SourceRef(
                    id=source["source_id"],
                    digest=source["digest"],
                    tenant=source["tenant"],
                    media=source["media"],
                    storage_key=source["storage_key"],
                    filename=source["filename"],
                )
                for source in connection.execute(
                    "SELECT * FROM case_sources WHERE root_id = ? ORDER BY attached_at, source_id",
                    (root_id,),
                )
            )
        finally:
            connection.close()
        if not sources:
            return
        assert self._transcriber is not None
        outcome = await self._transcriber(
            sources=sources,
            budget=RunBudget(),
            provider_mode=self._provider_mode,
        )
        transcription = getattr(outcome, "transcription", None)
        if transcription is None:
            return
        with self.db.transaction() as cx:
            cx.execute(
                "INSERT OR REPLACE INTO case_transcriptions (root_id, transcription_json, "
                "created_at) VALUES (?, ?, ?)",
                (root_id, transcription.model_dump_json(), self._now_iso()),
            )

    async def read_advance_draft(
        self,
        session: DemoSession,
        root_id: str,
        uploads: tuple[tuple[str, str, bytes], ...],
        *,
        method_hint: str | None = None,
    ):
        """Read an uploaded advance document into a prefilled draft (plan D).

        The accountant uploads a transfer receipt or cash voucher; the evidence
        pipeline reads every page and extracts fields, and this returns a DRAFT
        (never a committed event). Provider I/O runs OUTSIDE any transaction. A
        read that yields no usable document is a typed failure, not a fake draft.
        """
        import hashlib

        from invoice_referee.domain.evidence import SourceRef
        from invoice_referee.evidence.pipeline import read_root
        from invoice_referee.evidence.trace import RunBudget
        from invoice_referee.reconciliation.advance import draft_advance_from_document

        # Scope/employee come from the stored case, never the client.
        connection = self.db.connect()
        try:
            row = connection.execute(
                "SELECT * FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFoundError("Hồ sơ không tồn tại trong tenant này.")

        reader, classifier, artifacts, provider_mode = self._evidence_wiring()
        if reader is None:
            raise UnsupportedCommandError(
                "Chưa cấu hình đọc chứng từ (LIVE) cho môi trường này."
            )
        sources = []
        source_bytes: dict[str, bytes] = {}
        for index, (filename, media, payload) in enumerate(uploads, start=1):
            source_id = f"source:{hashlib.sha256(payload).hexdigest()[:16]}:adv{index}"
            sources.append(
                SourceRef(
                    id=source_id, digest=hashlib.sha256(payload).hexdigest(),
                    tenant=session.tenant, media=media,  # type: ignore[arg-type]
                    storage_key=f"{session.tenant}/{root_id}/{source_id}", filename=filename,
                )
            )
            source_bytes[source_id] = payload
        with self._trace_operation(
            "advance-draft-read",
            metadata={"root_id": root_id, "provider_mode": provider_mode, "sources": len(sources)},
            tags=("operation", "advance-draft-read"),
        ) as operation:
            report = await read_root(
                sources=tuple(sources), reader=reader, classifier=classifier,
                artifacts=artifacts, source_bytes=source_bytes, budget=RunBudget(),
                provider_mode=provider_mode, root_id=root_id,
            )
            operation.outputs["documents"] = len(report.documents)
        # Pick the document that actually carries advance fields; a clear one is
        # preferred over an unresolved one.
        def _score(document) -> int:
            fields = {f.field for f in document.fields if f.state == "FOUND"}
            score = len(fields & {"amount", "payee_name", "transaction_reference", "transaction_status"})
            if document.profile_status == "CLEAR":
                score += 1
            return score

        candidates = sorted(report.documents, key=_score, reverse=True)
        if not candidates or _score(candidates[0]) == 0:
            raise UnsupportedCommandError(
                "Không đọc được dữ liệu khoản ứng từ chứng từ đã tải lên."
            )
        return draft_advance_from_document(
            candidates[0], scope=str(row["activity"]), employee=str(row["employee"]),
            method_hint=method_hint,
        )

    async def read_settlement_draft(
        self,
        session: DemoSession,
        root_id: str,
        uploads: tuple[tuple[str, str, bytes], ...],
    ) -> dict[str, object]:
        """Read uploaded settlement documents through the OCR pipeline into a draft.

        Uses the SAME §12 evidence pipeline (OCR -> classify -> extract -> validate
        -> match) the reconciler consumes, so a PDF with text, a scanned PDF and a
        PNG/JPEG all go through one path (report P1-1). The typed report is
        persisted so a later submit can reuse it (W3). Provider I/O runs OUTSIDE
        any transaction; a provider failure raises, never a fabricated draft.
        """
        import hashlib

        from invoice_referee.domain.evidence import SourceRef
        from invoice_referee.evidence.pipeline import read_root
        from invoice_referee.evidence.trace import RunBudget
        from invoice_referee.reconciliation.settlement_draft import build_settlement_draft

        connection = self.db.connect()
        try:
            row = connection.execute(
                "SELECT * FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFoundError("Hồ sơ không tồn tại trong tenant này.")

        reader, classifier, artifacts, provider_mode = self._evidence_wiring()
        if reader is None:
            raise UnsupportedCommandError(
                "Chưa cấu hình đọc chứng từ (LIVE) cho môi trường này."
            )

        # Read the case's ATTACHED sources (the same bytes submit will reuse), so
        # the persisted report's basis matches on submit and OCR is not re-run
        # (W3). Uploads carry any not-yet-attached bytes; they are matched by
        # filename+digest and stored transiently for this read only.
        connection = self.db.connect()
        try:
            attached = tuple(
                SourceRef(
                    id=row2["source_id"], digest=row2["digest"], tenant=row2["tenant"],
                    media=row2["media"], storage_key=row2["storage_key"],
                    filename=row2["filename"],
                )
                for row2 in connection.execute(
                    "SELECT * FROM case_sources WHERE root_id = ? ORDER BY attached_at, source_id",
                    (root_id,),
                )
            )
        finally:
            connection.close()

        upload_by_digest = {
            hashlib.sha256(payload).hexdigest(): (filename, media, payload)
            for filename, media, payload in uploads
        }
        sources: list[SourceRef] = list(attached)
        source_bytes: dict[str, bytes] = {}
        for source in attached:
            payload = self._evidence_source_bytes.get(source.id)
            if payload is None:
                path = self.uploads_dir / source.storage_key
                if path.is_file():
                    payload = path.read_bytes()
            if payload is None:
                payload = upload_by_digest.get(source.digest, (None, None, None))[2]  # type: ignore[assignment]
            if payload is not None:
                source_bytes[source.id] = payload
        # Any uploaded file not yet attached is read transiently (so the preview
        # still works before attach); it will not be part of the submit basis.
        attached_digests = {s.digest for s in attached}
        for index, (filename, media, payload) in enumerate(uploads, start=1):
            digest = hashlib.sha256(payload).hexdigest()
            if digest in attached_digests:
                continue
            source_id = f"source:preview:{digest[:16]}:{index}"
            sources.append(
                SourceRef(
                    id=source_id, digest=digest, tenant=session.tenant,
                    media=media,  # type: ignore[arg-type]
                    storage_key=f"{session.tenant}/{root_id}/{source_id}",
                    filename=filename,
                )
            )
            source_bytes[source_id] = payload

        # One operation root for the draft read; spans buffer locally and flush
        # after the transaction below (no network inside the txn).
        with self._trace_operation(
            "settlement-draft-read",
            metadata={"root_id": root_id, "provider_mode": provider_mode, "sources": len(sources)},
            tags=("operation", "draft-read"),
        ) as operation:
            report = await read_root(
                sources=tuple(sources),
                reader=reader,
                classifier=classifier,
                artifacts=artifacts,
                source_bytes=source_bytes,
                budget=RunBudget(),
                provider_mode=provider_mode,
                root_id=root_id,
                activity_profile=str(row["profile"]) if "profile" in row.keys() else None,
            )

            draft = build_settlement_draft(report, sources=tuple(sources))
            operation.outputs["documents"] = len(report.documents)
            operation.outputs["warnings"] = len(draft.get("warnings", []))

            # Persist the typed report + its input basis so a submit on the same
            # sources reuses this read instead of calling OCR/LLM again (W3).
            with self.db.transaction() as cx:
                self._store_evidence_report(
                    cx,
                    tenant=session.tenant,
                    root_id=root_id,
                    report=report,
                    basis={
                        "sources": sorted(s.digest for s in attached),
                        "case_version": int(row["version"]),
                    },
                )
                # Persist the operation trace ref alongside the report (debug ref).
                self._last_trace_ref[root_id] = operation.run_id

        return draft

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
            "SELECT profile FROM context_activities WHERE activity_id = ? AND tenant = ?",
            (activity.activity_id, session.tenant),
        ).fetchone()
        # The activity's business profile is server/context-owned (T1): a known
        # activity uses its catalog profile; an unknown proposed activity defaults
        # to the general WORK_EXPENSE profile (not a global TRAVEL).
        activity_profile = (
            str(known["profile"])
            if known is not None and "profile" in known.keys() and known["profile"]
            else ("TRAVEL" if known is not None else "WORK_EXPENSE")
        )
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
                activity_profile,
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
        revision = self._next_declaration_revision(cx, str(row["id"]))
        cx.execute(
            "INSERT INTO case_declarations (root_id, revision, purpose, notes, draft_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(row["id"]),
                revision,
                command.declaration.declared_purpose,
                command.declaration.notes,
                self._declaration_draft_json(command.declaration, actor=context.actor_id, now=now),
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
    @staticmethod
    def _next_declaration_revision(cx: sqlite3.Connection, root_id: str) -> int:
        row = cx.execute(
            "SELECT COALESCE(MAX(revision), 0) AS r FROM case_declarations WHERE root_id = ?",
            (root_id,),
        ).fetchone()
        return int(row["r"]) + 1

    @staticmethod
    def _declaration_draft_json(declaration, *, actor: str, now: str) -> str:
        """The confirmed draft as auditable JSON (W4).

        Stores the employee-confirmed values AND the original OCR values, the
        server actor and the time. A correction is a declaration, not a verified
        fact: `corrected_fields` records which fields the employee changed.
        """
        confirmed = {
            "declared_name": declaration.declared_name,
            "destination": declaration.destination,
            "trip_start": declaration.trip_start,
            "trip_end": declaration.trip_end,
            "declared_advance": declaration.declared_advance,
            "incurred_total": declaration.incurred_total,
        }
        corrected: list[str] = []
        if (
            declaration.original_declared_advance is not None
            and declaration.declared_advance is not None
            and declaration.original_declared_advance != declaration.declared_advance
        ):
            corrected.append("declared_advance")
        return json.dumps(
            {
                "confirmed": confirmed,
                "original": {
                    "declared_advance": declaration.original_declared_advance,
                },
                "corrected_fields": corrected,
                "actor": actor,
                "observed_at": now,
            },
            ensure_ascii=False,
        )

    def _record_employee_paid_claims(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        command: "Submit",
        now: str,
    ) -> None:
        """Persist Q32 employee paid-claims as scoped confirmations (plan A2).

        The client states the claim; the server derives the actor (session),
        scope (root activity) and time (now), and resolves each file ref to an
        uploaded source of this root by filename + digest. A ref that does not
        resolve is rejected before any row is written, so a bad claim cannot
        leave a partial confirmation.
        """
        claims = getattr(command, "employee_paid_claims", ())
        if not claims:
            return
        root_id = str(row["id"])
        activity = str(row["activity"])
        sources = {}
        for r in cx.execute(
            "SELECT source_id, filename, digest FROM case_sources WHERE root_id = ?",
            (root_id,),
        ).fetchall():
            sources[(str(r["filename"]), str(r["digest"]))] = str(r["source_id"])
            sources[(str(r["source_id"]), str(r["digest"]))] = str(r["source_id"])
        for claim in claims:
            resolved_refs = []
            for ref in claim.refs:
                filename = ref.source_id[len("file:"):] if ref.source_id.startswith("file:") else ref.source_id
                source_id = sources.get((filename, ref.source_sha256))
                if source_id is None:
                    raise UnsupportedCommandError(
                        f"Chứng từ '{filename}' không khớp tệp đã tải lên hồ sơ này."
                    )
                resolved_refs.append(ref.model_copy(update={"source_id": source_id}))
            fact_key = f"expense:{claim.invoice_reference}:employee_paid"
            confirmation_id = (
                "confirmation:"
                + hashlib.sha256((root_id + fact_key).encode()).hexdigest()[:16]
            )
            cx.execute(
                "INSERT OR REPLACE INTO case_confirmations (id, tenant, root_id, fact_key, "
                "value, actor, scope, refs_json, reason, observed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    confirmation_id,
                    session.tenant,
                    root_id,
                    fact_key,
                    str(claim.amount),
                    session.actor_id,
                    activity,
                    json.dumps(
                        [ref.model_dump(mode="json") for ref in resolved_refs],
                        ensure_ascii=False,
                    ),
                    claim.reason,
                    now,
                ),
            )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=session.actor_id,
            action="RECORD_EMPLOYEE_PAID_CLAIMS",
            detail=json.dumps(
                {"claims": [c.invoice_reference for c in claims]}, ensure_ascii=False
            ),
        )

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
        root_id = str(row["id"])
        # P1-3: a draft root is created against a PROPOSED placeholder before the
        # activity is known (so the upload does not fabricate one). At submit the
        # declaration names the activity the employee chose; when the root is
        # still that unbound placeholder, rebind it to the AUTHORIZED catalog
        # activity (server-verified). A non-catalog activity is rejected. An
        # already-bound root must still match its own activity.
        declared_activity = command.declaration.activity_id
        current_activity = str(row["activity"])
        if declared_activity and declared_activity != current_activity:
            if current_activity.startswith(PROPOSED_ACTIVITY_PREFIX):
                entry = self.catalog_entry(session.tenant, declared_activity)
                if entry is None or entry.status != "AUTHORIZED":
                    raise UnsupportedCommandError(
                        "Hoạt động không có trong danh mục; không thể gắn hồ sơ."
                    )
                cx.execute(
                    "UPDATE cases SET activity = ?, activity_name = ?, "
                    "activity_occurred_at = ?, profile = ? WHERE id = ?",
                    (
                        entry.activity_id,
                        entry.name,
                        (entry.occurred_at or self._clock()).isoformat(),
                        entry.profile,
                        root_id,
                    ),
                )
                row = self._reload(cx, row)
            else:
                raise UnsupportedCommandError(
                    "Khai báo không khớp hoạt động của hồ sơ này."
                )
        elif current_activity.startswith(PROPOSED_ACTIVITY_PREFIX):
            # The employee kept the root's own NEW activity (it was not in the
            # catalog). Name it from the confirmed draft content so the dossier
            # does not carry the generic placeholder. It stays PROPOSED: no
            # budget/grant is fabricated; it enters the authorization follow-up
            # (requirement: a genuinely new activity asks for B/authority).
            name = (
                command.declaration.destination
                or command.declaration.declared_purpose
                or str(row["activity_name"])
            )
            cx.execute(
                "UPDATE cases SET activity_name = ? WHERE id = ?", (name, root_id)
            )
            row = self._reload(cx, row)
        # Q32 typed employee paid-claims (plan A2): the client states the claim;
        # the server resolves the file refs to the uploaded bytes and derives the
        # actor/scope/time. A foreign digest/ref is rejected before any write.
        self._record_employee_paid_claims(cx, session, row, command, now)
        # The employee-confirmed draft (W4): persist the confirmed values + notes
        # and the original OCR value as an auditable declaration. This is what the
        # reconciliation consumes; it never overwrites the actual company ledger.
        cx.execute(
            "INSERT INTO case_declarations (root_id, revision, purpose, notes, "
            "draft_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                root_id,
                self._next_declaration_revision(cx, root_id),
                command.declaration.declared_purpose,
                command.declaration.notes,
                self._declaration_draft_json(command.declaration, actor=context.actor_id, now=now),
                now,
            ),
        )
        # A submit is a durable job (contracts §6, §10.4): one active job per
        # root, READ -> ASSESS -> DONE. A crash mid-job leaves it recoverable
        # rather than half-applied. The read already ran outside the txn.
        from invoice_referee.workflow.jobs import JobStore

        store = JobStore(self.db)
        existing = store.active_job(cx, session.tenant, root_id)
        job_id = (
            str(existing["id"])
            if existing is not None
            else store.enqueue(cx, tenant=session.tenant, root_id=root_id, kind="SUBMIT", now=now)
        )
        # In evidence mode (LIVE/RECORDED_REPLAY) the submit normally enqueues a
        # durable evidence job and returns immediately; the worker produces the
        # typed report (contracts §12.5, plan E7). BUT when the employee already
        # reviewed a draft on the SAME sources, that read is reused: the stored
        # report is assessed directly instead of calling OCR/LLM again (W3). A
        # changed source set is not reused, so it re-reads.
        if self._evidence_reader is not None:
            reusable = self._reusable_report(cx, session.tenant, root_id)
            if reusable is not None:
                store.mark(cx, job_id, phase="ASSESSING", status="RUNNING", now=now)
                self._assess_and_commit(cx, session, row, now)
                store.mark(cx, job_id, phase="DONE", status="COMPLETED", now=now)
                return CommandResult(
                    case_view=self._case_view(cx, self._reload(cx, row)), job_id=job_id
                )
            # Persist the input basis at enqueue so a source change before the
            # worker publishes invalidates the stale result (contracts §6).
            basis = self._evidence_basis(cx, session.tenant, root_id)
            cx.execute(
                "UPDATE jobs SET submit_requested = 1, status = 'QUEUED', "
                "input_basis_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(basis, ensure_ascii=False), now, job_id),
            )
            cx.execute(
                "UPDATE cases SET state = 'PROCESSING', version = version + 1, "
                "input_revision = input_revision + 1, updated_at = ? WHERE id = ?",
                (now, root_id),
            )
            return CommandResult(
                case_view=self._case_view(cx, self._reload(cx, row)), job_id=job_id
            )
        store.mark(cx, job_id, phase="ASSESSING", status="RUNNING", now=now)
        self._assess_and_commit(cx, session, row, now)
        store.mark(cx, job_id, phase="DONE", status="COMPLETED", now=now)
        return CommandResult(
            case_view=self._case_view(cx, self._reload(cx, row)), job_id=job_id
        )

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
        # The answer is persisted as a responsible confirmation keyed by the
        # issue's field/rule, so the re-assessment consumes the supplied value
        # instead of recomputing the same issue back to OPEN (contracts §3, §5).
        fact_key = str(issue["field_or_rule"])
        if answer.value is not None and str(answer.value).strip() != "":
            confirmation_id = f"confirmation:{hashlib.sha256((str(row['id']) + fact_key).encode()).hexdigest()[:16]}"
            cx.execute(
                "INSERT OR REPLACE INTO case_confirmations (id, tenant, root_id, fact_key, "
                "value, actor, scope, refs_json, reason, observed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    confirmation_id,
                    session.tenant,
                    str(row["id"]),
                    fact_key,
                    str(answer.value),
                    context.actor_id,
                    str(row["activity"]),
                    json.dumps(
                        [ref.model_dump(mode="json") for ref in answer.refs],
                        ensure_ascii=False,
                    ),
                    answer.reason,
                    now,
                ),
            )
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
                str(row["profile"]),
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
        # The record binds to THIS dossier's scope: a client cannot record money
        # into another activity through this root (§4, plan D).
        if money.claimed_scope not in (str(row["activity"]), session.tenant):
            raise UnsupportedCommandError(
                "Phạm vi ghi nhận không khớp hoạt động của hồ sơ này."
            )
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
        # The server decides verification/allocation from the claim's evidence
        # (contracts §3–§4): a bare statement stays OBSERVED and never fulfills.
        verification = verify_money_claim(money, responsible_actor=context.actor_id)
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
            verification_state=verification.verification_state,  # type: ignore[arg-type]
            allocation_state=verification.allocation_state,  # type: ignore[arg-type]
            reverses_event_id=money.reverses_event_id,
            refs=money.refs,
            instrument_method=money.instrument_method,
            instrument_status=money.instrument_status,
            instrument_reference=money.instrument_reference,
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
                str(row["profile"]),
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

    def _covering_grant_ids(
        self,
        cx: sqlite3.Connection,
        tenant: str,
        actor: str,
        action: str,
        scope: str,
        amount: int,
    ) -> tuple[str, ...]:
        """The grant ids that authorize `action` at `scope` for `amount` (§2, §5)."""
        now = datetime.now(UTC)
        ids: list[str] = []
        for grant in cx.execute(
            "SELECT * FROM context_grants WHERE tenant = ? AND actor = ?",
            (tenant, actor),
        ).fetchall():
            if action not in json.loads(grant["actions_json"]):
                continue
            if str(grant["scope"]) not in (scope, tenant):
                continue
            if amount > int(grant["max_amount"]):
                continue
            eff_from = datetime.fromisoformat(grant["effective_from"])
            eff_to = (
                datetime.fromisoformat(grant["effective_to"])
                if grant["effective_to"]
                else None
            )
            if eff_from <= now and (eff_to is None or now <= eff_to):
                ids.append(str(grant["grant_id"]))
        return tuple(ids)

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
        profile: str | None = None,
    ) -> bool:
        """A grant authorizes one action, one scope, one profile and an amount.

        The scope must be the activity (or the tenant-wide convention); the
        profile must be allowed by the grant; a grant scoped elsewhere never
        authorizes this action. When `amount` is given it must not exceed the
        grant's `max_amount` (per action, inclusive). Contracts §5.
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
            if not _profile_allowed(grant, profile):
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

        root_id = str(row["id"])
        # Stop is atomic with the commit: a worker whose snapshot predates a
        # Stop must not create a new instruction (contracts §6).
        if str(row["state"]) == "STOPPED":
            return
        from invoice_referee.evidence.telemetry import step

        with step("admission", metadata={"root_id": root_id}) as s:
            assessment_input = self._build_assessment_input(cx, session, row, now)
            if assessment_input is not None:
                rs = assessment_input.read_set
                s.outputs["expenses"] = len(assessment_input.expense_facts)
                s.outputs["admission_issues"] = len(assessment_input.admission_issues)
                s.outputs["input_revision"] = rs.input_revision
                s.outputs["control_epoch"] = rs.control_epoch
                s.outputs["context_version"] = rs.context_version
                s.outputs["ledger_version"] = rs.ledger_version
                s.outputs["usage_version"] = rs.usage_version
                s.outputs["provider_mode"] = assessment_input.scope.profile
        if assessment_input is None:
            # Evidence mode with no published report yet: stay EVIDENCE_READY.
            # A LIVE/REPLAY root must never fall back to a seeded STUB
            # transcription (contracts §12.5, plan E7/A5).
            return
        with step("reconcile", metadata={"root_id": root_id}) as s:
            result = Reconciler().assess(assessment_input)
            s.outputs["state_S"] = result.projection.S.state
            s.outputs["issues"] = len(result.issues)
            s.outputs["allowed_effect"] = (
                None if result.allowed_effect is None
                else f"{result.allowed_effect.direction}:{result.allowed_effect.amount}"
            )
        with step("commit", metadata={"root_id": root_id}) as s:
            self._commit_assessment(cx, session, row, result, now)
            s.outputs["committed"] = True

    def _build_assessment_input(
        self, cx: sqlite3.Connection, session: DemoSession, row: sqlite3.Row, now: str
    ):
        """Build the typed AssessmentInput, or None when the evidence report is absent.

        In evidence mode (LIVE/RECORDED_REPLAY) the typed admission mapper is the
        only consumer: it reads the CURRENT stored report + context + confirmations
        (never a seeded STUB transcription). In STUB mode the hand-transcription
        path is used as before. `now` is the server/harness clock instant; it is
        passed through so coverage freshness and every time-scoped gate use the
        same assessment time (never a client-supplied clock).
        """
        from invoice_referee.workflow.snapshots import build_assessment_input

        as_of = datetime.fromisoformat(now)
        root_id = str(row["id"])
        if self._evidence_reader is not None:
            from invoice_referee.domain.evidence import ReadResult
            from invoice_referee.workflow.evidence_assessment import (
                build_evidence_assessment_input,
            )

            report_row = cx.execute(
                "SELECT report_json FROM case_evidence_reports WHERE root_id = ?",
                (root_id,),
            ).fetchone()
            if report_row is None or not report_row["report_json"]:
                return None
            report = ReadResult.model_validate_json(report_row["report_json"])
            return build_evidence_assessment_input(
                cx, tenant=session.tenant, root_id=root_id, report=report, as_of=as_of
            )
        transcription = self._transcription_for(cx, root_id)
        return build_assessment_input(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            employee=str(row["employee"]),
            activity=str(row["activity"]),
            profile=str(row["profile"]),
            transcription=transcription,
            as_of=as_of,
        )

    def _commit_assessment(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        row: sqlite3.Row,
        result,
        now: str,
    ) -> None:
        """Persist issues/conclusion/instruction for an assessed result atomically."""
        root_id = str(row["id"])

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
            cx, session.tenant, root_id, result
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

        decision = reconcile_instruction(
            _instruction_state(active) if active is not None else None,
            direction=effect.direction,
            amount=effect.amount,
            cost_basis=result.cost_basis,
        )

        if decision.action == "RETAIN":
            return decision.result_state
        if decision.action == "REACTIVATE":
            reactivated = "PARTIAL" if int(active["fulfilled_amount"]) > 0 else "ISSUED"
            cx.execute(
                "UPDATE instructions SET status = ?, updated_at = ? WHERE id = ?",
                (reactivated, now, str(active["id"])),
            )
            return decision.result_state
        if decision.action == "SUSPEND":
            cx.execute(
                "UPDATE instructions SET status = 'SUSPENDED', updated_at = ? WHERE id = ?",
                (now, str(active["id"])),
            )
            return decision.result_state

        # ISSUE / REPLACE: supersede any current actionable remainder, then issue
        # the full abs(S) as a new instruction.
        cx.execute(
            "UPDATE instructions SET status = 'SUPERSEDED', updated_at = ? "
            "WHERE root_id = ? AND status IN ('ISSUED','PARTIAL','SUSPENDED','EXECUTION_UNKNOWN')",
            (now, root_id),
        )
        self._issue_instruction(cx, session, row, result, now, active)
        return decision.result_state

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
        # The authority that lets this order be issued (contracts §2): the
        # covering system grant(s) for the action at this scope/amount. Recorded
        # so the instruction is grounded, not merely asserted.
        action = "ISSUE_PAYMENT" if effect.direction == "PAY" else "ISSUE_COLLECTION"
        authority_refs = self._covering_grant_ids(
            cx, session.tenant, "system:referee", action, str(row["activity"]), effect.amount
        )
        cx.execute(
            "INSERT INTO instructions (id, tenant, root_id, direction, amount, "
            "status, basis, cost_basis, authority_refs_json, supersedes_id, "
            "fulfilled_amount, execution_state, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'ISSUED', ?, ?, ?, ?, 0, 'NOT_STARTED', ?, ?)",
            (
                instruction_id,
                session.tenant,
                root_id,
                effect.direction,
                effect.amount,
                effect.basis,
                result.cost_basis,
                json.dumps(list(authority_refs), ensure_ascii=False),
                str(supersedes["id"]) if supersedes is not None else None,
                now,
                now,
            ),
        )
        # Record economic usage so a second root cannot claim the same obligation
        # (§10.2). The first writer becomes the canonical owner. The keys come
        # from the CURRENT result (each the document bound to a cost), so the
        # LIVE evidence path keys on the same identity admission used.
        for economic_key in (result.economic_keys or self._economic_keys_for(cx, root_id)):
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
        self, cx: sqlite3.Connection, tenant: str, root_id: str, result=None
    ) -> bool:
        """True if any of this root's economic keys is owned by another root.

        The keys come from the CURRENT assessment result when available (each the
        document bound to a cost), so the LIVE evidence path checks the same
        identity admission produced rather than a stale STUB transcription.
        """
        keys = (
            tuple(str(k) for k in result.economic_keys if str(k))
            if result is not None and getattr(result, "economic_keys", ())
            else self._economic_keys_for(cx, root_id)
        )
        for economic_key in keys:
            row = cx.execute(
                "SELECT owner_root FROM usage_registry WHERE tenant = ? AND economic_key = ?",
                (tenant, economic_key),
            ).fetchone()
            if row is not None and str(row["owner_root"]) != root_id:
                return True
        return False

    def _economic_keys_for(self, cx: sqlite3.Connection, root_id: str) -> tuple[str, ...]:
        """The canonical economic identities this root claims (dedup/usage).

        The evidence (LIVE/REPLAY) path stores the admitted expenses — each with
        the identity of the document BOUND to it — in the latest conclusion, so
        the usage/anti-duplicate consumer sees the same identity admission used.
        The STUB hand-transcription path keeps its `case_transcriptions` keys.
        A root with neither basis yields no keys (never a fabricated identity).
        """
        from invoice_referee.domain.case import AssessmentResult

        conclusion = cx.execute(
            "SELECT payload_json FROM case_conclusions WHERE root_id = ? "
            "ORDER BY revision DESC LIMIT 1",
            (root_id,),
        ).fetchone()
        if conclusion is not None and conclusion["payload_json"]:
            try:
                result = AssessmentResult.model_validate_json(conclusion["payload_json"])
            except Exception:
                result = None
            if result is not None:
                # The conclusion carries the distinct identities of the admitted
                # costs (each the document bound to that cost).
                keys = tuple(str(k) for k in result.economic_keys if str(k))
                if keys:
                    return keys
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
        # When a LIVE reader is wired, the read result is authoritative: a STUB
        # transcription seeded for the demo path must not be consulted, so a
        # failed read stays unresolved instead of falling back to fake input
        # (contracts §5, §8).
        if self._transcriber is not None:
            return None
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
                filename=source["filename"],
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
                payment_basis=result.payment_basis,
            )

        instructions = tuple(
            Instruction(
                id=inst["id"],
                root_id=inst["root_id"],
                direction=inst["direction"],
                amount=int(inst["amount"]),
                status=inst["status"],
                basis=inst["basis"],
                authority_refs=tuple(
                    json.loads(inst["authority_refs_json"] or "[]")
                    if "authority_refs_json" in inst.keys()
                    else ()
                ),
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
        # The typed evidence report (contracts §12.5): present after a LIVE/
        # RECORDED_REPLAY read; it is pipeline completion only, never finance.
        evidence_report = None
        assessment_ready = True
        assessment_blocker = None
        report_row = cx.execute(
            "SELECT report_json FROM case_evidence_reports WHERE root_id = ?",
            (str(row["id"]),),
        ).fetchone()
        if report_row is not None and report_row["report_json"]:
            from invoice_referee.domain.evidence import ReadResult

            evidence_report = ReadResult.model_validate_json(report_row["report_json"])
            if conclusion is None:
                # The report is published but the typed admission has not yet
                # produced a conclusion (the worker has not assessed, or a Stop
                # held it): show the report and mark the assessment pending. Once
                # the consumer runs, the real conclusion/instruction is shown
                # (plan A5; the E7 "never assess" guard is released here).
                assessment_ready = False
                assessment_blocker = "EVIDENCE_ASSESSMENT_PENDING"
                instructions = ()
        return CaseView(
            id=row["id"],
            version=int(row["version"]),
            state=row["state"],
            activity=row["activity"],
            employee=row["employee"],
            summary=(
                f"{activity_name} · {_vn_date(row['activity_occurred_at'])} · {employee_name}"
            ),
            sources=sources,
            issues=issues,
            problems=(evidence_report.problems if evidence_report is not None else ()),
            conclusion=conclusion,
            instructions=instructions,
            actual_money=actual_money,
            audit=tuple(
                f"{entry['occurred_at']} · {entry['actor']} · {entry['action']}"
                for entry in audit_rows
            ),
            evidence_report=evidence_report,
            assessment_ready=assessment_ready,
            assessment_blocker=assessment_blocker,
            payment_basis=conclusion.payment_basis if conclusion is not None else (),
            trace_refs=(
                (self._last_trace_ref[str(row["id"])],)
                if str(row["id"]) in self._last_trace_ref
                else ()
            ),
        )
