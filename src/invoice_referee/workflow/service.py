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

from pydantic import BaseModel, ConfigDict, Field, field_validator
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
    ConfirmCoverage,
    ConfirmMoneyHistory,
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
from invoice_referee.domain.evidence import EvidenceRef, SourceRef
from invoice_referee.domain.finance import (
    ActivityAcceptance,
    ActivityLinkSignal,
    CoverageRecord,
    EmployeeReturnDraft,
    MoneyEvent,
    MoneyMovementSignal,
    Projection,
)
from invoice_referee.domain.issues import BusinessIssue
from invoice_referee.workflow.controls import (
    StaleControlError,
    assert_epoch_current,
    bump_epoch,
    context_version,
)
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.money import can_reverse, net_by_kind, verify_money_claim
from invoice_referee.workflow.instructions import (
    InstructionState,
    reconcile_instruction,
)

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
    # Namespaced advance/dossier references this activity is known by
    # (e.g. "TU-2026-001"); used for DOCUMENT_REFERENCE linking (14/10/2026).
    references: tuple[str, ...] = ()

    @property
    def has_budget(self) -> bool:
        return self.budget_amount is not None


def _activity_references(row) -> tuple[str, ...]:
    """Parse the server-owned dossier references for one activity row.

    Stored as JSON in ``context_activities.references_json`` (migration v6).
    A missing column (pre-v6 DB) or bad payload yields no references — never
    a fabricated link.
    """
    try:
        raw = row["references_json"] if "references_json" in row.keys() else "[]"
    except (KeyError, TypeError, ValueError):
        return ()
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(str(v) for v in values if isinstance(v, str) and str(v).strip())


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
    digest = hashlib.sha256(
        f"{tenant}|{employee}|{activity}".encode("utf-8")
    ).hexdigest()
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


def _budget_for(
    budgets: tuple[dict[str, object], ...], activity_id: str
) -> dict[str, object] | None:
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
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _invoice_paid_reference(fact_key: str) -> str | None:
    prefix, suffix = "expense:", ":employee_paid"
    if not fact_key.startswith(prefix) or not fact_key.endswith(suffix):
        return None
    reference = fact_key[len(prefix) : -len(suffix)].strip()
    return reference or None


