"""SQLite metadata and filesystem artifacts for UC-03."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from invoice_referee.domain import (
    SettlementDecision,
    SettlementDraft,
    SettlementFinding,
    SettlementReceipt,
    SettlementUpload,
)

VIETNAM_TZ = timezone(timedelta(hours=7))


def _now_vietnam() -> datetime:
    return datetime.now(tz=VIETNAM_TZ)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "unnamed-file")[:140]


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settlement_cases (
    case_id TEXT PRIMARY KEY,
    case_type TEXT NOT NULL DEFAULT 'EXPENSE_SETTLEMENT',
    settlement_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    department TEXT NOT NULL,
    position TEXT NOT NULL,
    purpose TEXT NOT NULL,
    project_code TEXT,
    client_name TEXT,
    activity_start_date TEXT,
    activity_end_date TEXT,
    advance_id TEXT,
    allocated_advance_amount TEXT NOT NULL,
    claimed_total TEXT NOT NULL,
    currency TEXT NOT NULL,
    workflow_status TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    automation_decision TEXT,
    uncertainty_type TEXT,
    primary_finding_code TEXT,
    submitted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    policy_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS expense_items (
    item_id TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    expense_date TEXT,
    claimed_amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    policy_exception_code TEXT,
    PRIMARY KEY (case_id, item_id)
);

CREATE TABLE IF NOT EXISTS settlement_documents (
    document_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    linked_item_id TEXT,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_settlement_documents_sha
ON settlement_documents(sha256);

CREATE TABLE IF NOT EXISTS settlement_findings (
    finding_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    uncertainty_type TEXT NOT NULL,
    target TEXT NOT NULL,
    question TEXT,
    source_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settlement_decisions (
    decision_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    automation_decision TEXT NOT NULL,
    uncertainty_type TEXT NOT NULL,
    primary_finding_code TEXT,
    target TEXT NOT NULL,
    question TEXT,
    reason TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_processing_jobs_status
ON processing_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    reason TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS human_actions (
    action_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES settlement_cases(case_id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    previous_decision TEXT,
    new_decision TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_settlement_cases_queue
ON settlement_cases(automation_decision, submitted_at DESC);
"""


