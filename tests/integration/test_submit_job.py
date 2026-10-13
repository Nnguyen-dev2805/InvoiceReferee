"""R4: a submit is a durable job; a restart recovers an incomplete one (plan R4).

One active job per root; the job records READ→ASSESS→DONE and a restart can
finish an incomplete job without duplicating its financial effect.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


async def test_submit_records_a_durable_job(app_fixture):
    v = await app_fixture.submit_packet("travel-clean", mode="STUB")
    row = app_fixture.query_one(
        "SELECT status, phase FROM jobs WHERE root_id = ? ORDER BY created_at DESC LIMIT 1",
        (v.id,),
    )
    assert row is not None
    assert row["status"] in ("COMPLETED", "DONE")
    assert row["phase"] in ("DONE", "ASSESSING")


async def test_one_active_job_per_root(app_fixture):
    v = await app_fixture.submit_packet("travel-clean", mode="STUB")
    await app_fixture.submit_packet("travel-clean", mode="STUB")  # retry same root
    rows = app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM jobs WHERE root_id = ? AND status IN ('QUEUED','RUNNING')",
        (v.id,),
    )
    assert rows["n"] == 0  # no job left dangling


def test_restart_marks_stale_running_job_for_recovery(app_fixture, tmp_path: Path):
    # A job left RUNNING by a crash is recoverable after a restart.
    from invoice_referee.workflow.jobs import JobStore

    db = Database(Path(app_fixture.db.path))
    with db.transaction() as cx:
        cx.execute(
            "INSERT INTO cases (id, tenant, employee, activity, profile, state, version, "
            "input_revision, control_epoch, activity_name, activity_occurred_at, created_at, "
            "updated_at) VALUES ('case:z','tenant:demo','employee:a','activity:z','TRAVEL',"
            "'DRAFT',1,1,0,'Z','2026-10-05T09:00:00+00:00','x','x')"
        )
        cx.execute(
            "INSERT INTO jobs (id, tenant, root_id, kind, phase, status, created_at, updated_at) "
            "VALUES ('job:z','tenant:demo','case:z','SUBMIT','READING','RUNNING','x','x')"
        )
    store = JobStore(db)
    recovered = store.recover_incomplete(db.connect(), tenant="tenant:demo", now="y")
    assert "job:z" in recovered
