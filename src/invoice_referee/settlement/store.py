"""Settlement store (W01): SQLite + originals under ``artifact_root``.

Guards implemented here (System §S6/S7):

- Command idempotency is looked up per (operation, actor, case scope, key)
  before any version/gate check. Same semantic fingerprint returns the
  recorded result and current state; a different payload is a conflict.
- ``expected_case_version`` must match the persisted version on mutations.
- Sources are validated (size, format by magic bytes, active count) before
  any resource is spent; originals are written atomically via the shared
  artifact helper and never overwrite by filename — same bytes uploaded
  twice stay two associated sources.
- Files are staged before the DB transaction commits; a DB failure unlinks
  only the file this attempt just wrote.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3CompanyContext, is_b3_v1
from invoice_referee.settlement.b3_workflow import (
    b3_basis_signature,
    b3_context_signature,
    b3_route_for,
)
from invoice_referee.settlement.models import (
    MAX_ACTIVE_SOURCES_PER_CASE,
    MAX_SOURCE_BYTES,
    AllowedAction,
    AuditEntry,
    B3AdvanceEventPayload,
    B3AdvanceEventView,
    B3DecisionPayload,
    B3DecisionView,
    B3FundingIncident,
    B3PresentPayload,
    B3PresentationView,
    B3WorkflowView,
    B7LinkedIntake,
    B7OriginLink,
    CaseSnapshot,
    CaseStage,
    CaseSummary,
    CaseView,
    CallTrace,
    ClosurePayload,
    ClosureView,
    Command,
    DecisionPayload,
    DecisionView,
    MoneyEventPayload,
    MoneyEventView,
    MoneyIncident,
    MoneySummary,
    QuestionView,
    Report,
    ResponsePayload,
    ResponseView,
    ReviewPayload,
    ReviewView,
    RunInput,
    RunView,
    RunStatus,
    SourceRecord,
    SourceView,
    Submission,
    Upload,
    fingerprint,
)
from invoice_referee.storage.artifacts import put_artifact

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_CREATE_CASE = "CREATE_CASE"
_CREATE_B3_CASE = "CREATE_B3_CASE"
_REVISE_SUBMISSION = "REVISE_SUBMISSION"
_ADD_SOURCE = "ADD_SOURCE"
_START_RUN = "START_RUN"
_RESPOND = "RESPOND"
_DECIDE = "DECIDE"
_REVIEW = "REVIEW"
_RECORD_MONEY = "RECORD_MONEY"
_CONTROL = "CONTROL"
_HANDOFF = "HANDOFF"
_CLOSE_CASE = "CLOSE_CASE"
_B3_PRESENT = "B3_PRESENT"
_B3_DECIDE = "B3_DECIDE"
_B3_ADD_ADVANCE_PROOF = "B3_ADD_ADVANCE_PROOF"
_B3_RECORD_ADVANCE = "B3_RECORD_ADVANCE"
_PREPARE_LINKED_B7 = "PREPARE_LINKED_B7"
_REVISE_LINKED_B7 = "REVISE_LINKED_B7"
_B7_CONTEXT_REFRESH = "B7_CONTEXT_REFRESH"
_LINKED_B7_CONTEXT_USE = "LINKED_B7_CONTEXT"

_NONTERMINAL_STATUSES = ("QUEUED", "RUNNING")
_TERMINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "STOPPED",
                      "SUPERSEDED", "INTERRUPTED")
_CLOSED_STAGES: tuple[str, ...] = ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED")
_OPEN_QUESTION_STATUSES = ("OPEN", "ANSWERED")
MAX_ACCEPTED_RUNS = 5

# Legacy work-ref prefixes that mark eval/verify/debug-seeded cases as SYSTEM
# during the one-time ``origin`` backfill (see ``_migrate``).
_SYSTEM_WORK_REF_PREFIXES = ("CT-E2E-", "CT-DEBUG", "WORK-DEMO-")


def _is_system_work_ref(work_ref: str) -> bool:
    return any(work_ref.startswith(prefix)
               for prefix in _SYSTEM_WORK_REF_PREFIXES)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def detect_media_type(content: bytes, filename: str) -> str:
    """Classify source bytes by content, not by extension or Content-Length.

    JPEG/PNG/PDF are matched on magic bytes; ZIP-family containers (docx,
    xlsx, zip) are rejected explicitly so they cannot pass as text; anything
    that decodes as UTF-8 (BOM allowed) is the accepted text family, with the
    extension only refining text/csv vs text/markdown vs text/plain.
    """
    if content.startswith(b"PK\x03\x04"):
        raise DomainError(
            "UNSUPPORTED_FORMAT",
            "Định dạng ZIP/DOCX/XLSX nằm ngoài đường đọc v0; bổ sung dạng JPEG/PNG/PDF/CSV/TXT/Markdown.",
        )
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DomainError(
            "UNSUPPORTED_FORMAT",
            "Không nhận diện được định dạng hỗ trợ (JPEG/PNG/PDF/CSV/TXT/Markdown) từ nội dung file.",
        ) from None
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".md":
        return "text/markdown"
    return "text/plain"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(text: str) -> Any:
    return json.loads(text)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


class Store:
    """SQLite-backed store for cases, sources, runs and history."""

    def __init__(self, db_path: Path, artifact_root: Path) -> None:
        self.db_path = Path(db_path)
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            self._migrate(conn)
            conn.execute(
                "UPDATE runs SET status = 'INTERRUPTED', "
                "detail = COALESCE(detail, 'process restart: run không kết thúc'), "
                "updated_at = ? WHERE status IN ('QUEUED', 'RUNNING')",
                (_iso(utcnow()),),
            )

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Additive migrations for runtime DBs created by earlier slices.

        ``CREATE TABLE IF NOT EXISTS`` cannot evolve an existing table; new
        nullable columns are added explicitly so old pilot data keeps working.
        """
        columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
        if columns and "detail" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN detail TEXT")
        if columns and "stage" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN stage TEXT")
        if columns and "trace_json" not in columns:
            conn.execute("ALTER TABLE runs ADD COLUMN trace_json TEXT")
        case_columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)")}
        if case_columns and "origin" not in case_columns:
            conn.execute("ALTER TABLE cases ADD COLUMN origin TEXT NOT NULL "
                         "DEFAULT 'USER'")
            # One-time backfill: legacy cases seeded by eval/verify/debug runs
            # are marked SYSTEM. work_ref lives inside submission_json, so the
            # match is done in Python. Runs only when the column is first
            # created, so cases made after the migration are never relabeled.
            for row in conn.execute(
                    "SELECT id, submission_json FROM cases").fetchall():
                work_ref = _load(row["submission_json"]).get("work_ref", "")
                if _is_system_work_ref(work_ref):
                    conn.execute("UPDATE cases SET origin = 'SYSTEM' WHERE id = ?",
                                 (row["id"],))

    # --- connections and transactions --------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    # --- command idempotency ----------------------------------------------

    def _lookup_command(self, conn: sqlite3.Connection, operation: str,
                        command: Command, scope_key: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM audit_events WHERE operation = ? AND actor_id = ? "
            "AND scope_key = ? AND command_key = ?",
            (operation, command.actor_id, scope_key, command.key),
        ).fetchone()

    @staticmethod
    def _check_replay(row: sqlite3.Row, expected_fingerprint: str) -> None:
        if row["fingerprint"] != expected_fingerprint:
            raise DomainError(
                "IDEMPOTENCY_CONFLICT",
                "Khóa lệnh đã dùng cho một payload khác; dùng khóa mới cho nội dung mới.",
            )

    # --- cases -------------------------------------------------------------

    def create_case(self, submission: Submission, command: Command,
                    origin: str = "USER") -> CaseView:
        payload_fp = fingerprint(_CREATE_CASE, {
            "submission": submission.model_dump(mode="json"),
        })
        with self._write() as conn:
            row = self._lookup_command(conn, _CREATE_CASE, command, scope_key="")
            if row is not None:
                self._check_replay(row, payload_fp)
                view = self._case_view(conn, row["case_id"])
                return view.model_copy(update={"idempotent_replay": True})
            case_id = f"C-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            stage: CaseStage = "CHECKING"
            conn.execute(
                "INSERT INTO cases (id, case_version, input_revision, control_epoch, "
                "stop_active, stage, current_run_id, submission_json, origin, "
                "created_at, updated_at) "
                "VALUES (?, 1, 1, 1, 0, ?, NULL, ?, ?, ?, ?)",
                (case_id, stage, _dump(submission.model_dump(mode="json")),
                 origin, now, now),
            )
            conn.execute(
                "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
                "reason, actor_id, command_key, created_at) VALUES (?, ?, 1, ?, '', ?, ?, ?)",
                (f"R-{uuid.uuid4().hex[:12]}", case_id,
                 _dump(submission.model_dump(mode="json")), command.actor_id,
                 command.key, now),
            )
            self._record_command(conn, case_id, "", "CASE_CREATED", _CREATE_CASE,
                                 command, payload_fp, {"case_id": case_id}, now)
            return self._case_view(conn, case_id)

    def revise(self, case_id: str, submission: Submission, command: Command) -> CaseView:
        reason = str(command.body.get("reason") or "")
        payload_fp = fingerprint(_REVISE_SUBMISSION, {
            "submission": submission.model_dump(mode="json"),
            "reason": reason,
        })
        with self._write() as conn:
            row = self._lookup_command(conn, _REVISE_SUBMISSION, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                view = self._case_view(conn, case_id)
                return view.model_copy(update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_version(case, command)
            now = _iso(utcnow())
            new_version = case["case_version"] + 1
            new_revision = case["input_revision"] + 1
            conn.execute(
                "UPDATE cases SET case_version = ?, input_revision = ?, "
                "submission_json = ?, updated_at = ? WHERE id = ?",
                (new_version, new_revision,
                 _dump(submission.model_dump(mode="json")), now, case_id),
            )
            conn.execute(
                "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
                "reason, actor_id, command_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"R-{uuid.uuid4().hex[:12]}", case_id, new_revision,
                 _dump(submission.model_dump(mode="json")), reason,
                 command.actor_id, command.key, now),
            )
            self._record_command(conn, case_id, case_id, "SUBMISSION_REVISED",
                                 _REVISE_SUBMISSION, command, payload_fp,
                                 {"revision": new_revision, "case_version": new_version}, now)
            return self._case_view(conn, case_id)

    def get_case(self, case_id: str) -> CaseView:
        with self._read() as conn:
            return self._case_view(conn, case_id)

    def create_b3_case(self, build_submission, command: Command,
                       request_payload: dict[str, Any],
                       origin: str = "USER") -> CaseView:
        """Create a B3 v1 case: replay key checked BEFORE a new work id exists.

        ``request_payload`` is the semantic user request (actor + intake); it
        must stay stable across retries so the same key replays, while a new
        work id is generated exactly once and persisted with the case.
        """
        payload_fp = fingerprint(_CREATE_B3_CASE, request_payload)
        with self._write() as conn:
            row = self._lookup_command(conn, _CREATE_B3_CASE, command,
                                       scope_key="")
            if row is not None:
                self._check_replay(row, payload_fp)
                return self._case_view(conn, row["case_id"]).model_copy(
                    update={"idempotent_replay": True})
            work_ref = f"WORK-{uuid.uuid4().hex[:12]}"
            submission = build_submission(work_ref)
            case_id = f"C-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            stage: CaseStage = "CHECKING"
            conn.execute(
                "INSERT INTO cases (id, case_version, input_revision, control_epoch, "
                "stop_active, stage, current_run_id, submission_json, origin, "
                "created_at, updated_at) "
                "VALUES (?, 1, 1, 1, 0, ?, NULL, ?, ?, ?, ?)",
                (case_id, stage, _dump(submission.model_dump(mode="json")),
                 origin, now, now),
            )
            conn.execute(
                "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
                "reason, actor_id, command_key, created_at) VALUES (?, ?, 1, ?, '', ?, ?, ?)",
                (f"R-{uuid.uuid4().hex[:12]}", case_id,
                 _dump(submission.model_dump(mode="json")), command.actor_id,
                 command.key, now),
            )
            self._record_command(conn, case_id, "", "B3_CASE_CREATED",
                                 _CREATE_B3_CASE, command, payload_fp,
                                 {"case_id": case_id}, now)
            return self._case_view(conn, case_id)

    def list_cases(self) -> list[CaseSummary]:
        with self._read() as conn:
            rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
        summaries = []
        for row in rows:
            submission = _load(row["submission_json"])
            summaries.append(CaseSummary(
                id=row["id"], job=submission["job"],
                employee_ref=submission["employee_ref"],
                work_ref=submission["work_ref"], stage=row["stage"],
                case_version=row["case_version"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
                origin=row["origin"],
            ))
        return summaries

    def delete_case(self, case_id: str) -> None:
        """Remove a case and every child row plus its artifacts.

        Refuses while a run is active (QUEUED/RUNNING) so an in-flight worker
        cannot write into a half-deleted case. Irreversible by design: the case
        is gone from the database and its files are removed from disk.
        """
        with self._write() as conn:
            self._case_row(conn, case_id)  # CASE_NOT_FOUND when absent
            linked = self._find_linked_child(conn, case_id)
            if linked is not None:
                raise DomainError(
                    "LINKED_CASE_EXISTS",
                    f"Hồ sơ {case_id} có hồ sơ quyết toán liên kết "
                    f"({linked['id']}); xoá hồ sơ con trước để không mất "
                    f"dependency.",
                )
            active = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE case_id = ? AND status IN (?, ?)",
                (case_id, *_NONTERMINAL_STATUSES),
            ).fetchone()[0]
            if active:
                raise DomainError(
                    "CASE_BUSY",
                    f"Hồ sơ {case_id} đang có run xử lý; dừng/đợi xong rồi mới xoá.",
                )
            for table in ("sources", "runs", "interactions", "decisions",
                          "money_events", "case_revisions", "audit_events"):
                conn.execute(f"DELETE FROM {table} WHERE case_id = ?", (case_id,))
            conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        # Filesystem cleanup after the row is committed: best-effort, never
        # resurrects the case if a file is already missing.
        case_dir = self.artifact_root / case_id
        if case_dir.exists():
            shutil.rmtree(case_dir, ignore_errors=True)

    def snapshot(self, case_id: str) -> CaseSnapshot:
        with self._read() as conn:
            case = self._case_row(conn, case_id)
            return CaseSnapshot(
                case_id=case["id"], case_version=case["case_version"],
                input_revision=case["input_revision"],
                control_epoch=case["control_epoch"],
                stop_active=bool(case["stop_active"]), stage=case["stage"],
                submission=Submission.model_validate(_load(case["submission_json"])),
                sources=self._source_records(conn, case_id),
            )

    # --- sources -----------------------------------------------------------

    def add_source(self, case_id: str, upload: Upload, command: Command,
                   *, source_use: str = "PROPOSAL") -> SourceRecord:
        sha = hashlib.sha256(upload.content).hexdigest()
        operation = (_B3_ADD_ADVANCE_PROOF if source_use == "B3_ADVANCE_PROOF"
                     else _ADD_SOURCE)
        payload_fp = fingerprint(operation, {
            "filename": upload.filename,
            "sha256": sha,
            "size": len(upload.content),
            "provenance": upload.provenance,
            "source_use": source_use,
        })
        stored_path: Path | None = None
        with self._write() as conn:
            row = self._lookup_command(conn, operation, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                record = self._source_record(
                    conn.execute("SELECT * FROM sources WHERE id = ?",
                                 (_load(row["payload_json"])["source_id"],)).fetchone())
                return record.model_copy(update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            if len(upload.content) > MAX_SOURCE_BYTES:
                raise DomainError(
                    "FILE_TOO_LARGE",
                    f"File vượt giới hạn pilot {MAX_SOURCE_BYTES} bytes; không truncate để báo đủ.",
                )
            media_type = detect_media_type(upload.content, upload.filename)
            active = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE case_id = ? AND status = 'ACCEPTED'",
                (case_id,),
            ).fetchone()[0]
            if active >= MAX_ACTIVE_SOURCES_PER_CASE:
                raise DomainError(
                    "SOURCE_LIMIT_REACHED",
                    f"Hồ sơ đã đạt giới hạn pilot {MAX_ACTIVE_SOURCES_PER_CASE} nguồn active.",
                )
            self._check_version(case, command)
            source_id = f"S-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            # Reserved source-use metadata is backend-owned: a client-supplied
            # provenance key of the same name is dropped so it cannot fake a
            # proof role. Only the Service B5 branch sets B3_ADVANCE_PROOF.
            provenance = dict(upload.provenance)
            provenance.pop("source_use", None)
            if source_use == "B3_ADVANCE_PROOF":
                provenance["source_use"] = "B3_ADVANCE_PROOF"
            stored_path = put_artifact(self.artifact_root, case_id, "sources",
                                       source_id, upload.content)
            try:
                conn.execute(
                    "INSERT INTO sources (id, case_id, filename, media_type, sha256, "
                    "size_bytes, status, supersedes_source_id, uploader_actor_id, "
                    "received_at, provenance_json, original_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'ACCEPTED', NULL, ?, ?, ?, ?)",
                    (source_id, case_id, upload.filename, media_type, sha,
                     len(upload.content), command.actor_id, now,
                     _dump(provenance),
                     str(stored_path.relative_to(self.artifact_root))),
                )
                new_version = case["case_version"] + 1
                if source_use == "B3_ADVANCE_PROOF":
                    # Proof is fulfillment evidence, not proposal input: bump
                    # case_version only, never input_revision, so an approved
                    # proposal does not go stale just because a receipt arrived.
                    conn.execute(
                        "UPDATE cases SET case_version = ?, updated_at = ? "
                        "WHERE id = ?",
                        (new_version, now, case_id),
                    )
                    kind = "B3_ADVANCE_PROOF_ADDED"
                else:
                    conn.execute(
                        "UPDATE cases SET case_version = ?, input_revision = ?, "
                        "updated_at = ? WHERE id = ?",
                        (new_version, case["input_revision"] + 1, now, case_id),
                    )
                    kind = "SOURCE_ADDED"
                self._record_command(conn, case_id, case_id, kind,
                                     operation, command, payload_fp,
                                     {"source_id": source_id, "sha256": sha,
                                      "source_use": source_use,
                                      "case_version": new_version}, now)
            except BaseException:
                stored_path.unlink(missing_ok=True)
                raise
            record = self._source_record(
                conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            )
        return record

    def get_source(self, source_id: str) -> SourceRecord:
        with self._read() as conn:
            row = conn.execute("SELECT * FROM sources WHERE id = ?",
                               (source_id,)).fetchone()
            if row is None:
                raise DomainError("SOURCE_NOT_FOUND", f"Không tìm thấy nguồn {source_id}.")
            return self._source_record(row)

    # --- runs ---------------------------------------------------------------

    def create_run(self, run_input: RunInput, command: Command) -> RunView:
        """Accept a run: guards (Stop, active run, capacity, version) in txn."""
        payload_fp = fingerprint(_START_RUN, {
            "case_id": run_input.case_id,
            "input_revision": run_input.input_revision,
            "control_epoch": run_input.control_epoch,
            "snapshot_hash": run_input.snapshot_hash,
        })
        with self._write() as conn:
            row = self._lookup_command(conn, _START_RUN, command,
                                       scope_key=run_input.case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                replay_run_id = _load(row["payload_json"])["run_id"]
                return self._run_view(
                    conn.execute("SELECT * FROM runs WHERE id = ?",
                                 (replay_run_id,)).fetchone()
                ).model_copy(update={"idempotent_replay": True})
            case = self._case_row(conn, run_input.case_id)
            self._check_version(case, command)
            if case["stop_active"]:
                raise DomainError(
                    "STOP_ACTIVE",
                    "Hồ sơ đang Stop; không nhận run mới trước khi resume.",
                )
            current = conn.execute(
                "SELECT * FROM runs WHERE id = ?", (case["current_run_id"],)
            ).fetchone() if case["current_run_id"] else None
            if current is not None and current["status"] in _NONTERMINAL_STATUSES:
                raise DomainError(
                    "RUN_ACTIVE",
                    "Hồ sơ đang có run chưa kết thúc; chờ hoặc dùng lại kết quả.",
                )
            accepted = conn.execute(
                "SELECT COUNT(*) FROM runs WHERE status IN ('QUEUED', 'RUNNING')"
            ).fetchone()[0]
            if accepted >= MAX_ACCEPTED_RUNS:
                raise DomainError(
                    "TOO_MANY_RUNS",
                    f"Đã đạt giới hạn pilot {MAX_ACCEPTED_RUNS} run active/queued.",
                )
            run_id = f"R-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            mode = str(run_input.config.get("reader_mode", "UNKNOWN"))
            conn.execute(
                "INSERT INTO runs (id, case_id, input_revision, control_epoch, "
                "status, mode, snapshot_json, report_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, NULL, ?, ?)",
                (run_id, run_input.case_id, run_input.input_revision,
                 run_input.control_epoch, mode,
                 _dump(run_input.model_dump(mode="json")), now, now),
            )
            conn.execute(
                "UPDATE cases SET current_run_id = ?, case_version = ?, "
                "updated_at = ? WHERE id = ?",
                (run_id, case["case_version"] + 1, now, run_input.case_id),
            )
            self._record_command(conn, run_input.case_id, run_input.case_id,
                                 "RUN_STARTED", _START_RUN, command, payload_fp,
                                 {"run_id": run_id, "case_id": run_input.case_id},
                                 now)
            view = self._run_view(
                conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            )
        return view

    def mark_run(self, run_id: str, status: RunStatus,
                 detail: str | None = None) -> RunView:
        with self._write() as conn:
            run = self._run_row(conn, run_id)
            if run["status"] in _TERMINAL_STATUSES:
                raise DomainError(
                    "RUN_TERMINAL",
                    f"Run {run_id} đã kết thúc ({run['status']}); không ghi đè.",
                )
            now = _iso(utcnow())
            conn.execute(
                "UPDATE runs SET status = ?, detail = ?, updated_at = ? WHERE id = ?",
                (status, detail, now, run_id),
            )
            view = self._run_view(
                conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            )
        return view

    def publish(self, run_id: str, report: Report) -> RunView:
        """Publish a report only when controls still hold (Stop/revision/epoch).

        A run that is no longer RUNNING (e.g. marked INTERRUPTED by a process
        restart) keeps its recorded status; late worker output is discarded.
        """
        with self._write() as conn:
            run = self._run_row(conn, run_id)
            if run["status"] != "RUNNING":
                raise DomainError(
                    "RUN_TERMINAL",
                    f"Run {run_id} không còn RUNNING ({run['status']}); "
                    f"output đến muộn không được ghi đè.",
                )
            case = self._case_row(conn, run["case_id"])
            if (case["stop_active"] or case["control_epoch"] != run["control_epoch"]
                    or case["input_revision"] != run["input_revision"]):
                status: RunStatus = ("STOPPED" if case["stop_active"] else "SUPERSEDED")
                now = _iso(utcnow())
                conn.execute(
                    "UPDATE runs SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, run_id),
                )
                return self._run_view(
                    conn.execute("SELECT * FROM runs WHERE id = ?",
                                 (run_id,)).fetchone()
                )
            now = _iso(utcnow())
            conn.execute(
                "UPDATE runs SET status = 'SUCCEEDED', report_json = ?, "
                "updated_at = ? WHERE id = ?",
                (_dump(report.model_dump(mode="json")), now, run_id),
            )
            return self._run_view(
                conn.execute("SELECT * FROM runs WHERE id = ?",
                             (run_id,)).fetchone()
            )

    def get_run(self, run_id: str) -> RunView:
        with self._read() as conn:
            return self._run_view(self._run_row(conn, run_id))

    def update_run_stage(self, run_id: str, stage: str) -> None:
        with self._write() as conn:
            run = self._run_row(conn, run_id)
            if run["status"] in _TERMINAL_STATUSES:
                return  # run đã kết thúc; stage cũ giữ nguyên làm history
            conn.execute("UPDATE runs SET stage = ?, updated_at = ? WHERE id = ?",
                         (stage, _iso(utcnow()), run_id))

    def set_run_trace(self, run_id: str,
                      entries: list[dict[str, Any]]) -> None:
        with self._write() as conn:
            self._run_row(conn, run_id)
            conn.execute("UPDATE runs SET trace_json = ?, updated_at = ? "
                         "WHERE id = ?",
                         (_dump(entries), _iso(utcnow()), run_id))

    def get_report(self, run_id: str) -> Report | None:
        with self._read() as conn:
            row = self._run_row(conn, run_id)
            if not row["report_json"]:
                return None
            return Report.model_validate(_load(row["report_json"]))

    def get_run_input(self, run_id: str) -> RunInput:
        """The immutable snapshot a run evaluated (context/policy persisted)."""
        with self._read() as conn:
            row = self._run_row(conn, run_id)
            return RunInput.model_validate(_load(row["snapshot_json"]))

    def run_status(self, run_id: str) -> RunStatus:
        with self._read() as conn:
            return self._run_row(conn, run_id)["status"]

    @staticmethod
    def _run_row(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise DomainError("RUN_NOT_FOUND", f"Không tìm thấy run {run_id}.")
        return row

    @staticmethod
    def _run_view(row: sqlite3.Row) -> RunView:
        completion = None
        if row["report_json"]:
            completion = _load(row["report_json"]).get("completion")
        trace = []
        if row["trace_json"]:
            trace = [CallTrace.model_validate(entry)
                     for entry in _load(row["trace_json"])]
        return RunView(
            id=row["id"], case_id=row["case_id"], status=row["status"],
            mode=row["mode"], input_revision=row["input_revision"],
            control_epoch=row["control_epoch"], stage=row["stage"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            detail=row["detail"],
            completion=completion,
            trace=trace,
        )

    # --- questions and responses ---------------------------------------------

    def ensure_questions(self, case_id: str, issues, run_id: str) -> None:
        """Materialize unresolved report issues as owner-scoped questions."""
        with self._write() as conn:
            existing = {_load(row["payload_json"])["issue_id"] for row in
                        conn.execute("SELECT payload_json FROM interactions "
                                     "WHERE case_id = ? AND kind = 'QUESTION'",
                                     (case_id,))}
            now = _iso(utcnow())
            for issue in issues:
                if issue.issue_id in existing:
                    continue
                question_id = f"Q-{uuid.uuid4().hex[:12]}"
                payload = {
                    "id": question_id, "issue_id": issue.issue_id,
                    "owner": issue.owner, "message": issue.message,
                    "refs": issue.refs, "blocked": issue.blocked,
                    "status": "OPEN", "origin_run_id": run_id,
                    "answered_at": None, "resolved_run_id": None,
                }
                conn.execute(
                    "INSERT INTO interactions (id, case_id, kind, payload_json, "
                    "created_at) VALUES (?, ?, 'QUESTION', ?, ?)",
                    (question_id, case_id, _dump(payload), now),
                )

    def resolve_questions(self, case_id: str, unresolved_issue_ids: set[str],
                          run_id: str) -> None:
        """Mark questions RESOLVED when a re-check clears their issue."""
        with self._write() as conn:
            rows = conn.execute(
                "SELECT id, payload_json FROM interactions "
                "WHERE case_id = ? AND kind = 'QUESTION'", (case_id,)).fetchall()
            for row in rows:
                payload = _load(row["payload_json"])
                if payload["issue_id"] in unresolved_issue_ids or \
                        payload["status"] in {"RESOLVED", "SUPERSEDED"}:
                    continue
                payload["status"] = "RESOLVED"
                payload["resolved_run_id"] = run_id
                conn.execute(
                    "UPDATE interactions SET payload_json = ? WHERE id = ?",
                    (_dump(payload), row["id"]),
                )

    def get_question(self, question_id: str) -> QuestionView:
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM interactions WHERE id = ? AND kind = 'QUESTION'",
                (question_id,)).fetchone()
            if row is None:
                raise DomainError("QUESTION_NOT_FOUND",
                                  f"Không tìm thấy câu hỏi {question_id}.")
            return self._question_view(row)

    def list_questions(self, case_id: str) -> list[QuestionView]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM interactions WHERE case_id = ? AND kind = 'QUESTION' "
                "ORDER BY rowid", (case_id,)).fetchall()
        return [self._question_view(row) for row in rows]

    def record_response(self, question_id: str, payload: ResponsePayload,
                        command: Command, accepted: bool,
                        reason: str) -> ResponseView:
        """Record a response; accepted updates the question, else keeps OPEN."""
        semantic = {"question_id": question_id, "content": payload.content,
                    "source_ids": payload.source_ids}
        payload_fp = fingerprint(_RESPOND, semantic)
        with self._write() as conn:
            row = self._lookup_command(conn, _RESPOND, command,
                                       scope_key=question_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["response"]
                return ResponseView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            question = conn.execute(
                "SELECT * FROM interactions WHERE id = ? AND kind = 'QUESTION'",
                (question_id,)).fetchone()
            if question is None:
                raise DomainError("QUESTION_NOT_FOUND",
                                  f"Không tìm thấy câu hỏi {question_id}.")
            case = self._case_row(conn, question["case_id"])
            self._check_version(case, command)
            response_id = f"RS-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            response = {
                "id": response_id, "question_id": question_id,
                "case_id": question["case_id"], "actor_id": command.actor_id,
                "demo_role": command.demo_role, "content": payload.content,
                "source_ids": payload.source_ids, "accepted": accepted,
                "reason": reason, "created_at": now,
            }
            conn.execute(
                "INSERT INTO interactions (id, case_id, kind, payload_json, "
                "created_at) VALUES (?, ?, 'RESPONSE', ?, ?)",
                (response_id, question["case_id"], _dump(response), now),
            )
            if accepted:
                qpayload = _load(question["payload_json"])
                qpayload["status"] = "ANSWERED"
                qpayload["answered_at"] = now
                conn.execute(
                    "UPDATE interactions SET payload_json = ? WHERE id = ?",
                    (_dump(qpayload), question_id),
                )
            conn.execute(
                "UPDATE cases SET case_version = ?, input_revision = ?, "
                "updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, case["input_revision"] + 1, now,
                 question["case_id"]),
            )
            self._record_command(
                conn, question["case_id"], question_id, "QUESTION_ANSWERED",
                _RESPOND, command, payload_fp,
                {"response": response, "question_id": question_id}, now)
            return ResponseView.model_validate(response)

    @staticmethod
    def _question_view(row: sqlite3.Row) -> QuestionView:
        payload = _load(row["payload_json"])
        return QuestionView(
            id=payload["id"], case_id=row["case_id"],
            issue_id=payload["issue_id"], owner=payload["owner"],
            message=payload["message"], refs=payload["refs"],
            blocked=payload["blocked"], status=payload["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            origin_run_id=payload["origin_run_id"],
            answered_at=(datetime.fromisoformat(payload["answered_at"])
                          if payload["answered_at"] else None),
            resolved_run_id=payload["resolved_run_id"],
        )

    # --- decisions, reviews, money, control, handoff, closure (W05) -----------

    @staticmethod
    def _check_open(case: sqlite3.Row) -> None:
        if case["stage"] in _CLOSED_STAGES:
            raise DomainError(
                "CASE_CLOSED",
                f"Hồ sơ đã kết thúc ({case['stage']}); không nhận hành động mới.",
            )

    @staticmethod
    def _b3_v1_form(case: sqlite3.Row) -> dict[str, Any]:
        form = _load(case["submission_json"]).get("form")
        if isinstance(form, dict) and form.get("schema_version") == "b3-intake-v1":
            return form
        return {}

    def _check_b3_v1_action(self, case: sqlite3.Row, action: str) -> None:
        """B3 v1 là nhánh intake/report: financial/handoff/closure bị chặn ở
        transaction guard (backend code, không chỉ hide UI); review chỉ nhận
        khi bản khai đã confirm."""
        form = self._b3_v1_form(case)
        if not form:
            return
        if action == "REVIEW":
            if not form.get("confirmed"):
                raise DomainError(
                    "B3_REPORT_ONLY",
                    "Hồ sơ B3 v1 đang là draft chưa confirm; chưa nhận "
                    "accounting review.",
                )
            return
        raise DomainError(
            "B3_REPORT_ONLY",
            f"Hồ sơ B3 v1 (b3-intake-v1) chỉ tạo report intake; hành động "
            f"{action} chưa hỗ trợ ở nhánh này — duyệt ứng/chi/tiền là "
            f"lifecycle riêng.",
        )

    def _check_linked_b7_action(self, case: sqlite3.Row, action: str) -> None:
        """Linked B7 là report-only: generic decision/money/handoff/closure bị
        chặn ở transaction guard cho tới khi mở B8/B9 (backend code, không chỉ
        ẩn UI). Review vẫn được phép."""
        if self._b7_origin_link(case) is None:
            return
        if action == "REVIEW":
            return
        raise DomainError(
            "LINKED_B7_REPORT_ONLY",
            f"Hồ sơ quyết toán liên kết (b7-linked-intake-v1) mới hỗ trợ "
            f"report/questions/review; hành động {action} chưa mở (B8/B9 là "
            f"lát cắt sau).",
        )

    def _latest_decision_payload(self, conn: sqlite3.Connection,
                                  case_id: str) -> dict[str, Any] | None:
        """Latest B7 SETTLEMENT decision only.

        A B3_ADVANCE decision is a separate lifecycle: it must never become a
        B7 reimbursement obligation, so money/handoff/closure ignore it.
        """
        row = conn.execute(
            "SELECT payload_json FROM decisions WHERE case_id = ? "
            "ORDER BY rowid DESC", (case_id,)).fetchall()
        for candidate in row:
            payload = _load(candidate["payload_json"])
            if payload.get("kind") == "SETTLEMENT":
                return payload
        return None

    def record_decision(self, case_id: str, payload: DecisionPayload,
                        command: Command) -> DecisionView:
        """Record an authority-approved decision; closed/Stop/version gated."""
        payload_fp = fingerprint(_DECIDE, payload.model_dump(mode="json"))
        with self._write() as conn:
            row = self._lookup_command(conn, _DECIDE, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["decision"]
                return DecisionView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_b3_v1_action(case, "DECISION")
            self._check_linked_b7_action(case, "DECISION")
            self._check_open(case)
            if case["stop_active"]:
                raise DomainError(
                    "STOP_ACTIVE",
                    "Hồ sơ đang Stop; không ghi quyết định mới.",
                )
            self._check_version(case, command)
            run = self._run_row(conn, payload.basis_report_id)  # basis có thật
            if run["case_id"] != case_id:
                raise DomainError(
                    "BASIS_MISMATCH",
                    f"Run basis {payload.basis_report_id} thuộc hồ sơ khác "
                    f"({run['case_id']}); quyết định không được dựng trên "
                    f"report của hồ sơ khác.",
                )
            if run["status"] != "SUCCEEDED":
                raise DomainError(
                    "BASIS_MISMATCH",
                    f"Run basis {payload.basis_report_id} chưa SUCCEEDED "
                    f"({run['status']}); không duyệt trên report chưa sẵn sàng.",
                )
            if (case["current_run_id"] != payload.basis_report_id
                    or run["input_revision"] != case["input_revision"]):
                raise DomainError(
                    "BASIS_STALE",
                    "Report basis đã cũ (input đã đổi hoặc run khác là current); "
                    "re-check trước khi duyệt, không duyệt trên basis cũ.",
                )
            decision_id = f"D-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            decision = {
                "id": decision_id, "case_id": case_id, "kind": payload.kind,
                "amount_vnd": payload.amount_vnd, "direction": payload.direction,
                "reason": payload.reason, "basis_report_id": payload.basis_report_id,
                "basis_case_version": case["case_version"],
                "basis_input_revision": case["input_revision"],
                "exception_of": payload.exception_of,
                "conditions": payload.conditions, "actor_id": command.actor_id,
                "created_at": now,
            }
            conn.execute(
                "INSERT INTO decisions (id, case_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (decision_id, case_id, _dump(decision), now),
            )
            new_stage = case["stage"]
            if payload.direction != "REFUSE" and payload.amount_vnd is not None:
                new_stage = "AWAITING_MONEY"
            conn.execute(
                "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
                "WHERE id = ?",
                (new_stage, case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "DECISION_RECORDED",
                                 _DECIDE, command, payload_fp,
                                 {"decision": decision}, now)
            return DecisionView.model_validate(decision)

    def record_review(self, case_id: str, payload: ReviewPayload,
                      command: Command) -> ReviewView:
        """Record an accountant review: observation only, never approval."""
        payload_fp = fingerprint(_REVIEW, payload.model_dump(mode="json"))
        with self._write() as conn:
            row = self._lookup_command(conn, _REVIEW, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["review"]
                return ReviewView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_b3_v1_action(case, "REVIEW")
            self._check_linked_b7_action(case, "REVIEW")
            self._check_open(case)
            self._check_version(case, command)
            self._run_row(conn, payload.report_id)  # review phải chỉ vào run có thật
            review_id = f"RV-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            review = {
                "id": review_id, "case_id": case_id, "report_id": payload.report_id,
                "note": payload.note, "refs": payload.refs,
                "actor_id": command.actor_id, "created_at": now,
            }
            conn.execute(
                "INSERT INTO interactions (id, case_id, kind, payload_json, "
                "created_at) VALUES (?, ?, 'REVIEW', ?, ?)",
                (review_id, case_id, _dump(review), now),
            )
            conn.execute(
                "UPDATE cases SET case_version = ?, updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "REVIEW_RECORDED",
                                 _REVIEW, command, payload_fp,
                                 {"review": review}, now)
            return ReviewView.model_validate(review)

    # --- B3 present-and-approve (b3-intake-v1) -------------------------------

    def _b3_case_form(self, case: sqlite3.Row) -> dict[str, Any]:
        form = _load(case["submission_json"]).get("form")
        if not is_b3_v1(form):
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Trình duyệt/quyết định B3 chỉ áp dụng cho hồ sơ b3-intake-v1.",
            )
        return form

    def _b3_report_ready(self, conn: sqlite3.Connection, case_id: str,
                         basis_report_id: str) -> tuple[sqlite3.Row, Report]:
        """Resolve a current, COMPLETE, READY_FOR_ACCOUNTANT_REVIEW basis.

        Raises BASIS_MISMATCH/BASIS_STALE so a presentation/decision can never
        bind to another case's report, a stale revision or a not-ready report.
        """
        run = conn.execute("SELECT * FROM runs WHERE id = ?",
                           (basis_report_id,)).fetchone()
        if run is None or run["case_id"] != case_id:
            raise DomainError(
                "BASIS_MISMATCH",
                f"Report basis {basis_report_id} không thuộc hồ sơ {case_id}.",
            )
        case = self._case_row(conn, case_id)
        if run["status"] != "SUCCEEDED" or not run["report_json"]:
            raise DomainError(
                "BASIS_MISMATCH",
                f"Run basis {basis_report_id} chưa SUCCEEDED có report.",
            )
        if (case["current_run_id"] != basis_report_id
                or run["input_revision"] != case["input_revision"]
                or run["control_epoch"] != case["control_epoch"]):
            raise DomainError(
                "BASIS_STALE",
                "Report basis đã cũ (input/epoch đã đổi hoặc run khác là "
                "current); chạy và rà soát lại trước khi trình/quyết định.",
            )
        report = Report.model_validate(_load(run["report_json"]))
        proposal = report.b3
        if report.completion != "COMPLETE" or proposal is None \
                or proposal.readiness != "READY_FOR_ACCOUNTANT_REVIEW":
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Report basis chưa sẵn sàng cho kế toán (cần COMPLETE và "
                "READY_FOR_ACCOUNTANT_REVIEW).",
            )
        return run, report

    def _b3_has_open_question(self, conn: sqlite3.Connection,
                              case_id: str) -> bool:
        for row in conn.execute(
                "SELECT payload_json FROM interactions "
                "WHERE case_id = ? AND kind = 'QUESTION'", (case_id,)):
            if _load(row["payload_json"])["status"] in _OPEN_QUESTION_STATUSES:
                return True
        return False

    def _b3_active_run(self, conn: sqlite3.Connection, case_id: str) -> bool:
        return conn.execute(
            "SELECT COUNT(*) FROM runs WHERE case_id = ? AND status IN (?, ?)",
            (case_id, *_NONTERMINAL_STATUSES)).fetchone()[0] > 0

    def _b3_find_review(self, conn: sqlite3.Connection, case_id: str,
                        review_id: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM interactions WHERE id = ? AND case_id = ? "
            "AND kind = 'REVIEW'", (review_id, case_id)).fetchone()
        if row is None:
            raise DomainError(
                "BASIS_MISMATCH",
                f"Review {review_id} không thuộc hồ sơ {case_id}.",
            )
        return _load(row["payload_json"])

    def _b3_other_active_approval(self, conn: sqlite3.Connection,
                                  employee_ref: str, work_ref: str,
                                  exclude_case_id: str) -> str | None:
        """A current B3 APPROVE for the same employee/work in another case.

        The match is by explicit employee/work scope, never guessed from a
        duplicated purpose or filename; only records this store manages count.
        """
        for row in conn.execute(
                "SELECT payload_json FROM decisions ORDER BY rowid"):
            payload = _load(row["payload_json"])
            if payload.get("kind") != "B3_ADVANCE" \
                    or payload.get("outcome") != "APPROVE":
                continue
            if payload.get("employee_ref") != employee_ref \
                    or payload.get("work_ref") != work_ref:
                continue
            if payload.get("case_id") == exclude_case_id:
                continue
            return payload.get("id")
        return None

    def _b3_workflow(self, conn: sqlite3.Connection,
                     case_id: str) -> B3WorkflowView | None:
        """Derive the B3 workflow projection from records (not free text)."""
        case = self._case_row(conn, case_id)
        if not is_b3_v1(_load(case["submission_json"]).get("form")):
            return None
        pres_row = conn.execute(
            "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
            "ORDER BY rowid DESC LIMIT 1", (case_id, _B3_PRESENT)).fetchone()
        dec_row = conn.execute(
            "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
            "ORDER BY rowid DESC LIMIT 1", (case_id, _B3_DECIDE)).fetchone()
        presentation = None
        if pres_row is not None:
            presentation = B3PresentationView.model_validate(
                _load(pres_row["payload_json"])["presentation"])
        decision = None
        if dec_row is not None:
            decision = B3DecisionView.model_validate(
                _load(dec_row["payload_json"])["decision"])
        # A decision only governs the presentation it was made on. If a newer
        # presentation exists, the older decision is superseded history (except
        # REFUSE, which stays effective until a separate reopen action).
        decision_for_status = decision
        if decision is not None and decision.outcome != "REFUSE" \
                and (presentation is None
                     or decision.presentation_id != presentation.id):
            decision_for_status = None
        basis_current = False
        blocked: str | None = None
        if presentation is not None:
            run = conn.execute("SELECT * FROM runs WHERE id = ?",
                               (presentation.basis_report_id,)).fetchone()
            basis_current = bool(
                run is not None and run["status"] == "SUCCEEDED"
                and case["current_run_id"] == presentation.basis_report_id
                and run["input_revision"] == case["input_revision"]
                and run["control_epoch"] == case["control_epoch"])
            if not basis_current:
                blocked = ("Căn cứ đã đổi (nguồn/revision/epoch); cần chạy và "
                           "trình lại trước khi quyết định.")
        # A RETURN is addressed once a newer run has become current; the old
        # presentation is no longer pending and the case needs a fresh one.
        if decision_for_status is not None \
                and decision_for_status.outcome == "RETURN" \
                and case["current_run_id"] != decision_for_status.basis_report_id:
            decision_for_status = None
        status = "NOT_PRESENTED"
        if decision_for_status is not None:
            if decision_for_status.outcome == "APPROVE":
                status = "APPROVED" if basis_current else "NEEDS_RECHECK"
            elif decision_for_status.outcome == "RETURN":
                status = "RETURNED"
            else:
                status = "REFUSED"
        elif presentation is not None:
            status = "PENDING" if basis_current else "NEEDS_RECHECK"
        from invoice_referee.settlement.b3_funding import project_b3_funding

        events = self._b3_advance_events(conn, case_id)
        funding = None
        has_approval = (decision_for_status is not None
                        and decision_for_status.outcome == "APPROVE")
        if has_approval or events:
            funding = project_b3_funding(decision_for_status, events,
                                         bool(case["stop_active"]))
        return B3WorkflowView(
            status=status,
            presentation=presentation,
            decision=decision_for_status,
            basis_current=basis_current,
            blocked_reason=blocked,
            accountant_ref=(presentation.accountant_ref
                            if presentation else None),
            approver_ref=(presentation.approver_ref if presentation else None),
            funding=funding,
            advance_events=events,
        )

    def current_b3_decision(self, case_id: str) -> B3DecisionView | None:
        """This case's own APPROVE decision if it is still on a current basis.

        Used at run start to fold the case's verified approval into company
        history so re-checking the SAME request does not raise a false
        duplicate-approval issue. A foreign approval is never folded in.
        """
        with self._read() as conn:
            workflow = self._b3_workflow(conn, case_id)
        if workflow is None or workflow.decision is None:
            return None
        if workflow.decision.outcome != "APPROVE" or not workflow.basis_current:
            return None
        return workflow.decision

    def record_b3_presentation(self, case_id: str, payload: B3PresentPayload,
                               command: Command, context: B3CompanyContext,
                               policy: dict) -> B3PresentationView:
        """Accountant routes a confirmed B3 basis to the configured approver.

        Saves a new review (note+refs) or reuses a stored one, in ONE
        transaction with the presentation. Stage AWAITING_DECISION; the
        presentation stores a basis signature so a later source/context change
        makes it stale. No money/handoff/closure is created.
        """
        payload_fp = fingerprint(_B3_PRESENT, {
            "case_id": case_id, "payload": payload.model_dump(mode="json")})
        with self._write() as conn:
            row = self._lookup_command(conn, _B3_PRESENT, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["presentation"]
                return B3PresentationView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._b3_case_form(case)
            if case["stop_active"]:
                raise DomainError(
                    "STOP_ACTIVE",
                    "Hồ sơ đang Stop; không trình duyệt mới.")
            self._check_version(case, command)
            if not (context.activated):
                raise DomainError(
                    "CONFIG_NOT_ACTIVE",
                    "Company context B3 chưa active; không trình duyệt.")
            submission = Submission.model_validate(_load(case["submission_json"]))
            route = b3_route_for(context, submission.employee_ref)
            if (command.demo_role != "ACCOUNTANT" or route is None
                    or route.accountant_ref != command.actor_id):
                raise DomainError(
                    "BEYOND_AUTHORITY",
                    f"Vai {command.demo_role}/{command.actor_id} không phải kế "
                    f"toán được phân công cho {submission.employee_ref}; không "
                    f"trình duyệt.",
                )
            self._b3_report_ready(conn, case_id, payload.basis_report_id)
            if self._b3_has_open_question(conn, case_id):
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    "Còn câu hỏi/issue chưa được re-check xử lý; chưa trình "
                    "duyệt được.",
                )
            if self._b3_active_run(conn, case_id):
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    "Hồ sơ đang có run chưa kết thúc; chờ rồi mới trình duyệt.",
                )
            # An active approval for the same employee/work elsewhere blocks a
            # parallel first advance (dedup within managed records only).
            other = self._b3_other_active_approval(
                conn, submission.employee_ref, submission.work_ref, case_id)
            if other is not None:
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    f"Công việc {submission.work_ref} đã có quyết định ứng "
                    f"đang hiệu lực ({other}); không trình thêm đề nghị song song.",
                )
            # An existing decision (APPROVED/REFUSED) must not be bypassed by a
            # new presentation; RETURN/stale already cleared the old pending.
            current = self._b3_workflow(conn, case_id)
            if current is not None and current.decision is not None \
                    and current.decision.outcome in ("APPROVE", "REFUSE"):
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    "Đã có quyết định cho đề nghị này; điều chỉnh/mở lại là "
                    "hành động cần quyền riêng chưa hỗ trợ.",
                )
            sources = self._source_records(conn, case_id)
            report = self._b3_report_ready(conn, case_id,
                                           payload.basis_report_id)[1]
            basis_sig = b3_basis_signature(submission, sources, report, policy,
                                           context)
            ctx_sig = b3_context_signature(context)
            # Idempotent re-present with the same basis while still pending:
            # return the pending record, don't create a second parallel one.
            # After a RETURN/REFUSE decision, a new presentation must follow a
            # fresh run (new basis), never replay the returned one.
            if (current is not None and current.decision is None
                    and current.presentation is not None
                    and current.presentation.basis_signature == basis_sig):
                return current.presentation.model_copy(
                    update={"idempotent_replay": True})
            if (current is not None and current.decision is not None
                    and current.decision.outcome == "RETURN"
                    and current.presentation is not None
                    and current.presentation.basis_signature == basis_sig):
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    "Đề nghị đã bị yêu cầu bổ sung; nhân viên phải sửa/xác "
                    "nhận và chạy lại trước khi trình lại (basis chưa đổi).",
                )
            now = _iso(utcnow())
            if payload.review_id is not None:
                review = self._b3_find_review(conn, case_id, payload.review_id)
                if review["report_id"] != payload.basis_report_id \
                        or review["actor_id"] != command.actor_id:
                    raise DomainError(
                        "BASIS_MISMATCH",
                        "Review đã lưu không thuộc basis report hoặc không do "
                        "kế toán này tạo.",
                    )
                review_id = payload.review_id
            else:
                review = {
                    "id": f"RV-{uuid.uuid4().hex[:12]}", "case_id": case_id,
                    "report_id": payload.review.report_id,
                    "note": payload.review.note, "refs": payload.review.refs,
                    "actor_id": command.actor_id, "created_at": now,
                }
                review_id = review["id"]
                conn.execute(
                    "INSERT INTO interactions (id, case_id, kind, payload_json, "
                    "created_at) VALUES (?, ?, 'REVIEW', ?, ?)",
                    (review_id, case_id, _dump(review), now),
                )
            presentation = {
                "id": f"PR-{uuid.uuid4().hex[:12]}", "case_id": case_id,
                "basis_report_id": payload.basis_report_id,
                "review_id": review_id,
                "employee_ref": submission.employee_ref,
                "work_ref": submission.work_ref,
                "accountant_ref": route.accountant_ref,
                "approver_ref": route.approver_ref,
                "basis_input_revision": case["input_revision"],
                "basis_control_epoch": case["control_epoch"],
                "basis_signature": basis_sig,
                "context_signature": ctx_sig,
                "created_at": now,
            }
            conn.execute(
                "UPDATE cases SET stage = 'AWAITING_DECISION', case_version = ?, "
                "updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "B3_PRESENTED",
                                 _B3_PRESENT, command, payload_fp,
                                 {"presentation": presentation,
                                  "review": review}, now)
            return B3PresentationView.model_validate(presentation)

    def record_b3_decision(self, case_id: str, payload: B3DecisionPayload,
                           command: Command, context: B3CompanyContext,
                           policy: dict, grant_ref: str,
                           effective_at: datetime) -> B3DecisionView:
        """Record an approver's B3 outcome on a current pending presentation.

        Authority is resolved by the caller from the trusted context (never a
        client dict) and passed as ``grant_ref``. APPROVE → AWAITING_MONEY;
        RETURN → CHECKING; REFUSE → ADVANCE_REQUEST_REFUSED. No money event.
        """
        payload_fp = fingerprint(_B3_DECIDE, {
            "case_id": case_id, "payload": payload.model_dump(mode="json")})
        with self._write() as conn:
            row = self._lookup_command(conn, _B3_DECIDE, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["decision"]
                return B3DecisionView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._b3_case_form(case)
            if case["stop_active"]:
                raise DomainError(
                    "STOP_ACTIVE",
                    "Hồ sơ đang Stop; không ghi quyết định B3 mới.")
            self._check_version(case, command)
            current = self._b3_workflow(conn, case_id)
            if current is None or current.presentation is None:
                raise DomainError(
                    "B3_WORKFLOW_BLOCKED",
                    "Chưa có presentation để quyết định; kế toán phải trình trước.",
                )
            if current.decision is not None:
                raise DomainError(
                    "B3_DECISION_EXISTS",
                    "Đề nghị này đã có quyết định; điều chỉnh/thay thế chưa hỗ trợ.",
                )
            presentation = current.presentation
            if presentation.id != payload.presentation_id:
                raise DomainError(
                    "BASIS_MISMATCH",
                    "presentation_id không khớp presentation đang chờ.",
                )
            if not current.basis_current:
                raise DomainError(
                    "BASIS_STALE",
                    "Căn cứ đã đổi kể từ khi trình; cần chạy và trình lại.",
                )
            submission = Submission.model_validate(_load(case["submission_json"]))
            route = b3_route_for(context, submission.employee_ref)
            if route is None or route.approver_ref != command.actor_id:
                raise DomainError(
                    "BEYOND_AUTHORITY",
                    f"Vai {command.actor_id} không phải người duyệt được phân "
                    f"công cho {submission.employee_ref}.",
                )
            if payload.outcome == "APPROVE":
                proposal = self._b3_report_ready(
                    conn, case_id, presentation.basis_report_id)[1].b3
                forecast_total = proposal.forecast_total_vnd
                forecast_employee = proposal.forecast_employee_vnd
                requested = proposal.intake.request_amount_vnd
                if forecast_total is not None and payload.budget_vnd is not None \
                        and payload.budget_vnd < forecast_total:
                    raise DomainError(
                        "B3_WORKFLOW_BLOCKED",
                        "Budget duyệt thấp hơn tổng forecast hiện tại; RETURN để "
                        "sửa và kiểm lại.",
                    )
                if requested is not None and payload.advance_vnd is not None \
                        and payload.advance_vnd > requested:
                    raise DomainError(
                        "B3_WORKFLOW_BLOCKED",
                        "Số ứng duyệt cao hơn số xin; RETURN để sửa và kiểm lại.",
                    )
                if forecast_employee is not None \
                        and payload.advance_vnd is not None \
                        and payload.advance_vnd > forecast_employee:
                    raise DomainError(
                        "B3_WORKFLOW_BLOCKED",
                        "Số ứng duyệt cao hơn phần employee forecast; RETURN để "
                        "sửa và kiểm lại.",
                    )
            now = _iso(utcnow())
            decision = {
                "id": f"BD-{uuid.uuid4().hex[:12]}", "case_id": case_id,
                "kind": "B3_ADVANCE", "presentation_id": presentation.id,
                "outcome": payload.outcome, "reason": payload.reason,
                "work_allowed": payload.work_allowed,
                "budget_vnd": payload.budget_vnd,
                "advance_vnd": payload.advance_vnd,
                "basis_report_id": presentation.basis_report_id,
                "basis_review_id": presentation.review_id,
                "basis_input_revision": presentation.basis_input_revision,
                "basis_control_epoch": presentation.basis_control_epoch,
                "basis_signature": presentation.basis_signature,
                "context_signature": presentation.context_signature,
                "employee_ref": submission.employee_ref,
                "work_ref": submission.work_ref, "actor_id": command.actor_id,
                "grant_ref": grant_ref, "effective_at": _iso(effective_at),
                "created_at": now,
            }
            conn.execute(
                "INSERT INTO decisions (id, case_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (decision["id"], case_id, _dump(decision), now),
            )
            if payload.outcome == "APPROVE":
                new_stage: CaseStage = "AWAITING_MONEY"
            elif payload.outcome == "RETURN":
                new_stage = "CHECKING"
            else:
                new_stage = "ADVANCE_REQUEST_REFUSED"
            conn.execute(
                "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
                "WHERE id = ?",
                (new_stage, case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "B3_DECISION_RECORDED",
                                 _B3_DECIDE, command, payload_fp,
                                 {"decision": decision}, now)
            return B3DecisionView.model_validate(decision)

    # --- B5: advance receipts (actual money to employee) ---------------------

    def _b3_advance_events(self, conn: sqlite3.Connection,
                           case_id: str) -> list[B3AdvanceEventView]:
        """All persisted B3 advance events for a case, oldest first."""
        events: list[B3AdvanceEventView] = []
        for row in conn.execute(
                "SELECT payload_json FROM money_events WHERE case_id = ? "
                "ORDER BY rowid", (case_id,)):
            payload = _load(row["payload_json"])
            if payload.get("kind") != "ADVANCE_TO_EMPLOYEE":
                continue
            events.append(B3AdvanceEventView.model_validate(payload))
        return events

    def _b3_advance_proof_source_ids(self, conn: sqlite3.Connection,
                                     case_id: str) -> set[str]:
        """Source ids the backend recorded as B5 advance proof (audit-backed).

        Trusted by the audit operation's recorded ``source_id`` — not by a
        client-supplied provenance string or filename.
        """
        ids: set[str] = set()
        for row in conn.execute(
                "SELECT payload_json FROM audit_events WHERE case_id = ? "
                "AND operation = ?", (case_id, _B3_ADD_ADVANCE_PROOF)):
            source_id = _load(row["payload_json"]).get("source_id")
            if source_id:
                ids.add(source_id)
        return ids

    def _b3_proof_source_ids(self, case_id: str) -> set[str]:
        with self._read() as conn:
            return self._b3_advance_proof_source_ids(conn, case_id)

    def confirmed_b3_advances(self, case_id: str) -> list[B3AdvanceEventView]:
        """Confirmed RECEIVED advance events for a case (for history merge)."""
        with self._read() as conn:
            events = self._b3_advance_events(conn, case_id)
        return [e for e in events if e.classification == "CONFIRMED_RECEIPT"
                and e.reported_status == "RECEIVED" and e.gross_vnd is not None]

    def record_b3_advance(self, case_id: str, payload: B3AdvanceEventPayload,
                          command: Command,
                          context: B3CompanyContext) -> B3AdvanceEventView:
        """Record an actual advance money event with human-source evidence.

        Allowed under Stop/stale (the fact already happened) but never opens a
        new payment right or advances the stage past Stop. Records are immutable
        and append-only; a pending/nonfinal record is superseded by a new one,
        never overwritten. The raw gross is kept, never clipped to approval.
        """
        from invoice_referee.settlement.b3_funding import (
            derive_classification, project_b3_funding,
        )

        payload_fp = fingerprint(_B3_RECORD_ADVANCE, {
            "case_id": case_id, "payload": payload.model_dump(mode="json")})
        with self._write() as conn:
            row = self._lookup_command(conn, _B3_RECORD_ADVANCE, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["event"]
                return B3AdvanceEventView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._b3_case_form(case)
            self._check_version(case, command)
            submission = Submission.model_validate(_load(case["submission_json"]))
            route = b3_route_for(context, submission.employee_ref)
            if (command.demo_role != "ACCOUNTANT" or route is None
                    or route.accountant_ref != command.actor_id):
                raise DomainError(
                    "BEYOND_AUTHORITY",
                    f"Vai {command.demo_role}/{command.actor_id} không phải kế "
                    f"toán được phân công cho {submission.employee_ref}; không "
                    f"ghi sự kiện ứng.",
                )
            # Evidence sources must resolve to this case's retained sources.
            case_source_ids = {s.id for s in self._source_records(conn, case_id)}
            for field in payload.evidence:
                if field.source_id not in case_source_ids:
                    raise DomainError(
                        "BASIS_MISMATCH",
                        f"Nguồn căn cứ {field.source_id} không thuộc hồ sơ "
                        f"{case_id}.",
                    )
            # A decision_id, when given, must belong to this case/employee/work.
            decision = None
            if payload.decision_id is not None:
                dec_row = conn.execute(
                    "SELECT payload_json FROM decisions WHERE id = ? AND case_id = ?",
                    (payload.decision_id, case_id)).fetchone()
                if dec_row is not None:
                    candidate = _load(dec_row["payload_json"])
                    if candidate.get("kind") == "B3_ADVANCE" \
                            and candidate.get("employee_ref") == submission.employee_ref \
                            and candidate.get("work_ref") == submission.work_ref:
                        decision = B3DecisionView.model_validate(candidate)
            incidents: list[B3FundingIncident] = []
            if payload.decision_id is not None and decision is None:
                incidents.append(B3FundingIncident(
                    kind="UNAUTHORIZED_OR_UNALLOCATED", event_ids=[], refs=[],
                    amount_vnd=payload.gross_vnd,
                    reason="decision_id không thuộc hồ sơ/người/công việc này."))
            # Wrong recipient: money reached someone other than the employee.
            if (payload.reported_status == "RECEIVED"
                    and payload.payee_ref is not None
                    and payload.payee_ref != submission.employee_ref):
                incidents.append(B3FundingIncident(
                    kind="WRONG_RECIPIENT", event_ids=[], refs=[],
                    amount_vnd=payload.gross_vnd,
                    reason=(f"Người nhận {payload.payee_ref} không phải nhân viên "
                            f"{submission.employee_ref}; giữ raw, không tính "
                            f"thực nhận cho nhân viên.")))
            classification = derive_classification(
                payload, submission.employee_ref, incidents)
            existing = self._b3_advance_events(conn, case_id)
            # Same economic event (namespace+ref) already confirmed RECEIVED:
            # a new RECEIVED for the same identity is a conflicting outcome, not
            # a second payment.
            if (payload.reported_status == "RECEIVED"
                    and payload.event_namespace is not None
                    and payload.event_ref is not None):
                for prior in existing:
                    if (prior.event_namespace == payload.event_namespace
                            and prior.event_ref == payload.event_ref
                            and prior.reported_status == "RECEIVED"
                            and prior.classification == "CONFIRMED_RECEIPT"):
                        incidents.append(B3FundingIncident(
                            kind="CONFLICTING_OUTCOME",
                            event_ids=[prior.id], refs=[],
                            amount_vnd=payload.gross_vnd,
                            reason=("Cùng giao dịch đã có kết quả RECEIVED xác "
                                    "nhận; giữ cả hai, cần kế toán xử lý.")))
                        classification = "CONFLICT"
            now = _iso(utcnow())
            event = {
                "id": f"AE-{uuid.uuid4().hex[:12]}", "case_id": case_id,
                "kind": "ADVANCE_TO_EMPLOYEE",
                "decision_id": payload.decision_id,
                "event_namespace": payload.event_namespace,
                "event_ref": payload.event_ref, "method": payload.method,
                "gross_vnd": payload.gross_vnd, "payer_side": payload.payer_side,
                "payee_ref": payload.payee_ref,
                "event_at": _iso(payload.event_at) if payload.event_at else None,
                "reported_status": payload.reported_status,
                "evidence": [e.model_dump(mode="json") for e in payload.evidence],
                "allocation_note": payload.allocation_note,
                "supersedes_event_id": payload.supersedes_event_id,
                "employee_ref": submission.employee_ref,
                "work_ref": submission.work_ref,
                "classification": classification,
                "actor_id": command.actor_id, "created_at": now,
                "after_money_cutoff": bool(
                    payload.event_at is not None
                    and payload.event_at > submission.money_as_of),
                "incidents": [i.model_dump(mode="json") for i in incidents],
            }
            conn.execute(
                "INSERT INTO money_events (id, case_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (event["id"], case_id, _dump(event), now),
            )
            # Stage projection: only advance when the funding state is clean.
            view_events = existing + [B3AdvanceEventView.model_validate(event)]
            summary = project_b3_funding(decision, view_events,
                                         bool(case["stop_active"]))
            new_stage: CaseStage = case["stage"]
            if decision is not None and not case["stop_active"]:
                if summary.status == "FULFILLED":
                    new_stage = "AWAITING_WORK_SETTLEMENT"
                elif summary.status == "NEEDS_RESOLUTION":
                    new_stage = "RESOLVING_OBLIGATIONS"
                elif summary.status in ("PARTIAL", "PENDING", "UNCONFIRMED",
                                        "NOT_RECORDED"):
                    new_stage = "AWAITING_MONEY"
            conn.execute(
                "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
                "WHERE id = ?",
                (new_stage, case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id,
                                 "B3_ADVANCE_EVENT_RECORDED", _B3_RECORD_ADVANCE,
                                 command, payload_fp, {"event": event}, now)
            return B3AdvanceEventView.model_validate(event)

    # --- B6→B7 linked settlement (b7-linked-intake-v1) -----------------------

    @staticmethod
    def _b7_origin_link(case: sqlite3.Row) -> dict[str, Any] | None:
        form = _load(case["submission_json"]).get("form") or {}
        link = form.get("origin_link")
        return link if isinstance(link, dict) else None

    def _find_linked_child(self, conn: sqlite3.Connection,
                           parent_id: str) -> sqlite3.Row | None:
        """The active linked B7 child for a parent, if one exists."""
        for row in conn.execute("SELECT * FROM cases ORDER BY rowid"):
            if row["id"] == parent_id:
                continue
            submission = _load(row["submission_json"])
            if submission.get("job") != "B7":
                continue
            link = (submission.get("form") or {}).get("origin_link")
            if isinstance(link, dict) and link.get("origin_case_id") == parent_id:
                return row
        return None

    def prepare_linked_b7(self, parent_id: str, command: Command,
                          origin: str = "USER") -> CaseView:
        """Create (or reuse) the single active linked B7 child for a B3 parent.

        Server-owned link/employee/work; the parent is never mutated. A draft
        child is created with ``confirmed=False``; no run is started here.
        """
        payload_fp = fingerprint(_PREPARE_LINKED_B7, {"parent_id": parent_id})
        with self._write() as conn:
            row = self._lookup_command(conn, _PREPARE_LINKED_B7, command,
                                       scope_key=parent_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                return self._case_view(
                    conn, _load(row["payload_json"])["child_id"]).model_copy(
                    update={"idempotent_replay": True})
            parent = self._case_row(conn, parent_id)
            self._check_version(parent, command)
            if _load(parent["submission_json"]).get("job") != "B3":
                raise DomainError(
                    "LINKED_B7_INVALID",
                    "Chỉ hồ sơ B3 mới mở được hồ sơ quyết toán liên kết.",
                )
            existing = self._find_linked_child(conn, parent_id)
            if existing is not None:
                return self._case_view(conn, existing["id"])
            now_dt = utcnow()
            now = _iso(now_dt)
            child_id = f"C-{uuid.uuid4().hex[:12]}"
            link = {
                "origin_case_id": parent_id,
                "employee_ref": _load(parent["submission_json"])["employee_ref"],
                "work_ref": _load(parent["submission_json"])["work_ref"],
                "created_at": now,
            }
            form = {"schema_version": "b7-linked-intake-v1", "confirmed": False,
                    "expense_rows": [], "note": None, "origin_link": link}
            submission = Submission(
                employee_ref=link["employee_ref"], work_ref=link["work_ref"],
                job="B7", money_as_of=now_dt, knowledge_cutoff=now_dt, form=form)
            stage: CaseStage = "CHECKING"
            conn.execute(
                "INSERT INTO cases (id, case_version, input_revision, control_epoch, "
                "stop_active, stage, current_run_id, submission_json, origin, "
                "created_at, updated_at) "
                "VALUES (?, 1, 1, 1, 0, ?, NULL, ?, ?, ?, ?)",
                (child_id, stage, _dump(submission.model_dump(mode="json")),
                 origin, now, now),
            )
            conn.execute(
                "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
                "reason, actor_id, command_key, created_at) VALUES (?, ?, 1, ?, '', ?, ?, ?)",
                (f"R-{uuid.uuid4().hex[:12]}", child_id,
                 _dump(submission.model_dump(mode="json")), command.actor_id,
                 command.key, now),
            )
            self._record_command(conn, child_id, parent_id, "LINKED_B7_PREPARED",
                                 _PREPARE_LINKED_B7, command, payload_fp,
                                 {"child_id": child_id, "parent_id": parent_id},
                                 now)
            return self._case_view(conn, child_id)

    def revise_linked_b7(self, case_id: str, intake: B7LinkedIntake,
                         command: Command) -> CaseView:
        """Update a linked child's declarations; link/employee/work immutable."""
        payload_fp = fingerprint(_REVISE_LINKED_B7, {
            "intake": intake.model_dump(mode="json")})
        with self._write() as conn:
            row = self._lookup_command(conn, _REVISE_LINKED_B7, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                return self._case_view(conn, case_id).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._check_version(case, command)
            submission = Submission.model_validate(_load(case["submission_json"]))
            link = self._b7_origin_link(case)
            if link is None:
                raise DomainError(
                    "LINKED_B7_INVALID",
                    "Hồ sơ này không phải hồ sơ quyết toán liên kết.",
                )
            form = intake.model_dump(mode="json")
            form["origin_link"] = link  # server-owned, cannot be client-set
            merged = submission.model_copy(update={"form": form})
            now = _iso(utcnow())
            conn.execute(
                "UPDATE cases SET case_version = ?, input_revision = ?, "
                "submission_json = ?, updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, case["input_revision"] + 1,
                 _dump(merged.model_dump(mode="json")), now, case_id),
            )
            self._record_command(conn, case_id, case_id, "LINKED_B7_REVISED",
                                 _REVISE_LINKED_B7, command, payload_fp,
                                 {"confirmed": intake.confirmed}, now)
            return self._case_view(conn, case_id)

    def _store_linked_context_source(self, conn: sqlite3.Connection,
                                     case_id: str, snapshot,
                                     command: Command) -> str:
        """Persist the linked context snapshot as a backend-owned system source.

        Source-use ``LINKED_B7_CONTEXT`` is recorded in the audit operation, so
        the snapshot is trusted by audit — never by a client-supplied string.
        """
        source_id = f"S-{uuid.uuid4().hex[:12]}"
        now = _iso(utcnow())
        content = _dump(snapshot.model_dump(mode="json")).encode("utf-8")
        stored_path = put_artifact(self.artifact_root, case_id, "sources",
                                   source_id, content)
        sha = hashlib.sha256(content).hexdigest()
        conn.execute(
            "INSERT INTO sources (id, case_id, filename, media_type, sha256, "
            "size_bytes, status, supersedes_source_id, uploader_actor_id, "
            "received_at, provenance_json, original_path) "
            "VALUES (?, ?, 'linked-context.json', 'application/json', ?, ?, "
            "'ACCEPTED', NULL, ?, ?, ?, ?)",
            (source_id, case_id, sha, len(content), command.actor_id, now,
             _dump({"source_use": _LINKED_B7_CONTEXT_USE}),
             str(stored_path.relative_to(self.artifact_root))),
        )
        return source_id

    def record_b7_company_packet(self, case_id: str, payload: dict,
                                 command: Command, policy: dict,
                                 authority_version: str | None) -> CaseView:
        """Accountant records a source-backed company packet; build context.

        Persists the snapshot as a system source, bumps input_revision (a
        material context change), and keeps old run/source history.
        """
        from invoice_referee.settlement.b7_linked import (
            build_linked_context, load_b7_company_packet,
        )

        packet = load_b7_company_packet(payload)
        payload_fp = fingerprint(_B7_CONTEXT_REFRESH, {
            "case_id": case_id, "packet": packet.model_dump(mode="json")})
        with self._write() as conn:
            row = self._lookup_command(conn, _B7_CONTEXT_REFRESH, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                return self._case_view(conn, case_id).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._check_version(case, command)
            link = self._b7_origin_link(case)
            if link is None:
                raise DomainError(
                    "LINKED_B7_INVALID",
                    "Company packet chỉ áp dụng cho hồ sơ quyết toán liên kết.",
                )
            submission = Submission.model_validate(_load(case["submission_json"]))
            parent_id = link["origin_case_id"]
            decision = None
            parent_wf = self._b3_workflow(conn, parent_id)
            if parent_wf is not None and parent_wf.decision is not None:
                decision = parent_wf.decision
            managed = self._b3_advance_events(conn, parent_id)
            snapshot = build_linked_context(
                origin_case_id=parent_id,
                parent_fingerprint=self._linked_parent_fingerprint(conn, parent_id),
                decision=decision, managed_events=managed, packet=packet,
                policy=policy, authority_version=authority_version,
                money_as_of=submission.money_as_of,
                knowledge_cutoff=submission.knowledge_cutoff)
            # Identical snapshot (same packet, same parent dependency): reuse the
            # existing source and do NOT bump input_revision.
            snapshot_fp = fingerprint("LINKED_CONTEXT",
                                      snapshot.model_dump(mode="json"))
            prior_ids = self._linked_context_source_ids(conn, case_id)
            if prior_ids:
                prior = self._source_record(conn.execute(
                    "SELECT * FROM sources WHERE id = ?",
                    (prior_ids[-1],)).fetchone())
                prior_data = (self.artifact_root / prior.original_path
                              ).read_text(encoding="utf-8")
                if fingerprint("LINKED_CONTEXT", json.loads(prior_data)) \
                        == snapshot_fp:
                    return self._case_view(conn, case_id).model_copy(
                        update={"idempotent_replay": True})
            source_id = self._store_linked_context_source(
                conn, case_id, snapshot, command)
            now = _iso(utcnow())
            conn.execute(
                "UPDATE cases SET case_version = ?, input_revision = ?, "
                "updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, case["input_revision"] + 1, now,
                 case_id),
            )
            self._record_command(conn, case_id, case_id, "B7_CONTEXT_REFRESHED",
                                 _B7_CONTEXT_REFRESH, command, payload_fp,
                                 {"source_id": source_id,
                                  "context_version": snapshot.context_version},
                                 now)
            return self._case_view(conn, case_id)

    def _linked_parent_fingerprint(self, conn: sqlite3.Connection,
                                   parent_id: str) -> str:
        """Fingerprint of parent case/decision/managed events (dependency)."""
        case = self._case_row(conn, parent_id)
        decision = None
        wf = self._b3_workflow(conn, parent_id)
        if wf is not None and wf.decision is not None:
            decision = wf.decision.model_dump(mode="json")
        events = [e.model_dump(mode="json")
                  for e in self._b3_advance_events(conn, parent_id)]
        return fingerprint("LINKED_PARENT", {
            "case_version": case["case_version"],
            "input_revision": case["input_revision"],
            "stop_active": bool(case["stop_active"]),
            "control_epoch": case["control_epoch"],
            "decision": decision, "events": events})

    def linked_b7_dependency_fingerprint(self, child_id: str) -> str:
        """Current dependency fingerprint of a linked child's parent chain."""
        with self._read() as conn:
            case = self._case_row(conn, child_id)
            link = self._b7_origin_link(case)
            if link is None:
                raise DomainError(
                    "LINKED_B7_INVALID",
                    "Hồ sơ này không phải hồ sơ quyết toán liên kết.",
                )
            return self._linked_parent_fingerprint(
                conn, link["origin_case_id"])

    def get_linked_b7_context(self, case_id: str) -> "LinkedB7ContextSnapshot":
        """Latest persisted linked context snapshot for a child (or raise)."""
        from invoice_referee.settlement.models import LinkedB7ContextSnapshot

        with self._read() as conn:
            source_ids = self._linked_context_source_ids(conn, case_id)
            if not source_ids:
                raise DomainError(
                    "BASIS_MISMATCH",
                    "Hồ sơ chưa có company context snapshot.",
                )
            row = conn.execute("SELECT * FROM sources WHERE id = ?",
                               (source_ids[-1],)).fetchone()
            record = self._source_record(row)
            data = json.loads((self.artifact_root / record.original_path)
                              .read_text(encoding="utf-8"))
        return LinkedB7ContextSnapshot.model_validate(data)

    def _linked_context_source_ids(self, conn: sqlite3.Connection,
                                   case_id: str) -> list[str]:
        ids: list[str] = []
        for row in conn.execute(
                "SELECT payload_json FROM audit_events WHERE case_id = ? "
                "AND operation = ? ORDER BY rowid", (case_id, _B7_CONTEXT_REFRESH)):
            source_id = _load(row["payload_json"]).get("source_id")
            if source_id:
                ids.append(source_id)
        return ids

    def refresh_linked_b7_context(self, case_id: str, command: Command,
                                  policy: dict,
                                  authority_version: str | None) -> CaseView:
        """Rebuild the context from the stored company packet; reuse if same.

        The exact packet is reused from the last snapshot, so a refresh
        re-evaluates against current parent dependencies without fabricating
        coverage.
        """
        snapshot = self.get_linked_b7_context(case_id)
        if snapshot.company_packet is None:
            raise DomainError(
                "BASIS_MISMATCH",
                "Chưa có company packet để làm mới context.",
            )
        return self.record_b7_company_packet(
            case_id, snapshot.company_packet.model_dump(mode="json"), command,
            policy, authority_version)

    def record_money(self, case_id: str, payload: MoneyEventPayload,
                     after_cutoff: bool, command: Command) -> MoneyEventView:
        """Record an actual money event; allowed under Stop, deduped by event_ref."""
        payload_fp = fingerprint(_RECORD_MONEY, payload.model_dump(mode="json"))
        with self._write() as conn:
            row = self._lookup_command(conn, _RECORD_MONEY, command,
                                       scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["money_event"]
                return MoneyEventView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            self._check_b3_v1_action(case, "MONEY_EVENT")
            self._check_linked_b7_action(case, "MONEY_EVENT")
            self._check_open(case)
            for event_row in conn.execute(
                    "SELECT payload_json FROM money_events WHERE case_id = ?",
                    (case_id,)):
                if _load(event_row["payload_json"])["event_ref"] == payload.event_ref:
                    raise DomainError(
                        "DUPLICATE_EVENT_REF",
                        f"event_ref {payload.event_ref} đã được ghi cho hồ sơ; "
                        f"sự kiện tiền không được ghi hai lần.",
                    )
            self._check_version(case, command)
            event_id = f"M-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            event = {
                "id": event_id, "case_id": case_id,
                "event_ref": payload.event_ref, "kind": payload.kind,
                "gross_vnd": payload.gross_vnd,
                "decision_id": payload.decision_id,
                "payee_ref": payload.payee_ref, "event_at": _iso(payload.event_at),
                "reported_status": payload.reported_status, "refs": payload.refs,
                "after_cutoff": after_cutoff, "created_at": now,
            }
            conn.execute(
                "INSERT INTO money_events (id, case_id, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (event_id, case_id, _dump(event), now),
            )
            conn.execute(
                "UPDATE cases SET case_version = ?, updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "MONEY_EVENT_RECORDED",
                                 _RECORD_MONEY, command, payload_fp,
                                 {"money_event": event}, now)
            return MoneyEventView.model_validate(event)

    def control(self, case_id: str, action: str, command: Command) -> dict[str, Any]:
        """STOP acknowledges and freezes new actions; RESUME opens a new epoch."""
        if action not in ("STOP", "RESUME"):
            raise DomainError(
                "CONTROL_INVALID",
                f"Hành động control phải là STOP hoặc RESUME, nhận {action!r}.",
            )
        reason = str(command.body.get("reason") or "")
        payload_fp = fingerprint(_CONTROL, {"action": action, "reason": reason})
        with self._write() as conn:
            row = self._lookup_command(conn, _CONTROL, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["control"]
                return dict(stored, idempotent_replay=True)
            case = self._case_row(conn, case_id)
            self._check_open(case)
            self._check_version(case, command)
            if action == "STOP" and case["stop_active"]:
                raise DomainError(
                    "CONTROL_INVALID",
                    "Hồ sơ đang Stop; không Stop lần nữa.",
                )
            if action == "RESUME" and not case["stop_active"]:
                raise DomainError(
                    "CONTROL_INVALID",
                    "Hồ sơ không đang Stop; không có gì để resume.",
                )
            now = _iso(utcnow())
            new_version = case["case_version"] + 1
            if action == "STOP":
                stop_active, epoch = 1, case["control_epoch"]
                kind = "CONTROL_STOPPED"
            else:
                stop_active, epoch = 0, case["control_epoch"] + 1
                kind = "CONTROL_RESUMED"
            conn.execute(
                "UPDATE cases SET stop_active = ?, control_epoch = ?, "
                "case_version = ?, updated_at = ? WHERE id = ?",
                (stop_active, epoch, new_version, now, case_id),
            )
            control = {
                "case_id": case_id, "action": action, "reason": reason,
                "stop_active": bool(stop_active), "control_epoch": epoch,
                "case_version": new_version, "actor_id": command.actor_id,
                "created_at": now,
            }
            self._record_command(conn, case_id, case_id, kind, _CONTROL,
                                 command, payload_fp, {"control": control}, now)
            return dict(control)

    def handoff(self, case_id: str, decision_id: str,
                command: Command) -> dict[str, Any]:
        """Create a stage-A handoff reference for an approved, fresh-basis decision."""
        payload_fp = fingerprint(_HANDOFF, {"decision_id": decision_id})
        with self._write() as conn:
            row = self._lookup_command(conn, _HANDOFF, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["handoff"]
                return dict(stored, idempotent_replay=True)
            case = self._case_row(conn, case_id)
            self._check_b3_v1_action(case, "HANDOFF")
            self._check_linked_b7_action(case, "HANDOFF")
            self._check_open(case)
            if case["stop_active"]:
                raise DomainError(
                    "STOP_ACTIVE",
                    "Hồ sơ đang Stop; không tạo handoff.",
                )
            self._check_version(case, command)
            decision_row = conn.execute(
                "SELECT * FROM decisions WHERE id = ? AND case_id = ?",
                (decision_id, case_id),
            ).fetchone()
            if decision_row is None:
                raise DomainError(
                    "DECISION_NOT_FOUND",
                    f"Không tìm thấy quyết định {decision_id} trong hồ sơ.",
                )
            run = (conn.execute("SELECT * FROM runs WHERE id = ?",
                                (case["current_run_id"],)).fetchone()
                   if case["current_run_id"] else None)
            if (run is None or run["status"] != "SUCCEEDED"
                    or run["input_revision"] != case["input_revision"]):
                raise DomainError(
                    "BASIS_STALE",
                    "Input đã thay đổi sau quyết định và chưa re-check xong; "
                    "không handoff trên basis cũ.",
                )
            now = _iso(utcnow())
            handoff_id = f"H-{uuid.uuid4().hex[:12]}"
            handoff = {
                "id": handoff_id, "case_id": case_id, "decision_id": decision_id,
                "report_id": case["current_run_id"], "actor_id": command.actor_id,
                "created_at": now,
            }
            conn.execute(
                "UPDATE cases SET case_version = ?, updated_at = ? WHERE id = ?",
                (case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id, "HANDOFF_RECORDED",
                                 _HANDOFF, command, payload_fp,
                                 {"handoff": handoff}, now)
            return dict(handoff)

    def close_case(self, case_id: str, payload: ClosurePayload,
                   command: Command) -> ClosureView:
        """Close a case only when every closure gate holds, inside the txn."""
        payload_fp = fingerprint(_CLOSE_CASE, payload.model_dump(mode="json"))
        with self._write() as conn:
            row = self._lookup_command(conn, _CLOSE_CASE, command, scope_key=case_id)
            if row is not None:
                self._check_replay(row, payload_fp)
                stored = _load(row["payload_json"])["closure"]
                return ClosureView.model_validate(stored).model_copy(
                    update={"idempotent_replay": True})
            case = self._case_row(conn, case_id)
            if case["stage"] in _CLOSED_STAGES:
                existing = conn.execute(
                    "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
                    "ORDER BY rowid DESC LIMIT 1", (case_id, _CLOSE_CASE),
                ).fetchone()
                if existing is not None and existing["fingerprint"] == payload_fp:
                    stored = _load(existing["payload_json"])["closure"]
                    return ClosureView.model_validate(stored).model_copy(
                        update={"idempotent_replay": True})
                raise DomainError(
                    "CASE_CLOSED",
                    "Hồ sơ đã đóng; nội dung đóng mới phải dùng hồ sơ mới.",
                )
            self._check_version(case, command)
            self._check_b3_v1_action(case, "CLOSURE")
            self._check_linked_b7_action(case, "CLOSURE")
            blockers = self._closure_blockers(conn, case, payload.kind)
            if blockers:
                raise DomainError(
                    "CLOSURE_BLOCKED",
                    "Không đóng được hồ sơ: " + "; ".join(blockers),
                )
            closure_id = f"CL-{uuid.uuid4().hex[:12]}"
            now = _iso(utcnow())
            closure = {
                "id": closure_id, "case_id": case_id, "kind": payload.kind,
                "basis": payload.basis, "actor_id": command.actor_id,
                "created_at": now,
            }
            new_stage: CaseStage = ("SETTLEMENT_CLOSED"
                                    if payload.kind == "SETTLEMENT_COMPLETE"
                                    else "REJECTED_REQUEST_ENDED")
            conn.execute(
                "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
                "WHERE id = ?",
                (new_stage, case["case_version"] + 1, now, case_id),
            )
            self._record_command(conn, case_id, case_id,
                                 "CASE_CLOSED" if payload.kind == "SETTLEMENT_COMPLETE"
                                 else "REQUEST_REJECTED_ENDED",
                                 _CLOSE_CASE, command, payload_fp,
                                 {"closure": closure}, now)
            return ClosureView.model_validate(closure)

    def closed(self, case_id: str) -> bool:
        with self._read() as conn:
            return self._case_row(conn, case_id)["stage"] in _CLOSED_STAGES

    def handoff_allowed(self, case_id: str) -> bool:
        with self._read() as conn:
            case = self._case_row(conn, case_id)
            if case["stage"] in _CLOSED_STAGES or case["stop_active"]:
                return False
            if self._latest_decision_payload(conn, case_id) is None:
                return False
            run = (conn.execute("SELECT * FROM runs WHERE id = ?",
                                (case["current_run_id"],)).fetchone()
                   if case["current_run_id"] else None)
            return (run is not None and run["status"] == "SUCCEEDED"
                    and run["input_revision"] == case["input_revision"])

    def _money_summary(self, conn: sqlite3.Connection,
                       case: sqlite3.Row) -> MoneySummary:
        """Approved vs actual per direction; gross truth, never clipped.

        PAY_EMPLOYEE counts PAYMENT_TO_EMPLOYEE events received by the
        employee; COLLECT_FROM_EMPLOYEE counts PAYMENT_FROM_EMPLOYEE events
        received back (payee = the employee returning to themself is a
        WRONG_RECIPIENT incident, not fulfillment).
        """
        approved: int | None = None
        direction: str | None = None
        latest = self._latest_decision_payload(conn, case["id"])
        if latest is not None and latest.get("amount_vnd") is not None \
                and latest.get("direction") != "REFUSE":
            approved = latest["amount_vnd"]
            direction = latest.get("direction")
        employee_ref = _load(case["submission_json"])["employee_ref"]
        received: int | None = None
        pending = 0
        incidents: list[MoneyIncident] = []
        for event_row in conn.execute(
                "SELECT payload_json FROM money_events WHERE case_id = ? "
                "ORDER BY rowid", (case["id"],)):
            event = _load(event_row["payload_json"])
            # B5 advance events (kind ADVANCE_TO_EMPLOYEE) are a separate
            # lifecycle: they must never count as a B7 reimbursement, not even
            # in the pending count. Filter by kind BEFORE any sum/count.
            if event["kind"] not in ("PAYMENT_TO_EMPLOYEE",
                                     "PAYMENT_FROM_EMPLOYEE"):
                continue
            if event["reported_status"] == "PENDING":
                pending += 1
            if direction == "COLLECT_FROM_EMPLOYEE":
                if event["kind"] != "PAYMENT_FROM_EMPLOYEE":
                    continue
                if event["payee_ref"] == employee_ref:
                    incidents.append(MoneyIncident(
                        kind="WRONG_RECIPIENT", event_ref=event["event_ref"],
                        payee_ref=event["payee_ref"]))
                    continue
                if event["reported_status"] == "RECEIVED":
                    received = (received or 0) + event["gross_vnd"]
            else:
                if event["kind"] != "PAYMENT_TO_EMPLOYEE":
                    continue
                if event["payee_ref"] != employee_ref:
                    incidents.append(MoneyIncident(
                        kind="WRONG_RECIPIENT", event_ref=event["event_ref"],
                        payee_ref=event["payee_ref"]))
                    continue
                if event["reported_status"] == "RECEIVED":
                    received = (received or 0) + event["gross_vnd"]
        remaining: int | None = None
        if approved is not None:
            actual = received or 0
            if actual > approved:
                incidents.append(MoneyIncident(
                    kind="OVERPAY", excess_vnd=actual - approved))
            remaining = max(approved - actual, 0)
        return MoneySummary(approved_vnd=approved, received_vnd=received,
                            remaining_vnd=remaining, pending_events=pending,
                            incidents=incidents)

    def _closure_blockers(self, conn: sqlite3.Connection, case: sqlite3.Row,
                          kind: str) -> list[str]:
        """All reasons a closure must be refused; empty list means closable."""
        blockers: list[str] = []
        if case["stop_active"]:
            blockers.append("Hồ sơ đang Stop; không đóng khi control đang giữ.")
        summary = self._money_summary(conn, case)
        if kind == "SETTLEMENT_COMPLETE":
            if summary.remaining_vnd is not None and summary.remaining_vnd > 0:
                blockers.append(
                    f"Còn phần quyết toán chưa thực nhận: remaining "
                    f"{summary.remaining_vnd} VND > 0.")
        elif summary.approved_vnd is not None:
            blockers.append(
                "Đã có quyết định duyệt số tiền; không thể kết thúc như "
                "yêu cầu bị từ chối.")
        if kind == "REJECTED_REQUEST_ENDED" and summary.received_vnd is not None:
            blockers.append(
                "Đã có tiền thực nhận; không được kết thúc hồ sơ như yêu cầu "
                "bị từ chối — phải xử lý nghĩa vụ tiền đã nhận.")
        if summary.pending_events:
            blockers.append(
                f"Còn {summary.pending_events} sự kiện tiền ở trạng thái PENDING.")
        if summary.incidents:
            kinds = ", ".join(sorted({incident.kind
                                       for incident in summary.incidents}))
            blockers.append(f"Còn money incident chưa xử lý: {kinds}.")
        open_questions = 0
        for question_row in conn.execute(
                "SELECT payload_json FROM interactions "
                "WHERE case_id = ? AND kind = 'QUESTION'", (case["id"],)):
            if _load(question_row["payload_json"])["status"] in _OPEN_QUESTION_STATUSES:
                open_questions += 1
        if open_questions:
            blockers.append(
                f"Còn {open_questions} câu hỏi chưa được re-check xử lý.")
        return blockers

    # --- history -----------------------------------------------------------

    def history(self, case_id: str) -> list[AuditEntry]:
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE case_id = ? ORDER BY rowid",
                (case_id,),
            ).fetchall()
        return [
            AuditEntry(
                id=row["id"], case_id=row["case_id"], kind=row["kind"],
                operation=row["operation"], actor_id=row["actor_id"],
                command_key=row["command_key"],
                occurred_at=datetime.fromisoformat(row["created_at"]),
                detail=_load(row["payload_json"]),
            )
            for row in rows
        ]

    # --- internals ---------------------------------------------------------

    @staticmethod
    def _case_row(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise DomainError("CASE_NOT_FOUND", f"Không tìm thấy hồ sơ {case_id}.")
        return row

    @staticmethod
    def _check_version(case: sqlite3.Row, command: Command) -> None:
        expected = command.expected_case_version
        if expected is None or expected != case["case_version"]:
            raise DomainError(
                "STALE_VERSION",
                "Phiên bản kỳ vọng không khớp hiện tại; tải lại hồ sơ trước khi sửa.",
            )

    @staticmethod
    def _record_command(conn: sqlite3.Connection, case_id: str, scope_key: str,
                        kind: str, operation: str, command: Command,
                        payload_fp: str, detail: dict[str, Any], now: str) -> None:
        conn.execute(
            "INSERT INTO audit_events (id, case_id, scope_key, kind, operation, "
            "actor_id, command_key, fingerprint, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"A-{uuid.uuid4().hex[:12]}", case_id, scope_key, kind, operation,
             command.actor_id, command.key, payload_fp, _dump(detail), now),
        )

    def _case_view(self, conn: sqlite3.Connection, case_id: str) -> CaseView:
        case = self._case_row(conn, case_id)
        submission = Submission.model_validate(_load(case["submission_json"]))
        rows = conn.execute(
            "SELECT * FROM sources WHERE case_id = ? AND status = 'ACCEPTED' "
            "ORDER BY received_at, rowid",
            (case_id,),
        ).fetchall()
        sources = [
            SourceView(
                id=row["id"], filename=row["filename"], media_type=row["media_type"],
                sha256=row["sha256"], size_bytes=row["size_bytes"],
                status="ACCEPTED", uploader_actor_id=row["uploader_actor_id"],
                received_at=datetime.fromisoformat(row["received_at"]),
                supersedes_source_id=row["supersedes_source_id"],
                provenance=_load(row["provenance_json"]),
            )
            for row in rows
        ]
        actions = [
            AllowedAction(
                action="REVISE_SUBMISSION",
                reason="Hồ sơ intake có thể sửa khai báo; mỗi lần sửa tạo revision mới.",
            ),
            AllowedAction(
                action="ADD_SOURCE",
                reason=f"Có thể bổ sung nguồn trong giới hạn pilot "
                       f"{MAX_ACTIVE_SOURCES_PER_CASE} nguồn active.",
            ),
        ]
        current_run = (conn.execute("SELECT * FROM runs WHERE id = ?",
                                     (case["current_run_id"],)).fetchone()
                       if case["current_run_id"] else None)
        run_active = current_run is not None and current_run["status"] in _NONTERMINAL_STATUSES
        if not case["stop_active"] and not run_active:
            actions.append(AllowedAction(
                action="START_RUN",
                reason="Chạy kiểm tra B3/B7 trên snapshot hiện tại của hồ sơ.",
            ))
        b3_v1_form = self._b3_v1_form(case)
        b3_v1 = bool(b3_v1_form)
        linked_b7 = self._b7_origin_link(case) is not None
        if case["stage"] in _CLOSED_STAGES:
            actions.append(AllowedAction(
                action="NONE",
                reason="Hồ sơ đã đóng; chỉ đọc lại history và report.",
            ))
        else:
            actions.append(AllowedAction(
                action="STOP_CONTROL" if not case["stop_active"] else "RESUME_CONTROL",
                reason=("Stop giữ run/decision mới nhưng vẫn nhận nguồn và "
                        "sự kiện tiền đã xảy ra; resume tạo epoch mới."
                        if not case["stop_active"] else
                        "Resume mở epoch mới; run cũ không tự hồi phục."),
            ))
            if current_run is not None and current_run["status"] == "SUCCEEDED":
                if not b3_v1 and not linked_b7:
                    actions.append(AllowedAction(
                        action="DECIDE",
                        reason="Report đã có; người có quyền duyệt hoặc từ chối.",
                    ))
                if not b3_v1 or b3_v1_form.get("confirmed"):
                    actions.append(AllowedAction(
                        action="REVIEW",
                        reason="Kế toán rà soát report; review không phải phê duyệt.",
                    ))
                if b3_v1:
                    b3_workflow = self._b3_workflow(conn, case_id)
                    if b3_workflow is not None and (
                            b3_workflow.decision is None
                            or b3_workflow.status in ("RETURNED", "NEEDS_RECHECK")):
                        actions.append(AllowedAction(
                            action="B3_PRESENT",
                            reason="Kế toán trình duyệt đề nghị tạm ứng cho "
                                   "người có quyền.",
                        ))
            if case["stage"] == "AWAITING_MONEY" and not b3_v1 and not linked_b7:
                actions.append(AllowedAction(
                    action="RECORD_MONEY",
                    reason="Ghi nhận thực nhận/thực chi; gross giữ nguyên, "
                           "không clip theo mức duyệt.",
                ))
            if not b3_v1 and not linked_b7:
                actions.append(AllowedAction(
                    action="CLOSE_CASE",
                    reason="Đóng hồ sơ khi các gate (remaining/pending/incident/"
                           "Stop/câu hỏi) đều sạch.",
                ))
        return CaseView(
            id=case["id"], job=submission.job,
            case_version=case["case_version"], input_revision=case["input_revision"],
            control_epoch=case["control_epoch"], stop_active=bool(case["stop_active"]),
            stage=case["stage"], current_run_id=case["current_run_id"],
            submission=submission, sources=sources,
            allowed_actions=actions,
            money_summary=self._money_summary(conn, case).model_dump(mode="json"),
            origin=case["origin"],
            b3_workflow=self._b3_workflow(conn, case_id),
            linked_b7=self._linked_b7_view(conn, case),
            created_at=datetime.fromisoformat(case["created_at"]),
            updated_at=datetime.fromisoformat(case["updated_at"]),
        )

    def _linked_b7_view(self, conn: sqlite3.Connection,
                        case: sqlite3.Row) -> "LinkedB7View | None":
        """Projection for a linked B7 child: origin + managed advance subtotal."""
        from invoice_referee.settlement.models import LinkedB7View

        link = self._b7_origin_link(case)
        if link is None:
            return None
        origin = B7OriginLink.model_validate(link)
        parent = conn.execute("SELECT * FROM cases WHERE id = ?",
                              (origin.origin_case_id,)).fetchone()
        parent_events = (self._b3_advance_events(conn, origin.origin_case_id)
                         if parent is not None else [])
        confirmed = [e for e in parent_events
                     if e.classification == "CONFIRMED_RECEIPT"
                     and e.reported_status == "RECEIVED" and e.gross_vnd is not None]
        subtotal = sum(e.gross_vnd for e in confirmed) if confirmed else None
        context_ids = self._linked_context_source_ids(conn, case["id"])
        context_current = False
        if context_ids:
            latest = conn.execute(
                "SELECT * FROM sources WHERE id = ?", (context_ids[-1],)).fetchone()
            if latest is not None:
                try:
                    data = json.loads((self.artifact_root
                                       / Path(latest["original_path"])
                                       ).read_text(encoding="utf-8"))
                    from invoice_referee.settlement.models import (
                        LinkedB7ContextSnapshot,
                    )
                    snap = LinkedB7ContextSnapshot.model_validate(data)
                    current_fp = self._linked_parent_fingerprint(
                        conn, origin.origin_case_id)
                    context_current = snap.parent_fingerprint == current_fp
                except (OSError, ValueError):
                    context_current = False
        return LinkedB7View(
            origin=origin,
            context_source_id=context_ids[-1] if context_ids else None,
            context_current=context_current,
            blocked_reasons=[],
            managed_advance_subtotal_vnd=subtotal,
        )

    def _source_records(self, conn: sqlite3.Connection, case_id: str) -> list[SourceRecord]:
        rows = conn.execute(
            "SELECT * FROM sources WHERE case_id = ? AND status = 'ACCEPTED' "
            "ORDER BY received_at, rowid",
            (case_id,),
        ).fetchall()
        return [self._source_record(row) for row in rows]

    @staticmethod
    def _source_record(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            id=row["id"], case_id=row["case_id"], filename=row["filename"],
            media_type=row["media_type"], sha256=row["sha256"],
            size_bytes=row["size_bytes"], status="ACCEPTED",
            uploader_actor_id=row["uploader_actor_id"],
            received_at=datetime.fromisoformat(row["received_at"]),
            supersedes_source_id=row["supersedes_source_id"],
            provenance=_load(row["provenance_json"]),
            original_path=Path(row["original_path"]),
        )
