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
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    MAX_ACTIVE_SOURCES_PER_CASE,
    MAX_SOURCE_BYTES,
    AllowedAction,
    AuditEntry,
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

_NONTERMINAL_STATUSES = ("QUEUED", "RUNNING")
_TERMINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "STOPPED",
                      "SUPERSEDED", "INTERRUPTED")
_CLOSED_STAGES: tuple[str, ...] = ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED")
_OPEN_QUESTION_STATUSES = ("OPEN", "ANSWERED")
MAX_ACCEPTED_RUNS = 5


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

    def create_case(self, submission: Submission, command: Command) -> CaseView:
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
                "stop_active, stage, current_run_id, submission_json, created_at, updated_at) "
                "VALUES (?, 1, 1, 1, 0, ?, NULL, ?, ?, ?)",
                (case_id, stage, _dump(submission.model_dump(mode="json")), now, now),
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
            ))
        return summaries

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

    def add_source(self, case_id: str, upload: Upload, command: Command) -> SourceRecord:
        sha = hashlib.sha256(upload.content).hexdigest()
        payload_fp = fingerprint(_ADD_SOURCE, {
            "filename": upload.filename,
            "sha256": sha,
            "size": len(upload.content),
            "provenance": upload.provenance,
        })
        stored_path: Path | None = None
        with self._write() as conn:
            row = self._lookup_command(conn, _ADD_SOURCE, command, scope_key=case_id)
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
                     _dump(upload.provenance),
                     str(stored_path.relative_to(self.artifact_root))),
                )
                new_version = case["case_version"] + 1
                conn.execute(
                    "UPDATE cases SET case_version = ?, input_revision = ?, updated_at = ? "
                    "WHERE id = ?",
                    (new_version, case["input_revision"] + 1, now, case_id),
                )
                self._record_command(conn, case_id, case_id, "SOURCE_ADDED",
                                     _ADD_SOURCE, command, payload_fp,
                                     {"source_id": source_id, "sha256": sha,
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

    def _latest_decision_payload(self, conn: sqlite3.Connection,
                                  case_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT payload_json FROM decisions WHERE case_id = ? "
            "ORDER BY rowid DESC LIMIT 1", (case_id,)).fetchone()
        return _load(row["payload_json"]) if row is not None else None

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
                actions.append(AllowedAction(
                    action="DECIDE",
                    reason="Report đã có; người có quyền duyệt hoặc từ chối.",
                ))
                actions.append(AllowedAction(
                    action="REVIEW",
                    reason="Kế toán rà soát report; review không phải phê duyệt.",
                ))
            if case["stage"] == "AWAITING_MONEY":
                actions.append(AllowedAction(
                    action="RECORD_MONEY",
                    reason="Ghi nhận thực nhận/thực chi; gross giữ nguyên, "
                           "không clip theo mức duyệt.",
                ))
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
            created_at=datetime.fromisoformat(case["created_at"]),
            updated_at=datetime.fromisoformat(case["updated_at"]),
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
