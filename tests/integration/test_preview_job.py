"""Preview job: read-only, cached, no financial effect (contracts §6, §10.4).

A preview reads sources and caches the read; it must not write any money,
instruction or eligibility row. A second preview on the same basis reuses the
cache instead of calling the reader again.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.reader import EvidenceReader
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.jobs import JobStore, run_preview


class CountingReader:
    def __init__(self) -> None:
        self.calls = 0

    async def read(self, source, requested_fields, budget, *, pages=(1,)):
        self.calls += 1
        from invoice_referee.evidence.reader import EvidenceReader

        return await EvidenceReader(mode="STUB", mistral=None).read(
            source, requested_fields, budget, pages=pages
        )


def _db(tmp: Path) -> Database:
    db = Database(tmp / "app.sqlite")
    db.migrate()
    return db


def _source() -> SourceRef:
    return SourceRef(
        id="source:1",
        digest="a" * 64,
        tenant="tenant:demo",
        media="PDF",
        storage_key="tenant:demo/case/source:1",
    )


async def test_preview_has_no_financial_effect(tmp_path: Path) -> None:
    db = _db(tmp_path)
    # A root must exist for the FK; create a minimal one.
    with db.transaction() as cx:
        cx.execute(
            "INSERT INTO cases (id, tenant, employee, activity, profile, state, version, "
            "input_revision, control_epoch, activity_name, activity_occurred_at, created_at, "
            "updated_at) VALUES ('case:1','tenant:demo','employee:a','activity:a','TRAVEL',"
            "'DRAFT',1,1,0,'A','2026-10-05T09:00:00+00:00','x','x')"
        )
    store = JobStore(db)
    reader = CountingReader()
    now = datetime(2026, 10, 13, tzinfo=UTC).isoformat()

    result = await run_preview(
        store,
        reader,
        tenant="tenant:demo",
        root_id="case:1",
        sources=(_source(),),
        requested_fields=("amount",),
        budget=RunBudget(),
        now=now,
    )
    assert result is not None

    # The preview wrote its job/cache rows but NO financial rows (the tables
    # exist from the schema, but a preview must leave them empty).
    conn = db.connect()
    try:
        tables = [
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        financial_tables = [
            t
            for t in tables
            if any(h in t for h in ("instruction", "expense", "ledger", "usage"))
        ]
        for table in ("jobs", "read_cache"):
            assert conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] >= 1
        for table in financial_tables:
            assert (
                conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0
            ), f"{table} must have no rows after a preview"
    finally:
        conn.close()


async def test_preview_reuses_cache(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db.transaction() as cx:
        cx.execute(
            "INSERT INTO cases (id, tenant, employee, activity, profile, state, version, "
            "input_revision, control_epoch, activity_name, activity_occurred_at, created_at, "
            "updated_at) VALUES ('case:1','tenant:demo','employee:a','activity:a','TRAVEL',"
            "'DRAFT',1,1,0,'A','2026-10-05T09:00:00+00:00','x','x')"
        )
    store = JobStore(db)
    reader = CountingReader()
    now = datetime(2026, 10, 13, tzinfo=UTC).isoformat()

    await run_preview(
        store, reader, tenant="tenant:demo", root_id="case:1",
        sources=(_source(),), requested_fields=("amount",), budget=RunBudget(), now=now,
    )
    first_calls = reader.calls
    await run_preview(
        store, reader, tenant="tenant:demo", root_id="case:1",
        sources=(_source(),), requested_fields=("amount",), budget=RunBudget(), now=now,
    )
    assert reader.calls == first_calls  # second preview reused the cache