def _employee_paid_amount(value: object) -> int | None:
    """Parse an exact positive VND integer from the employee answer field."""
    import re

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"\d+|\d{1,3}(?:[. ]\d{3})+", text):
            return None
        amount = int(text.replace(".", "").replace(" ", ""))
    else:
        return None
    return amount if amount > 0 else None


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
    # Server-owned dossier identities used by backend settlement linking.
    references: tuple[str, ...] = ()
    budget: _DemoBudget | None = None
    # Optional STUB hand-transcription for the dev/UI path (contracts §5).
    transcription: tuple[dict[str, object], ...] | None = None

    @field_validator("references", mode="before")
    @classmethod
    def _validate_references(cls, value: object) -> tuple[str, ...]:
        from invoice_referee.workflow.context_records import validate_activity_references

        return validate_activity_references(value)


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

    def enable_live_read(
        self, transcriber: Callable[..., object], *, provider_mode: str
    ) -> None:
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

    def _evidence_basis(
        self, cx: sqlite3.Connection, tenant: str, root_id: str
    ) -> dict:
        """The input basis (source digest set + case version) for a job (§6)."""
        sources = [
            str(row["digest"])
            for row in cx.execute(
                "SELECT digest FROM case_sources WHERE root_id = ? ORDER BY source_id",
                (root_id,),
            )
        ]
        case = cx.execute(
            "SELECT version FROM cases WHERE id = ?", (root_id,)
        ).fetchone()
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

    def _fail_evidence_job(
        self, cx: sqlite3.Connection, job_id: str, message: str
    ) -> None:
        # A provider/artifact/OCR failure is visible: the case becomes
        # TECHNICAL_ERROR with a typed problem, never a silent PROCESSING (E7).
        cx.execute(
            "UPDATE jobs SET phase = 'DONE', status = 'FAILED', updated_at = ? WHERE id = ?",
            (self._now_iso(), job_id),
        )
        row = cx.execute(
            "SELECT tenant, root_id FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
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
        detail = (
            f"{type(message).__name__}: {message}"
            if not isinstance(message, str)
            else message
        )
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
                root_id,
                tenant,
                report.model_dump_json(),
                json.dumps(basis or {}, ensure_ascii=False),
                self._now_iso(),
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
        return DemoSession(
            session_id=session_id, tenant=tenant, persona=persona, actor_id=actor
        )

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
            session_id=session_id,
            tenant=current.tenant,
            persona=persona,
            actor_id=actor,
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
                    "occurred_at, purpose, budget_amount, budget_effect_from, status, profile, "
                    "references_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant, activity_id) DO UPDATE SET name = excluded.name, "
                    "occurred_at = excluded.occurred_at, purpose = excluded.purpose, "
                    "budget_amount = excluded.budget_amount, "
                    "budget_effect_from = excluded.budget_effect_from, "
                    "status = excluded.status, profile = excluded.profile, "
                    "references_json = excluded.references_json",
                    (
                        activity.id,
                        tenant,
                        activity.name,
                        activity.occurred_at.isoformat()
                        if activity.occurred_at
                        else None,
                        activity.purpose,
                        budget.amount if budget else None,
                        budget.effect_from.isoformat()
                        if budget and budget.effect_from
                        else None,
                        activity.status,
                        activity.profile,
                        json.dumps(list(activity.references), ensure_ascii=False),
                    ),
                )
            # Seed a demo STUB transcription for activities that declare one, so
            # the STUB dev/UI path can assess without a provider (contracts §5).
            from invoice_referee.evaluation.models import (
                Transcription,
                TranscriptionFact,
            )

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
            self._store_demo_snapshot(
                cx, data, tenant=tenant, origin=origin, digest=digest
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
                    {
                        "digest": digest,
                        "origin": origin,
                        "activities": len(data.activities),
                    },
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
                "occurred_at": activity.occurred_at.isoformat()
                if activity.occurred_at
                else None,
                "purpose": activity.purpose,
                "status": activity.status,
                "profile": activity.profile,
                "references": list(activity.references),
            }
            for activity in data.activities
        )
        budgets = tuple(
            {
                "id": activity.budget.record_key
                if activity.budget
                else f"budget:{activity.id}",
                "activity": activity.id,
                "amount": activity.budget.amount,
                "effect_range": [
                    activity.budget.effect_from.isoformat()
                    if activity.budget.effect_from
                    else None,
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
                "effective_to": grant.effective_to.isoformat()
                if grant.effective_to
                else None,
                "allowed_profiles": list(grant.allowed_profiles),
            }
            for grant in data.grants
        )
        context = OrganizationContext.model_validate(
            {
                "organization_id": tenant,
                "company_name": data.organization.name,
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
                cx,
                tenant=tenant,
                root_id=None,
                session_id=None,
                actor="system:context-import",
                action="CONTEXT_IMPORT",
                detail=_json.dumps(
                    {"digest": digest, "origin": origin}, ensure_ascii=False
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
                profile=row["profile"] if "profile" in row.keys() else "TRAVEL",
                references=_activity_references(row),
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

    def last_context_import(
        self, tenant: str = DEFAULT_TENANT
    ) -> dict[str, str] | None:
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
    async def execute(
        self, context: CommandContext, command: CaseCommand
    ) -> CommandResult:
        session = self.session(context.session_id)
        handlers: dict[str, Callable[..., CommandResult]] = {
            "CREATE_DRAFT": self._create_draft,
            "ATTACH_SOURCES": self._attach_sources,
            "REVISE_DECLARATION": self._revise_declaration,
            "SUBMIT": self._submit,
            "ANSWER_ISSUE": self._answer_issue,
            "DECIDE": self._decide,
            "RECORD_ACTUAL": self._record_actual,
            "CONFIRM_COVERAGE": self._confirm_coverage,
            "CONFIRM_MONEY_HISTORY": self._confirm_money_history,
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
        from invoice_referee.evidence.trace import stage_payload

        def _command_trace_payload(
            result: CommandResult,
            *,
            status: str,
            duplicate: bool,
            before,
            after,
        ) -> dict[str, object]:
            view = result.case_view
            axes = {}
            for axis in ("T", "E", "C", "A", "P", "R", "unpaid", "S"):
                fact = getattr(view.actual_money, axis)
                axes[axis] = {
                    "state": fact.state,
                    "value": fact.value if fact.state == "KNOWN" else None,
                }
            issues = []
            for issue in view.issues:
                field_or_rule = issue.field_or_rule
                issue_owner = (
                    issue.owner
                    if issue.owner in {"employee", "accountant", "approver", "org-data"}
                    else "REDACTED_OWNER"
                )
                item = {
                    "kind": issue.kind,
                    "field_or_rule": field_or_rule,
                    "owner": issue_owner,
                    "status": issue.status,
                }
                if "arithmetic" in field_or_rule.lower():
                    item["basis"] = issue.basis
                issues.append(item)
            return stage_payload(
                "command",
                {
                    "command": command.kind,
                    "status": status,
                    "duplicate_command": duplicate,
                    "state": view.state,
                    "case_version": view.version,
                    "state_before": str(before["state"])
                    if before is not None
                    else None,
                    "state_after": view.state,
                    "version_before": int(before["version"])
                    if before is not None
                    else None,
                    "version_after": int(after["version"])
                    if after is not None
                    else view.version,
                    "input_revision": int(after["input_revision"])
                    if after is not None
                    else None,
                    "job_id": result.job_id,
                    "instructions": [
                        {
                            "id": instruction.id,
                            "direction": instruction.direction,
                            "amount": instruction.amount,
                            "status": instruction.status,
                            "execution_state": instruction.execution_state,
                            "fulfilled_amount": instruction.fulfilled_amount,
                            "remaining": instruction.remaining,
                        }
                        for instruction in view.instructions
                    ],
                    "axes": axes,
                    "issues": issues,
                    "issue_count": len(issues),
                    "conclusion_status": (
                        view.conclusion.status if view.conclusion is not None else None
                    ),
                },
            )

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
                before = (
                    cx.execute(
                        "SELECT state, version, input_revision FROM cases "
                        "WHERE id = ? AND tenant = ?",
                        (command_root, session.tenant),
                    ).fetchone()
                    if command_root is not None
                    else None
                )
                operation.inputs.update(
                    stage_payload(
                        "command",
                        {
                            "command": command.kind,
                            "state_before": str(before["state"])
                            if before is not None
                            else None,
                            "version_before": int(before["version"])
                            if before is not None
                            else None,
                            "input_revision": int(before["input_revision"])
                            if before is not None
                            else None,
                        },
                    )
                )
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
                    after = cx.execute(
                        "SELECT state, version, input_revision FROM cases WHERE id = ? AND tenant = ?",
                        (previous.case_view.id, session.tenant),
                    ).fetchone()
                    operation.outputs.update(
                        _command_trace_payload(
                            previous,
                            status="DUPLICATE",
                            duplicate=True,
                            before=before,
                            after=after,
                        )
                    )
                    return previous.model_copy(update={"duplicate_command": True})

                with self._trace.step("handler", operation=operation) as step:
                    result = handler(cx, session, context, command)
                    step.outputs.update(
                        _command_trace_payload(
                            result,
                            status="HANDLED",
                            duplicate=False,
                            before=before,
                            after=None,
                        )
                    )
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
                after = cx.execute(
                    "SELECT state, version, input_revision FROM cases "
                    "WHERE id = ? AND tenant = ?",
                    (result.case_view.id, session.tenant),
                ).fetchone()
                result_trace = _command_trace_payload(
                    result,
                    status="COMPLETED",
                    duplicate=False,
                    before=before,
                    after=after,
                )
                operation.outputs.update(result_trace)
                self._record_trace_ref(command_root, operation)
                return result

    async def _read_sources_for_submit(
        self, session: DemoSession, root_id: str
    ) -> None:
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
        """Read an attached advance document into a durable, prefilled draft.

        The accountant uploads a transfer receipt or cash voucher; the evidence
        pipeline reads every page and extracts fields, and this returns a DRAFT
        (never a committed event). The source must already belong to this root and
        is loaded by its persisted source ID/digest. Provider I/O runs OUTSIDE any
        transaction. The report and draft are stored so confirmation can validate
        the exact read later, including after restart.
        """
        import hashlib

        from invoice_referee.domain.evidence import SourceRef
        from invoice_referee.evidence.pipeline import read_root, trace_read_report
        from invoice_referee.evidence.trace import RunBudget
        from invoice_referee.reconciliation.advance import draft_advance_from_document

        if session.persona != "accountant":
            raise UnsupportedCommandError("Chỉ kế toán được bổ sung chứng từ ứng.")

        # Scope/employee and source identities come from the stored root, never
        # the client or a transient reference.
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
        for filename, media, payload in uploads:
            digest = hashlib.sha256(payload).hexdigest()
            connection = self.db.connect()
            try:
                stored = connection.execute(
                    "SELECT * FROM case_sources WHERE tenant = ? AND root_id = ? "
                    "AND digest = ? ORDER BY attached_at DESC, source_id DESC LIMIT 1",
                    (session.tenant, root_id, digest),
                ).fetchone()
            finally:
                connection.close()
            if stored is None:
                raise UnsupportedCommandError(
                    "Chứng từ ứng chưa được lưu vào hồ sơ này. Tải lại chứng từ trước khi đọc."
                )
            sources.append(
                SourceRef(
                    id=str(stored["source_id"]),
                    digest=digest,
                    tenant=session.tenant,
                    media=media,  # type: ignore[arg-type]
                    storage_key=str(stored["storage_key"]),
                    filename=str(stored["filename"] or filename),
                )
            )
            source_bytes[str(stored["source_id"])] = payload
        with self._trace_operation(
            "advance-draft-read",
            metadata={
                "root_id": root_id,
                "provider_mode": provider_mode,
                "sources": len(sources),
            },
            tags=("operation", "advance-draft-read"),
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
            )

            # Pick the document that actually carries advance fields; a clear one
            # is preferred over an unresolved one. Keep this result in the root
            # so it records the draft users actually received.
            def _score(document) -> int:
                fields = {f.field for f in document.fields if f.state == "FOUND"}
                score = len(
                    fields
                    & {
                        "amount",
                        "payee_name",
                        "transaction_reference",
                        "transaction_status",
                    }
                )
                if document.profile_status == "CLEAR":
                    score += 1
                return score

            candidates = sorted(report.documents, key=_score, reverse=True)
            if not candidates or _score(candidates[0]) == 0:
                raise UnsupportedCommandError(
                    "Không đọc được dữ liệu khoản ứng từ chứng từ đã tải lên."
                )
            draft = draft_advance_from_document(
                candidates[0],
                scope=str(row["activity"]),
                employee=str(row["employee"]),
                method_hint=method_hint,
            )
            draft_id = f"advance-draft:{uuid.uuid4().hex}"
            draft = draft._replace(draft_id=draft_id)
            now = self._now_iso()
            # Link resolution and draft insertion share one short serialized
            # transaction. A second root reading the same transaction after this
            # insert sees the competing draft and cannot also auto-link it.
            with self.db.transaction() as cx:
                root = self._require_root(cx, session, root_id)
                if str(root["activity"]) != draft.scope or str(root["employee"]) != draft.employee:
                    raise CommandConflictError(
                        "Phạm vi hồ sơ đã đổi trong lúc đọc chứng từ; hãy đọc lại bản nháp."
                    )
                activity_link = self._advance_activity_link(
                    cx,
                    session.tenant,
                    str(root["employee"]),
                    draft.activity_reference,
                    current_activity=str(root["activity"]),
                    root_id=root_id,
                    advance_document=candidates[0],
                    transaction_reference=draft.transaction_reference,
                    instrument_method=draft.instrument_method,
                    draft_refs=draft.refs,
                )
                matched_activity = (
                    activity_link.activity_id
                    if activity_link.status == "LINKED"
                    and activity_link.activity_id == str(root["activity"])
                    else None
                )
                draft = draft._replace(
                    activity_link_status=(
                        "CONFLICT"
                        if activity_link.status == "LINKED" and matched_activity is None
                        else activity_link.status
                    ),
                    matched_activity_id=matched_activity,
                    activity_link_basis=activity_link.basis,
                    activity_link_signals=activity_link.signals,
                    activity_link_candidate_count=activity_link.candidate_count,
                )
                if draft.transaction_reference and draft.instrument_method:
                    from invoice_referee.reconciliation.advance_identity import (
                        build_external_key,
                    )

                    key = build_external_key(
                        draft.instrument_method.lower(), draft.transaction_reference
                    )
                    if key is not None:
                        known = (
                            cx.execute(
                                "SELECT 1 FROM money_events WHERE tenant = ? "
                                "AND external_key = ? LIMIT 1",
                                (session.tenant, key),
                            ).fetchone()
                            is not None
                        )
                        if not known:
                            known = self._snapshot_ledger_entry(cx, session.tenant, key) is not None
                        if known:
                            draft = draft._replace(already_recorded=True)
                draft_payload = {
                    **draft._asdict(),
                    "refs": [ref.model_dump(mode="json") for ref in draft.refs],
                    "activity_link_signals": [
                        signal.model_dump(mode="json")
                        for signal in draft.activity_link_signals
                    ],
                }
                cx.execute(
                    "INSERT INTO case_advance_drafts (draft_id, tenant, root_id, source_id, "
                    "actor, draft_json, report_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        draft_id,
                        session.tenant,
                        root_id,
                        draft.source_id,
                        session.actor_id,
                        json.dumps(draft_payload, ensure_ascii=False),
                        report.model_dump_json(),
                        now,
                    ),
                )
                self._audit(
                    cx,
                    tenant=session.tenant,
                    root_id=root_id,
                    session_id=session.session_id,
                    actor=session.actor_id,
                    action="READ_ADVANCE_DRAFT",
                    detail=json.dumps(
                        {
                            "draft_id": draft_id,
                            "source_id": draft.source_id,
                            "link_status": draft.activity_link_status,
                            "link_basis": draft.activity_link_basis,
                            "candidate_count": draft.activity_link_candidate_count,
                        },
                        ensure_ascii=False,
                    ),
                )
            operation.outputs.update(trace_read_report(
                report,
                draft={
                    "draft_id": draft.draft_id,
                    "activity_link_status": draft.activity_link_status,
                    "activity_link_basis": draft.activity_link_basis,
                    "candidate_count": draft.activity_link_candidate_count,
                    "link_signals": [signal.model_dump(mode="json") for signal in draft.activity_link_signals],
                },
            ))
        return draft

    def get_advance_draft(self, session: DemoSession, root_id: str, draft_id: str | None = None):
        """Re-evaluate a saved draft against current state without provider I/O or money writes."""
        from invoice_referee.domain.evidence import ReadResult

        if session.persona != "accountant":
            raise UnsupportedCommandError("Chỉ kế toán được mở bản nháp chứng từ ứng.")
        with self.db.transaction() as cx:
            root = self._require_root(cx, session, root_id)
            saved = cx.execute(
                "SELECT * FROM case_advance_drafts WHERE tenant = ? AND root_id = ? "
                "AND (? IS NULL OR draft_id = ?) ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (session.tenant, root_id, draft_id, draft_id),
            ).fetchone()
            if saved is None:
                raise NotFoundError("Chưa có bản nháp chứng từ ứng đã lưu cho hồ sơ này.")
            payload = json.loads(saved["draft_json"])
            report = ReadResult.model_validate_json(saved["report_json"])
            source = cx.execute(
                "SELECT * FROM case_sources WHERE tenant = ? AND root_id = ? AND source_id = ?",
                (session.tenant, root_id, saved["source_id"]),
            ).fetchone()
            document = next((d for d in report.documents if d.source_id == saved["source_id"]), None)
            refs = tuple(EvidenceRef.model_validate(ref) for ref in payload.get("refs", ()))
            if (
                source is None or document is None or not refs
                or any(ref.source_id != source["source_id"] or ref.source_sha256 != source["digest"] for ref in refs)
                or payload.get("scope") != root["activity"] or payload.get("employee") != root["employee"]
            ):
                raise CommandConflictError("Nguồn hoặc phạm vi bản nháp đã thay đổi; kiểm tra lại chứng từ.")
            link = self._advance_activity_link(
                cx, session.tenant, str(root["employee"]), payload.get("activity_reference"),
                current_activity=str(root["activity"]), root_id=root_id,
                advance_document=document, transaction_reference=payload.get("transaction_reference"),
                instrument_method=payload.get("instrument_method"), draft_refs=refs,
            )
            matched = link.activity_id if link.status == "LINKED" and link.activity_id == root["activity"] else None
            payload.update(
                activity_link_status="CONFLICT" if link.status == "LINKED" and matched is None else link.status,
                matched_activity_id=matched,
                activity_link_basis=link.basis,
                activity_link_signals=[signal.model_dump(mode="json") for signal in link.signals],
                activity_link_candidate_count=link.candidate_count,
            )
            return {"draft": payload, "case_view": self._case_view(cx, root)}

    async def read_employee_return_draft(
        self,
        session: DemoSession,
        root_id: str,
        source_id: str,
        instruction_id: str,
        *,
        method_hint: str | None,
        expected_case_version: int,
    ) -> dict[str, object]:
        """Read one employee return proof against a live COLLECT instruction.

        The PDF is already stored in the root's case_sources. A saved read is
        reused after retry/restart; this method creates no money event or coverage.
        """
        from datetime import time

        from invoice_referee.domain.common import parse_vnd
        from invoice_referee.domain.evidence import ReadResult, SourceRef
        from invoice_referee.evidence.pipeline import read_root, trace_read_report
        from invoice_referee.evidence.trace import RunBudget
        from invoice_referee.reconciliation.advance import _method, _status
        from invoice_referee.reconciliation.advance_identity import build_external_key
        from invoice_referee.reconciliation.employee_return import (
            match_employee_return,
            read_field,
        )
        from invoice_referee.source_dates import parse_source_date

        if session.persona != "employee":
            raise UnsupportedCommandError("Chỉ nhân viên trong hồ sơ được tải chứng từ hoàn trả.")

        connection = self.db.connect()
        try:
            root = connection.execute(
                "SELECT * FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
            if root is None:
                raise NotFoundError("Hồ sơ không tồn tại trong tenant này.")
            if str(root["employee"]) != session.actor_id:
                raise UnsupportedCommandError("Nhân viên chỉ có thể gửi chứng từ cho hồ sơ của mình.")
            if int(root["version"]) != expected_case_version:
                raise StaleCommandError("Hồ sơ vừa thay đổi; tải lại rồi gửi lại chứng từ.")
            instruction = connection.execute(
                "SELECT * FROM instructions WHERE tenant = ? AND root_id = ? AND id = ?",
                (session.tenant, root_id, instruction_id),
            ).fetchone()
            if (
                instruction is None
                or instruction["direction"] != "COLLECT"
                or instruction["status"] not in ("ISSUED", "PARTIAL")
                or int(instruction["amount"]) <= int(instruction["fulfilled_amount"])
            ):
                raise CommandConflictError("Không còn lệnh thu hiệu lực để gắn chứng từ hoàn trả.")
            source = connection.execute(
                "SELECT * FROM case_sources WHERE tenant = ? AND root_id = ? AND source_id = ?",
                (session.tenant, root_id, source_id),
            ).fetchone()
            if source is None:
                raise NotFoundError("Chứng từ hoàn trả chưa được lưu trong hồ sơ này.")
            saved = connection.execute(
                "SELECT * FROM case_money_drafts WHERE tenant = ? AND root_id = ? "
                "AND source_id = ? AND instruction_id = ?",
                (session.tenant, root_id, source_id, instruction_id),
            ).fetchone()
            if saved is not None:
                report = ReadResult.model_validate_json(saved["report_json"])
                existing_draft_id = str(saved["draft_id"])
            else:
                report = None
                existing_draft_id = None
            root_copy = dict(root)
            instruction_copy = dict(instruction)
            source_copy = dict(source)
        finally:
            connection.close()

        if report is None:
            reader, classifier, artifacts, provider_mode = self._evidence_wiring()
            if reader is None:
                raise UnsupportedCommandError("Chưa cấu hình đọc chứng từ (LIVE) cho môi trường này.")
            source_ref = SourceRef(
                id=str(source_copy["source_id"]),
                digest=str(source_copy["digest"]),
                tenant=session.tenant,
                media=str(source_copy["media"]),  # type: ignore[arg-type]
                storage_key=str(source_copy["storage_key"]),
                filename=str(source_copy["filename"]),
            )
            source_path = self.uploads_dir / source_ref.storage_key
            if not source_path.is_file():
                raise UnsupportedCommandError("Không tìm thấy tệp hoàn trả đã lưu để đọc.")
            with self._trace_operation(
                "employee-return-draft-read",
                metadata={"root_id": root_id, "instruction_id": instruction_id, "provider_mode": provider_mode},
                tags=("operation", "employee-return-draft"),
            ) as operation:
                report = await read_root(
                    sources=(source_ref,),
                    reader=reader,
                    classifier=classifier,
                    artifacts=artifacts,
                    source_bytes={source_id: source_path.read_bytes()},
                    budget=RunBudget(),
                    provider_mode=provider_mode,
                    root_id=root_id,
                    activity_profile=str(root_copy["profile"]),
                )
                operation.outputs.update(trace_read_report(report))

        documents = sorted(
            report.documents,
            key=lambda document: (
                document.document_type == "PAYMENT_PROOF",
                document.profile_status == "CLEAR",
                sum(field.state == "FOUND" for field in document.fields),
            ),
            reverse=True,
        )
        document = next(
            (item for item in documents if item.document_type in ("PAYMENT_PROOF", "COLLECTION_RECEIPT")),
            None,
        )
        if document is None:
            raise UnsupportedCommandError("Không nhận diện được chứng từ chuyển tiền hoàn trả.")

        field_names = (
            "payer_name", "payee_name", "amount", "event_at",
            "transaction_reference", "transaction_status",
        )
        values: dict[str, object | None] = {}
        field_refs: dict[str, tuple[EvidenceRef, ...]] = {}
        ambiguous_fields: list[str] = []
        conflicting_fields: list[str] = []
        for field_name in field_names:
            value, refs, issue = read_field(document, field_name)
            values[field_name] = value
            field_refs[field_name] = refs
            if issue == "ambiguous":
                ambiguous_fields.append(field_name)
            elif issue == "conflict":
                conflicting_fields.append(field_name)

        amount_value = parse_vnd(values["amount"])
        amount = int(amount_value) if amount_value is not None else None
        raw_date = str(values["event_at"]) if values["event_at"] is not None else None
        source_day = parse_source_date(raw_date)
        event_at = (
            datetime.combine(source_day, time.min, _VN_TZ)
            if source_day is not None
            else None
        )
        instrument_method = _method(document, method_hint) or "TRANSFER"
        instrument_status = _status(document)
        transaction_reference = (
            str(values["transaction_reference"]).strip()
            if values["transaction_reference"] is not None
            else None
        )
        external_key = (
            build_external_key(instrument_method.lower(), transaction_reference)
            if transaction_reference
            else None
        )
        refs = tuple(dict.fromkeys(ref for source_refs in field_refs.values() for ref in source_refs))
        missing_fields = tuple(
            field_name
            for field_name in field_names
            if values[field_name] is None or field_name in ambiguous_fields or field_name in conflicting_fields
        )

        current = datetime.fromisoformat(self._now_iso()).astimezone(_VN_TZ)
        instruction_day = datetime.fromisoformat(str(instruction_copy["created_at"])).astimezone(_VN_TZ).date()
        with self.db.connect() as cx:
            company_name = self._tenant_company_name(cx, session.tenant)
        transaction_owner_root = None
        already_recorded = False
        if external_key is not None:
            with self.db.connect() as cx:
                owner = cx.execute(
                    "SELECT root_id, payload_json FROM money_events WHERE tenant = ? AND external_key = ?",
                    (session.tenant, external_key),
                ).fetchone()
                if owner is not None:
                    transaction_owner_root = str(owner["root_id"])
                    if transaction_owner_root == root_id:
                        try:
                            existing_event = MoneyEvent.model_validate_json(owner["payload_json"])
                            already_recorded = existing_event.instruction_id == instruction_id
                        except (TypeError, ValueError):
                            already_recorded = False
                else:
                    snapshot = self._snapshot_ledger_entry(cx, session.tenant, external_key)
                    if snapshot is not None:
                        snapshot_scope = str(snapshot.get("scope") or snapshot.get("activity") or "")
                        snapshot_event_at = snapshot.get("event_at")
                        snapshot_amount = parse_vnd(snapshot.get("amount"))
                        try:
                            snapshot_day = datetime.fromisoformat(str(snapshot_event_at)).astimezone(_VN_TZ).date()
                        except (TypeError, ValueError):
                            snapshot_day = None
                        already_recorded = (
                            snapshot_scope == str(root_copy["activity"])
                            and str(snapshot.get("kind") or "") == "EMPLOYEE_RETURN"
                            and str(snapshot.get("verification_state") or "") == "CONFIRMED"
                            and str(snapshot.get("allocation_state") or "") == "ALLOCATED"
                            and amount is not None
                            and snapshot_amount == amount
                            and self._same_party(session.tenant, str(snapshot.get("payer") or ""), str(root_copy["employee"]))
                            and self._same_party(session.tenant, str(snapshot.get("payee") or ""), company_name)
                            and source_day is not None
                            and snapshot_day == source_day
                        )
                        if not already_recorded:
                            transaction_owner_root = "context:other-scope"
        result = match_employee_return(
            root_id=root_id,
            instruction_id=instruction_id,
            instruction_active=(
                instruction_copy["status"] in ("ISSUED", "PARTIAL")
                and int(instruction_copy["amount"]) > int(instruction_copy["fulfilled_amount"])
            ),
            instruction_remaining=max(
                int(instruction_copy["amount"]) - int(instruction_copy["fulfilled_amount"]),
                0,
            ),
            instruction_date=instruction_day,
            as_of=current.date(),
            employee_name=self.display_name(session.tenant, str(root_copy["employee"])),
            company_name=company_name,
            payer_name=str(values["payer_name"]) if values["payer_name"] is not None else None,
            payee_name=str(values["payee_name"]) if values["payee_name"] is not None else None,
            amount=amount,
            event_date=source_day,
            transaction_reference=transaction_reference,
            instrument_status=instrument_status,
            ambiguous_fields=tuple(ambiguous_fields),
            conflicting_fields=tuple(conflicting_fields),
            transaction_owner_root=transaction_owner_root,
            already_recorded=already_recorded,
            field_refs=field_refs,
        )
        draft = EmployeeReturnDraft(
            draft_id=existing_draft_id or f"money-draft:{uuid.uuid4().hex}",
            root_id=root_id,
            employee=str(root_copy["employee"]),
            activity=str(root_copy["activity"]),
            instruction_id=instruction_id,
            source_id=str(source_copy["source_id"]),
            source_sha256=str(source_copy["digest"]),
            source_filename=str(source_copy["filename"]),
            status=(str(saved["status"]) if saved is not None else "WAITING_ACCOUNTANT"),
            match_status=result.status,
            amount=amount,
            payer_name=str(values["payer_name"]) if values["payer_name"] is not None else None,
            payee_name=str(values["payee_name"]) if values["payee_name"] is not None else None,
            transaction_reference=transaction_reference,
            external_key=external_key,
            instrument_method=instrument_method,
            instrument_status=instrument_status,
            event_at=event_at,
            instruction_amount=int(instruction_copy["amount"]),
            instruction_remaining=max(
                int(instruction_copy["amount"]) - int(instruction_copy["fulfilled_amount"]),
                0,
            ),
            refs=refs,
            missing_fields=missing_fields,
            signals=result.signals,
            uploaded_at=datetime.fromisoformat(str(saved["created_at"])) if saved is not None else datetime.fromisoformat(self._now_iso()),
            confirmed_at=(datetime.fromisoformat(str(saved["confirmed_at"])) if saved is not None and saved["confirmed_at"] else None),
            confirmed_by=(str(saved["confirmed_by"]) if saved is not None and saved["confirmed_by"] else None),
            money_event_id=(str(saved["confirmed_event_id"]) if saved is not None and saved["confirmed_event_id"] else None),
        )

        now = self._now_iso()
        with self.db.transaction() as cx:
            root = self._require_root(cx, session, root_id)
            self._require_version(root, expected_case_version)
            current_instruction = cx.execute(
                "SELECT * FROM instructions WHERE id = ? AND tenant = ? AND root_id = ?",
                (instruction_id, session.tenant, root_id),
            ).fetchone()
            current_instruction_active = (
                current_instruction is not None
                and current_instruction["direction"] == "COLLECT"
                and current_instruction["status"] in ("ISSUED", "PARTIAL")
                and int(current_instruction["amount"]) > int(current_instruction["fulfilled_amount"])
            )
            if current_instruction is None or current_instruction["direction"] != "COLLECT":
                raise CommandConflictError("Lệnh thu không còn thuộc hồ sơ này.")
            cx.execute(
                "INSERT OR IGNORE INTO case_money_drafts "
                "(draft_id, tenant, root_id, instruction_id, source_id, status, draft_json, "
                "report_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    draft.draft_id, session.tenant, root_id, instruction_id, source_id,
                    draft.status, draft.model_dump_json(), report.model_dump_json(), now, now,
                ),
            )
            saved_row = cx.execute(
                "SELECT * FROM case_money_drafts WHERE tenant = ? AND root_id = ? "
                "AND source_id = ? AND instruction_id = ?",
                (session.tenant, root_id, source_id, instruction_id),
            ).fetchone()
            if saved_row is None:
                raise CommandConflictError("Không lưu được bản nháp hoàn trả.")
            if not current_instruction_active and saved_row["status"] != "CONFIRMED":
                raise CommandConflictError("Lệnh thu đã thay đổi trong lúc đọc chứng từ; tải lại để đối chiếu.")
            if saved_row["draft_id"] != draft.draft_id:
                draft = EmployeeReturnDraft.model_validate_json(saved_row["draft_json"])
            else:
                self._audit(
                    cx,
                    tenant=session.tenant,
                    root_id=root_id,
                    session_id=session.session_id,
                    actor=session.actor_id,
                    action="READ_EMPLOYEE_RETURN_DRAFT",
                    detail=json.dumps({
                        "draft_id": draft.draft_id,
                        "instruction_id": instruction_id,
                        "source_id": source_id,
                        "match_status": draft.match_status,
                    }, ensure_ascii=False),
                )
            case_view = self._case_view(cx, root)
        return {"draft": draft.model_dump(mode="json"), "case_view": case_view.model_dump(mode="json")}

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
        from invoice_referee.evidence.pipeline import read_root, trace_read_report
        from invoice_referee.evidence.trace import RunBudget
        from invoice_referee.reconciliation.settlement_draft import (
            build_settlement_draft,
        )

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
                    id=row2["source_id"],
                    digest=row2["digest"],
                    tenant=row2["tenant"],
                    media=row2["media"],
                    storage_key=row2["storage_key"],
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
                    id=source_id,
                    digest=digest,
                    tenant=session.tenant,
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
            metadata={
                "root_id": root_id,
                "provider_mode": provider_mode,
                "sources": len(sources),
            },
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
                activity_profile=str(row["profile"])
                if "profile" in row.keys()
                else None,
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
                # Backend dossier link (14/10/2026): the server decides which
                # advance/work dossier this settlement belongs to; the draft
                # carries the decision for review, never an activity dropdown.
                from invoice_referee.reconciliation.settlement_link import (
                    link_to_payload,
                )

                link = self._settlement_link_for(
                    cx,
                    tenant=session.tenant,
                    employee=str(row["employee"]),
                    case_activity=str(row["activity"]),
                    report=report,
                )
                draft["link"] = link_to_payload(link)
                operation.outputs.clear()
                operation.outputs.update(trace_read_report(report, draft=draft))
                # Persist the operation trace ref alongside the report (debug ref).
                self._last_trace_ref[root_id] = operation.run_id

        return draft

    async def get_settlement_draft(
        self, session: DemoSession, root_id: str
    ) -> dict[str, object]:
        """Return the persisted settlement draft for an existing case.

        Rebuilds the employee review draft from the stored typed report when
        its source basis still matches (W3 reuse); a stale/missing report is
        a typed failure, never a fabricated draft.
        """
        from invoice_referee.reconciliation.settlement_draft import (
            build_settlement_draft,
        )

        self._require_session_root(session, root_id)
        with self.db.transaction() as cx:
            report = self._reusable_report(cx, session.tenant, root_id)
            if report is None:
                raise UnsupportedCommandError(
                    "Chưa có bản đọc còn hiệu lực cho hồ sơ này; tải chứng từ và đọc lại."
                )
            sources = tuple(
                {
                    "id": row["source_id"],
                    "digest": row["digest"],
                    "tenant": row["tenant"],
                    "media": row["media"],
                    "storage_key": row["storage_key"],
                    "filename": row["filename"],
                }
                for row in cx.execute(
                    "SELECT * FROM case_sources WHERE root_id = ? ORDER BY attached_at, source_id",
                    (root_id,),
                )
            )
            case = cx.execute("SELECT * FROM cases WHERE id = ?", (root_id,)).fetchone()
            link = self._settlement_link_for(
                cx,
                tenant=session.tenant,
                employee=str(case["employee"]),
                case_activity=str(case["activity"]),
                report=report,
            )
        from invoice_referee.domain.evidence import SourceRef
        from invoice_referee.reconciliation.settlement_link import link_to_payload

        refs = tuple(SourceRef(**s) for s in sources)  # type: ignore[arg-type]
        draft = build_settlement_draft(report, sources=refs)
        draft["link"] = link_to_payload(link)
        return draft

    def _settlement_link_for(
        self,
        cx: sqlite3.Connection,
        *,
        tenant: str,
        employee: str,
        case_activity: str,
        report,
    ):
        """Backend dossier link for one settlement report (14/10/2026).

        Thin wiring over the pure ``settlement_link`` module: the catalog and
        the company ledger history are server-owned; the employee never picks
        a standing activity code.
        """
        from invoice_referee.reconciliation.settlement_link import (
            catalog_from_entries,
            ledger_from_events,
            link_settlement,
        )

        # Bound means an AUTHORIZED catalog entry — not a prefix: a custom
        # non-catalog id is an unbound (PROPOSED) draft even without the
        # generated `activity:proposed:` prefix.
        catalog_entries = [
            {
                "activity_id": entry.activity_id,
                "name": entry.name,
                "status": entry.status,
                "purpose": entry.purpose,
                "references": list(entry.references),
            }
            for entry in self.catalog(tenant)
        ]
        proposed = all(e["activity_id"] != case_activity for e in catalog_entries)
        catalog = catalog_from_entries(catalog_entries)
        # Company ledger history = recorded money events plus the witnessed
        # imported ledgers across ALL snapshots newest-first (a transaction
        # code already in company history links by namespaced identity,
        # whichever store holds it; a later import without ledger history
        # must not hide an earlier witnessed one).
        seen_keys: set[str] = set()
        raw_events: list[dict[str, object]] = []
        for row in cx.execute(
            "SELECT external_key, scope, payee, amount, kind FROM money_events "
            "WHERE tenant = ?",
            (tenant,),
        ):
            raw_events.append(
                {
                    "external_key": row["external_key"],
                    "activity": row["scope"],
                    "employee": row["payee"],
                    "amount": int(row["amount"]),
                    "kind": row["kind"],
                }
            )
            seen_keys.add(str(row["external_key"]))
        for snapshot in cx.execute(
            "SELECT payload_json FROM context_snapshots WHERE tenant = ? "
            "ORDER BY version DESC",
            (tenant,),
        ):
            if not snapshot["payload_json"]:
                continue
            try:
                payload = json.loads(snapshot["payload_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict) or not isinstance(
                payload.get("ledger"), list
            ):
                continue
            for item in payload["ledger"]:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("external_key") or "")
                if not key or key in seen_keys:
                    continue
                seen_keys.add(key)
                raw_events.append(
                    {
                        "external_key": key,
                        "activity": item.get("activity") or item.get("scope") or "",
                        "employee": item.get("employee") or item.get("payee") or "",
                        "amount": int(item.get("amount") or 0),
                        "kind": item.get("kind") or "",
                    }
                )
        ledger = ledger_from_events(raw_events)  # type: ignore[arg-type]
        return link_settlement(
            report,
            employee=employee,
            current_activity=None if proposed else case_activity,
            current_activity_proposed=proposed,
            catalog=catalog,
            ledger=ledger,
        )

    def _require_session_root(self, session: DemoSession, root_id: str):
        """Check the case exists in this tenant; tenant isolation first."""
        connection = self.db.connect()
        try:
            row = connection.execute(
                "SELECT id FROM cases WHERE id = ? AND tenant = ?",
                (root_id, session.tenant),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFoundError("Hồ sơ không tồn tại trong tenant này.")
        return row

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
                self._declaration_draft_json(
                    command.declaration, actor=context.actor_id, now=now
                ),
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
            # Backend dossier link (14/10/2026): the employee's confirmation of
            # a weak link, if any. The decided activity is on the case row.
            "confirmed_activity_id": declaration.confirmed_activity_id,
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
                filename = (
                    ref.source_id[len("file:") :]
                    if ref.source_id.startswith("file:")
                    else ref.source_id
                )
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

    def _bind_proposed_dossier(
        self,
        cx,
        session,
        row,
        root_id: str,
        current_activity: str,
        *,
        confirmed_activity: str | None,
        declaration,
    ):
        """Bind a PROPOSED draft root to its dossier at submit (14/10/2026).

        The backend link decides; the employee only confirms a weak link or
        corrects within their scope. A LINKED dossier rebinds silently. A
        weak/conflicting basis asks the right owner instead of guessing. No
        link fabricates a budget/grant: an unlinked draft stays PROPOSED and
        enters the authorization follow-up. A rebind that would collide with
        an existing dossier for the same scope is a conflict — the old
        dossier is never overwritten, and sources/ledger are never moved
        implicitly.
        """
        report = self._reusable_report(cx, session.tenant, root_id)
        link = None
        if report is not None:
            link = self._settlement_link_for(
                cx,
                tenant=session.tenant,
                employee=str(row["employee"]),
                case_activity=current_activity,
                report=report,
            )
        if confirmed_activity and confirmed_activity != current_activity:
            entry = self.catalog_entry(session.tenant, confirmed_activity)
            if entry is None or entry.status != "AUTHORIZED":
                raise UnsupportedCommandError(
                    "Hoạt động không có trong danh mục; không thể gắn hồ sơ."
                )
            if link is not None and link.status == "CONFLICT":
                raise UnsupportedCommandError(
                    "Các căn cứ mạnh trỏ tới các hồ sơ khác nhau; kế toán xác minh "
                    "trước khi gắn. " + " ".join(link.reasons)
                )
            self._rebind_case_activity(cx, session, row, root_id, entry)
            return self._reload(cx, row)
        if confirmed_activity and link is not None and link.status == "CONFLICT":
            # The client echoed the draft's own activity, but the documents
            # carry contradicting strong bases — a material conflict for the
            # accountant, never a silent keep.
            raise UnsupportedCommandError(
                "Chứng từ mang căn cứ mạnh trái với hồ sơ đã gắn; giữ mâu thuẫn "
                "để kế toán xác minh. " + " ".join(link.reasons)
            )
        if link is not None:
            if link.status == "LINKED" and link.activity_id is not None:
                entry = self.catalog_entry(session.tenant, link.activity_id)
                if entry is None or entry.status != "AUTHORIZED":
                    raise UnsupportedCommandError(
                        "Hồ sơ được liên kết không còn trong danh mục; kế toán kiểm tra."
                    )
                self._rebind_case_activity(cx, session, row, root_id, entry)
                return self._reload(cx, row)
            if link.status == "NEEDS_CONFIRMATION":
                names = ", ".join(
                    f"{c.name} ({c.activity_id})" for c in link.candidates
                )
                raise UnsupportedCommandError(
                    "Hồ sơ này quyết toán cho khoản tạm ứng nào? "
                    f"Ứng viên: {names}. Nhân viên xác nhận một hồ sơ trong phạm vi."
                )
            if link.status == "CONFLICT":
                raise UnsupportedCommandError(
                    "Các căn cứ mạnh trỏ tới các hồ sơ khác nhau; giữ mâu thuẫn "
                    "để kế toán xác minh. " + " ".join(link.reasons)
                )
        # NOT_FOUND (or no typed report): the draft is accepted as an
        # independent, server-managed dossier. It stays PROPOSED: no activity
        # decision, grant, or legacy budget is fabricated. Later costs and
        # effects still pass the ordinary evidence, policy, coverage, and
        # action/scope authority gates; B is not one of those gates.
        name = (
            declaration.destination
            or declaration.declared_purpose
            or str(row["activity_name"])
        )
        cx.execute("UPDATE cases SET activity_name = ? WHERE id = ?", (name, root_id))
        return self._reload(cx, row)

    def _rebind_case_activity(self, cx, session, row, root_id: str, entry) -> None:
        """Move a PROPOSED root onto an AUTHORIZED catalog activity.

        A colliding dossier for the same (tenant, employee, activity) is a
        conflict: continue that dossier instead of duplicating it. An unknown
        activity date stays unknown — never the upload time.
        """
        employee = str(row["employee"])
        clash = cx.execute(
            "SELECT id FROM cases WHERE tenant = ? AND employee = ? AND activity = ? "
            "AND id != ?",
            (session.tenant, employee, entry.activity_id, root_id),
        ).fetchone()
        if clash is not None:
            raise CommandConflictError(
                f"Hồ sơ cho hoạt động này đã tồn tại ({clash['id']}); "
                "tiếp tục hồ sơ đó thay vì tạo hồ sơ mới."
            )
        occurred = (
            entry.occurred_at.isoformat()
            if entry.occurred_at is not None
            else row["activity_occurred_at"]
        )
        cx.execute(
            "UPDATE cases SET activity = ?, activity_name = ?, "
            "activity_occurred_at = ?, profile = ? WHERE id = ?",
            (entry.activity_id, entry.name, occurred, entry.profile, root_id),
        )

    def _check_link_conflict(self, cx, session, row) -> None:
        """An AUTHORIZED root keeps its inherited link; contradicting strong
        refs are a material conflict for the accountant, never a silent keep."""
        report = self._reusable_report(cx, session.tenant, str(row["id"]))
        if report is None:
            return
        link = self._settlement_link_for(
            cx,
            tenant=session.tenant,
            employee=str(row["employee"]),
            case_activity=str(row["activity"]),
            report=report,
        )
        if link.status == "CONFLICT":
            raise UnsupportedCommandError(
                "Chứng từ mang căn cứ mạnh trái với hồ sơ đã gắn; giữ mâu thuẫn "
                "để kế toán xác minh. " + " ".join(link.reasons)
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
        # Backend dossier linking (14/10/2026): the server decides which
        # advance/work dossier this settlement belongs to. The employee never
        # picks a standing activity code; they only confirm when the basis is
        # weak/conflicting (confirmed_activity_id), within their own scope.
        # An old client's activity_id is treated as that confirmation.
        current_activity = str(row["activity"])
        confirmed_activity = (
            command.declaration.confirmed_activity_id or command.declaration.activity_id
        )
        # Bound means an AUTHORIZED catalog entry — a custom non-catalog id is
        # an unbound draft even without the generated `activity:proposed:` prefix.
        bound = self.catalog_entry(session.tenant, current_activity) is not None
        if not bound:
            row = self._bind_proposed_dossier(
                cx,
                session,
                row,
                root_id,
                current_activity,
                confirmed_activity=confirmed_activity,
                declaration=command.declaration,
            )
        else:
            if confirmed_activity and confirmed_activity != current_activity:
                raise UnsupportedCommandError(
                    "Khai báo không khớp hoạt động của hồ sơ này."
                )
            self._check_link_conflict(cx, session, row)
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
                self._declaration_draft_json(
                    command.declaration, actor=context.actor_id, now=now
                ),
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
            else store.enqueue(
                cx, tenant=session.tenant, root_id=root_id, kind="SUBMIT", now=now
            )
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
        if issue["owner"] not in (
            context.actor_id,
            "employee",
            "accountant",
            "approver",
            "org-data",
        ):
            raise UnsupportedCommandError("Bạn không phải người xử lý việc này.")
        if _owner_persona(issue["owner"]) not in ("any", session.persona):
            raise UnsupportedCommandError(
                "Việc này thuộc người xử lý khác; câu trả lời không được áp dụng."
            )
        now = self._now_iso()
        fact_key = str(issue["field_or_rule"])
        invoice_reference = _invoice_paid_reference(fact_key)
        confirmation_value: object = answer.value
        confirmation_refs = answer.refs
        invoice_issue_refs = ()
        if self._evidence_reader is not None and fact_key == "expense:payer":
            raise UnsupportedCommandError(
                "Xác nhận người trả phải gắn với đúng hóa đơn và số tiền."
            )
        if invoice_reference is not None:
            if (
                session.persona != "employee"
                or context.actor_id != str(row["employee"])
                or session.actor_id != str(row["employee"])
            ):
                raise UnsupportedCommandError(
                    "Chỉ nhân viên đứng tên hồ sơ mới xác nhận khoản tự thanh toán."
                )
            amount = _employee_paid_amount(answer.value)
            if amount is None:
                raise UnsupportedCommandError(
                    "Nhập số tiền VND nguyên dương đã trực tiếp thanh toán cho hóa đơn."
                )
            if not answer.reason.strip():
                raise UnsupportedCommandError(
                    "Cần ghi lý do/xác nhận chịu trách nhiệm cho khoản thanh toán."
                )

            report_row = cx.execute(
                "SELECT report_json FROM case_evidence_reports WHERE root_id = ?",
                (str(row["id"]),),
            ).fetchone()
            if report_row is None or not report_row["report_json"]:
                raise UnsupportedCommandError(
                    "Không còn bản đọc nguồn để xác định hóa đơn của câu trả lời."
                )
            from invoice_referee.domain.evidence import ReadResult
            from invoice_referee.domain.issues import BusinessIssue

            report = ReadResult.model_validate_json(report_row["report_json"])
            matching_documents = []
            for document in report.documents:
                document_number = next(
                    (
                        candidate.value
                        for candidate in document.fields
                        if candidate.field == "document_number"
                        and candidate.state == "FOUND"
                    ),
                    None,
                )
                if (
                    document_number is not None
                    and str(document_number).strip() == invoice_reference
                    and document.profile_status == "CLEAR"
                ):
                    matching_documents.append(document)
            if len(matching_documents) != 1:
                raise UnsupportedCommandError(
                    "Không thể ràng buộc câu trả lời với đúng một hóa đơn đã đọc rõ."
                )
            invoice = matching_documents[0]
            total_raw = next(
                (
                    candidate.value
                    for candidate in invoice.fields
                    if candidate.field == "total_amount" and candidate.state == "FOUND"
                ),
                None,
            )
            from invoice_referee.domain.common import parse_vnd

            invoice_total = parse_vnd(total_raw)
            if invoice_total is None or amount > invoice_total:
                raise UnsupportedCommandError(
                    "Số tiền xác nhận vượt số tiền hóa đơn hoặc hóa đơn chưa có tổng hợp lệ."
                )

            issue_payload = BusinessIssue.model_validate_json(issue["payload_json"])
            source_refs = {
                (ref.source_id, ref.source_sha256)
                for ref in invoice.refs
            }
            source_refs.update(
                (ref.source_id, ref.source_sha256)
                for candidate in invoice.fields
                if candidate.state == "FOUND"
                for ref in candidate.refs
            )
            source_refs.update(
                (ref.source_id, ref.source_sha256)
                for line in invoice.line_items
                for candidate in line.fields
                if candidate.state == "FOUND"
                for ref in candidate.refs
            )
            if not issue_payload.refs or any(
                (ref.source_id, ref.source_sha256) not in source_refs
                for ref in issue_payload.refs
            ):
                raise UnsupportedCommandError(
                    "Câu hỏi không còn locator gắn với hóa đơn đã đọc."
                )

            # Q32 is a scoped employee declaration, not independent payment proof:
            # payer comes from the authenticated case employee, amount from the
            # answer, activity from the server-owned case, and refs from this issue.
            confirmation_value = amount
            confirmation_refs = issue_payload.refs
            invoice_issue_refs = issue_payload.refs

        # The answer is persisted under the issue's recovery key. Invoice-scoped
        # Q32 keys match the LIVE consumer's per-invoice claim index; other answer
        # kinds keep their existing fact/value behavior.
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
                    str(confirmation_value),
                    context.actor_id,
                    str(row["activity"]),
                    json.dumps(
                        [ref.model_dump(mode="json") for ref in confirmation_refs],
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
        view = self._case_view(cx, self._reload(cx, row))
        if invoice_reference is not None:
            still_open = cx.execute(
                "SELECT 1 FROM case_issues WHERE root_id = ? AND field_or_rule = ? "
                "AND status = 'OPEN' LIMIT 1",
                (str(row["id"]), fact_key),
            ).fetchone()
            basis_applied = any(
                basis.kind == "EMPLOYEE_DECLARATION_Q32"
                and basis.actor == str(row["employee"])
                and all(ref in basis.refs for ref in invoice_issue_refs)
                for basis in view.payment_basis
            )
            if still_open is not None or not basis_applied:
                raise UnsupportedCommandError(
                    "Câu trả lời chưa tạo được căn cứ cho hóa đơn này; kiểm tra số tiền, người trả và phạm vi."
                )
        return CommandResult(case_view=view)

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

    def _advance_party_block(
        self, cx: sqlite3.Connection, tenant: str, dossier_employee: str, money
    ) -> str | None:
        """Block CONFIRMED A for a mismatched advance voucher (14/10/2026).

        Returns the blocking reason, or None when the parties check out. Thin
        wiring over the pure ``check_advance_parties``: the payee must be this
        dossier's employee (id or display name); the payer must be the tenant's
        configured company source (organization name or ``company:*`` id).
        """
        from invoice_referee.reconciliation.advance_identity import (
            check_advance_parties,
        )

        company_name = self._tenant_company_name(cx, tenant)
        expected: list[str] = []
        if company_name:
            expected.append(company_name)
        check = check_advance_parties(
            payee_name=money.payee,
            employee=dossier_employee,
            payer_name=money.payer,
            expected_payer_names=tuple(expected),
            employee_aliases=(self.display_name(tenant, dossier_employee),),
        )
        return None if check.ok else check.reason

    def _advance_activity_link(
        self,
        cx: sqlite3.Connection,
        tenant: str,
        employee: str,
        activity_reference: str | None,
        *,
        current_activity: str,
        root_id: str,
        advance_document,
        transaction_reference: str | None,
        instrument_method: str | None,
        draft_refs: tuple[EvidenceRef, ...] = (),
    ):
        """Decide the voucher/work link from explicit references or sourced facts.

        Opening the current root is never evidence. Strong references still win
        when unique and consistent; an unregistered voucher-only reference does
        not stop the separate multi-field path. Candidate enumeration is tenant
        scoped and the returned explanation contains no other-root identifiers.
        """
        import unicodedata

        from invoice_referee.domain.evidence import ReadResult
        from invoice_referee.domain.finance import ActivityLinkSignal
        from invoice_referee.reconciliation.advance import _found_value
        from invoice_referee.reconciliation.advance_identity import build_external_key
        from invoice_referee.reconciliation.linking import (
            ActivityCandidate,
            AdvanceLinkCandidate,
            AdvanceLinkEvidence,
            LinkResult,
            LedgerTxn,
            link_advance_multifield,
            link_dossier,
        )

        def _norm_text(value: object) -> str:
            text = unicodedata.normalize("NFD", str(value or ""))
            text = "".join(ch for ch in text if not unicodedata.combining(ch))
            return " ".join(
                "".join(ch for ch in text.casefold() if ch.isalnum() or ch.isspace()).split()
            )

        def _field_value(document, name: str):
            candidates = [field for field in document.fields if field.field == name]
            refs = tuple(dict.fromkeys(
                ref for candidate in candidates for ref in candidate.refs
            ))
            if any(candidate.state == "AMBIGUOUS" for candidate in candidates):
                return None, refs, "ambiguous"
            found = [candidate for candidate in candidates if candidate.state == "FOUND"]
            normalized = {_norm_text(candidate.value) for candidate in found}
            if len(normalized) > 1:
                return None, refs, "conflict"
            if not found:
                return None, refs, None
            return found[0].value, refs, None

        def _aliases(document, names: tuple[str, ...]):
            values = []
            refs: list[EvidenceRef] = []
            issues: set[str] = set()
            for name in names:
                value, field_refs, issue = _field_value(document, name)
                refs.extend(field_refs)
                if issue:
                    issues.add(issue)
                if value is not None:
                    values.append(value)
            normalized = {_norm_text(value) for value in values}
            if "conflict" in issues or len(normalized) > 1:
                issues.add("conflict")
            if "ambiguous" in issues:
                return None, tuple(dict.fromkeys(refs)), "ambiguous"
            if "conflict" in issues:
                return None, tuple(dict.fromkeys(refs)), "conflict"
            return (values[0] if values else None), tuple(dict.fromkeys(refs)), None

        def _settlement_candidate(case_row, report_json: str | None):
            report = None
            if report_json:
                try:
                    report = ReadResult.model_validate_json(report_json)
                except (TypeError, ValueError):
                    report = None
            forms = [
                document for document in (report.documents if report is not None else ())
                if document.document_type == "SETTLEMENT_FORM"
            ]
            clear_forms = [document for document in forms if document.profile_status == "CLEAR"]
            source_forms = clear_forms or forms

            def _read(name: str):
                values = []
                refs: list[EvidenceRef] = []
                issues: set[str] = set()
                for document in source_forms:
                    value, field_refs, issue = _field_value(document, name)
                    refs.extend(field_refs)
                    if issue:
                        issues.add(issue)
                    if value is not None:
                        values.append(value)
                normalized = {_norm_text(value) for value in values}
                if "conflict" in issues or len(normalized) > 1:
                    issues.add("conflict")
                if "ambiguous" in issues:
                    issue = "ambiguous"
                elif "conflict" in issues:
                    issue = "conflict"
                else:
                    issue = None
                return (values[0] if values and issue is None else None,
                        tuple(dict.fromkeys(refs)), issue)

            declared_name, employee_refs, employee_issue = _read("declared_name")
            purpose, purpose_refs, purpose_issue = _read("purpose")
            advance_value, advance_refs, advance_issue = _read("declared_advance")
            document_date, date_refs, date_issue = _read("document_date")
            work_start, work_start_refs, work_start_issue = _read("trip_start")
            work_end, work_end_refs, work_end_issue = _read("trip_end")
            reference, reference_refs, reference_issue = _read("advance_reference")
            if purpose is None:
                purpose = str(case_row["declared_purpose"] or case_row["activity_name"] or "")
            try:
                from invoice_referee.domain.common import parse_vnd

                declared_advance = parse_vnd(advance_value)
            except (TypeError, ValueError):
                declared_advance = None
            field_issues = {
                "declared_name": employee_issue,
                "purpose": purpose_issue,
                "declared_advance": advance_issue,
                "document_date": date_issue,
                "trip_start": work_start_issue,
                "trip_end": work_end_issue,
                "advance_reference": reference_issue,
            }
            conflicts = tuple(name for name, issue in field_issues.items() if issue == "conflict")
            ambiguous = tuple(name for name, issue in field_issues.items() if issue == "ambiguous")
            person = cx.execute(
                "SELECT name FROM context_people WHERE tenant = ? AND id = ?",
                (tenant, str(case_row["employee"])),
            ).fetchone()
            employee_name = str(person["name"]) if person is not None else str(case_row["employee"])
            return AdvanceLinkCandidate(
                root_id=str(case_row["id"]),
                activity_id=str(case_row["activity"]),
                employee_id=str(case_row["employee"]),
                employee_name=employee_name,
                purpose=str(purpose) if purpose is not None else None,
                declared_advance=int(declared_advance) if declared_advance is not None else None,
                settlement_date=str(document_date) if document_date is not None else None,
                declared_name=str(declared_name) if declared_name is not None else None,
                source_clear=bool(clear_forms) and not conflicts and not ambiguous,
                work_start=str(work_start) if work_start is not None else None,
                work_end=str(work_end) if work_end is not None else None,
                ambiguous_fields=ambiguous,
                conflicting_fields=conflicts,
                purpose_refs=purpose_refs,
                declared_advance_refs=advance_refs,
                settlement_date_refs=date_refs,
                employee_refs=employee_refs,
                declared_name_refs=employee_refs,
                reference_refs=reference_refs,
                work_period_refs=tuple(dict.fromkeys((*work_start_refs, *work_end_refs))),
            ), (report, forms, clear_forms, reference, reference_issue)

        # Load every root in this tenant. Other roots are considered internally
        # for ambiguity/duplicate protection; their IDs/names are never returned.
        rows = cx.execute(
            "SELECT c.*, "
            "(SELECT d.purpose FROM case_declarations d WHERE d.root_id = c.id "
            "ORDER BY d.revision DESC LIMIT 1) AS declared_purpose, "
            "r.report_json AS report_json "
            "FROM cases c LEFT JOIN case_evidence_reports r ON r.root_id = c.id "
            "AND r.tenant = c.tenant WHERE c.tenant = ? ORDER BY c.created_at, c.id",
            (tenant,),
        ).fetchall()
        candidates: list[AdvanceLinkCandidate] = []
        target_info = None
        for case_row in rows:
            candidate, info = _settlement_candidate(case_row, case_row["report_json"])
            candidates.append(candidate)
            if str(case_row["id"]) == root_id:
                target_info = info
        if target_info is None:
            return LinkResult(
                status="NOT_FOUND",
                reasons=("Hồ sơ quyết toán không còn trong phạm vi tenant này.",),
                owner="accountant",
            )
        report, settlement_forms, clear_forms, settlement_reference, reference_issue = target_info

        # A strong reference that contradicts another reference is never
        # overridden by the purpose/amount/date combination.
        settlement_references: list[tuple[str, tuple[EvidenceRef, ...]]] = []
        settlement_support_refs: list[EvidenceRef] = []
        for document in clear_forms:
            for candidate in document.fields:
                if candidate.state != "FOUND":
                    continue
                if candidate.field in {"declared_name", "purpose", "declared_advance", "document_date"}:
                    settlement_support_refs.extend(candidate.refs)
                if candidate.field == "advance_reference" and candidate.value:
                    settlement_references.append((str(candidate.value).strip(), candidate.refs))
        distinct_settlement_refs = {_norm_text(value) for value, _ in settlement_references}
        settlement_ref = settlement_references[0][0] if len(distinct_settlement_refs) == 1 else None
        combined_refs = tuple(dict.fromkeys((
            *draft_refs,
            *settlement_support_refs,
            *(ref for _value, refs in settlement_references for ref in refs),
        )))
        if len(distinct_settlement_refs) > 1 or reference_issue == "conflict":
            return LinkResult(
                status="CONFLICT",
                refs=combined_refs,
                reasons=("Các giấy quyết toán trong hồ sơ ghi mã khoản ứng mâu thuẫn nhau.",),
                conflicting_fields=("activity",),
                owner="accountant",
            )
        if activity_reference and settlement_ref and _norm_text(activity_reference) != _norm_text(settlement_ref):
            return LinkResult(
                status="CONFLICT",
                refs=combined_refs,
                reasons=("Mã khoản ứng trên biên nhận khác mã trên giấy quyết toán.",),
                conflicting_fields=("activity",),
                owner="accountant",
            )

        catalog: list[ActivityCandidate] = []
        for item in cx.execute(
            "SELECT activity_id, name, status, purpose, references_json "
            "FROM context_activities WHERE tenant = ? ORDER BY activity_id",
            (tenant,),
        ):
            try:
                references = json.loads(item["references_json"] or "[]")
            except (TypeError, ValueError):
                references = []
            catalog.append(
                ActivityCandidate(
                    activity_id=str(item["activity_id"]),
                    name=str(item["name"]),
                    status=str(item["status"] or "PROPOSED"),
                    purpose=str(item["purpose"] or ""),
                    references=tuple(str(v) for v in references if isinstance(v, str)),
                )
            )

        external_key = None
        if transaction_reference and instrument_method in ("TRANSFER", "CASH"):
            external_key = build_external_key(instrument_method.lower(), transaction_reference)
        transaction_owner_root = None
        transaction_owner_activity = None
        transaction_refs: tuple[EvidenceRef, ...] = ()
        if external_key is not None:
            event = cx.execute(
                "SELECT root_id, scope, payload_json FROM money_events "
                "WHERE tenant = ? AND external_key = ?",
                (tenant, external_key),
            ).fetchone()
            if event is not None:
                transaction_owner_root = str(event["root_id"])
                transaction_owner_activity = str(event["scope"])
                try:
                    from invoice_referee.domain.finance import MoneyEvent

                    transaction_refs = MoneyEvent.model_validate_json(event["payload_json"]).refs
                except (TypeError, ValueError):
                    transaction_refs = ()
            else:
                snapshot_event = self._snapshot_ledger_entry(cx, tenant, external_key)
                if snapshot_event is not None:
                    transaction_owner_activity = str(
                        snapshot_event.get("scope") or snapshot_event.get("activity") or ""
                    ) or None

        other_draft_roots: list[str] = []
        if external_key is not None:
            for saved in cx.execute(
                "SELECT root_id, draft_json FROM case_advance_drafts WHERE tenant = ? "
                "AND root_id != ?",
                (tenant, root_id),
            ):
                try:
                    saved_draft = json.loads(saved["draft_json"] or "{}")
                except (TypeError, ValueError):
                    continue
                saved_method = saved_draft.get("instrument_method")
                saved_reference = saved_draft.get("transaction_reference")
                saved_key = (
                    build_external_key(str(saved_method).lower(), str(saved_reference))
                    if saved_method and saved_reference
                    else None
                )
                if saved_key == external_key:
                    other_draft_roots.append(str(saved["root_id"]))

        ledger: list[LedgerTxn] = []
        for item in cx.execute(
            "SELECT m.payload_json, c.employee AS employee_id FROM money_events m "
            "JOIN cases c ON c.id = m.root_id AND c.tenant = m.tenant "
            "WHERE m.tenant = ? ORDER BY m.recorded_at, m.id",
            (tenant,),
        ):
            try:
                from invoice_referee.domain.finance import MoneyEvent

                event = MoneyEvent.model_validate_json(item["payload_json"])
            except (TypeError, ValueError):
                continue
            namespace, separator, reference = event.external_key.partition(":")
            ledger.append(
                LedgerTxn(
                    external_key=event.external_key,
                    activity=event.scope,
                    employee=str(item["employee_id"]),
                    amount=event.amount,
                    kind=event.kind,
                    namespace=namespace if separator else None,
                    reference=reference if separator else None,
                    refs=event.refs,
                )
            )

        from invoice_referee.reconciliation.linking import link_dossier

        catalog_link = link_dossier(
            employee=employee,
            current_activity=None,
            current_activity_proposed=True,
            document_references=(activity_reference,) if activity_reference else (),
            transaction_references=(transaction_reference,) if transaction_reference else (),
            catalog=tuple(catalog),
            ledger=tuple(ledger),
        )
        if catalog_link.status == "CONFLICT" or (
            catalog_link.status == "LINKED" and catalog_link.activity_id != current_activity
        ):
            return LinkResult(
                status="CONFLICT",
                refs=combined_refs,
                reasons=("Một căn cứ mạnh trỏ tới hồ sơ/hoạt động khác.",),
                conflicting_fields=catalog_link.conflicting_fields or ("activity",),
                owner="accountant",
                signals=(ActivityLinkSignal(
                    field="reference",
                    state="CONFLICT",
                    summary="Mã hồ sơ hoặc mã giao dịch khớp một hoạt động khác.",
                    refs=tuple(dict.fromkeys((
                        *draft_refs,
                        *catalog_link.refs,
                        *transaction_refs,
                    ))),
                ),),
            )

        mapped_reference_activity = None
        transaction_activity = transaction_owner_activity
        if catalog_link.status == "LINKED":
            if catalog_link.basis == "DOCUMENT_REFERENCE":
                mapped_reference_activity = current_activity
            elif catalog_link.basis == "TRANSACTION_IDENTITY":
                transaction_activity = current_activity
        elif activity_reference and settlement_ref and _norm_text(activity_reference) == _norm_text(settlement_ref):
            mapped_reference_activity = current_activity

        target_person = cx.execute(
            "SELECT name FROM context_people WHERE tenant = ? AND id = ?",
            (tenant, employee),
        ).fetchone()
        employee_name = str(target_person["name"]) if target_person is not None else employee
        person_rows = cx.execute(
            "SELECT id, name FROM context_people WHERE tenant = ?",
            (tenant,),
        ).fetchall()
        name_matches = [
            str(person["id"])
            for person in person_rows
            if _norm_text(person["name"]) == _norm_text(employee_name)
        ]
        employee_name_unique = len(name_matches) == 1 and name_matches[0] == employee

        def _payment_value(names: tuple[str, ...]):
            values = []
            refs: list[EvidenceRef] = []
            issues: set[str] = set()
            for name in names:
                field_candidates = [f for f in advance_document.fields if f.field == name]
                refs.extend(ref for f in field_candidates for ref in f.refs)
                if any(f.state == "AMBIGUOUS" for f in field_candidates):
                    issues.add("ambiguous")
                found = [f for f in field_candidates if f.state == "FOUND"]
                normalized = {_norm_text(f.value) for f in found}
                if len(normalized) > 1:
                    issues.add("conflict")
                if found:
                    values.append(found[0].value)
            normalized_values = {_norm_text(value) for value in values}
            if len(normalized_values) > 1:
                issues.add("conflict")
            issue = "conflict" if "conflict" in issues else "ambiguous" if "ambiguous" in issues else None
            return (values[0] if values and issue is None else None), tuple(dict.fromkeys(refs)), issue

        payer_name, payer_refs, payer_issue = _payment_value(("payer_name",))
        payee_name, payee_refs, payee_issue = _payment_value(("payee_name",))
        amount_value, amount_refs, amount_issue = _payment_value(("amount", "total_amount"))
        _transaction_value, transaction_reference_refs, transaction_issue = _payment_value(
            ("transaction_reference", "document_number")
        )
        # Prefer the field explicitly labelled as the transfer event. Only use
        # the voucher's own document_date if no event_at was read; never mix an
        # invoice date or settlement-paper date into this source date.
        payment_date, payment_date_refs, payment_date_issue = _payment_value(("event_at",))
        if payment_date is None and payment_date_issue is None:
            payment_date, payment_date_refs, payment_date_issue = _payment_value(("document_date",))
        payment_purpose, purpose_refs, purpose_issue = _payment_value(
            ("payment_description", "description", "collection_reason")
        )
        from invoice_referee.domain.common import parse_vnd

        amount = parse_vnd(amount_value)
        conflicting_fields = tuple(
            field_name
            for field_name, issue in (
                ("payer_name", payer_issue),
                ("payee_name", payee_issue),
                ("amount", amount_issue),
                ("transaction_reference", transaction_issue),
                ("event_at", payment_date_issue),
                ("payment_purpose", purpose_issue),
            )
            if issue == "conflict"
        )
        ambiguous_fields = tuple(
            field_name
            for field_name, issue in (
                ("payer_name", payer_issue),
                ("payee_name", payee_issue),
                ("amount", amount_issue),
                ("transaction_reference", transaction_issue),
                ("event_at", payment_date_issue),
                ("payment_purpose", purpose_issue),
            )
            if issue == "ambiguous"
        )
        company_name = self._tenant_company_name(cx, tenant)
        evidence = AdvanceLinkEvidence(
            root_id=root_id,
            activity_id=current_activity,
            employee_id=employee,
            employee_name=employee_name,
            employee_name_unique=employee_name_unique,
            expected_company_names=(company_name,) if company_name else (),
            payer_name=str(payer_name) if payer_name is not None else None,
            payee_name=str(payee_name) if payee_name is not None else None,
            amount=int(amount) if amount is not None else None,
            transaction_reference=transaction_reference,
            payment_date=str(payment_date) if payment_date is not None else None,
            payment_purpose=str(payment_purpose) if payment_purpose is not None else None,
            payer_refs=payer_refs,
            payee_refs=payee_refs,
            amount_refs=amount_refs,
            payment_date_refs=payment_date_refs,
            payment_purpose_refs=purpose_refs,
            activity_reference=activity_reference,
            activity_reference_refs=tuple(ref for f in advance_document.fields if f.field == "advance_reference" and f.state == "FOUND" for ref in f.refs),
            transaction_reference_refs=transaction_reference_refs,
            transaction_owner_refs=transaction_refs,
            mapped_reference_activity=mapped_reference_activity,
            transaction_owner_root=transaction_owner_root,
            transaction_owner_activity=transaction_activity,
            other_draft_roots=tuple(other_draft_roots),
            ambiguous_fields=ambiguous_fields,
            conflicting_fields=conflicting_fields,
        )
        link = link_advance_multifield(evidence, tuple(candidates))
        if link.activity_id != current_activity:
            return LinkResult(
                status="CONFLICT" if link.status == "LINKED" else link.status,
                refs=tuple(dict.fromkeys((*combined_refs, *link.refs))),
                reasons=("Căn cứ không xác định duy nhất hồ sơ đang mở.",),
                conflicting_fields=("activity",) if link.status == "LINKED" else link.conflicting_fields,
                owner="accountant",
                signals=link.signals,
                candidate_count=link.candidate_count,
                requires_confirmation=link.status != "CONFLICT",
            )
        return LinkResult(
            status=link.status,
            activity_id=link.activity_id,
            basis=link.basis,
            refs=tuple(dict.fromkeys((*combined_refs, *link.refs))),
            reasons=link.reasons,
            conflicting_fields=link.conflicting_fields,
            owner=link.owner,
            requires_confirmation=link.requires_confirmation,
            signals=link.signals,
            candidate_count=link.candidate_count,
        )

    def _advance_record_basis(self, cx, session, row, money):
        """Validate a user confirmation against the persisted read and root scope."""
        from invoice_referee.domain.evidence import ReadResult
        from invoice_referee.domain.common import EvidenceRef

        draft_row = cx.execute(
            "SELECT * FROM case_advance_drafts WHERE draft_id = ? AND tenant = ? "
            "AND root_id = ?",
            (money.advance_draft_id, session.tenant, str(row["id"])),
        ).fetchone()
        if draft_row is None:
            raise UnsupportedCommandError("Bản đọc chứng từ ứng không thuộc hồ sơ này.")
        try:
            draft = json.loads(draft_row["draft_json"])
            report = ReadResult.model_validate_json(draft_row["report_json"])
        except (TypeError, ValueError) as error:
            raise UnsupportedCommandError("Không khôi phục được bản đọc chứng từ ứng.") from error
        if (
            str(draft.get("scope")) != str(row["activity"])
            or str(draft.get("employee")) != str(row["employee"])
            or money.claimed_scope != str(row["activity"])
        ):
            raise CommandConflictError("Chứng từ ứng không cùng nhân viên và hồ sơ đang mở.")
        document = next(
            (
                item
                for item in report.documents
                if item.source_id == str(draft_row["source_id"])
            ),
            None,
        )
        if document is None:
            raise UnsupportedCommandError("Bản đọc không còn gắn với chứng từ đã lưu.")

        def _norm(value: object) -> str:
            import unicodedata

            text = unicodedata.normalize("NFD", str(value or ""))
            text = "".join(ch for ch in text if not unicodedata.combining(ch))
            return " ".join("".join(ch for ch in text.casefold() if ch.isalnum() or ch.isspace()).split())

        amount = draft.get("amount")
        if amount is not None and int(amount) != money.amount:
            raise CommandConflictError("Số tiền xác nhận khác số tiền đã đọc trên chứng từ.")
        for name, source_key, submitted in (
            ("bên chi", "payer_name", money.payer),
            ("người nhận", "payee_name", money.payee),
        ):
            source_value = draft.get(source_key)
            if source_value is not None and _norm(source_value) != _norm(submitted):
                raise CommandConflictError(f"{name.capitalize()} xác nhận khác dữ kiện đã đọc.")
        transaction_reference = draft.get("transaction_reference")
        submitted_reference = money.instrument_reference or money.external_key.partition(":")[2]
        if transaction_reference is not None and _norm(transaction_reference) != _norm(submitted_reference):
            raise CommandConflictError("Mã giao dịch xác nhận khác mã đã đọc trên chứng từ.")
        if draft.get("instrument_method") and money.instrument_method != draft["instrument_method"]:
            raise CommandConflictError("Phương thức giao dịch khác bản đọc chứng từ.")
        if draft.get("instrument_status") not in (None, "UNKNOWN") and money.instrument_status != draft["instrument_status"]:
            raise CommandConflictError("Trạng thái xác nhận khác trạng thái đã đọc trên chứng từ.")
        source_date = str(draft.get("event_at") or "")
        if source_date:
            try:
                from zoneinfo import ZoneInfo

                source_day = datetime.fromisoformat(source_date[:10]).date()
                submitted_day = money.event_at.astimezone(
                    ZoneInfo("Asia/Ho_Chi_Minh")
                ).date()
            except ValueError:
                source_day = None
                submitted_day = None
            if source_day is not None and submitted_day is not None and source_day != submitted_day:
                raise CommandConflictError("Ngày giao dịch xác nhận khác ngày đã đọc trên chứng từ.")

        refs = tuple(EvidenceRef.model_validate(ref) for ref in draft.get("refs", ()))
        if not refs or any(ref not in refs for ref in money.refs):
            raise UnsupportedCommandError("Căn cứ xác nhận không thuộc bản đọc chứng từ đã lưu.")

        # A missing OCR field may be corrected by the accountant from the same
        # saved source. This remains visibly human-reviewed; a conflicting value
        # already read from the source is rejected above and never overridden.
        correctable_values = {
            "payer_name": bool(money.payer.strip()),
            "payee_name": bool(money.payee.strip()),
            "amount": money.amount > 0,
            "event_at": money.event_at is not None,
            "transaction_reference": bool(submitted_reference.strip()),
            "transaction_status": money.instrument_status is not None,
        }
        blocking_findings = [finding for finding in document.profile_findings if finding.blocking]
        accountant_completed_missing_fields = (
            document.profile_status == "NEEDS_HUMAN"
            and bool(blocking_findings)
            and all(
                finding.code == "REQUIRED_FIELD_MISSING"
                and finding.field in correctable_values
                and correctable_values[str(finding.field)]
                for finding in blocking_findings
            )
        )
        source_reviewed = (
            document.profile_status == "CLEAR"
            or accountant_completed_missing_fields
        )

        link = self._advance_activity_link(
            cx,
            session.tenant,
            str(row["employee"]),
            str(draft["activity_reference"]) if draft.get("activity_reference") else None,
            current_activity=str(row["activity"]),
            root_id=str(row["id"]),
            advance_document=document,
            transaction_reference=str(draft["transaction_reference"])
            if draft.get("transaction_reference") else None,
            instrument_method=str(draft["instrument_method"])
            if draft.get("instrument_method") else None,
            draft_refs=refs,
        )
        current_activity = str(row["activity"])
        if link.status == "CONFLICT" or (
            link.status == "LINKED" and link.activity_id != current_activity
        ):
            raise CommandConflictError(
                "Tham chiếu trên chứng từ ứng chỉ tới hồ sơ khác hoặc nhiều hồ sơ; không tự chuyển giao dịch."
            )
        if link.status == "LINKED":
            link_basis = link.basis or "DOCUMENT_REFERENCE"
            link_reason = (
                " ".join(link.reasons).strip()
                or "Căn cứ trên chứng từ khớp duy nhất với hồ sơ đang xác minh."
            )
        else:
            link_reason = (money.activity_link_reason or "").strip()
            if not money.activity_link_confirmed or len(link_reason) < 12:
                raise UnsupportedCommandError(
                    "Kế toán cần xác nhận rõ chứng từ thuộc công việc này và nêu căn cứ đối chiếu."
                )
            link_basis = "ACCOUNTANT_CONFIRMATION"
        explanation = (
            money.reason.strip()
            or (money.completion_claim or "").strip()
            or (money.activity_link_reason or "").strip()
        )
        needs_explanation = (
            bool(draft.get("missing_fields"))
            or accountant_completed_missing_fields
            or link.status != "LINKED"
        )
        if needs_explanation and len(explanation) < 12:
            raise UnsupportedCommandError(
                "Cần giải thích căn cứ bổ sung thông tin hoặc liên kết công việc."
            )
        if not source_reviewed and money.instrument_status == "COMPLETED":
            raise UnsupportedCommandError(
                "Chứng từ còn vấn đề chưa giải quyết; giải thích không thay thế được căn cứ nhận tiền."
            )
        # The authenticated source-bound RecordActual command is the accountant's
        # explicit confirmation. Text is only additional evidence for exceptions.
        received = money.instrument_status == "COMPLETED"
        record_reason = (
            "Kế toán xác nhận ghi nhận tiền ứng thực nhận theo chứng từ đã kiểm tra."
            if received else "Kế toán lưu chứng từ ứng chưa hoàn tất để đối chiếu."
        )
        if explanation:
            record_reason += " Giải thích: " + explanation
        return {
            "draft_id": str(draft_row["draft_id"]),
            "refs": tuple(dict.fromkeys((*refs, *link.refs))),
            "link_basis": link_basis,
            "link_reason": link_reason,
            "link_signals": link.signals,
            "source_clear": source_reviewed,
            "record_reason": record_reason,
            "completion_claim": record_reason if received else None,
        }

    def _employee_return_record_basis(self, cx, session, row, money):
        """Revalidate a saved employee return read before accountant confirmation."""
        from invoice_referee.domain.evidence import ReadResult
        from invoice_referee.reconciliation.employee_return import match_employee_return
        if session.persona != "accountant":
            raise UnsupportedCommandError("Chỉ kế toán được xác nhận tiền hoàn trả đã nhận.")
        if not money.money_movement_draft_id:
            raise UnsupportedCommandError("Cần xác nhận từ bản nháp chứng từ hoàn trả đã lưu.")
        draft_row = cx.execute(
            "SELECT * FROM case_money_drafts WHERE tenant = ? AND root_id = ? AND draft_id = ?",
            (session.tenant, str(row["id"]), money.money_movement_draft_id),
        ).fetchone()
        if draft_row is None:
            raise NotFoundError("Không tìm thấy bản nháp chứng từ hoàn trả trong hồ sơ này.")
        try:
            draft = EmployeeReturnDraft.model_validate_json(draft_row["draft_json"])
            report = ReadResult.model_validate_json(draft_row["report_json"])
        except (TypeError, ValueError) as error:
            raise UnsupportedCommandError("Không khôi phục được bản đọc chứng từ hoàn trả.") from error
        if (
            draft.instruction_id != money.instruction_id
            or draft.instruction_id != str(draft_row["instruction_id"])
            or draft.root_id != str(row["id"])
            or draft.employee != str(row["employee"])
            or draft.activity != str(row["activity"])
            or money.claimed_scope != str(row["activity"])
        ):
            raise CommandConflictError("Bản nháp hoàn trả không thuộc lệnh và hồ sơ đang mở.")
        source = cx.execute(
            "SELECT root_id, digest FROM case_sources WHERE tenant = ? AND root_id = ? AND source_id = ?",
            (session.tenant, str(row["id"]), draft.source_id),
        ).fetchone()
        document = next(
            (item for item in report.documents if item.source_id == draft.source_id), None
        )
        if (
            source is None
            or str(source["digest"]) != draft.source_sha256
            or document is None
            or document.profile_status != "CLEAR"
            or not draft.refs
            or any(ref.source_id != draft.source_id or ref.source_sha256 != draft.source_sha256 for ref in draft.refs)
        ):
            raise UnsupportedCommandError("Chứng từ hoàn trả chưa đủ căn cứ nguồn đã đọc rõ.")
        if draft.status == "CONFIRMED":
            existing = cx.execute(
                "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? AND external_key = ?",
                (session.tenant, str(row["id"]), draft.external_key),
            ).fetchone()
            if existing is None:
                raise CommandConflictError("Bản nháp đã xác nhận nhưng không còn giao dịch để đối chiếu.")
        if draft.match_status not in ("MATCHED", "OVERPAY", "ALREADY_RECORDED"):
            message = next((signal.summary for signal in draft.signals if signal.state in (
                "CONFLICT", "STALE", "NOT_COMPLETED", "MISSING", "MISMATCH", "AMBIGUOUS"
            )), "Chứng từ hoàn trả cần được xác minh trước khi ghi tiền.")
            raise CommandConflictError(message)
        if (
            draft.amount is None
            or money.amount != draft.amount
            or money.external_key != draft.external_key
            or money.instrument_reference != draft.transaction_reference
            or money.instrument_method != draft.instrument_method
            or money.instrument_status != draft.instrument_status
        ):
            raise CommandConflictError("Giao dịch xác nhận khác dữ kiện của bản đọc hoàn trả đã lưu.")
        if draft.instrument_status != "COMPLETED":
            raise UnsupportedCommandError("Chứng từ chưa hoàn tất; chưa thể ghi công ty đã nhận tiền.")
        if not self._same_party(session.tenant, money.payer, str(row["employee"])):
            raise CommandConflictError("Bên chuyển khoản hoàn trả không phải nhân viên của hồ sơ.")
        if not self._same_party(session.tenant, money.payee, "company:demo"):
            raise CommandConflictError("Bên nhận trên chứng từ hoàn trả không phải công ty.")
        submitted_day = money.event_at.astimezone(_VN_TZ).date()
        source_day = draft.event_at.astimezone(_VN_TZ).date() if draft.event_at else None
        if source_day is None or submitted_day != source_day:
            raise CommandConflictError("Ngày xác nhận khác ngày giao dịch trên chứng từ.")
        if any(ref not in draft.refs for ref in money.refs):
            raise UnsupportedCommandError("Căn cứ xác nhận không thuộc bản đọc chứng từ đã lưu.")

        instruction = cx.execute(
            "SELECT * FROM instructions WHERE tenant = ? AND root_id = ? AND id = ?",
            (session.tenant, str(row["id"]), draft.instruction_id),
        ).fetchone()
        if instruction is None or instruction["direction"] != "COLLECT":
            raise CommandConflictError("Không tìm thấy đúng lệnh thu của bản nháp.")
        existing = cx.execute(
            "SELECT root_id, payload_json FROM money_events WHERE tenant = ? AND external_key = ?",
            (session.tenant, draft.external_key),
        ).fetchone()
        existing_event = None
        if existing is not None:
            if str(existing["root_id"]) != str(row["id"]):
                raise CommandConflictError("Mã giao dịch hoàn trả đã thuộc hồ sơ khác.")
            existing_event = MoneyEvent.model_validate_json(existing["payload_json"])
            if (
                existing_event.instruction_id not in (None, draft.instruction_id)
                or existing_event.amount != draft.amount
                or existing_event.kind != "EMPLOYEE_RETURN"
            ):
                raise CommandConflictError("Mã giao dịch đã được ghi với nội dung hoặc lệnh khác.")
        remaining = max(
            int(instruction["amount"]) - int(instruction["fulfilled_amount"]), 0
        )
        active = instruction["status"] in ("ISSUED", "PARTIAL") and remaining > 0
        if not active and existing_event is None:
            raise CommandConflictError("Lệnh thu đã hoàn tất hoặc không còn hiệu lực.")
        current_day = datetime.fromisoformat(self._now_iso()).astimezone(_VN_TZ).date()
        company_name = self._tenant_company_name(cx, session.tenant)
        result = match_employee_return(
            root_id=str(row["id"]),
            instruction_id=draft.instruction_id,
            instruction_active=active or existing_event is not None,
            instruction_remaining=remaining,
            instruction_date=datetime.fromisoformat(str(instruction["created_at"])).astimezone(_VN_TZ).date(),
            as_of=current_day,
            employee_name=self.display_name(session.tenant, str(row["employee"])),
            company_name=company_name,
            payer_name=draft.payer_name,
            payee_name=draft.payee_name,
            amount=draft.amount,
            event_date=source_day,
            transaction_reference=draft.transaction_reference,
            instrument_status=draft.instrument_status,
            transaction_owner_root=str(existing["root_id"]) if existing is not None else None,
            already_recorded=existing_event is not None,
            field_refs={signal.field: signal.refs for signal in draft.signals},
        )
        if result.status not in ("MATCHED", "OVERPAY", "ALREADY_RECORDED"):
            detail = next((signal.summary for signal in result.signals if signal.state in (
                "CONFLICT", "STALE", "NOT_COMPLETED", "MISSING", "MISMATCH", "AMBIGUOUS"
            )), "Lệnh thu đã thay đổi; cần kiểm tra lại chứng từ.")
            raise CommandConflictError(detail)
        reason = "Kế toán xác nhận đã đối chiếu chứng từ hoàn trả với đúng lệnh thu."
        return {
            "draft_id": draft.draft_id,
            "instruction_id": draft.instruction_id,
            "money_event_id": str(existing_event.id) if existing_event is not None else None,
            "refs": draft.refs,
            "reason": reason,
            "completion_claim": reason,
            "match_status": result.status,
            "draft": draft,
        }

    def _complete_employee_return_draft(
        self, cx, *, session, draft_id: str, event_id: str | None, now: str
    ) -> None:
        row = cx.execute(
            "SELECT draft_json FROM case_money_drafts WHERE tenant = ? AND draft_id = ?",
            (session.tenant, draft_id),
        ).fetchone()
        if row is None:
            return
        draft = EmployeeReturnDraft.model_validate_json(row["draft_json"])
        if draft.status != "CONFIRMED":
            draft = draft.model_copy(update={
                "status": "CONFIRMED",
                "confirmed_at": datetime.fromisoformat(now),
                "confirmed_by": session.actor_id,
                "money_event_id": event_id,
            })
            cx.execute(
                "UPDATE case_money_drafts SET status = 'CONFIRMED', draft_json = ?, "
                "confirmed_event_id = ?, confirmed_at = ?, confirmed_by = ?, updated_at = ? "
                "WHERE tenant = ? AND draft_id = ?",
                (
                    draft.model_dump_json(), event_id, now, session.actor_id, now,
                    session.tenant, draft_id,
                ),
            )
            self._audit(
                cx,
                tenant=session.tenant,
                root_id=draft.root_id,
                session_id=session.session_id,
                actor=session.actor_id,
                action="EMPLOYEE_RETURN_CONFIRMED",
                detail=json.dumps({
                    "draft_id": draft_id,
                    "instruction_id": draft.instruction_id,
                    "event_id": event_id,
                }, ensure_ascii=False),
            )

    def _store_activity_acceptance(
        self, cx, *, session, row, money, basis, now: str
    ) -> bool:
        acceptance_id = f"activity-acceptance:{uuid.uuid4().hex}"
        acceptance = ActivityAcceptance(
            root_id=str(row["id"]),
            employee=str(row["employee"]),
            activity=str(row["activity"]),
            advance_external_key=money.external_key,
            advance_draft_id=basis["draft_id"],
            actor=session.actor_id,
            accepted_at=datetime.fromisoformat(now),
            link_basis=basis["link_basis"],
            reason=(
                f"{basis['link_reason']} Kế toán xác nhận: {money.reason.strip()}"
            ),
            refs=basis["refs"],
            link_signals=tuple(basis.get("link_signals", ())),
        )
        cursor = cx.execute(
            "INSERT OR IGNORE INTO case_activity_acceptances (acceptance_id, tenant, "
            "root_id, employee, activity, advance_external_key, advance_draft_id, actor, "
            "accepted_at, link_basis, reason, refs_json, link_signals_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                acceptance_id,
                session.tenant,
                str(row["id"]),
                acceptance.employee,
                acceptance.activity,
                acceptance.advance_external_key,
                acceptance.advance_draft_id,
                acceptance.actor,
                acceptance.accepted_at.isoformat(),
                acceptance.link_basis,
                acceptance.reason,
                json.dumps(
                    [ref.model_dump(mode="json") for ref in acceptance.refs],
                    ensure_ascii=False,
                ),
                json.dumps(
                    [signal.model_dump(mode="json") for signal in acceptance.link_signals],
                    ensure_ascii=False,
                ),
            ),
        )
        if cursor.rowcount:
            self._audit(
                cx,
                tenant=session.tenant,
                root_id=str(row["id"]),
                session_id=session.session_id,
                actor=session.actor_id,
                action="ACTIVITY_ACCEPTANCE_FROM_ADVANCE",
                detail=json.dumps(
                    {
                        "advance_external_key": money.external_key,
                        "activity": str(row["activity"]),
                        "basis": acceptance.link_basis,
                        "link_signals": [signal.summary for signal in acceptance.link_signals],
                    },
                    ensure_ascii=False,
                ),
            )
        return bool(cursor.rowcount)

    def _tenant_company_name(self, cx: sqlite3.Connection, tenant: str) -> str | None:
        """The configured company name: newest snapshot that carries one."""
        for row in cx.execute(
            "SELECT payload_json FROM context_snapshots WHERE tenant = ? "
            "ORDER BY version DESC",
            (tenant,),
        ):
            if not row["payload_json"]:
                continue
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            name = payload.get("company_name")
            if name:
                return str(name)
        return None

    def _same_party(self, tenant: str, a: str, b: str) -> bool:
        """Whether two party strings name the same person (id or display name)."""
        import unicodedata

        def _norm(value: object) -> str:
            text = unicodedata.normalize("NFD", str(value or ""))
            text = "".join(ch for ch in text if not unicodedata.combining(ch))
            return " ".join(text.casefold().split())

        if _norm(a) == _norm(b):
            return True
        return _norm(self.display_name(tenant, a)) == _norm(b) or _norm(a) == _norm(
            self.display_name(tenant, b)
        )

    def _snapshot_ledger_entry(
        self, cx: sqlite3.Connection, tenant: str, external_key: str
    ) -> dict[str, object] | None:
        """One witnessed ledger entry by external key, newest snapshot first."""
        for row in cx.execute(
            "SELECT payload_json FROM context_snapshots WHERE tenant = ? "
            "ORDER BY version DESC",
            (tenant,),
        ):
            if not row["payload_json"]:
                continue
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            ledger = payload.get("ledger")
            if not isinstance(ledger, list):
                continue
            for item in ledger:
                if (
                    isinstance(item, dict)
                    and str(item.get("external_key") or "") == external_key
                ):
                    return item
        return None

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
        if session.persona not in (
            "accountant",
            "approver",
        ) and not self._actor_has_grant(
            cx, session.tenant, context.actor_id, "RECORD_ACTUAL", money.claimed_scope
        ):
            raise UnsupportedCommandError("Bạn không có quyền ghi nhận tiền thực tế.")
        now = self._now_iso()
        root_id = str(row["id"])
        # Source refs are checked against uploaded bytes: a ref that names a
        # source attached to ANOTHER dossier, or a digest that contradicts the
        # attached bytes, is rejected before any write (14/10/2026). Refs from
        # a transient advance-draft read (never attached) carry the read proof
        # itself; the accountant's permission and responsible confirmation
        # cover them.
        for ref in money.refs:
            source_id = str(ref.source_id)
            if source_id.startswith("file:"):
                source_id = source_id[len("file:") :]
            stored_source = cx.execute(
                "SELECT root_id, digest FROM case_sources WHERE source_id = ? "
                "AND tenant = ?",
                (source_id, session.tenant),
            ).fetchone()
            if stored_source is None:
                continue
            if str(stored_source["root_id"]) != root_id or str(
                stored_source["digest"]
            ) != str(ref.source_sha256):
                raise UnsupportedCommandError(
                    "Chứng từ đối chiếu không khớp tệp đã tải lên hồ sơ này."
                )
        # External identity is namespaced (14/10/2026): "<namespace>:<reference>".
        # A missing/blank identity stays an unresolved draft — the server never
        # mints a UUID in place of the missing transaction code and then claims
        # dedup protection. The key is unique per tenant, and two sources under
        # different namespaces are different transactions.
        from invoice_referee.reconciliation.advance_identity import build_external_key

        namespace, _, reference = money.external_key.partition(":")
        if build_external_key(namespace, reference) is None:
            raise UnsupportedCommandError(
                "Thiếu mã giao dịch có namespace (ví dụ ngân hàng:số UNC, quỹ:số phiếu); "
                "giữ chứng từ chưa giải quyết, không tự bịa định danh."
            )
        instruction_row = None
        return_basis = None
        if money.claimed_kind in ("REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN"):
            if session.persona != "accountant":
                raise UnsupportedCommandError("Chỉ kế toán được xác nhận giao dịch theo lệnh chi/thu.")
            if not money.instruction_id:
                raise UnsupportedCommandError("Giao dịch phải gắn với đúng lệnh chi/thu đang hiệu lực.")
            instruction_row = cx.execute(
                "SELECT * FROM instructions WHERE id = ? AND tenant = ?",
                (money.instruction_id, session.tenant),
            ).fetchone()
            expected_direction = (
                "PAY" if money.claimed_kind == "REIMBURSEMENT_RECEIVED" else "COLLECT"
            )
            if (
                instruction_row is None
                or str(instruction_row["root_id"]) != root_id
                or str(instruction_row["direction"]) != expected_direction
            ):
                raise CommandConflictError("Lệnh chi/thu không thuộc hồ sơ này hoặc sai chiều giao dịch.")
            if not money.refs:
                raise UnsupportedCommandError("Gắn chứng từ thực tế trước khi ghi nhận giao dịch.")
            for ref in money.refs:
                stored_source = cx.execute(
                    "SELECT root_id, digest FROM case_sources WHERE source_id = ? AND tenant = ?",
                    (str(ref.source_id), session.tenant),
                ).fetchone()
                if (
                    stored_source is None
                    or str(stored_source["root_id"]) != root_id
                    or str(stored_source["digest"]) != str(ref.source_sha256)
                ):
                    raise UnsupportedCommandError(
                        "Chứng từ giao dịch phải được lưu trong đúng hồ sơ trước khi xác nhận."
                    )
            existing_for_key = cx.execute(
                "SELECT root_id, payload_json FROM money_events WHERE tenant = ? AND external_key = ?",
                (session.tenant, money.external_key),
            ).fetchone()
            existing_instruction_id = None
            if existing_for_key is not None:
                if str(existing_for_key["root_id"]) != root_id:
                    raise CommandConflictError("Mã giao dịch này đã được ghi nhận trong hồ sơ khác.")
                try:
                    existing_event = MoneyEvent.model_validate_json(existing_for_key["payload_json"])
                except (TypeError, ValueError) as error:
                    raise CommandConflictError("Không khôi phục được giao dịch đã ghi.") from error
                existing_instruction_id = existing_event.instruction_id
                if (
                    existing_instruction_id is not None
                    and existing_instruction_id != money.instruction_id
                ):
                    raise CommandConflictError("Mã giao dịch đã gắn với một lệnh khác.")
            remaining = max(
                int(instruction_row["amount"]) - int(instruction_row["fulfilled_amount"]),
                0,
            )
            instruction_is_active = (
                str(instruction_row["status"]) in ("ISSUED", "PARTIAL")
                and remaining > 0
            )
            if not instruction_is_active and existing_for_key is None:
                raise CommandConflictError("Lệnh chi/thu này đã hoàn tất hoặc không còn hiệu lực.")
            if money.amount <= 0:
                raise UnsupportedCommandError("Số tiền giao dịch phải lớn hơn 0 VND.")
            if not money.refs:
                raise UnsupportedCommandError("Gắn chứng từ thực tế trước khi ghi nhận giao dịch.")
            if money.claimed_kind == "EMPLOYEE_RETURN":
                if not money.money_movement_draft_id:
                    raise UnsupportedCommandError("Cần xác nhận từ chứng từ hoàn trả đã lưu.")
                return_basis = self._employee_return_record_basis(cx, session, row, money)
                money = money.model_copy(update={
                    "refs": return_basis["refs"],
                    "reason": return_basis["reason"],
                    "completion_claim": return_basis["completion_claim"],
                })
            elif money.money_movement_draft_id is not None:
                raise UnsupportedCommandError("Bản nháp này chỉ có thể ghi nhận nhân viên hoàn trả.")
        advance_basis = None
        if money.advance_draft_id is not None:
            if money.claimed_kind != "ADVANCE_RECEIVED":
                raise UnsupportedCommandError("Bản đọc này chỉ có thể xác nhận khoản ứng.")
            if session.persona != "accountant":
                raise UnsupportedCommandError("Chỉ kế toán được xác nhận khoản ứng và liên kết công việc.")
            if money.claimed_scope != str(row["activity"]):
                raise UnsupportedCommandError("Khoản ứng phải gắn đúng phạm vi của hồ sơ này.")
            advance_basis = self._advance_record_basis(cx, session, row, money)
            money = money.model_copy(update={
                "reason": advance_basis["record_reason"],
                "completion_claim": advance_basis["completion_claim"],
            })
            for ref in advance_basis["refs"]:
                stored_ref = cx.execute(
                    "SELECT root_id, digest FROM case_sources WHERE source_id = ? AND tenant = ?",
                    (str(ref.source_id), session.tenant),
                ).fetchone()
                if (
                    stored_ref is None
                    or str(stored_ref["root_id"]) != root_id
                    or str(stored_ref["digest"]) != str(ref.source_sha256)
                ):
                    raise UnsupportedCommandError(
                        "Căn cứ liên kết không còn thuộc đúng hồ sơ hoặc tệp nguồn đã thay đổi."
                    )
        # external_key is unique per tenant: a re-sent transaction is not counted
        # twice, and the same key with a different MATERIAL payload (kind,
        # amount, payer, payee or scope — not just amount/kind) is a conflict
        # (§4, 14/10/2026). The same reference under a different namespace is a
        # different key, never an implicit merge.
        from invoice_referee.reconciliation.advance_identity import check_record_payload

        existing = cx.execute(
            "SELECT * FROM money_events WHERE tenant = ? AND external_key = ?",
            (session.tenant, money.external_key),
        ).fetchone()
        if existing is not None:
            if str(existing["root_id"]) != root_id:
                raise CommandConflictError(
                    "Mã giao dịch này đã được ghi nhận trong hồ sơ khác."
                )
            stored = {
                "kind": existing["kind"],
                "amount": int(existing["amount"]),
                "payer": existing["payer"],
                "payee": existing["payee"],
                "scope": existing["scope"],
            }
            claim = {
                "kind": money.claimed_kind,
                "amount": money.amount,
                "payer": money.payer,
                "payee": money.payee,
                "scope": money.claimed_scope,
            }
            if check_record_payload(stored, claim) == "CONFLICT":
                raise CommandConflictError(
                    "external_key đã dùng cho một giao dịch khác nội dung."
                )
            if instruction_row is not None:
                try:
                    existing_event = MoneyEvent.model_validate_json(existing["payload_json"])
                except (TypeError, ValueError) as error:
                    raise CommandConflictError("Không xác minh được lệnh của giao dịch đã ghi.") from error
                if (
                    existing_event.instruction_id is not None
                    and existing_event.instruction_id != money.instruction_id
                ):
                    raise CommandConflictError("Mã giao dịch đã gắn với một lệnh khác.")
                if (
                    return_basis is not None
                    and existing_event.money_movement_draft_id not in (
                        None, money.money_movement_draft_id
                    )
                ):
                    raise CommandConflictError("Mã giao dịch đã gắn với một bản nháp hoàn trả khác.")
            if return_basis is not None:
                self._complete_employee_return_draft(
                    cx,
                    session=session,
                    draft_id=return_basis["draft_id"],
                    event_id=str(existing["id"]),
                    now=now,
                )
            if (
                advance_basis is not None
                and existing["verification_state"] == "CONFIRMED"
                and existing["allocation_state"] == "ALLOCATED"
                and money.instrument_status == "COMPLETED"
                and advance_basis["source_clear"]
                and self._advance_party_block(
                    cx, session.tenant, str(row["employee"]), money
                ) is None
            ):
                accepted = self._store_activity_acceptance(
                    cx, session=session, row=row, money=money, basis=advance_basis, now=now
                )
                from invoice_referee.workflow.money_history import record_dossier_history
                tracked = record_dossier_history(cx, row, actor=context.actor_id, now=datetime.fromisoformat(now))
                if accepted or tracked:
                    self._bump(cx, row, now)
                    self._assess_and_commit(cx, session, self._reload(cx, row), now)
            return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))
        # The witnessed imported ledger is the same transaction history under
        # another store: re-recording it must not raise A a second time.
        snapshot_hit = self._snapshot_ledger_entry(
            cx, session.tenant, money.external_key
        )
        if snapshot_hit is not None:
            stored = {
                "kind": str(snapshot_hit.get("kind") or ""),
                "amount": int(snapshot_hit.get("amount") or 0),
                "payer": str(snapshot_hit.get("payer") or ""),
                "payee": str(snapshot_hit.get("payee") or ""),
                "scope": str(
                    snapshot_hit.get("scope") or snapshot_hit.get("activity") or ""
                ),
            }
            claim = {
                "kind": money.claimed_kind,
                "amount": money.amount,
                "payer": money.payer,
                "payee": money.payee,
                "scope": money.claimed_scope,
            }
            # The snapshot stores employee ids while the UI sends the voucher's
            # payee name: resolve through the tenant's display names before
            # calling it a conflict.
            if self._same_party(session.tenant, stored["payee"], claim["payee"]):
                stored = dict(stored, payee=claim["payee"])
            if check_record_payload(stored, claim) == "CONFLICT":
                raise CommandConflictError(
                    "external_key đã dùng cho một giao dịch khác nội dung."
                )
            if (
                advance_basis is not None
                and str(snapshot_hit.get("verification_state") or "") == "CONFIRMED"
                and str(snapshot_hit.get("allocation_state") or "") == "ALLOCATED"
                and money.instrument_status == "COMPLETED"
                and advance_basis["source_clear"]
                and self._advance_party_block(
                    cx, session.tenant, str(row["employee"]), money
                ) is None
            ):
                accepted = self._store_activity_acceptance(
                    cx, session=session, row=row, money=money, basis=advance_basis, now=now
                )
                from invoice_referee.workflow.money_history import record_dossier_history
                tracked = record_dossier_history(cx, row, actor=context.actor_id, now=datetime.fromisoformat(now))
                if accepted or tracked:
                    self._bump(cx, row, now)
                    self._assess_and_commit(cx, session, self._reload(cx, row), now)
            return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

        kind = money.claimed_kind
        event_id = f"money:{uuid.uuid4().hex}"
        # The server decides verification/allocation from the claim's evidence
        # (contracts §3–§4): a bare statement stays OBSERVED and never fulfills.
        verification = verify_money_claim(money, responsible_actor=context.actor_id)
        # Advance guard (14/10/2026): an ADVANCE_RECEIVED whose voucher payee is
        # not this dossier's employee, or whose payer is not the configured
        # company source, is kept OBSERVED — it never becomes confirmed A.
        # The event is preserved for audit; only verified money projects.
        advance_block_reason: str | None = None
        if kind == "ADVANCE_RECEIVED":
            advance_block_reason = self._advance_party_block(
                cx, session.tenant, str(row["employee"]), money
            )
            if advance_block_reason is not None:
                from invoice_referee.workflow.money import MoneyVerification

                verification = MoneyVerification(
                    verification_state="OBSERVED",
                    allocation_state="UNALLOCATED",
                    reason=advance_block_reason,
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
            verification_state=verification.verification_state,  # type: ignore[arg-type]
            allocation_state=verification.allocation_state,  # type: ignore[arg-type]
            reverses_event_id=money.reverses_event_id,
            refs=money.refs,
            instrument_method=money.instrument_method,
            instrument_status=money.instrument_status,
            instrument_reference=money.instrument_reference,
            recorded_by=context.actor_id,
            record_reason=money.reason,
            advance_draft_id=money.advance_draft_id,
            instruction_id=money.instruction_id,
            money_movement_draft_id=money.money_movement_draft_id,
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
        accepted_work = False
        if (
            advance_basis is not None
            and money.instrument_status == "COMPLETED"
            and advance_basis["source_clear"]
            and advance_block_reason is None
            and verification.verification_state == "CONFIRMED"
            and verification.allocation_state == "ALLOCATED"
        ):
            accepted_work = self._store_activity_acceptance(
                cx, session=session, row=row, money=money, basis=advance_basis, now=now
            )
        if return_basis is not None:
            self._complete_employee_return_draft(
                cx,
                session=session,
                draft_id=return_basis["draft_id"],
                event_id=event.id,
                now=now,
            )
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=root_id,
            session_id=session.session_id,
            actor=context.actor_id,
            action="RECORD_ACTUAL",
            detail=json.dumps(
                {
                "kind": event.kind,
                "amount": event.amount,
                "key": event.external_key,
                "verification": event.verification_state,
                "activity_accepted": accepted_work,
                    **(
                        {"advance_block": advance_block_reason}
                        if advance_block_reason is not None
                        else {}
                    ),
                },
                ensure_ascii=False,
            ),
        )
        from invoice_referee.workflow.money_history import maintain_history, record_dossier_history

        if (
            advance_basis is not None and advance_basis["source_clear"]
            and verification.verification_state == "CONFIRMED"
            and verification.allocation_state == "ALLOCATED"
            and advance_block_reason is None and money.instrument_status == "COMPLETED"
        ):
            record_dossier_history(cx, row, actor=context.actor_id, now=datetime.fromisoformat(now))
        elif (
            instruction_row is not None and money.instrument_status == "COMPLETED"
            and verification.verification_state == "CONFIRMED"
            and verification.allocation_state == "ALLOCATED"
        ):
            # A context-imported advance may have no local receipt checkpoint.
            # The confirmed, instruction-bound movement starts dossier tracking.
            record_dossier_history(cx, row, actor=context.actor_id,
                                   now=datetime.fromisoformat(now), only_if_untracked=True)

        tracked_history = maintain_history(
            cx, row, event, now=datetime.fromisoformat(now),
            controlled=(
                session.persona == "accountant"
                and verification.verification_state == "CONFIRMED"
                and verification.allocation_state == "ALLOCATED"
                and money.instrument_status == "COMPLETED"
                and (advance_basis is not None or return_basis is not None or instruction_row is not None)
                and money.reverses_event_id is None
            ),
        )
        if tracked_history is not None:
            self._audit(cx, tenant=session.tenant, root_id=root_id,
                        session_id=session.session_id, actor=context.actor_id,
                        action="TRACK_MONEY_HISTORY",
                        detail=json.dumps({"coverage_id": tracked_history, "event_id": event.id}))
        # Re-assess so the projection reflects the new money and the active
        # instruction's fulfillment is re-derived (contracts §4).
        self._reconcile_money(cx, session, self._reload(cx, row), now)
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _confirm_money_history(self, cx, session, context, command: ConfirmMoneyHistory):
        row = self._require_root(cx, session, command.root_id)
        self._require_version(row, context.expected_case_version)
        if session.persona != "accountant":
            raise UnsupportedCommandError("Chỉ kế toán được xác nhận lịch sử tiền ban đầu.")
        if not command.all_prior_money_recorded:
            raise UnsupportedCommandError("Cần xác nhận đã ghi nhận đầy đủ các khoản tiền trước khi tiếp nhận.")
        from invoice_referee.workflow.money_history import initial_history

        now = self._now_iso()
        try:
            coverage = initial_history(cx, row, actor=context.actor_id, now=datetime.fromisoformat(now))
        except ValueError as error:
            raise UnsupportedCommandError(str(error)) from error
        coverage_id = f"coverage:{uuid.uuid4().hex}"
        cx.execute(
            "INSERT INTO case_coverage_records (coverage_id, tenant, root_id, ledger_version, "
            "coverage_json, actor, recorded_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (coverage_id, session.tenant, str(row["id"]), coverage.ledger_version,
             coverage.model_dump_json(), context.actor_id, now, coverage.reason),
        )
        self._bump(cx, row, now)
        self._audit(cx, tenant=session.tenant, root_id=str(row["id"]),
                    session_id=session.session_id, actor=context.actor_id,
                    action="CONFIRM_INITIAL_MONEY_HISTORY",
                    detail=json.dumps({"coverage_id": coverage_id, "ledger_version": coverage.ledger_version,
                                       "statement": coverage.reason}, ensure_ascii=False))
        self._assess_and_commit(cx, session, self._reload(cx, row), now)
        return CommandResult(case_view=self._case_view(cx, self._reload(cx, row)))

    def _confirm_coverage(
        self,
        cx: sqlite3.Connection,
        session: DemoSession,
        context: CommandContext,
        command: ConfirmCoverage,
    ) -> CommandResult:
        from invoice_referee.domain.common import Fact
        from invoice_referee.domain.finance import COVERAGE_REQUIRED_FLOW_KINDS

        row = self._require_root(cx, session, command.root_id)
        self._require_version(row, context.expected_case_version)
        if session.persona != "accountant":
            raise UnsupportedCommandError("Chỉ kế toán được xác nhận lịch sử tiền.")
        now = self._now_iso()
        confirmed_at = datetime.fromisoformat(now)
        if command.start > confirmed_at:
            raise UnsupportedCommandError("Ngày bắt đầu đối chiếu không được ở tương lai.")
        if not command.funds or any(not item.strip() for item in command.funds):
            raise UnsupportedCommandError("Chọn ít nhất một nguồn tiền đã đối chiếu.")
        if len(set(command.funds)) != len(command.funds):
            raise UnsupportedCommandError("Nguồn tiền bị lặp trong phạm vi đối chiếu.")
        if len(set(command.flow_kinds)) != len(command.flow_kinds):
            raise UnsupportedCommandError("Loại giao dịch bị lặp trong phạm vi đối chiếu.")
        if set(COVERAGE_REQUIRED_FLOW_KINDS) != set(command.flow_kinds):
            raise UnsupportedCommandError(
                "Chọn đúng các loại đã đối chiếu: ứng, chi bổ sung, hoàn trả, đảo giao dịch và khoản chưa phân bổ."
            )
        if not command.witness_refs:
            raise UnsupportedCommandError("Cần gắn ít nhất một chứng từ làm căn cứ đối chiếu.")
        for ref in command.witness_refs:
            source = cx.execute(
                "SELECT root_id, digest FROM case_sources WHERE source_id = ? AND tenant = ?",
                (str(ref.source_id), session.tenant),
            ).fetchone()
            if (
                source is None
                or str(source["root_id"]) != str(row["id"])
                or str(source["digest"]) != str(ref.source_sha256)
            ):
                raise UnsupportedCommandError(
                    "Căn cứ đối chiếu phải là chứng từ đã lưu trong đúng hồ sơ."
                )

        unallocated_rows = cx.execute(
            "SELECT id FROM money_events WHERE tenant = ? AND root_id = ? "
            "AND (verification_state != 'CONFIRMED' OR allocation_state != 'ALLOCATED') "
            "ORDER BY id",
            (session.tenant, str(row["id"])),
        ).fetchall()
        actual_unallocated = {str(item["id"]) for item in unallocated_rows}
        from invoice_referee.workflow.context_records import context_ledger, load_context

        organization = load_context(
            cx,
            session.tenant,
            str(row["activity"]),
            confirmed_at,
        )
        if organization is not None:
            context_digest = hashlib.sha256(
                organization.model_dump_json().encode("utf-8")
            ).hexdigest()
            actual_unallocated.update(
                event.id
                for event in context_ledger(organization, digest=context_digest)
                if event.verification_state != "CONFIRMED"
                or event.allocation_state != "ALLOCATED"
            )
        declared_unallocated = set(str(item) for item in command.unallocated_event_ids)
        if actual_unallocated != declared_unallocated:
            raise UnsupportedCommandError(
                "Danh sách khoản chưa phân bổ đã thay đổi; tải lại lịch sử trước khi xác nhận."
            )

        ledger_version = cx.execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?",
            (session.tenant, str(row["id"])),
        ).fetchone()
        version_value = int(ledger_version["n"]) if ledger_version else 0
        coverage = CoverageRecord(
            scope=str(row["activity"]),
            start=command.start,
            as_of=confirmed_at,
            funds=tuple(command.funds),
            flow_kinds=tuple(command.flow_kinds),  # type: ignore[arg-type]
            opening_balance=Fact[int](
                key="coverage:opening",
                value=command.opening_balance,
                state="KNOWN",
                refs=command.witness_refs,
            ),
            ledger_version=str(version_value),
            witness_refs=command.witness_refs,
            source="ACCOUNTANT_CONFIRMATION",
            employee=str(row["employee"]),
            actor=context.actor_id,
            recorded_at=confirmed_at,
            reason=command.reason,
            unallocated_event_ids=tuple(command.unallocated_event_ids),
        )
        coverage_id = f"coverage:{uuid.uuid4().hex}"
        cx.execute(
            "INSERT INTO case_coverage_records (coverage_id, tenant, root_id, "
            "ledger_version, coverage_json, actor, recorded_at, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                coverage_id,
                session.tenant,
                str(row["id"]),
                str(version_value),
                coverage.model_dump_json(),
                context.actor_id,
                now,
                command.reason,
            ),
        )
        self._bump(cx, row, now)
        self._audit(
            cx,
            tenant=session.tenant,
            root_id=str(row["id"]),
            session_id=session.session_id,
            actor=context.actor_id,
            action="CONFIRM_HISTORY_COVERAGE",
            detail=json.dumps(
                {
                    "coverage_id": coverage_id,
                    "activity": str(row["activity"]),
                    "ledger_version": str(version_value),
                    "fund_count": len(coverage.funds),
                    "flow_kind_count": len(coverage.flow_kinds),
                },
                ensure_ascii=False,
            ),
        )
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
            raise UnsupportedCommandError(
                "Chỉ kế toán/người có quyền đánh dấu thực hiện."
            )
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
                {
                    "instruction": command.instruction_id,
                    "state": command.execution_state,
                },
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
        from invoice_referee.workflow.money import fulfillment_for

        employee = str(row["employee"])
        for inst in cx.execute(
            "SELECT * FROM instructions WHERE root_id = ? AND status IN ('ISSUED','PARTIAL')",
            (root_id,),
        ).fetchall():
            expected_payee = employee if inst["direction"] == "PAY" else "company:demo"
            fulfilled = fulfillment_for(
                events,
                payee=expected_payee,
                direction=str(inst["direction"]),
                instruction_id=str(inst["id"]),
                legacy_after=datetime.fromisoformat(str(inst["created_at"])),
            )
            amount = int(inst["amount"])
            capped = min(fulfilled, amount)
            status = (
                "FULFILLED"
                if capped >= amount and amount > 0
                else ("PARTIAL" if capped > 0 else "ISSUED")
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
        from invoice_referee.evidence.trace import stage_payload

        def _fact_summary(fact) -> dict[str, object]:
            state = getattr(fact, "state", "UNKNOWN")
            result: dict[str, object] = {"state": state}
            if state == "KNOWN":
                result["value"] = getattr(fact, "value", None)
            refs = getattr(fact, "refs", ())
            if refs:
                result["refs"] = [
                    {
                        "source_id": getattr(ref, "source_id", None),
                        "source_sha256": getattr(ref, "source_sha256", None),
                        "page": getattr(ref, "page", None),
                    }
                    for ref in refs
                ]
            return result

        def _business_issue_summary(issue) -> dict[str, object]:
            issue_owner = getattr(issue, "owner", "UNKNOWN")
            if issue_owner not in {"employee", "accountant", "approver", "org-data"}:
                issue_owner = "REDACTED_OWNER"
            field_or_rule = getattr(issue, "field_or_rule", "")
            arithmetic = "arithmetic" in field_or_rule.lower()
            return {
                "kind": getattr(issue, "kind", "UNKNOWN"),
                "field_or_rule": field_or_rule,
                "owner": issue_owner,
                "status": getattr(issue, "status", "UNKNOWN"),
                "depends_on": list(getattr(issue, "depends_on", ())),
                **({"basis": getattr(issue, "basis", "")} if arithmetic else {}),
                "refs": [
                    {
                        "source_id": getattr(ref, "source_id", None),
                        "source_sha256": getattr(ref, "source_sha256", None),
                        "page": getattr(ref, "page", None),
                    }
                    for ref in getattr(issue, "refs", ())
                ],
            }

        root_id = str(row["id"])
        # Stop is atomic with the commit: a worker whose snapshot predates a
        # Stop must not create a new instruction (contracts §6).
        if str(row["state"]) == "STOPPED":
            return
        from invoice_referee.evidence.telemetry import step

        with step("admission", metadata={"trace_stage": "admission"}) as s:
            assessment_input = self._build_assessment_input(cx, session, row, now)
            if assessment_input is not None:
                rs = assessment_input.read_set
                expenses = [
                    {
                        "expense_id": expense.id,
                        "economic_key": expense.economic_key,
                        "fact": "T",
                        "incurred": _fact_summary(expense.incurred),
                        "eligibility_state": expense.eligibility,
                        "payment_state": expense.payment_state,
                        "payment_basis_kinds": sorted(
                            {payment.basis_kind for payment in expense.payments}
                        ),
                        "category": expense.category,
                        "refs": [
                            {
                                "source_id": ref.source_id,
                                "source_sha256": ref.source_sha256,
                                "page": ref.page,
                            }
                            for ref in expense.refs
                        ],
                    }
                    for expense in assessment_input.expense_facts
                ]
                unverified = [
                    {
                        "field": observation.field,
                        "read_state": observation.read_state,
                        "normalized": observation.normalized,
                        "refs": [
                            {
                                "source_id": observation.ref.source_id,
                                "source_sha256": observation.ref.source_sha256,
                                "page": observation.ref.page,
                            }
                        ],
                    }
                    for observation in assessment_input.observations
                ]
                blocked = [
                    _business_issue_summary(issue)
                    for issue in assessment_input.admission_issues
                ]
                arithmetic_findings = [
                    {
                        "field_or_rule": issue.field_or_rule,
                        "reason": issue.basis,
                        "refs": [
                            {
                                "source_id": ref.source_id,
                                "source_sha256": ref.source_sha256,
                                "page": ref.page,
                            }
                            for ref in issue.refs
                        ],
                    }
                    for issue in assessment_input.admission_issues
                    if "arithmetic" in issue.field_or_rule.lower()
                ]
                history = [
                    {
                        "kind": event.kind,
                        "amount": event.amount,
                        "verification_state": event.verification_state,
                        "allocation_state": event.allocation_state,
                        "refs": [
                            {
                                "source_id": ref.source_id,
                                "source_sha256": ref.source_sha256,
                                "page": ref.page,
                            }
                            for ref in event.refs
                        ],
                    }
                    for event in assessment_input.ledger
                ]
                relations = [
                    {
                        "kind": relation.kind,
                        "from_id": relation.from_id,
                        "to_id": relation.to_id,
                        "state": relation.state,
                        "refs": [
                            {
                                "source_id": ref.source_id,
                                "source_sha256": ref.source_sha256,
                                "page": ref.page,
                            }
                            for ref in relation.refs
                        ],
                    }
                    for relation in assessment_input.relations
                ]
                confirmations = [
                    {
                        "field": item.fact_key,
                        "value": item.value,
                        "scope": item.scope,
                        "actor": "REDACTED",
                        "refs": [
                            {
                                "source_id": ref.source_id,
                                "source_sha256": ref.source_sha256,
                                "page": ref.page,
                            }
                            for ref in item.refs
                        ],
                    }
                    for item in assessment_input.confirmations
                ]
                processing_problems = [
                    {
                        "kind": problem.kind,
                        "affected_fields": list(problem.affected_fields),
                        "relevance": problem.relevance,
                        "blocking": problem.blocking,
                        "next_action": problem.next_action,
                    }
                    for problem in assessment_input.admission_problems
                ]
                read_set = {
                    "input_revision": rs.input_revision,
                    "control_epoch": rs.control_epoch,
                    "context_version": rs.context_version,
                    "ledger_version": rs.ledger_version,
                    "usage_version": rs.usage_version,
                }
                admission_payload = stage_payload(
                    "admission",
                    {
                        "status": "ASSEMBLED",
                        "accepted_facts": expenses,
                        "unverified_facts": unverified,
                        "blocked_facts": blocked,
                        "fact_count": len(expenses),
                        "issue_count": len(blocked),
                        "issues": blocked,
                        "read_set": read_set,
                        "money_basis": "NOT_COMPUTED_BEFORE_RECONCILIATION",
                        "employee_paid_state": "NOT_INDEPENDENTLY_BANK_VERIFIED",
                        "binding": {
                            "activity": assessment_input.scope.activity,
                            "profile": assessment_input.scope.profile,
                            "employee_identity": "REDACTED",
                            "tenant_identity": "REDACTED",
                            "scope_source": "SERVER_CONTEXT",
                        },
                        "money_history": history,
                        "relations": relations,
                        "confirmations": confirmations,
                        "problems": processing_problems,
                        "arithmetic_findings": arithmetic_findings,
                    },
                )
                s.inputs.update(admission_payload)
                s.outputs.update(admission_payload)
            else:
                s.skipped = "no_published_evidence_report"
                s.outputs.update(
                    stage_payload("admission", {"status": "PENDING_EVIDENCE"})
                )
        if assessment_input is None:
            # Evidence mode with no published report yet: stay EVIDENCE_READY.
            # A LIVE/REPLAY root must never fall back to a seeded STUB
            # transcription (contracts §12.5, plan E7/A5).
            return
        with step(
            "reconcile",
            metadata={"trace_stage": "reconcile"},
            inputs=stage_payload(
                "reconcile",
                {
                    "cost_basis": assessment_input.previous_eligibility.cost_basis
                    if assessment_input.previous_eligibility is not None
                    else None,
                },
            ),
        ) as s:
            result = Reconciler().assess(assessment_input)
            axes = {
                name: _fact_summary(getattr(result.projection, name))
                for name in ("T", "E", "C", "A", "P", "R", "unpaid", "S")
            }
            issue_summaries = [
                _business_issue_summary(issue) for issue in result.issues
            ]
            technical_problems = [
                {
                    "kind": problem.kind,
                    "field_or_rule": ",".join(problem.affected_fields) or problem.kind,
                    "owner": "system",
                    "status": "BLOCKING" if problem.blocking else "OBSERVED",
                }
                for problem in result.problems
            ]
            issue_summaries.extend(technical_problems)
            effect = (
                {
                    "state": "PERMITTED",
                    "direction": result.allowed_effect.direction,
                    "amount": result.allowed_effect.amount,
                    "basis": result.allowed_effect.basis,
                }
                if result.allowed_effect is not None
                else {"state": "NONE"}
            )
            blockers = [
                {"kind": issue["kind"], "field_or_rule": issue["field_or_rule"]}
                for issue in issue_summaries
            ]
            if result.allowed_effect is None and not blockers:
                if result.projection.S.state != "KNOWN":
                    blockers.append({"kind": "FACT", "field_or_rule": "S_UNKNOWN"})
                else:
                    blockers.append(
                        {"kind": "POLICY", "field_or_rule": "NO_EFFECT_REQUIRED"}
                    )
            decision_state = (
                "PERMITTED"
                if result.allowed_effect is not None
                else "BLOCKED"
                if result.issues
                or result.problems
                or result.projection.S.state != "KNOWN"
                else "NO_EFFECT_REQUIRED"
            )
            s.outputs.update(
                stage_payload(
                    "reconcile",
                    {
                        "axes": axes,
                        "issues": issue_summaries,
                        "authorizations": [
                            str(item) for item in result.required_authorizations
                        ],
                        "allowed_effect": effect,
                        "effect_blockers": blockers,
                        "decision_state": decision_state,
                        "state": "KNOWN"
                        if result.projection.S.state == "KNOWN"
                        else "UNKNOWN",
                        "cost_basis": result.cost_basis,
                        "money_basis": result.money_basis,
                    },
                )
            )
        with step("commit", metadata={"trace_stage": "commit"}) as s:
            version_before = int(row["version"])
            state_before = str(row["state"])
            self._commit_assessment(cx, session, row, result, now)
            after = cx.execute(
                "SELECT state, version, input_revision FROM cases WHERE id = ?",
                (root_id,),
            ).fetchone()
            instruction_row = cx.execute(
                "SELECT id, direction, amount, status, execution_state, fulfilled_amount "
                "FROM instructions WHERE root_id = ? ORDER BY rowid DESC LIMIT 1",
                (root_id,),
            ).fetchone()
            conclusion_row = cx.execute(
                "SELECT status FROM case_conclusions WHERE root_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (root_id,),
            ).fetchone()
            s.outputs.update(
                stage_payload(
                    "commit",
                    {
                        "state_before": state_before,
                        "state_after": str(after["state"])
                        if after is not None
                        else None,
                        "version_before": version_before,
                        "version_after": int(after["version"])
                        if after is not None
                        else None,
                        "input_revision": int(after["input_revision"])
                        if after is not None
                        else None,
                        "instruction": (
                            {
                                "id": str(instruction_row["id"]),
                                "direction": str(instruction_row["direction"]),
                                "amount": int(instruction_row["amount"]),
                                "status": str(instruction_row["status"]),
                                "execution_state": str(
                                    instruction_row["execution_state"]
                                ),
                                "fulfilled_amount": int(
                                    instruction_row["fulfilled_amount"]
                                ),
                                "semantics": "instruction_is_not_payment_confirmation",
                            }
                            if instruction_row is not None
                            else None
                        ),
                        "conclusion_status": (
                            str(conclusion_row["status"])
                            if conclusion_row is not None
                            else None
                        ),
                        "committed": True,
                    },
                )
            )

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
            conclusion_status = (
                "OUTSTANDING" if state == "READY_TO_EXECUTE" else "BLOCKED"
            )
        elif result.issues:
            state = "WAITING"
            conclusion_status = "BLOCKED"
        elif (
            result.projection.S.state == "KNOWN"
            and int(result.projection.S.value or 0) == 0
        ):
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
        basis_digest = hashlib.sha256(
            (root_id + result.cost_basis).encode()
        ).hexdigest()[:16]
        instruction_id = f"instruction:{basis_digest}:{uuid.uuid4().hex[:8]}"
        # The authority that lets this order be issued (contracts §2): the
        # covering system grant(s) for the action at this scope/amount. Recorded
        # so the instruction is grounded, not merely asserted.
        action = "ISSUE_PAYMENT" if effect.direction == "PAY" else "ISSUE_COLLECTION"
        authority_refs = self._covering_grant_ids(
            cx,
            session.tenant,
            "system:referee",
            action,
            str(row["activity"]),
            effect.amount,
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
        for economic_key in result.economic_keys or self._economic_keys_for(
            cx, root_id
        ):
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

    def _economic_keys_for(
        self, cx: sqlite3.Connection, root_id: str
    ) -> tuple[str, ...]:
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
                result = AssessmentResult.model_validate_json(
                    conclusion["payload_json"]
                )
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
            str(fact.value)
            for fact in transcription.facts
            if fact.field == "economic_key"
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
        if (
            result.projection.S.state == "KNOWN"
            and int(result.projection.S.value or 0) == 0
        ):
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
        return cx.execute(
            "SELECT * FROM cases WHERE id = ?", (str(row["id"]),)
        ).fetchone()

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

    def _query_one(
        self, sql: str, params: tuple[object, ...] = ()
    ) -> sqlite3.Row | None:
        connection = self.db.connect()
        try:
            return connection.execute(sql, params).fetchone()
        finally:
            connection.close()

    def _case_view(self, cx: sqlite3.Connection, row: sqlite3.Row) -> CaseView:
        activity = cx.execute(
            "SELECT name FROM context_activities "
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
        activity_name = (
            activity["name"] if activity is not None else row["activity_name"]
        )
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
        conclusion_row = cx.execute(
            "SELECT payload_json, decided_at FROM case_conclusions WHERE root_id = ? "
            "ORDER BY revision DESC LIMIT 1",
            (str(row["id"]),),
        ).fetchone()
        conclusion = None
        actual_money = _unknown_projection()
        if conclusion_row is not None:
            from invoice_referee.domain.case import SettlementConclusion

            result = AssessmentResult.model_validate_json(
                conclusion_row["payload_json"]
            )
            actual_money = result.projection
            if result.issues:
                status = "BLOCKED"
            elif (
                result.projection.S.state == "KNOWN"
                and int(result.projection.S.value or 0) == 0
            ):
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
        activity_acceptances = tuple(
            ActivityAcceptance(
                root_id=str(item["root_id"]),
                employee=str(item["employee"]),
                activity=str(item["activity"]),
                advance_external_key=str(item["advance_external_key"]),
                advance_draft_id=str(item["advance_draft_id"]),
                actor=str(item["actor"]),
                accepted_at=datetime.fromisoformat(str(item["accepted_at"])),
                link_basis=str(item["link_basis"]),
                reason=str(item["reason"]),
                refs=tuple(
                    EvidenceRef.model_validate(ref)
                    for ref in json.loads(item["refs_json"] or "[]")
                ),
                link_signals=tuple(
                    ActivityLinkSignal.model_validate({
                        **signal,
                        "refs": tuple(
                            EvidenceRef.model_validate(ref)
                            for ref in signal.get("refs", [])
                        ),
                    })
                    for signal in json.loads(item["link_signals_json"] or "[]")
                ),
            )
            for item in cx.execute(
                "SELECT * FROM case_activity_acceptances WHERE tenant = ? AND root_id = ? "
                "ORDER BY accepted_at, acceptance_id",
                (str(row["tenant"]), str(row["id"])),
            )
        )
        coverage_row = cx.execute(
            "SELECT coverage_json FROM case_coverage_records WHERE tenant = ? AND root_id = ? "
            "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
            (str(row["tenant"]), str(row["id"])),
        ).fetchone()
        coverage_record = (
            CoverageRecord.model_validate_json(coverage_row["coverage_json"])
            if coverage_row is not None
            else None
        )
        ledger_version_row = cx.execute(
            "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?",
            (str(row["tenant"]), str(row["id"])),
        ).fetchone()
        ledger_version = int(ledger_version_row["n"]) if ledger_version_row else 0
        now_dt = datetime.fromisoformat(self._now_iso())
        import hashlib
        from invoice_referee.domain.case import CaseScope
        from invoice_referee.reconciliation.admission import coverage_is_valid, history_fingerprint
        from invoice_referee.workflow.context_records import context_ledger, load_context, merge_ledger

        organization = load_context(cx, str(row["tenant"]), str(row["activity"]), now_dt)
        imported_history = context_ledger(
            organization, digest=hashlib.sha256(organization.model_dump_json().encode()).hexdigest()
        ) if organization is not None else ()

        coverage_current = (
            coverage_is_valid(
                coverage_record,
                scope=CaseScope(
                    tenant=str(row["tenant"]),
                    employee=str(row["employee"]),
                    activity=str(row["activity"]),
                    profile=str(row["profile"]),
                ),
                as_of=now_dt,
                current_ledger_version=ledger_version,
                current_context_ledger_fingerprint=history_fingerprint(imported_history),
            )
            if coverage_record is not None
            else False
        )
        local_money_history = tuple(
            MoneyEvent.model_validate_json(event["payload_json"])
            for event in cx.execute(
                "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? "
                "ORDER BY event_at, recorded_at, id",
                (str(row["tenant"]), str(row["id"])),
            )
        )
        money_history, _history_conflicts = merge_ledger(imported_history, local_money_history)
        employee_return_drafts: list[EmployeeReturnDraft] = []
        for draft_row in cx.execute(
            "SELECT draft_json FROM case_money_drafts WHERE tenant = ? AND root_id = ? "
            "ORDER BY created_at, draft_id",
            (str(row["tenant"]), str(row["id"])),
        ).fetchall():
            draft = EmployeeReturnDraft.model_validate_json(draft_row["draft_json"])
            if draft.status != "CONFIRMED":
                current_instruction = cx.execute(
                    "SELECT * FROM instructions WHERE tenant = ? AND root_id = ? AND id = ?",
                    (str(row["tenant"]), str(row["id"]), draft.instruction_id),
                ).fetchone()
                is_active = (
                    current_instruction is not None
                    and current_instruction["direction"] == "COLLECT"
                    and current_instruction["status"] in ("ISSUED", "PARTIAL")
                    and int(current_instruction["amount"]) > int(current_instruction["fulfilled_amount"])
                )
                if not is_active:
                    draft = draft.model_copy(update={
                        "match_status": "STALE",
                        "signals": tuple(signal for signal in draft.signals if signal.field != "instruction") + (
                            MoneyMovementSignal(
                                field="instruction",
                                state="STALE",
                                summary="Lệnh thu đã hoàn tất hoặc không còn hiệu lực.",
                            ),
                        ),
                    })
                else:
                    remaining = max(
                        int(current_instruction["amount"]) - int(current_instruction["fulfilled_amount"]),
                        0,
                    )
                    draft = draft.model_copy(update={"instruction_remaining": remaining})
                    amount_signal = next(
                        (signal for signal in draft.signals if signal.field == "amount"), None
                    )
                    if draft.amount is not None and draft.amount > remaining:
                        draft = draft.model_copy(update={
                            "match_status": "OVERPAY",
                            "signals": tuple(signal for signal in draft.signals if signal.field != "amount") + (
                                MoneyMovementSignal(
                                    field="amount",
                                    state="OVERPAY",
                                    summary=f"Số hoàn {draft.amount:,} VND vượt lệnh thu còn {remaining:,} VND.",
                                    refs=amount_signal.refs if amount_signal is not None else (),
                                ),
                            ),
                        })
            employee_return_drafts.append(draft)
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
            activity_acceptances=activity_acceptances,
            coverage_record=coverage_record,
            coverage_current=coverage_current,
            money_history=tuple(
                sorted(money_history, key=lambda event: (event.event_at, event.recorded_at, event.id))
            ),
            employee_return_drafts=tuple(employee_return_drafts),
            trace_refs=(
                (self._last_trace_ref[str(row["id"])],)
                if str(row["id"]) in self._last_trace_ref
                else ()
            ),
        )
