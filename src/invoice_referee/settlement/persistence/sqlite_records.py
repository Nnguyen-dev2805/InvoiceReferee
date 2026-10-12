"""Common SQLite record helpers shared by the settlement lifecycle modules.

These are pure functions over an already-open ``sqlite3.Connection``. They do
NOT open their own connection, commit, or read financial policy: the caller
(``Store``) owns the transaction boundary so every financial check and write
stays atomic inside one ``BEGIN IMMEDIATE``.

Semantics are moved verbatim from the previous ``Store`` private helpers; the
``Store`` façade keeps the same private method names as thin delegators so
callers and tests are unaffected.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import Command, SourceRecord


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def load(text: str) -> Any:
    return json.loads(text)


def new_id(prefix: str) -> str:
    """Record id: ``prefix`` + 12 hex chars (format preserved verbatim)."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def case_row(conn: sqlite3.Connection, case_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        raise DomainError("CASE_NOT_FOUND", f"Không tìm thấy hồ sơ {case_id}.")
    return row


def run_row(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise DomainError("RUN_NOT_FOUND", f"Không tìm thấy run {run_id}.")
    return row


def source_records(conn: sqlite3.Connection, case_id: str) -> list[SourceRecord]:
    rows = conn.execute(
        "SELECT * FROM sources WHERE case_id = ? AND status = 'ACCEPTED' "
        "ORDER BY received_at, rowid",
        (case_id,),
    ).fetchall()
    return [source_record(row) for row in rows]


def source_record(row: sqlite3.Row) -> SourceRecord:
    from datetime import datetime
    from pathlib import Path
    return SourceRecord(
        id=row["id"], case_id=row["case_id"], filename=row["filename"],
        media_type=row["media_type"], sha256=row["sha256"],
        size_bytes=row["size_bytes"], status="ACCEPTED",
        uploader_actor_id=row["uploader_actor_id"],
        received_at=datetime.fromisoformat(row["received_at"]),
        supersedes_source_id=row["supersedes_source_id"],
        provenance=load(row["provenance_json"]),
        original_path=Path(row["original_path"]),
    )


def lookup_command(conn: sqlite3.Connection, operation: str, command: Command,
                   scope_key: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM audit_events WHERE operation = ? AND actor_id = ? "
        "AND scope_key = ? AND command_key = ?",
        (operation, command.actor_id, scope_key, command.key),
    ).fetchone()


def check_replay(row: sqlite3.Row, expected_fingerprint: str) -> None:
    if row["fingerprint"] != expected_fingerprint:
        raise DomainError(
            "IDEMPOTENCY_CONFLICT",
            "Khóa lệnh đã dùng cho một payload khác; dùng khóa mới cho nội dung mới.",
        )


def check_version(case: sqlite3.Row, command: Command) -> None:
    expected = command.expected_case_version
    if expected is None or expected != case["case_version"]:
        raise DomainError(
            "STALE_VERSION",
            "Phiên bản kỳ vọng không khớp hiện tại; tải lại hồ sơ trước khi sửa.",
        )


def check_open(case: sqlite3.Row) -> None:
    if case["stage"] in ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED"):
        raise DomainError(
            "CASE_CLOSED",
            f"Hồ sơ đã kết thúc ({case['stage']}); không nhận hành động mới.",
        )


def record_command(conn: sqlite3.Connection, case_id: str, scope_key: str,
                   kind: str, operation: str, command: Command,
                   payload_fp: str, detail: dict[str, Any], now: str) -> None:
    conn.execute(
        "INSERT INTO audit_events (id, case_id, scope_key, kind, operation, "
        "actor_id, command_key, fingerprint, payload_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id("A-"), case_id, scope_key, kind, operation,
         command.actor_id, command.key, payload_fp, dump(detail), now),
    )
