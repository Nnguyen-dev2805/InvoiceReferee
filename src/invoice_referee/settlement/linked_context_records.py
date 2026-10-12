"""B6→B7 linked settlement context records: child creation, declarations,
company packet/context snapshots and parent dependency fingerprints.

Functions take an already-open ``sqlite3.Connection`` plus the ``artifact_root``
for file-backed context. Case mutations return ``(case_id, idempotent_replay)``
so the ``Store`` builds the ``CaseView`` inside the SAME transaction. Nothing
here opens its own connection or commits.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement import sqlite_records as _rec
from invoice_referee.settlement.models import (
    B7LinkedIntake,
    CaseStage,
    Command,
    Report,
    Submission,
    fingerprint,
)
from invoice_referee.storage.artifacts import put_artifact

_PREPARE_LINKED_B7 = "PREPARE_LINKED_B7"
_REVISE_LINKED_B7 = "REVISE_LINKED_B7"
_B7_CONTEXT_REFRESH = "B7_CONTEXT_REFRESH"
_B7_MONEY_CONTEXT_REFRESH = "B7_MONEY_CONTEXT_REFRESH"
_LINKED_B7_CONTEXT_USE = "LINKED_B7_CONTEXT"
_CLOSED_STAGES: tuple[str, ...] = ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED")


def _iso(value) -> str:
    from datetime import timezone
    return value.astimezone(timezone.utc).isoformat()


def _now() -> str:
    from invoice_referee.settlement.store import utcnow
    return _iso(utcnow())


def _now_dt():
    from invoice_referee.settlement.store import utcnow
    return utcnow()


def origin_link(case: sqlite3.Row) -> dict[str, Any] | None:
    form = _rec.load(case["submission_json"]).get("form") or {}
    link = form.get("origin_link")
    return link if isinstance(link, dict) else None


def find_linked_child(conn: sqlite3.Connection,
                      parent_id: str) -> sqlite3.Row | None:
    """The active (not closed) linked B7 child for a parent, if one exists."""
    for row in conn.execute("SELECT * FROM cases ORDER BY rowid"):
        if row["id"] == parent_id:
            continue
        if row["stage"] in _CLOSED_STAGES:
            continue
        submission = _rec.load(row["submission_json"])
        if submission.get("job") != "B7":
            continue
        link = (submission.get("form") or {}).get("origin_link")
        if isinstance(link, dict) and link.get("origin_case_id") == parent_id:
            return row
    return None


def prepare_linked_child(conn: sqlite3.Connection, parent_id: str,
                         command: Command,
                         origin: str = "USER") -> tuple[str, bool]:
    """Create (or reuse) the single active linked B7 child for a B3 parent.

    Server-owned link/employee/work; the parent is never mutated. A draft
    child is created with ``confirmed=False``; no run is started here.
    Returns ``(child_id, idempotent_replay)``.
    """
    payload_fp = fingerprint(_PREPARE_LINKED_B7, {"parent_id": parent_id})
    row = _rec.lookup_command(conn, _PREPARE_LINKED_B7, command,
                              scope_key=parent_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return _rec.load(row["payload_json"])["child_id"], True
    parent = _rec.case_row(conn, parent_id)
    _rec.check_version(parent, command)
    if _rec.load(parent["submission_json"]).get("job") != "B3":
        raise DomainError(
            "LINKED_B7_INVALID",
            "Chỉ hồ sơ B3 mới mở được hồ sơ quyết toán liên kết.",
        )
    existing = find_linked_child(conn, parent_id)
    if existing is not None:
        return existing["id"], False
    now_dt = _now_dt()
    now = _iso(now_dt)
    child_id = f"C-{uuid.uuid4().hex[:12]}"
    link = {
        "origin_case_id": parent_id,
        "employee_ref": _rec.load(parent["submission_json"])["employee_ref"],
        "work_ref": _rec.load(parent["submission_json"])["work_ref"],
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
        (child_id, stage, _rec.dump(submission.model_dump(mode="json")),
         origin, now, now),
    )
    conn.execute(
        "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
        "reason, actor_id, command_key, created_at) VALUES (?, ?, 1, ?, '', ?, ?, ?)",
        (f"R-{uuid.uuid4().hex[:12]}", child_id,
         _rec.dump(submission.model_dump(mode="json")), command.actor_id,
         command.key, now),
    )
    _rec.record_command(conn, child_id, parent_id, "LINKED_B7_PREPARED",
                        _PREPARE_LINKED_B7, command, payload_fp,
                        {"child_id": child_id, "parent_id": parent_id}, now)
    return child_id, False


def revise_linked_child(conn: sqlite3.Connection, case_id: str,
                        intake: B7LinkedIntake,
                        command: Command) -> tuple[str, bool]:
    """Update a linked child's declarations; link/employee/work immutable.

    Returns ``(case_id, idempotent_replay)``.
    """
    payload_fp = fingerprint(_REVISE_LINKED_B7, {
        "intake": intake.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _REVISE_LINKED_B7, command,
                              scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return case_id, True
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    _rec.check_version(case, command)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    link = origin_link(case)
    if link is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Hồ sơ này không phải hồ sơ quyết toán liên kết.",
        )
    form = intake.model_dump(mode="json")
    form["origin_link"] = link  # server-owned, cannot be client-set
    merged = submission.model_copy(update={"form": form})
    now = _now()
    conn.execute(
        "UPDATE cases SET case_version = ?, input_revision = ?, "
        "submission_json = ?, updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, case["input_revision"] + 1,
         _rec.dump(merged.model_dump(mode="json")), now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "LINKED_B7_REVISED",
                        _REVISE_LINKED_B7, command, payload_fp,
                        {"confirmed": intake.confirmed}, now)
    return case_id, False


def store_context_source(conn: sqlite3.Connection, artifact_root: Path,
                         case_id: str, snapshot, command: Command) -> str:
    """Persist the linked context snapshot as a backend-owned system source.

    Source-use ``LINKED_B7_CONTEXT`` is recorded in the audit operation, so
    the snapshot is trusted by audit — never by a client-supplied string.
    """
    source_id = f"S-{uuid.uuid4().hex[:12]}"
    now = _now()
    content = _rec.dump(snapshot.model_dump(mode="json")).encode("utf-8")
    stored_path = put_artifact(artifact_root, case_id, "sources", source_id,
                               content)
    sha = hashlib.sha256(content).hexdigest()
    conn.execute(
        "INSERT INTO sources (id, case_id, filename, media_type, sha256, "
        "size_bytes, status, supersedes_source_id, uploader_actor_id, "
        "received_at, provenance_json, original_path) "
        "VALUES (?, ?, 'linked-context.json', 'application/json', ?, ?, "
        "'ACCEPTED', NULL, ?, ?, ?, ?)",
        (source_id, case_id, sha, len(content), command.actor_id, now,
         _rec.dump({"source_use": _LINKED_B7_CONTEXT_USE}),
         str(stored_path.relative_to(artifact_root))),
    )
    return source_id


def record_company_packet(conn: sqlite3.Connection, artifact_root: Path,
                          case_id: str, payload: dict, command: Command,
                          policy: dict, authority_version: str | None,
                          b3_workflow, b3_advance_events) -> tuple[str, bool]:
    """Accountant records a source-backed company packet; build context.

    Persists the snapshot as a system source, bumps input_revision (a
    material context change), and keeps old run/source history.
    ``b3_workflow(conn, parent_id)`` and ``b3_advance_events(conn, parent_id)``
    are injected by the Store so this module does not import the advance group.
    Returns ``(case_id, idempotent_replay)``.
    """
    from invoice_referee.settlement.linked_context import (
        build_linked_context, load_b7_company_packet,
    )

    packet = load_b7_company_packet(payload)
    payload_fp = fingerprint(_B7_CONTEXT_REFRESH, {
        "case_id": case_id, "packet": packet.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_CONTEXT_REFRESH, command,
                              scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return case_id, True
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    _rec.check_version(case, command)
    link = origin_link(case)
    if link is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Company packet chỉ áp dụng cho hồ sơ quyết toán liên kết.",
        )
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    parent_id = link["origin_case_id"]
    decision = None
    parent_wf = b3_workflow(conn, parent_id)
    if parent_wf is not None and parent_wf.decision is not None:
        decision = parent_wf.decision
    managed = b3_advance_events(conn, parent_id)
    snapshot = build_linked_context(
        origin_case_id=parent_id,
        parent_fingerprint=parent_fingerprint(conn, parent_id, b3_workflow,
                                              b3_advance_events),
        decision=decision, managed_events=managed, packet=packet,
        policy=policy, authority_version=authority_version,
        money_as_of=submission.money_as_of,
        knowledge_cutoff=submission.knowledge_cutoff,
        submission=submission,
        source_records=_rec.source_records(conn, case_id))
    # Identical snapshot (same packet, same parent dependency): reuse the
    # existing source and do NOT bump input_revision.
    snapshot_fp = fingerprint("LINKED_CONTEXT",
                              snapshot.model_dump(mode="json"))
    prior_ids = context_source_ids(conn, case_id)
    if prior_ids:
        prior = _rec.source_record(conn.execute(
            "SELECT * FROM sources WHERE id = ?",
            (prior_ids[-1],)).fetchone())
        prior_data = (artifact_root / prior.original_path
                      ).read_text(encoding="utf-8")
        if fingerprint("LINKED_CONTEXT", json.loads(prior_data)) == snapshot_fp:
            return case_id, True
    source_id = store_context_source(conn, artifact_root, case_id, snapshot,
                                     command)
    now = _now()
    conn.execute(
        "UPDATE cases SET case_version = ?, input_revision = ?, "
        "updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, case["input_revision"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_CONTEXT_REFRESHED",
                        _B7_CONTEXT_REFRESH, command, payload_fp,
                        {"source_id": source_id,
                         "context_version": snapshot.context_version}, now)
    return case_id, False


def parent_fingerprint(conn: sqlite3.Connection, parent_id: str,
                       b3_workflow, b3_advance_events) -> str:
    """Fingerprint of parent case/decision/managed events (dependency)."""
    case = _rec.case_row(conn, parent_id)
    decision = None
    wf = b3_workflow(conn, parent_id)
    if wf is not None and wf.decision is not None:
        decision = wf.decision.model_dump(mode="json")
    events = [e.model_dump(mode="json")
              for e in b3_advance_events(conn, parent_id)]
    return fingerprint("LINKED_PARENT", {
        "case_version": case["case_version"],
        "input_revision": case["input_revision"],
        "stop_active": bool(case["stop_active"]),
        "control_epoch": case["control_epoch"],
        "decision": decision, "events": events})


def context_source_ids(conn: sqlite3.Connection, case_id: str) -> list[str]:
    # Both the accountant packet refresh and the B9 money-context refresh
    # retain a linked-context source; the current one is the latest of
    # either operation.
    ids: list[str] = []
    for row in conn.execute(
            "SELECT payload_json FROM audit_events WHERE case_id = ? "
            "AND operation IN (?, ?) ORDER BY rowid",
            (case_id, _B7_CONTEXT_REFRESH, _B7_MONEY_CONTEXT_REFRESH)):
        source_id = _rec.load(row["payload_json"]).get("source_id")
        if source_id:
            ids.append(source_id)
    return ids


def load_context(conn: sqlite3.Connection, artifact_root: Path, source_id: str):
    from invoice_referee.settlement.models import LinkedB7ContextSnapshot

    row = conn.execute("SELECT * FROM sources WHERE id = ?",
                       (source_id,)).fetchone()
    record = _rec.source_record(row)
    data = json.loads((artifact_root / record.original_path)
                      .read_text(encoding="utf-8"))
    return LinkedB7ContextSnapshot.model_validate(data)


def linked_ready(conn: sqlite3.Connection, case_id: str, basis_report_id: str):
    """Resolve a current, COMPLETE, confirmed linked basis for present.

    Raises BASIS_MISMATCH/BASIS_STALE/B7_WORKFLOW_BLOCKED so a presentation
    never binds another case's report, a stale revision or an incomplete
    context. Returns (case, run, report, context_source_id).
    """
    run = conn.execute("SELECT * FROM runs WHERE id = ?",
                       (basis_report_id,)).fetchone()
    if run is None or run["case_id"] != case_id:
        raise DomainError(
            "BASIS_MISMATCH",
            f"Report basis {basis_report_id} không thuộc hồ sơ {case_id}.",
        )
    case = _rec.case_row(conn, case_id)
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
            "current); chạy lại và trình lại.",
        )
    report = Report.model_validate(_rec.load(run["report_json"]))
    if report.completion != "COMPLETE":
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Report basis chưa COMPLETE; không trình quyết toán được.",
        )
    form = _rec.load(case["submission_json"]).get("form") or {}
    if not form.get("confirmed"):
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Khai báo quyết toán chưa được xác nhận; chưa trình duyệt.",
        )
    context_ids = context_source_ids(conn, case_id)
    if not context_ids:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Chưa có company context; không trình quyết toán được.",
        )
    return case, run, report, context_ids[-1]


def check_origin_not_stopped(conn: sqlite3.Connection, parent_id: str) -> None:
    parent = _rec.case_row(conn, parent_id)
    if parent["stop_active"]:
        raise DomainError(
            "ORIGIN_STOP_ACTIVE",
            f"Hồ sơ gốc {parent_id} đang Stop; không hành động trên con.",
        )
