"""T04 integration tests — SQLite history, atomic request lifecycle, artifacts.

The bundle injected here comes from ``seed_case`` (persistence/fake boundary);
these tests do NOT prove OCR/PDF quality. They prove the persisted guard,
idempotency, dedup, path safety and restart behavior of the storage layer.
"""
from __future__ import annotations

import hashlib
import threading

import pytest

from invoice_referee.domain.models import (
    Claim,
    DomainError,
    PipelineResult,
    StoppedRun,
    Upload,
)
from invoice_referee.policy.decision import evaluate
from invoice_referee.storage.artifacts import put_artifact, safe_name
from invoice_referee.storage.repository import Repository
from tests.builders import demo_policy
from tests.integration.support import seed_case


def _result(snapshot, bundle):
    return PipelineResult(
        decision=evaluate(snapshot, bundle), bundle=bundle,
        artifacts=[], stage_durations_ms={}, provider_calls=0, repair_calls=0,
    )


# --- Brief step 1: idempotent finalize + history ------------------------------

def test_finalize_is_idempotent_and_keeps_history(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    result = PipelineResult(decision=evaluate(snapshot, bundle), bundle=bundle,
        artifacts=[], stage_durations_ms={}, provider_calls=0, repair_calls=0)
    repo.finalize_run(run.id, result)
    first = repo.get_payment_request(case.id)
    repo.finalize_run(run.id, result)
    assert repo.get_payment_request(case.id).id == first.id
    assert first.amount_vnd == 1_200_000 and first.status == 'CREATED'
    assert repo.history(case.id)


def test_seed_case_remaps_bundle_to_real_evidence_ids(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    real_ids = {ev.id for ev in case.evidence}
    assert bundle.documents, 'bundle should carry the seeded document'
    for doc in bundle.documents:
        assert doc.evidence_id in real_ids
        for fact in doc.fields.values():
            for ref in fact.refs:
                assert ref.evidence_id in real_ids
    assert set(bundle.registries) <= real_ids


def test_create_run_rejects_second_active_run(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    repo.create_run(snapshot)
    with pytest.raises(DomainError) as exc:
        repo.create_run(repo.snapshot(case.id, demo_policy()))
    assert exc.value.code == 'RUN_BUSY'
    # Only the first run exists; the guard left no orphan.
    rows = repo._read('SELECT COUNT(*) AS n FROM runs WHERE case_id = ?', (case.id,))
    assert rows[0]['n'] == 1


def test_superseded_run_cannot_create_request(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    superseded = repo.create_run(snapshot)
    # Simulate the hazardous precondition the create_run guard now blocks: a
    # second run becomes the case's current run while the first is still open.
    with repo._write() as conn:
        conn.execute(
            'INSERT INTO runs (id, case_id, input_hash, case_version, status, stop_requested, '
            'stage, started_at, finished_at, policy_version, threshold_version, identities_json, '
            'result_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('run-current', case.id, snapshot.input_hash, snapshot.case_version, 'RUNNING', 0,
             'created', '2026-10-04T00:00:00+00:00', None, snapshot.policy.version,
             snapshot.policy.threshold_version, '[]', None),
        )
        conn.execute('UPDATE cases SET current_run_id = ? WHERE id = ?', ('run-current', case.id))

    ended = repo.finalize_run(superseded.id, _result(snapshot, bundle))
    assert ended.status == 'FAILED'
    assert repo.get_run(superseded.id).stage == 'stale'
    assert repo.get_payment_request(case.id) is None
    stale = [e for e in repo.history(case.id) if e.kind == 'RUN_STALE']
    assert stale and stale[-1].payload.get('code') == 'STALE_VERSION'


def test_finalize_returns_stored_run_ignoring_new_result(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    # A second call with a different bundle must NOT change the stored run.
    empty = PipelineResult(decision=evaluate(snapshot, bundle.model_copy(update={'documents': []})),
                           bundle=bundle, artifacts=[], stage_durations_ms={},
                           provider_calls=0, repair_calls=0)
    again = repo.finalize_run(run.id, empty)
    assert again.result.decision.action == 'CREATE_PAYMENT_REQUEST'
    assert again.status == 'SUCCEEDED'


# --- Stop vs finalization race orderings --------------------------------------

def test_stop_before_final_creates_no_request(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    reply = repo.request_stop(run.id)
    assert reply.status == 'STOP_REQUESTED'
    assert repo.get_run(run.id).stop_requested is True
    ended = repo.finalize_run(run.id, _result(snapshot, bundle))
    assert ended.status == 'STOPPED'
    assert repo.get_payment_request(case.id) is None
    assert any(e.kind == 'STOP_REQUESTED' for e in repo.history(case.id))


def test_final_then_stop_is_already_completed(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    reply = repo.request_stop(run.id)
    assert reply.status == 'ALREADY_COMPLETED'
    assert repo.get_payment_request(case.id) is not None


def test_assert_run_current_raises_stopped(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.request_stop(run.id)
    with pytest.raises(StoppedRun) as exc:
        repo.assert_run_current(run.id)
    assert exc.value.code == 'STOPPED'


def test_concurrent_stop_and_finalize_never_leave_running(tmp_path):
    """Two real threads contend on the write lock; invariant holds either way."""
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    barrier = threading.Barrier(2)

    def stopper():
        barrier.wait()
        repo.request_stop(run.id)

    def finalizer():
        barrier.wait()
        repo.finalize_run(run.id, _result(snapshot, bundle))

    threads = [threading.Thread(target=stopper), threading.Thread(target=finalizer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not any(t.is_alive() for t in threads), 'a worker thread hung on the write lock'

    ended = repo.get_run(run.id)
    assert ended.status in {'STOPPED', 'SUCCEEDED'}
    request = repo.get_payment_request(case.id)
    # Either order is valid, but the persisted result must be self-consistent:
    if ended.status == 'STOPPED':
        assert request is None
    else:
        assert request is not None


# --- Stale version discards old result ----------------------------------------

def test_stale_snapshot_run_fails_without_touching_request(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    # A data-revising human action bumps case_version while the run is in flight.
    from tests.builders import human_action
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Công tác đã sửa'}})
    repo.apply_human_action(action)
    with pytest.raises(DomainError) as exc:
        repo.assert_run_current(run.id)
    assert exc.value.code == 'STALE_VERSION'

    ended = repo.finalize_run(run.id, _result(snapshot, bundle))
    assert ended.status == 'FAILED'
    assert repo.get_run(run.id).stage == 'stale'
    assert repo.get_payment_request(case.id) is None


# --- Intake validation --------------------------------------------------------

def test_empty_input_is_rejected(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='UNKNOWN', purpose='',
                  trip='', payer_type='PERSONAL')
    with pytest.raises(DomainError) as exc:
        repo.create_case(claim, [])
    assert exc.value.code == 'INVALID_INPUT'


def test_bool_amount_is_not_an_amount(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')
    bad = claim.model_copy(update={'requested_amount_vnd': True})
    with pytest.raises(DomainError):
        repo.create_case(bad, [])


def test_missing_amount_in_nonempty_case_is_accepted(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác demo', trip='HN', payer_type='PERSONAL')
    case = repo.create_case(claim, [])
    assert case.id
    assert case.claim.requested_amount_vnd is None


def test_unsupported_extension_is_rejected(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')
    with pytest.raises(DomainError):
        repo.create_case(claim, [Upload(original_name='x.exe', mime='application/pdf',
                                        content=b'%PDF', role='PRIMARY_BILL')])
    with pytest.raises(DomainError):
        repo.create_case(claim, [Upload(original_name='x.pdf', mime='text/plain',
                                        content=b'%PDF', role='PRIMARY_BILL')])


def test_file_and_case_size_limits(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')
    too_many = [Upload(original_name=f'{i}.pdf', mime='application/pdf', content=b'%PDF',
                       role='CONTEXT') for i in range(13)]
    with pytest.raises(DomainError):
        repo.create_case(claim, too_many)
    big = Upload(original_name='big.pdf', mime='application/pdf',
                 content=b'%PDF' + b'x' * (15 * 1024 * 1024), role='PRIMARY_BILL')
    with pytest.raises(DomainError):
        repo.create_case(claim, [big])


def test_duplicate_bytes_are_deduplicated(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')
    same = b'%PDF-1.4 identical bytes'
    uploads = [
        Upload(original_name='a.pdf', mime='application/pdf', content=same, role='PRIMARY_BILL'),
        Upload(original_name='b.pdf', mime='application/pdf', content=same, role='CONTEXT'),
    ]
    case = repo.create_case(claim, uploads)
    assert len(case.evidence) == 1


def test_no_orphan_case_when_artifact_write_fails(tmp_path, monkeypatch):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')

    import invoice_referee.storage.repository as repository_module

    def boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(repository_module, 'put_artifact', boom)
    with pytest.raises(OSError):
        repo.create_case(claim, [Upload(original_name='a.pdf', mime='application/pdf',
                                        content=b'%PDF', role='PRIMARY_BILL')])
    assert repo.list_cases() == []


# --- Artifact path safety -----------------------------------------------------

def test_safe_name_rejects_traversal_and_separators():
    for bad in ['', '.', '..', 'a/b', '..\\x', 'sub/../x']:
        with pytest.raises(ValueError):
            safe_name(bad)
    assert safe_name('receipt.pdf') == 'receipt.pdf'


def test_put_artifact_writes_atomically(tmp_path):
    path = put_artifact(tmp_path, 'case-1', 'run-1', 'raw.txt', b'hello')
    assert path.read_bytes() == b'hello'
    assert path.parent.name == 'run-1'
    assert not list(path.parent.glob('.tmp-*'))


def test_artifact_path_is_backend_owned_not_client_supplied(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    claim = Claim(employee_id='emp', profile='TRAVEL', purpose_type='BUSINESS',
                  purpose='Công tác', trip='HN', payer_type='PERSONAL')
    upload = Upload(original_name='../../etc/passwd.pdf', mime='application/pdf',
                    content=b'%PDF', role='PRIMARY_BILL')
    case = repo.create_case(claim, [upload])
    stored = case.evidence[0].stored_path
    assert '..' not in stored
    assert stored.endswith('passwd.pdf')


# --- Policy versions survive restart ------------------------------------------

def test_policy_activation_survives_restart(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    from tests.builders import demo_policy
    policy = demo_policy()
    assert repo.get_active_policy() is None
    repo.record_policy_change(policy, actor_mode='SYSTEM', reason='Kích hoạt demo')
    reopened = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    assert reopened.get_active_policy().version == policy.version


def test_record_policy_change_requires_actor_and_reason(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    with pytest.raises(DomainError):
        repo.record_policy_change(demo_policy(), actor_mode='SYSTEM', reason='  ')
    with pytest.raises(DomainError):
        repo.record_policy_change(demo_policy(), actor_mode='HUMAN', reason='x')


def test_inactive_policy_is_not_activated(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    proposed = demo_policy(active=False)
    with pytest.raises(DomainError):
        repo.record_policy_change(proposed, actor_mode='SYSTEM', reason='kích hoạt')
    assert repo.get_active_policy() is None


def test_activating_new_policy_deactivates_old(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    from invoice_referee.config import activate_demo_policy
    old = activate_demo_policy(demo_policy(active=False), 'kích hoạt lần 1')
    repo.record_policy_change(old, actor_mode='SYSTEM', reason='kích hoạt lần 1')
    new = activate_demo_policy(old, 'kích hoạt lần 2')
    repo.record_policy_change(new, actor_mode='SYSTEM', reason='kích hoạt lần 2')
    active = repo.get_active_policy()
    assert active.activation_id == new.activation_id
    # Exactly one active row may exist.
    rows = repo._read('SELECT COUNT(*) AS n FROM policy_versions WHERE active = 1')
    assert rows[0]['n'] == 1


# --- Interrupted runs ---------------------------------------------------------

def test_mark_interrupted_runs(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    assert repo.mark_interrupted_runs() == 1
    assert repo.get_run(run.id).status == 'FAILED'


def test_mark_interrupted_runs_honors_acknowledged_stop(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.request_stop(run.id)
    assert repo.mark_interrupted_runs() == 1
    assert repo.get_run(run.id).status == 'STOPPED'


# --- Lifecycle side effects ---------------------------------------------------

def test_stop_marks_case_workflow_stopped(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.request_stop(run.id)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    assert repo.get_case(case.id).workflow_state == 'STOPPED'


def test_non_create_decision_revokes_current_request(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run1 = repo.create_run(snapshot)
    repo.finalize_run(run1.id, _result(snapshot, bundle))
    assert repo.get_payment_request(case.id) is not None
    # A rerun whose decision no longer creates a request must revoke the stale one.
    empty_bundle = bundle.model_copy(update={'documents': [], 'registries': {}})
    run2 = repo.create_run(repo.snapshot(case.id, demo_policy()))
    repo.finalize_run(run2.id, _result(snapshot, empty_bundle))
    assert repo.get_payment_request(case.id) is None
    kinds = [e.kind for e in repo.history(case.id)]
    assert 'REQUEST_REVOKED' in kinds


def test_input_revision_revokes_current_request_same_transaction(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    from tests.builders import human_action
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Đã bổ sung mô tả'}})
    updated = repo.apply_human_action(action)
    assert updated.case_version == case.case_version + 1
    assert repo.get_payment_request(case.id) is None
    assert any(e.kind == 'REQUEST_REVOKED' for e in repo.history(case.id))


def test_identical_request_is_not_duplicated(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    first = repo.get_payment_request(case.id)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    assert repo.get_payment_request(case.id).id == first.id


def test_approval_does_not_change_case_version(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    from tests.builders import human_action
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER', payload={
        'amount_vnd': 1_200_000, 'profile': 'TRAVEL',
        'purpose': snapshot.claim.purpose, 'policy_version': snapshot.policy.version,
    })
    updated = repo.apply_human_action(action)
    assert updated.case_version == case.case_version
    # The approval is now an in-force authorization in the snapshot.
    rebuilt = repo.snapshot(case.id, demo_policy())
    assert rebuilt.active_action_ids == [action.id]
    assert rebuilt.authorizations[0].amount_vnd == 1_200_000


# --- Schema version guard (no migration framework) ----------------------------

def test_schema_version_is_stamped_on_open(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    from invoice_referee.storage.repository import SCHEMA_VERSION
    row = repo._read_one("SELECT value FROM schema_meta WHERE key = 'version'")
    assert row['value'] == SCHEMA_VERSION


def test_incompatible_schema_version_is_refused(tmp_path):
    db = tmp_path / 'cases.sqlite'
    repo = Repository(db, tmp_path / 'artifacts')
    with repo._write() as conn:
        conn.execute("UPDATE schema_meta SET value = '1' WHERE key = 'version'")
    with pytest.raises(DomainError) as exc:
        Repository(db, tmp_path / 'artifacts')
    assert exc.value.code == 'INVALID_INPUT'
    assert 'schema' in exc.value.message.lower()


def test_legacy_db_without_schema_meta_is_refused(tmp_path):
    """A pre-change DB (old global issues(id) PK, no schema_meta) must be refused.

    Regression for the finding that a missing schema_meta row was silently
    stamped v2 while keeping the incompatible DDL, so the second run died with
    ``UNIQUE constraint failed: issues.id``. The guard must inspect the ACTUAL
    schema, not default on a missing row.
    """
    import sqlite3

    db = tmp_path / 'legacy.sqlite'
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE cases (id TEXT PRIMARY KEY, case_version INTEGER NOT NULL,
          workflow_state TEXT NOT NULL, current_run_id TEXT, input_hash TEXT NOT NULL DEFAULT '',
          claim_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE runs (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, input_hash TEXT NOT NULL,
          case_version INTEGER NOT NULL, status TEXT NOT NULL, stop_requested INTEGER NOT NULL DEFAULT 0,
          stage TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, policy_version TEXT NOT NULL,
          threshold_version TEXT NOT NULL, identities_json TEXT NOT NULL DEFAULT '[]', result_json TEXT);
        -- The OLD global-PK shape this change replaced:
        CREATE TABLE issues (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
          stable_key TEXT NOT NULL, issue_class TEXT NOT NULL, owner_mode TEXT NOT NULL,
          status TEXT NOT NULL, payload_json TEXT NOT NULL);
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(DomainError) as exc:
        Repository(db, tmp_path / 'artifacts')
    assert exc.value.code == 'INVALID_INPUT'
    assert str(db) in exc.value.message
    # The legacy DB must NOT have been stamped (never silently upgraded).
    check = sqlite3.connect(str(db))
    try:
        tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert 'schema_meta' not in tables
        pk_cols = [r[1] for r in check.execute('PRAGMA table_info(issues)') if r[5]]
        assert pk_cols == ['id']  # old global PK retained, not silently changed
    finally:
        check.close()
