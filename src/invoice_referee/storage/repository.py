"""SQLite repository: history, guarded transactions and the atomic payment
request lifecycle (T04, System §6/§8/§10).

Design rulings (recorded at T04):

- **One connection per transaction.** ``_write`` opens a fresh ``sqlite3``
  connection, issues ``BEGIN IMMEDIATE`` (write lock) and commits/rolls back;
  ``_read`` opens its own connection. A connection is never shared across
  threads. Foreign keys are enabled on every connection.
- **Minimal schema, JSON payload columns.** Structured identity/version/status
  columns plus JSON blobs for the full record; no ORM, no migration framework.
  ``schema.sql`` is idempotent.
- **One current payment request per case**, enforced by a partial unique index
  ``one_current_payment_request`` over ``status='CREATED'``. Superseded/revoked
  rows are kept for history so Override can be explained.
- **``finalize_run`` is one transaction.** It re-reads run + case under the
  write lock, returns the stored run when already finalized (ignoring the new
  result), ends a stopped/stale run without inserting, and persists
  decision/issues/events/payment request atomically.
- **Stop and finalization share the lock.** ``request_stop`` returns
  ``ALREADY_COMPLETED`` once the final commit landed; otherwise it persists the
  stop flag + event before acknowledging. ``assert_run_current`` raises
  ``StoppedRun`` on a stop flag and ``STALE_VERSION`` on changed input.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from invoice_referee.config import snapshot_hash
from invoice_referee.domain.models import (
    AuditEvent,
    Authorization,
    CaseRecord,
    CaseSnapshot,
    Claim,
    DomainError,
    Evidence,
    HumanAction,
    PaymentRequest,
    PipelineResult,
    PolicyActor,
    PolicyConfig,
    RunRecord,
    StageIdentity,
    StopReply,
    StoppedRun,
    Upload,
)
from invoice_referee.storage.artifacts import put_artifact, safe_name

SCHEMA_PATH = Path(__file__).with_name('schema.sql')

ALLOWED_MIME = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXT = {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}
MAX_FILES = 12
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_CASE_BYTES = 50 * 1024 * 1024

# Kinds that change effective input data (bump case_version, revoke request).
DATA_REVISING = {
    'SUPPLY_DECLARATION', 'ADD_EVIDENCE', 'CONFIRM_FIELD', 'CONFIRM_MAPPING',
}
AUTHORIZATION_KINDS = {'GRANT_POLICY_EXCEPTION', 'APPROVE_AMOUNT'}
_TERMINAL_RUN = {'STOPPED', 'SUCCEEDED', 'FAILED'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_INPUT', message)


class Repository:
    """Structured state/history plus the guarded final-action transaction."""

    def __init__(self, db_path: Path, artifact_root: Path) -> None:
        self._db_path = Path(db_path)
        self._artifact_root = Path(artifact_root)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
        finally:
            conn.close()

    # --- connection helpers ---------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), isolation_level=None, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.execute('COMMIT')
        except BaseException:
            try:
                conn.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def _read(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _read_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        rows = self._read(sql, params)
        return rows[0] if rows else None

    def _insert_event(
        self, conn: sqlite3.Connection, *, case_id: str | None, run_id: str | None,
        case_version: int | None, kind: str, stage: str, reason: str,
        refs: list | None = None, payload: dict | None = None,
    ) -> None:
        conn.execute(
            'INSERT INTO events (id, case_id, run_id, case_version, timestamp, kind, '
            'stage, reason, refs_json, payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (
                f'evt-{uuid.uuid4().hex}', case_id, run_id, case_version, _now(),
                kind, stage, reason,
                json.dumps([r.model_dump(mode='json') for r in (refs or [])]),
                json.dumps(payload or {}),
            ),
        )

    # --- intake validation ----------------------------------------------------

    @staticmethod
    def _safe_upload_name(original_name: str) -> str:
        base = original_name.replace('\\', '/').rsplit('/', 1)[-1]
        return safe_name(base)

    def _validate_intake(self, claim: Claim, uploads: list[Upload]) -> None:
        # A meaningful expense input needs real content, not just employee
        # identity/profile/payer defaults.
        has_purpose = bool(claim.purpose and claim.purpose.strip())
        has_amount = claim.requested_amount_vnd is not None
        if not (has_purpose or has_amount or uploads):
            raise _invalid('Hồ sơ chưa có nội dung chi tiêu (thiếu purpose/số tiền/chứng từ).')

        amount = claim.requested_amount_vnd
        if amount is not None and (isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0):
            raise _invalid('Số tiền đề nghị phải là số nguyên dương VND.')

        if len(uploads) > MAX_FILES:
            raise _invalid(f'Quá {MAX_FILES} tệp cho một hồ sơ.')

        total = 0
        for upload in uploads:
            name = self._safe_upload_name(upload.original_name)
            if Path(name).suffix.lower() not in ALLOWED_EXT:
                raise _invalid(f'Định dạng tệp không hỗ trợ: {name}')
            if upload.mime.lower() not in ALLOWED_MIME:
                raise _invalid(f'Loại tệp không hỗ trợ: {upload.mime}')
            size = len(upload.content)
            if size == 0:
                raise _invalid(f'Tệp rỗng không phải chứng từ hợp lệ: {name}')
            if size > MAX_FILE_BYTES:
                raise _invalid(f'Tệp vượt 15 MiB: {name}')
            total += size
        if total > MAX_CASE_BYTES:
            raise _invalid('Tổng dung lượng tệp vượt 50 MiB cho một hồ sơ.')

    # --- cases ----------------------------------------------------------------

    def create_case(self, claim: Claim, uploads: list[Upload]) -> CaseRecord:
        self._validate_intake(claim, uploads)
        case_id = f'case-{uuid.uuid4().hex}'
        now = _now()

        seen: set[str] = set()
        staged: list[tuple[Upload, str, int]] = []
        for upload in uploads:
            data = bytes(upload.content)
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:  # same bytes are not two independent sources
                continue
            seen.add(digest)
            staged.append((upload, digest, len(data)))

        written: list[Path] = []
        evidence_rows: list[Evidence] = []
        try:
            for upload, digest, size in staged:
                name = self._safe_upload_name(upload.original_name)
                path = put_artifact(self._artifact_root, case_id, 'evidence', name, upload.content)
                written.append(path)
                evidence_rows.append(Evidence(
                    id=f'ev-{uuid.uuid4().hex}', case_id=case_id, role=upload.role,
                    original_name=upload.original_name, stored_path=str(path),
                    sha256=digest, mime=upload.mime, size=size,
                ))
            with self._write() as conn:
                conn.execute(
                    'INSERT INTO cases (id, case_version, workflow_state, current_run_id, '
                    'input_hash, claim_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)',
                    (case_id, 1, 'DRAFT', None, '', claim.model_dump_json(), now, now),
                )
                for ev in evidence_rows:
                    conn.execute(
                        'INSERT INTO evidence (id, case_id, role, original_name, stored_path, '
                        'sha256, mime, size, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                        (ev.id, ev.case_id, ev.role, ev.original_name, ev.stored_path,
                         ev.sha256, ev.mime, ev.size, now),
                    )
                self._insert_event(
                    conn, case_id=case_id, run_id=None, case_version=1, kind='CASE_CREATED',
                    stage='intake', reason='Tạo hồ sơ từ khai báo và chứng từ đã tải lên.',
                    payload={'evidence_count': len(evidence_rows)},
                )
        except BaseException:
            # Never leave an orphan case: remove artifacts we created and the dirs.
            for path in written:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            for directory in (self._artifact_root / case_id / 'evidence',
                              self._artifact_root / case_id):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> CaseRecord:
        row = self._read_one('SELECT * FROM cases WHERE id = ?', (case_id,))
        if row is None:
            raise DomainError('NOT_FOUND', f'Không tìm thấy hồ sơ {case_id}.')
        return self._case_from_row(row)

    def list_cases(self) -> list[CaseRecord]:
        rows = self._read('SELECT * FROM cases ORDER BY created_at, id')
        return [self._case_from_row(row) for row in rows]

    def _case_from_row(self, row: sqlite3.Row) -> CaseRecord:
        evidence = [
            self._evidence_from_row(e)
            for e in self._read('SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at, id', (row['id'],))
        ]
        return CaseRecord(
            id=row['id'], case_version=row['case_version'],
            claim=Claim.model_validate_json(row['claim_json']),
            current_run_id=row['current_run_id'], workflow_state=row['workflow_state'],
            evidence=evidence,
        )

    @staticmethod
    def _evidence_from_row(row: sqlite3.Row) -> Evidence:
        return Evidence(
            id=row['id'], case_id=row['case_id'], role=row['role'],
            original_name=row['original_name'], stored_path=row['stored_path'],
            sha256=row['sha256'], mime=row['mime'], size=row['size'],
        )

    def snapshot(self, case_id: str, policy: PolicyConfig) -> CaseSnapshot:
        case = self.get_case(case_id)
        actions = self._list_actions(case_id)
        authorizations = self._authorizations(case, actions)
        active_ids = [a.id for a in actions if a.case_version == case.case_version]
        snap = CaseSnapshot(
            case_id=case.id, case_version=case.case_version, claim=case.claim,
            evidence=case.evidence, policy=policy, authorizations=authorizations,
            confirmations=actions, active_action_ids=active_ids, input_hash='',
        )
        return snap.model_copy(update={'input_hash': snapshot_hash(snap)})

    # --- runs -----------------------------------------------------------------

    def create_run(self, snapshot: CaseSnapshot) -> RunRecord:
        run_id = f'run-{uuid.uuid4().hex}'
        now = _now()
        with self._write() as conn:
            case = conn.execute('SELECT * FROM cases WHERE id = ?', (snapshot.case_id,)).fetchone()
            if case is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy hồ sơ {snapshot.case_id}.')
            # The repository is the final persisted guard: at most one active
            # run per case. T08's one-slot executor is an additional guard, not a
            # replacement. A second active run would let a superseded result
            # reach finalization, so reject it here.
            active = conn.execute(
                "SELECT id FROM runs WHERE case_id = ? AND status IN ('QUEUED','RUNNING') LIMIT 1",
                (snapshot.case_id,),
            ).fetchone()
            if active is not None:
                raise DomainError(
                    'RUN_BUSY', f"Hồ sơ {snapshot.case_id} đang có run {active['id']} chạy."
                )
            conn.execute(
                'INSERT INTO runs (id, case_id, input_hash, case_version, status, stop_requested, '
                'stage, started_at, finished_at, policy_version, threshold_version, identities_json, '
                'result_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (run_id, snapshot.case_id, snapshot.input_hash, snapshot.case_version, 'RUNNING', 0,
                 'created', now, None, snapshot.policy.version, snapshot.policy.threshold_version,
                 '[]', None),
            )
            conn.execute(
                'UPDATE cases SET current_run_id = ?, workflow_state = ?, input_hash = ?, '
                'updated_at = ? WHERE id = ?',
                (run_id, 'REVIEWING', snapshot.input_hash, now, snapshot.case_id),
            )
            self._insert_event(
                conn, case_id=snapshot.case_id, run_id=run_id, case_version=snapshot.case_version,
                kind='RUN_STARTED', stage='created',
                reason='Bắt đầu chạy kiểm tra cho snapshot hiện hành.',
                payload={'input_hash': snapshot.input_hash},
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> RunRecord:
        row = self._read_one('SELECT * FROM runs WHERE id = ?', (run_id,))
        if row is None:
            raise DomainError('NOT_FOUND', f'Không tìm thấy run {run_id}.')
        return self._run_from_row(row)

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> RunRecord:
        identities = [StageIdentity.model_validate(i) for i in json.loads(row['identities_json'])]
        result = PipelineResult.model_validate_json(row['result_json']) if row['result_json'] else None
        return RunRecord(
            id=row['id'], case_id=row['case_id'], input_hash=row['input_hash'],
            case_version=row['case_version'], status=row['status'],
            stop_requested=bool(row['stop_requested']), stage=row['stage'],
            started_at=_dt(row['started_at']), finished_at=_dt(row['finished_at']),
            policy_version=row['policy_version'], threshold_version=row['threshold_version'],
            identities=identities, result=result,
        )

    def record_stage(
        self, run_id: str, stage: str, identity: StageIdentity | None, reason: str
    ) -> None:
        with self._write() as conn:
            row = conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
            if row is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy run {run_id}.')
            identities = json.loads(row['identities_json'])
            if identity is not None:
                identities.append(identity.model_dump(mode='json'))
            conn.execute(
                'UPDATE runs SET stage = ?, identities_json = ? WHERE id = ?',
                (stage, json.dumps(identities), run_id),
            )
            self._insert_event(
                conn, case_id=row['case_id'], run_id=run_id, case_version=row['case_version'],
                kind='STAGE', stage=stage, reason=reason,
                payload={'identity': identity.model_dump(mode='json')} if identity else {},
            )

    def request_stop(self, run_id: str) -> StopReply:
        with self._write() as conn:
            row = conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
            if row is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy run {run_id}.')
            status = row['status']
            if status in _TERMINAL_RUN:
                # Final commit already happened (or the run already ended):
                # acknowledge reality instead of pretending we prevented it.
                return StopReply(status='ALREADY_COMPLETED', run_id=run_id)
            if status == 'STOP_REQUESTED':
                return StopReply(status='STOP_REQUESTED', run_id=run_id)
            conn.execute(
                'UPDATE runs SET status = ?, stop_requested = 1, stage = ? WHERE id = ?',
                ('STOP_REQUESTED', 'stop-requested', run_id),
            )
            self._insert_event(
                conn, case_id=row['case_id'], run_id=run_id, case_version=row['case_version'],
                kind='STOP_REQUESTED', stage='stop',
                reason='Người thao tác yêu cầu dừng run; không áp dụng kết quả muộn.',
            )
            return StopReply(status='STOP_REQUESTED', run_id=run_id)

    def assert_run_current(self, run_id: str) -> None:
        row = self._read_one('SELECT * FROM runs WHERE id = ?', (run_id,))
        if row is None:
            raise DomainError('NOT_FOUND', f'Không tìm thấy run {run_id}.')
        if row['stop_requested'] or row['status'] == 'STOP_REQUESTED':
            raise StoppedRun()
        case = self._read_one('SELECT * FROM cases WHERE id = ?', (row['case_id'],))
        if case is None:
            raise DomainError('NOT_FOUND', f"Không tìm thấy hồ sơ {row['case_id']}.")
        if case['case_version'] != row['case_version'] or case['input_hash'] != row['input_hash']:
            raise DomainError('STALE_VERSION', 'Snapshot đã thay đổi; kết quả không còn hiện hành.')

    def finalize_run(self, run_id: str, result: PipelineResult) -> RunRecord:
        with self._write() as conn:
            run = conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
            if run is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy run {run_id}.')
            case_id = run['case_id']

            # Already finalized: return the STORED run, ignore the incoming result.
            if run['status'] in _TERMINAL_RUN:
                return self._run_from_row(run)

            now = _now()

            # Stop acknowledged: end the run STOPPED, keep diagnostics, no insert.
            if run['stop_requested'] or run['status'] == 'STOP_REQUESTED':
                conn.execute(
                    'UPDATE runs SET status = ?, finished_at = ?, stage = ? WHERE id = ?',
                    ('STOPPED', now, 'stopped', run_id),
                )
                conn.execute(
                    "UPDATE cases SET workflow_state = 'STOPPED', updated_at = ? WHERE id = ?",
                    (now, case_id),
                )
                self._insert_event(
                    conn, case_id=case_id, run_id=run_id, case_version=run['case_version'],
                    kind='RUN_STOPPED', stage='stop',
                    reason='Run dừng theo yêu cầu; kết quả muộn không được áp dụng.',
                )
                return self._run_from_row(
                    conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
                )

            case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
            if case is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy hồ sơ {case_id}.')

            # A superseded run (no longer the case's current run) must never write
            # a request, even when its version/hash still happen to match. End it
            # FAILED/STALE_VERSION with diagnostics; do not touch the current run.
            if case['current_run_id'] != run_id:
                return self._end_stale_run(
                    conn, run_id, case_id, run, result,
                    'Run không còn là run hiện hành của hồ sơ; kết quả bị loại bỏ.',
                )

            # Stale snapshot: end FAILED/STALE_VERSION, keep diagnostics, do not
            # touch current case/run/request.
            if case['case_version'] != run['case_version'] or case['input_hash'] != run['input_hash']:
                return self._end_stale_run(
                    conn, run_id, case_id, run, result,
                    'Snapshot/version đã đổi; kết quả cũ bị loại bỏ (không đổi request hiện hành).',
                )

            # --- Normal finalization -------------------------------------------
            decision = result.decision
            run_status = 'FAILED' if decision.technical_code else 'SUCCEEDED'
            state = self._workflow_state(decision)
            payment_ok = decision.action == 'CREATE_PAYMENT_REQUEST'
            if payment_ok and not self._valid_request(decision):
                # Fail closed: a CREATE without a positive VND amount and a valid
                # basis never becomes a request.
                payment_ok = False
                run_status = 'FAILED'
                state = 'TECHNICAL_ERROR'
                self._insert_event(
                    conn, case_id=case_id, run_id=run_id, case_version=run['case_version'],
                    kind='REQUEST_GUARD_FAILED', stage='payment',
                    reason='CREATE thiếu amount VND dương/basis hợp lệ; không tạo request.',
                    payload={'accepted_amount_vnd': decision.accepted_amount_vnd,
                             'completion_basis': decision.completion_basis},
                )

            conn.execute(
                'UPDATE runs SET status = ?, finished_at = ?, stage = ?, identities_json = ?, '
                'result_json = ? WHERE id = ?',
                (run_status, now, 'finalized', json.dumps(
                    [i.model_dump(mode='json') for i in result.identities]), result.model_dump_json(), run_id),
            )
            conn.execute('DELETE FROM issues WHERE run_id = ?', (run_id,))
            for issue in decision.issues:
                conn.execute(
                    'INSERT INTO issues (id, run_id, case_id, stable_key, issue_class, owner_mode, '
                    'status, payload_json) VALUES (?,?,?,?,?,?,?,?)',
                    (issue.id, run_id, case_id, issue.stable_key, issue.issue_class,
                     issue.owner_mode, issue.status, issue.model_dump_json()),
                )
            conn.execute(
                'INSERT OR REPLACE INTO decisions (run_id, case_id, action, completion_basis, '
                'accepted_amount_vnd, technical_code, payload_json) VALUES (?,?,?,?,?,?,?)',
                (run_id, case_id, decision.action, decision.completion_basis,
                 decision.accepted_amount_vnd, decision.technical_code, decision.model_dump_json()),
            )
            self._insert_event(
                conn, case_id=case_id, run_id=run_id, case_version=run['case_version'],
                kind='RUN_FINALIZED', stage='finalized',
                reason=f'Kết quả: {decision.action}.',
                payload={'action': decision.action, 'technical_code': decision.technical_code,
                         'completion_basis': decision.completion_basis},
            )
            conn.execute(
                'UPDATE cases SET workflow_state = ?, updated_at = ? WHERE id = ?',
                (state, now, case_id),
            )
            if payment_ok:
                self._ensure_payment_request(conn, case, run, decision)
            else:
                # A decision that no longer creates a request must not leave a
                # stale current request standing (fail closed).
                self._revoke_current_request(
                    conn, case_id, run_id, run['case_version'],
                    reason=f'Decision hiện hành là {decision.action}; request cũ không còn hiệu lực.',
                )

            return self._run_from_row(
                conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
            )

    @staticmethod
    def _valid_request(decision) -> bool:
        amount = decision.accepted_amount_vnd
        basis = decision.completion_basis
        return (
            isinstance(amount, int) and not isinstance(amount, bool) and amount > 0
            and basis in ('ROUTINE_AUTO', 'HUMAN_AUTHORIZED')
        )

    @staticmethod
    def _workflow_state(decision) -> str:
        if decision.technical_code:
            return 'TECHNICAL_ERROR'
        return {
            'CREATE_PAYMENT_REQUEST': 'REQUEST_CREATED',
            'REQUEST_INFO': 'WAITING_INPUT',
            'ESCALATE': 'WAITING_APPROVAL',
            'REJECT': 'REJECTED',
        }.get(decision.action, 'REVIEWING')

    def _ensure_payment_request(
        self, conn: sqlite3.Connection, case: sqlite3.Row, run: sqlite3.Row, decision
    ) -> None:
        claim = Claim.model_validate_json(case['claim_json'])
        amount = decision.accepted_amount_vnd
        basis = decision.completion_basis
        payee = claim.employee_id
        policy_version = run['policy_version']

        existing = conn.execute(
            "SELECT * FROM payment_requests WHERE case_id = ? AND status = 'CREATED'", (case['id'],)
        ).fetchone()
        if existing is not None:
            if (existing['amount_vnd'] == amount and existing['completion_basis'] == basis
                    and existing['payee'] == payee and existing['policy_version'] == policy_version):
                # Identical current request: keep it and create nothing. The
                # existing row's run_id intentionally keeps pointing at the FIRST
                # run that produced it, so request identity stays stable across a
                # repeated (idempotent) finalize.
                return
            conn.execute("UPDATE payment_requests SET status = 'SUPERSEDED' WHERE id = ?", (existing['id'],))
            self._insert_event(
                conn, case_id=case['id'], run_id=run['id'], case_version=run['case_version'],
                kind='REQUEST_SUPERSEDED', stage='payment',
                reason='Decision mới thay thế request hiện hành; bản cũ giữ lại để giải thích Override.',
                payload={'superseded_request_id': existing['id']},
            )

        request_id = f'pr-{uuid.uuid4().hex}'
        conn.execute(
            'INSERT INTO payment_requests (id, case_id, run_id, payee, amount_vnd, currency, '
            'completion_basis, status, policy_version, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (request_id, case['id'], run['id'], payee, amount, 'VND', basis, 'CREATED',
             policy_version, _now()),
        )
        self._insert_event(
            conn, case_id=case['id'], run_id=run['id'], case_version=run['case_version'],
            kind='REQUEST_CREATED', stage='payment',
            reason='Tạo payment request cho accepted amount.',
            payload={'request_id': request_id, 'amount_vnd': amount, 'completion_basis': basis},
        )

    def _end_stale_run(
        self, conn: sqlite3.Connection, run_id: str, case_id: str,
        run: sqlite3.Row, result: PipelineResult, reason: str,
    ) -> RunRecord:
        """End a superseded/stale run FAILED with a stable ``STALE_VERSION`` code.

        Diagnostics (the incoming result + reason) are kept so Verify can assert
        the code; the current case/run/request are left untouched.
        """
        conn.execute(
            'UPDATE runs SET status = ?, finished_at = ?, stage = ?, result_json = ? WHERE id = ?',
            ('FAILED', _now(), 'stale', result.model_dump_json(), run_id),
        )
        self._insert_event(
            conn, case_id=case_id, run_id=run_id, case_version=run['case_version'],
            kind='RUN_STALE', stage='stale', reason=reason,
            payload={'code': 'STALE_VERSION'},
        )
        return self._run_from_row(
            conn.execute('SELECT * FROM runs WHERE id = ?', (run_id,)).fetchone()
        )

    def _revoke_current_request(
        self, conn: sqlite3.Connection, case_id: str, run_id: str | None,
        case_version: int | None, *, reason: str,
    ) -> None:
        current = conn.execute(
            "SELECT id FROM payment_requests WHERE case_id = ? AND status = 'CREATED'", (case_id,)
        ).fetchone()
        if current is None:
            return
        conn.execute("UPDATE payment_requests SET status = 'REVOKED' WHERE id = ?", (current['id'],))
        self._insert_event(
            conn, case_id=case_id, run_id=run_id, case_version=case_version,
            kind='REQUEST_REVOKED', stage='payment', reason=reason,
            payload={'revoked_request_id': current['id']},
        )

    def mark_interrupted_runs(self) -> int:
        with self._write() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE status IN ('QUEUED','RUNNING','STOP_REQUESTED')"
            ).fetchall()
            now = _now()
            for row in rows:
                # An acknowledged stop is honored as STOPPED; a genuinely
                # in-flight run becomes FAILED (technical interruption). Neither
                # is auto-rerun.
                if row['status'] == 'STOP_REQUESTED' or row['stop_requested']:
                    status, stage, kind = 'STOPPED', 'stopped', 'RUN_STOPPED'
                    reason = 'Run đã được yêu cầu dừng trước khi app khởi động lại.'
                else:
                    status, stage, kind = 'FAILED', 'interrupted', 'RUN_INTERRUPTED'
                    reason = ('App khởi động lại khi run còn dang dở; '
                              'không tự chạy lại business action.')
                conn.execute(
                    'UPDATE runs SET status = ?, finished_at = ?, stage = ? WHERE id = ?',
                    (status, now, stage, row['id']),
                )
                self._insert_event(
                    conn, case_id=row['case_id'], run_id=row['id'], case_version=row['case_version'],
                    kind=kind, stage=stage, reason=reason,
                )
            return len(rows)

    # --- payment requests -----------------------------------------------------

    def get_payment_request(self, case_id: str) -> PaymentRequest | None:
        row = self._read_one(
            "SELECT * FROM payment_requests WHERE case_id = ? AND status = 'CREATED' "
            'ORDER BY created_at DESC, id DESC LIMIT 1',
            (case_id,),
        )
        return self._payment_from_row(row) if row is not None else None

    @staticmethod
    def _payment_from_row(row: sqlite3.Row) -> PaymentRequest:
        return PaymentRequest(
            id=row['id'], case_id=row['case_id'], run_id=row['run_id'], payee=row['payee'],
            amount_vnd=row['amount_vnd'], currency=row['currency'],
            completion_basis=row['completion_basis'], status=row['status'],
            policy_version=row['policy_version'],
        )

    # --- human actions --------------------------------------------------------

    def _list_actions(self, case_id: str) -> list[HumanAction]:
        rows = self._read(
            'SELECT * FROM human_actions WHERE case_id = ? ORDER BY created_at, id', (case_id,)
        )
        return [self._action_from_row(row) for row in rows]

    @staticmethod
    def _action_from_row(row: sqlite3.Row) -> HumanAction:
        return HumanAction(
            id=row['id'], case_id=row['case_id'], case_version=row['case_version'],
            issue_id=row['issue_id'], mode=row['mode'], kind=row['kind'],
            payload=json.loads(row['payload_json']), reason=row['reason'],
            created_at=_dt(row['created_at']),
        )

    @staticmethod
    def _authorizations(case: CaseRecord, actions: list[HumanAction]) -> list[Authorization]:
        authorizations: list[Authorization] = []
        for action in actions:
            if action.kind not in AUTHORIZATION_KINDS or action.case_version != case.case_version:
                continue
            payload = action.payload
            try:
                authorizations.append(Authorization(
                    action_id=action.id,
                    kind='POLICY_EXCEPTION' if action.kind == 'GRANT_POLICY_EXCEPTION' else 'AMOUNT_APPROVAL',
                    case_version=action.case_version,
                    policy_version=payload['policy_version'],
                    profile=payload['profile'],
                    purpose=payload['purpose'],
                    amount_vnd=payload['amount_vnd'],
                    mode=action.mode,
                    reason=action.reason,
                ))
            except (KeyError, ValueError):
                # Incomplete payloads are validated by T07 before apply; skip here.
                continue
        return authorizations

    def apply_human_action(self, action: HumanAction) -> CaseRecord:
        now = _now()
        with self._write() as conn:
            case = conn.execute('SELECT * FROM cases WHERE id = ?', (action.case_id,)).fetchone()
            if case is None:
                raise DomainError('NOT_FOUND', f'Không tìm thấy hồ sơ {action.case_id}.')
            if action.case_version != case['case_version']:
                raise DomainError('STALE_VERSION', 'Hành động gắn với case_version cũ.')

            conn.execute(
                'INSERT INTO human_actions (id, case_id, case_version, issue_id, mode, kind, reason, '
                'payload_json, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (action.id, action.case_id, action.case_version, action.issue_id, action.mode,
                 action.kind, action.reason, json.dumps(action.payload), action.created_at.isoformat()),
            )
            self._insert_event(
                conn, case_id=action.case_id, run_id=case['current_run_id'],
                case_version=case['case_version'], kind=f'HUMAN_ACTION:{action.kind}', stage='human',
                reason=action.reason, payload={'mode': action.mode, 'issue_id': action.issue_id},
            )

            new_version = case['case_version']
            workflow = case['workflow_state']
            dirty = False
            revoke = False

            if action.kind in DATA_REVISING:
                new_version += 1
                dirty = True
                revoke = True
                if action.kind == 'SUPPLY_DECLARATION':
                    changes = action.payload.get('changes', {})
                    merged = {**Claim.model_validate_json(case['claim_json']).model_dump(), **changes}
                    claim = Claim.model_validate(merged)
                    conn.execute('UPDATE cases SET claim_json = ? WHERE id = ?',
                                 (claim.model_dump_json(), action.case_id))
            elif action.kind == 'DENY':
                workflow = 'REJECTED'
                dirty = True
                revoke = True
            elif action.kind in AUTHORIZATION_KINDS or action.kind == 'OVERRIDE':
                # Approvals do not change the data version, but active action IDs
                # (and thus the snapshot hash) change, so the hash must be redone.
                dirty = True
            # PROPOSE_CORRECTION records a proposal only — not an effective fact.

            if revoke:
                conn.execute(
                    "UPDATE payment_requests SET status = 'REVOKED' WHERE case_id = ? AND status = 'CREATED'",
                    (action.case_id,),
                )
                self._insert_event(
                    conn, case_id=action.case_id, run_id=case['current_run_id'],
                    case_version=new_version, kind='REQUEST_REVOKED', stage='payment',
                    reason='Input thay đổi làm request hiện hành hết hiệu lực.',
                )

            conn.execute(
                'UPDATE cases SET case_version = ?, workflow_state = ?, input_hash = ?, '
                'updated_at = ? WHERE id = ?',
                (new_version, workflow, '' if dirty else case['input_hash'], now, action.case_id),
            )

        return self.get_case(action.case_id)

    # --- history --------------------------------------------------------------

    def history(self, case_id: str) -> list[AuditEvent]:
        rows = self._read(
            'SELECT * FROM events WHERE case_id = ? ORDER BY timestamp, rowid', (case_id,)
        )
        return [self._event_from_row(row) for row in rows]

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            id=row['id'], case_id=row['case_id'], run_id=row['run_id'],
            case_version=row['case_version'], timestamp=_dt(row['timestamp']),
            kind=row['kind'], stage=row['stage'], reason=row['reason'],
            refs=json.loads(row['refs_json']), payload=json.loads(row['payload_json']),
        )

    # --- policy versions ------------------------------------------------------

    def record_policy_change(
        self, policy: PolicyConfig, actor_mode: PolicyActor, reason: str
    ) -> None:
        if actor_mode not in ('POLICY_OWNER', 'SYSTEM'):
            raise _invalid('actor_mode phải là POLICY_OWNER hoặc SYSTEM.')
        if not reason or not reason.strip():
            raise _invalid('Cần lý do cho thay đổi policy.')
        if not policy.active:
            # Only an explicitly activated config becomes the persisted active
            # policy; a proposed/inactive file must never be silently activated.
            raise _invalid('Chỉ policy đã active mới được ghi nhận là active.')
        config_hash = hashlib.sha256(
            json.dumps(policy.model_dump(mode='json'), sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        with self._write() as conn:
            conn.execute('UPDATE policy_versions SET active = 0 WHERE active = 1')
            conn.execute(
                'INSERT INTO policy_versions (version, config_hash, activation_id, '
                'threshold_version, active, payload_json, created_at) VALUES (?,?,?,?,?,?,?)',
                (policy.version, config_hash, policy.activation_id, policy.threshold_version, 1,
                 policy.model_dump_json(), _now()),
            )
            self._insert_event(
                conn, case_id=None, run_id=None, case_version=None, kind='POLICY_CHANGE',
                stage='policy', reason=reason,
                payload={'actor_mode': actor_mode, 'config_hash': config_hash,
                         'version': policy.version, 'activation_id': policy.activation_id,
                         'threshold_version': policy.threshold_version,
                         'automatic': actor_mode == 'SYSTEM'},
            )

    def get_active_policy(self) -> PolicyConfig | None:
        row = self._read_one(
            'SELECT payload_json FROM policy_versions WHERE active = 1 ORDER BY id DESC LIMIT 1'
        )
        return PolicyConfig.model_validate_json(row['payload_json']) if row is not None else None
