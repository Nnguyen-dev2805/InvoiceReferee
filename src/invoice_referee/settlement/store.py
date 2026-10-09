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
    Command,
    CallTrace,
    Report,
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

_NONTERMINAL_STATUSES = ("QUEUED", "RUNNING")
_TERMINAL_STATUSES = ("SUCCEEDED", "FAILED", "TIMED_OUT", "STOPPED",
                      "SUPERSEDED", "INTERRUPTED")
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
        """Publish a report only when controls still hold (Stop/revision/epoch)."""
        with self._write() as conn:
            run = self._run_row(conn, run_id)
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
        return CaseView(
            id=case["id"], job=submission.job,
            case_version=case["case_version"], input_revision=case["input_revision"],
            control_epoch=case["control_epoch"], stop_active=bool(case["stop_active"]),
            stage=case["stage"], current_run_id=case["current_run_id"],
            submission=submission, sources=sources,
            allowed_actions=actions,
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