class SQLiteSettlementRepository:
    """Repository boundary for settlement metadata and immutable source files."""

    def __init__(
        self,
        database_path: Path,
        artifacts_root: Path,
        *,
        clock: Callable[[], datetime] = _now_vietnam,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.artifacts_root = Path(artifacts_root)
        self.clock = clock
        self.id_factory = id_factory or self._new_case_id
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                """
                INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                VALUES (1, ?)
                """,
                (self.clock().isoformat(),),
            )

    def _new_case_id(self) -> str:
        return f"SET-{self.clock():%Y%m%d}-{uuid4().hex[:8].upper()}"

    def find_duplicate_uploads(
        self,
        uploads: list[SettlementUpload],
    ) -> list[str]:
        if not uploads:
            return []
        with self._connect() as connection:
            duplicates = []
            for upload in uploads:
                row = connection.execute(
                    """
                    SELECT original_name
                    FROM settlement_documents
                    WHERE sha256 = ?
                    LIMIT 1
                    """,
                    (upload.sha256,),
                ).fetchone()
                if row is not None:
                    duplicates.append(upload.original_name)
            return duplicates

    def find_case_duplicate_documents(self, case_id: str) -> list[str]:
        """Return documents whose hash already exists in another case."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT current.original_name
                FROM settlement_documents AS current
                WHERE current.case_id = ?
                  AND EXISTS (
                      SELECT 1
                      FROM settlement_documents AS previous
                      WHERE previous.sha256 = current.sha256
                        AND previous.case_id <> current.case_id
                  )
                ORDER BY current.original_name
                """,
                (case_id,),
            ).fetchall()
        return [str(row["original_name"]) for row in rows]

    def create_case(
        self,
        draft: SettlementDraft,
        uploads: list[SettlementUpload],
        *,
        policy_id: str,
        policy_version: str,
    ) -> SettlementReceipt:
        case_id = self.id_factory()
        submitted_at = self.clock().isoformat()
        case_dir = self.artifacts_root / case_id
        temp_dir = self.artifacts_root / f".{case_id}-{uuid4().hex}.tmp"
        if case_dir.exists():
            raise FileExistsError(f"Hồ sơ đã tồn tại: {case_id}")

        documents: list[dict[str, Any]] = []
        try:
            (temp_dir / "source").mkdir(parents=True, exist_ok=False)
            (temp_dir / "canonical").mkdir(parents=True, exist_ok=True)
            for upload in uploads:
                document_id = f"DOC-{uuid4().hex[:10].upper()}"
                stored_name = f"{document_id}__{_safe_filename(upload.original_name)}"
                relative_path = Path("source") / stored_name
                (temp_dir / relative_path).write_bytes(upload.content)
                documents.append(
                    {
                        "document_id": document_id,
                        "role": upload.role.value,
                        "linked_item_id": upload.linked_item_id,
                        "original_name": upload.original_name,
                        "stored_name": stored_name,
                        "mime_type": upload.mime_type,
                        "size_bytes": upload.size_bytes,
                        "sha256": upload.sha256,
                        "relative_path": relative_path.as_posix(),
                    }
                )

            canonical = {
                "schema_version": "1.0",
                "case_id": case_id,
                "case_type": "EXPENSE_SETTLEMENT",
                "submitted_at": submitted_at,
                **draft.model_dump(mode="json"),
                "claimed_total": str(draft.claimed_total),
                "documents": documents,
            }
            (temp_dir / "canonical" / "settlement_request.v1.json").write_text(
                json.dumps(canonical, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO settlement_cases(
                        case_id, settlement_type, source_type, employee_id,
                        employee_name, department, position, purpose, project_code,
                        client_name, activity_start_date, activity_end_date,
                        advance_id, allocated_advance_amount, claimed_total, currency,
                        workflow_status, processing_status, submitted_at, updated_at,
                        policy_id, policy_version
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        'ACTIVE', 'PENDING', ?, ?, ?, ?
                    )
                    """,
                    (
                        case_id,
                        draft.settlement_type.value,
                        draft.source_type.value,
                        draft.employee.employee_id,
                        draft.employee.name,
                        draft.employee.department,
                        draft.employee.position,
                        draft.business_context.purpose,
                        draft.business_context.project_code,
                        draft.business_context.client_name,
                        (
                            draft.business_context.activity_start_date.isoformat()
                            if draft.business_context.activity_start_date
                            else None
                        ),
                        (
                            draft.business_context.activity_end_date.isoformat()
                            if draft.business_context.activity_end_date
                            else None
                        ),
                        draft.advance_id,
                        str(draft.allocated_advance_amount),
                        str(draft.claimed_total),
                        draft.currency,
                        submitted_at,
                        submitted_at,
                        policy_id,
                        policy_version,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO expense_items(
                        item_id, case_id, category, description, expense_date,
                        claimed_amount, currency, policy_exception_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item.item_id,
                            case_id,
                            item.category.value,
                            item.description,
                            item.expense_date.isoformat() if item.expense_date else None,
                            str(item.claimed_amount),
                            item.currency,
                            item.policy_exception_code,
                        )
                        for item in draft.expense_items
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO settlement_documents(
                        document_id, case_id, role, linked_item_id, original_name,
                        stored_name, mime_type, size_bytes, sha256, relative_path,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item["document_id"],
                            case_id,
                            item["role"],
                            item["linked_item_id"],
                            item["original_name"],
                            item["stored_name"],
                            item["mime_type"],
                            item["size_bytes"],
                            item["sha256"],
                            item["relative_path"],
                            submitted_at,
                        )
                        for item in documents
                    ],
                )
                job_id = f"JOB-{uuid4().hex[:12].upper()}"
                connection.execute(
                    """
                    INSERT INTO processing_jobs(
                        job_id, case_id, job_type, status, created_at
                    ) VALUES (?, ?, 'PROCESS_SETTLEMENT', 'PENDING', ?)
                    """,
                    (job_id, case_id, submitted_at),
                )
                self._insert_audit(
                    connection,
                    case_id=case_id,
                    event_type="CASE_CREATED",
                    actor_type="EMPLOYEE",
                    actor_id=draft.employee.employee_id,
                    reason="Nhân viên gửi hồ sơ hoàn ứng/quyết toán.",
                    payload={"document_count": len(documents)},
                )

            temp_dir.replace(case_dir)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM settlement_cases WHERE case_id = ?",
                    (case_id,),
                )
            raise

        return SettlementReceipt(
            case_id=case_id,
            workflow_status="ACTIVE",
            processing_status="PENDING",
            submitted_at=submitted_at,
            claimed_total=draft.claimed_total,
            currency=draft.currency,
            document_count=len(documents),
        )

    def claim_next_job(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT job_id, case_id, attempts
                FROM processing_jobs
                WHERE status = 'PENDING'
                ORDER BY created_at
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            started_at = self.clock().isoformat()
            connection.execute(
                """
                UPDATE processing_jobs
                SET status = 'RUNNING', attempts = attempts + 1, started_at = ?
                WHERE job_id = ?
                """,
                (started_at, row["job_id"]),
            )
            connection.execute(
                """
                UPDATE settlement_cases
                SET processing_status = 'PROCESSING', updated_at = ?
                WHERE case_id = ?
                """,
                (started_at, row["case_id"]),
            )
            return dict(row)

    def load_processing_input(self, case_id: str) -> dict[str, Any]:
        detail = self.get_case(case_id)
        canonical_path = (
            self.artifacts_root
            / case_id
            / "canonical"
            / "settlement_request.v1.json"
        )
        detail["canonical"] = json.loads(canonical_path.read_text(encoding="utf-8"))
        return detail

    def complete_job(
        self,
        job_id: str,
        case_id: str,
        findings: list[SettlementFinding],
        decision: SettlementDecision,
    ) -> None:
        finished_at = self.clock().isoformat()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM settlement_findings WHERE case_id = ?",
                (case_id,),
            )
            connection.executemany(
                """
                INSERT INTO settlement_findings(
                    finding_id, case_id, rule_id, status, message,
                    uncertainty_type, target, question, source_refs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"FND-{uuid4().hex[:12].upper()}",
                        case_id,
                        finding.rule_id,
                        finding.status,
                        finding.message,
                        finding.uncertainty_type.value,
                        finding.target.value,
                        finding.question,
                        json.dumps(finding.source_refs, ensure_ascii=False),
                        finished_at,
                    )
                    for finding in findings
                ],
            )
            connection.execute(
                """
                INSERT INTO settlement_decisions(
                    decision_id, case_id, automation_decision, uncertainty_type,
                    primary_finding_code, target, question, reason,
                    source_refs_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"DEC-{uuid4().hex[:12].upper()}",
                    case_id,
                    decision.automation_decision.value,
                    decision.uncertainty_type.value,
                    decision.primary_finding_code,
                    decision.target.value,
                    decision.question,
                    decision.reason,
                    json.dumps(decision.source_refs, ensure_ascii=False),
                    finished_at,
                ),
            )
            connection.execute(
                """
                UPDATE settlement_cases
                SET processing_status = 'COMPLETED', automation_decision = ?,
                    uncertainty_type = ?, primary_finding_code = ?, updated_at = ?
                WHERE case_id = ?
                """,
                (
                    decision.automation_decision.value,
                    decision.uncertainty_type.value,
                    decision.primary_finding_code,
                    finished_at,
                    case_id,
                ),
            )
            connection.execute(
                """
                UPDATE processing_jobs
                SET status = 'COMPLETED', finished_at = ?, error_message = NULL
                WHERE job_id = ?
                """,
                (finished_at, job_id),
            )
            self._insert_audit(
                connection,
                case_id=case_id,
                event_type="CASE_PROCESSED",
                actor_type="AGENT",
                actor_id="invoice_referee",
                reason=decision.reason,
                payload=decision.model_dump(mode="json"),
            )

    def fail_job(self, job_id: str, case_id: str, error: str) -> None:
        finished_at = self.clock().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE processing_jobs
                SET status = 'FAILED', finished_at = ?, error_message = ?
                WHERE job_id = ?
                """,
                (finished_at, error[:2000], job_id),
            )
            connection.execute(
                """
                UPDATE settlement_cases
                SET processing_status = 'PROCESSING_ERROR', updated_at = ?
                WHERE case_id = ?
                """,
                (finished_at, case_id),
            )
            self._insert_audit(
                connection,
                case_id=case_id,
                event_type="PROCESSING_FAILED",
                actor_type="SYSTEM",
                actor_id="settlement_worker",
                reason=error[:500],
                payload={},
            )

    def record_human_action(
        self,
        *,
        case_id: str,
        action_type: str,
        actor_id: str,
        reason: str,
        workflow_status: str,
        new_decision: SettlementDecision | None = None,
    ) -> None:
        occurred_at = self.clock().isoformat()
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT automation_decision
                FROM settlement_cases
                WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
            previous_decision = current["automation_decision"]
            next_decision = (
                new_decision.automation_decision.value
                if new_decision
                else previous_decision
            )
            connection.execute(
                """
                INSERT INTO human_actions(
                    action_id, case_id, action_type, actor_id, reason,
                    previous_decision, new_decision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"ACT-{uuid4().hex[:12].upper()}",
                    case_id,
                    action_type,
                    actor_id,
                    reason,
                    previous_decision,
                    next_decision,
                    occurred_at,
                ),
            )
            if new_decision is not None:
                connection.execute(
                    """
                    INSERT INTO settlement_decisions(
                        decision_id, case_id, automation_decision,
                        uncertainty_type, primary_finding_code, target,
                        question, reason, source_refs_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"DEC-{uuid4().hex[:12].upper()}",
                        case_id,
                        new_decision.automation_decision.value,
                        new_decision.uncertainty_type.value,
                        new_decision.primary_finding_code,
                        new_decision.target.value,
                        new_decision.question,
                        new_decision.reason,
                        json.dumps(new_decision.source_refs, ensure_ascii=False),
                        occurred_at,
                    ),
                )
            connection.execute(
                """
                UPDATE settlement_cases
                SET workflow_status = ?, automation_decision = ?,
                    uncertainty_type = COALESCE(?, uncertainty_type),
                    primary_finding_code = COALESCE(?, primary_finding_code),
                    updated_at = ?
                WHERE case_id = ?
                """,
                (
                    workflow_status,
                    next_decision,
                    (
                        new_decision.uncertainty_type.value
                        if new_decision
                        else None
                    ),
                    (
                        new_decision.primary_finding_code
                        if new_decision
                        else None
                    ),
                    occurred_at,
                    case_id,
                ),
            )
            self._insert_audit(
                connection,
                case_id=case_id,
                event_type=action_type,
                actor_type="HUMAN",
                actor_id=actor_id,
                reason=reason,
                payload={
                    "previous_decision": previous_decision,
                    "new_decision": next_decision,
                    "workflow_status": workflow_status,
                },
            )

    def requeue_case(
        self,
        *,
        case_id: str,
        actor_id: str,
        reason: str,
    ) -> None:
        occurred_at = self.clock().isoformat()
        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT automation_decision
                FROM settlement_cases
                WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
            connection.execute(
                """
                INSERT INTO human_actions(
                    action_id, case_id, action_type, actor_id, reason,
                    previous_decision, new_decision, created_at
                ) VALUES (?, ?, 'REPROCESS_CASE', ?, ?, ?, NULL, ?)
                """,
                (
                    f"ACT-{uuid4().hex[:12].upper()}",
                    case_id,
                    actor_id,
                    reason,
                    current["automation_decision"],
                    occurred_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO processing_jobs(
                    job_id, case_id, job_type, status, created_at
                ) VALUES (?, ?, 'PROCESS_SETTLEMENT', 'PENDING', ?)
                """,
                (f"JOB-{uuid4().hex[:12].upper()}", case_id, occurred_at),
            )
            connection.execute(
                """
                UPDATE settlement_cases
                SET workflow_status = 'ACTIVE', processing_status = 'PENDING',
                    automation_decision = NULL, uncertainty_type = NULL,
                    primary_finding_code = NULL, updated_at = ?
                WHERE case_id = ?
                """,
                (occurred_at, case_id),
            )
            self._insert_audit(
                connection,
                case_id=case_id,
                event_type="REPROCESS_CASE",
                actor_type="HUMAN",
                actor_id=actor_id,
                reason=reason,
                payload={"previous_decision": current["automation_decision"]},
            )

    def list_cases(self, decision: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT case_id, settlement_type, source_type, employee_name,
                   department, purpose, claimed_total, currency, workflow_status,
                   processing_status, automation_decision, uncertainty_type,
                   primary_finding_code, submitted_at,
                   CASE WHEN automation_decision IS NOT NULL THEN (
                       SELECT reason
                       FROM settlement_decisions AS latest_decision
                       WHERE latest_decision.case_id = settlement_cases.case_id
                       ORDER BY latest_decision.created_at DESC,
                                latest_decision.rowid DESC
                       LIMIT 1
                   ) END AS decision_reason
            FROM settlement_cases
        """
        params: tuple[Any, ...] = ()
        if decision:
            query += " WHERE automation_decision = ?"
            params = (decision,)
        query += " ORDER BY submitted_at DESC"
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_case(self, case_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            case = connection.execute(
                "SELECT * FROM settlement_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if case is None:
                raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
            result = dict(case)
            result["expense_items"] = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM expense_items
                    WHERE case_id = ?
                    ORDER BY item_id
                    """,
                    (case_id,),
                ).fetchall()
            ]
            result["documents"] = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM settlement_documents
                    WHERE case_id = ?
                    ORDER BY created_at, document_id
                    """,
                    (case_id,),
                ).fetchall()
            ]
            result["findings"] = [
                {
                    **dict(row),
                    "source_refs": json.loads(row["source_refs_json"]),
                }
                for row in connection.execute(
                    """
                    SELECT * FROM settlement_findings
                    WHERE case_id = ?
                    ORDER BY created_at, finding_id
                    """,
                    (case_id,),
                ).fetchall()
            ]
            decision = connection.execute(
                """
                SELECT * FROM settlement_decisions
                WHERE case_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (case_id,),
            ).fetchone()
            if decision and result["automation_decision"]:
                result["decision"] = {
                    **dict(decision),
                    "source_refs": json.loads(decision["source_refs_json"]),
                }
            else:
                result["decision"] = None
            result["audit_events"] = [
                {**dict(row), "payload": json.loads(row["payload_json"])}
                for row in connection.execute(
                    """
                    SELECT * FROM audit_events
                    WHERE case_id = ?
                    ORDER BY occurred_at, rowid
                    """,
                    (case_id,),
                ).fetchall()
            ]
            result["human_actions"] = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM human_actions
                    WHERE case_id = ?
                    ORDER BY created_at, rowid
                    """,
                    (case_id,),
                ).fetchall()
            ]
            return result

    def delete_case(self, case_id: str) -> None:
        """Permanently delete a demo case, its metadata and stored artifacts."""

        root = self.artifacts_root.resolve()
        if (
            not case_id.startswith("SET-")
            or Path(case_id).name != case_id
            or case_id in {".", ".."}
        ):
            raise ValueError("Mã hồ sơ không hợp lệ.")
        case_dir = (root / case_id).resolve()
        if case_dir.parent != root:
            raise ValueError("Đường dẫn hồ sơ không hợp lệ.")

        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM settlement_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
        if exists is None:
            raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")

        staged_dir: Path | None = None
        if case_dir.is_dir():
            staged_dir = root / f".deleting-{case_id}-{uuid4().hex}"
            case_dir.rename(staged_dir)

        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM settlement_cases WHERE case_id = ?",
                    (case_id,),
                )
        except Exception:
            if staged_dir is not None and staged_dir.exists():
                staged_dir.rename(case_dir)
            raise

        if staged_dir is not None:
            shutil.rmtree(staged_dir)

    def document_path(self, case_id: str, document_id: str) -> Path:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT relative_path
                FROM settlement_documents
                WHERE case_id = ? AND document_id = ?
                """,
                (case_id, document_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Không tìm thấy chứng từ.")
        case_dir = (self.artifacts_root / case_id).resolve()
        path = (case_dir / row["relative_path"]).resolve()
        if not path.is_relative_to(case_dir) or not path.is_file():
            raise FileNotFoundError("File chứng từ không tồn tại.")
        return path

    def load_ocr_artifact(
        self,
        case_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        """Load a persisted OCR response after verifying document ownership."""

        with self._connect() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM settlement_documents
                WHERE case_id = ? AND document_id = ?
                """,
                (case_id, document_id),
            ).fetchone()
        if exists is None:
            return None
        artifact = (
            self.artifacts_root.resolve()
            / case_id
            / "ocr"
            / f"{document_id}.json"
        ).resolve()
        case_dir = (self.artifacts_root.resolve() / case_id).resolve()
        if not artifact.is_relative_to(case_dir) or not artifact.is_file():
            return None
        return json.loads(artifact.read_text(encoding="utf-8"))

    def save_json_artifact(
        self,
        case_id: str,
        group: str,
        filename: str,
        payload: dict[str, Any],
    ) -> Path:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", group):
            raise ValueError("Nhóm artifact không hợp lệ.")
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("Tên artifact không hợp lệ.")
        case_dir = (self.artifacts_root / case_id).resolve()
        if not case_dir.is_dir() or case_dir.parent != self.artifacts_root.resolve():
            raise FileNotFoundError(f"Không tìm thấy hồ sơ: {case_id}")
        output_dir = case_dir / group
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return output_path

    def _insert_audit(
        self,
        connection: sqlite3.Connection,
        *,
        case_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        reason: str | None,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events(
                event_id, case_id, event_type, actor_type, actor_id,
                occurred_at, correlation_id, reason, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"AUD-{uuid4().hex[:12].upper()}",
                case_id,
                event_type,
                actor_type,
                actor_id,
                self.clock().isoformat(),
                f"COR-{uuid4().hex[:12].upper()}",
                reason,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
