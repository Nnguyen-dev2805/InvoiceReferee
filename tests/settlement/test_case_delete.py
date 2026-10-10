"""Case deletion + system-case origin (bounded feature).

A case is removed from the DB (every child table) and its artifacts are
removed from disk. ``origin`` marks system-seeded cases so the UI can tag
them; system cases are still deletable. Fake/local only — no LIVE providers.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Command, Submission, Upload
from invoice_referee.settlement.store import Store

CHILD_TABLES = (
    "sources", "runs", "interactions", "decisions", "money_events",
    "case_revisions", "audit_events",
)


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")


def submission(work_ref="CT-01"):
    cutoff = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)
    return Submission(employee_ref="NV-01", work_ref=work_ref, job="B7",
                      money_as_of=cutoff, knowledge_cutoff=cutoff,
                      form={"purpose": "Công tác A"})


def create(store, work_ref="CT-01", key="create-1", **kwargs):
    return store.create_case(submission(work_ref), Command(
        key=key, actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}), **kwargs)


def add_source(store, case, key="src-1"):
    return store.add_source(case.id, Upload(filename="hoa-don.png",
                                            content=b"\x89PNG\r\n\x1a\n" + b"0" * 32),
                            Command(key=key, actor_id="NV-01",
                                    demo_role="EMPLOYEE",
                                    expected_case_version=case.case_version,
                                    body={}))


def _rows(store, table, case_id):
    column = "id" if table == "cases" else "case_id"
    conn = sqlite3.connect(store.db_path)
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (case_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# --- origin -------------------------------------------------------------------

def test_new_case_defaults_to_user_origin(store):
    case = create(store)
    assert case.origin == "USER"


def test_create_case_can_be_marked_system(store):
    case = create(store, origin="SYSTEM")
    assert case.origin == "SYSTEM"


def test_list_cases_exposes_origin(store):
    create(store, work_ref="CT-USER", key="u")
    create(store, work_ref="CT-SYS", key="s", origin="SYSTEM")
    by_work = {c.work_ref: c.origin for c in store.list_cases()}
    assert by_work == {"CT-USER": "USER", "CT-SYS": "SYSTEM"}


def test_migration_backfills_legacy_system_cases(tmp_path):
    db = tmp_path / "legacy.sqlite"
    # A DB that predates the ``origin`` column: build the legacy ``cases``
    # table by hand (no origin), then open it with Store to migrate.
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE cases (id TEXT PRIMARY KEY, case_version INTEGER NOT NULL, "
        "input_revision INTEGER NOT NULL, control_epoch INTEGER NOT NULL, "
        "stop_active INTEGER NOT NULL, stage TEXT NOT NULL, current_run_id TEXT, "
        "submission_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    now = "2026-10-08T11:00:00+00:00"
    for case_id, work_ref in (("C-a", "CT-E2E-01"), ("C-b", "WORK-DEMO-01"),
                              ("C-c", "CT-DEBUG-2"), ("C-d", "CT-USER-9")):
        conn.execute(
            "INSERT INTO cases (id, case_version, input_revision, control_epoch, "
            "stop_active, stage, current_run_id, submission_json, created_at, "
            "updated_at) VALUES (?, 1, 1, 1, 0, 'CHECKING', NULL, ?, ?, ?)",
            (case_id, Submission(employee_ref="NV-01", work_ref=work_ref,
                                 job="B7", money_as_of=datetime(2026, 10, 8, tzinfo=timezone.utc),
                                 knowledge_cutoff=datetime(2026, 10, 8, tzinfo=timezone.utc),
                                 form={}).model_dump_json(), now, now),
        )
    conn.commit()
    conn.close()

    by_id = {c.id: c.origin for c in Store(db, tmp_path / "artifacts").list_cases()}
    assert by_id["C-a"] == "SYSTEM"
    assert by_id["C-b"] == "SYSTEM"
    assert by_id["C-c"] == "SYSTEM"
    assert by_id["C-d"] == "USER"


# --- delete -------------------------------------------------------------------

def test_delete_case_removes_all_rows_and_artifacts(store):
    case = create(store)
    add_source(store, case)
    assert _rows(store, "cases", case.id) == 1
    assert _rows(store, "sources", case.id) == 1

    store.delete_case(case.id)

    for table in ("cases",) + CHILD_TABLES:
        assert _rows(store, table, case.id) == 0, table
    # Artifacts directory for the case is gone.
    assert not (store.artifact_root / case.id).exists()
    # Listing no longer returns it.
    assert all(c.id != case.id for c in store.list_cases())


def test_delete_case_is_idempotent_or_not_found(store):
    with pytest.raises(DomainError) as error:
        store.delete_case("C-does-not-exist")
    assert error.value.code == "CASE_NOT_FOUND"


def test_delete_refused_while_run_is_active(store):
    case = create(store)
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT INTO runs (id, case_id, input_revision, control_epoch, status, "
        "mode, snapshot_json, created_at, updated_at) "
        "VALUES ('R-run', ?, 1, 1, 'RUNNING', 'FAKE_OR_REPLAY', '{}', ?, ?)",
        (case.id, "2026-10-08T11:00:00+00:00", "2026-10-08T11:00:00+00:00"))
    conn.commit()
    conn.close()

    with pytest.raises(DomainError) as error:
        store.delete_case(case.id)
    assert error.value.code == "CASE_BUSY"
    # Case still present after a refused delete.
    assert _rows(store, "cases", case.id) == 1


def test_delete_system_case_is_allowed(store):
    case = create(store, work_ref="CT-E2E-99", origin="SYSTEM")
    store.delete_case(case.id)
    assert _rows(store, "cases", case.id) == 0
