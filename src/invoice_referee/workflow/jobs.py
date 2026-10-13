"""Durable preview/read jobs (contracts §6, §10.4; plan T5).

A preview job reads the root's sources and caches the read. It has **no
financial effect**: no money, instruction or eligibility is written. One active
job per root; the job persists so a restart resumes it rather than duplicating
effects. Read results are cached by (tenant, source digest, reader config) so a
submit on the same basis reuses them instead of calling the provider again.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass

from invoice_referee.domain.evidence import ReadResult, SourceRef
from invoice_referee.evidence.trace import RunBudget


@dataclass(frozen=True)
class Job:
    id: str
    tenant: str
    root_id: str
    kind: str
    phase: str
    status: str


def _reader_config(reader: object) -> str:
    mode = getattr(reader, "mode", "STUB")
    return f"mode={mode}"


class JobStore:
    """Persistence for jobs and the read cache; no business decisions."""

    def __init__(self, db) -> None:
        self.db = db

    def active_job(self, cx: sqlite3.Connection, tenant: str, root_id: str) -> sqlite3.Row | None:
        return cx.execute(
            "SELECT * FROM jobs WHERE tenant = ? AND root_id = ? "
            "AND status IN ('QUEUED','RUNNING') ORDER BY created_at LIMIT 1",
            (tenant, root_id),
        ).fetchone()

    def enqueue(
        self, cx: sqlite3.Connection, *, tenant: str, root_id: str, kind: str, now: str
    ) -> str:
        job_id = f"job:{uuid.uuid4().hex}"
        cx.execute(
            "INSERT INTO jobs (id, tenant, root_id, kind, phase, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'READING', 'QUEUED', ?, ?)",
            (job_id, tenant, root_id, kind, now, now),
        )
        return job_id

    def mark(
        self,
        cx: sqlite3.Connection,
        job_id: str,
        *,
        phase: str,
        status: str,
        now: str,
        result: ReadResult | None = None,
    ) -> None:
        cx.execute(
            "UPDATE jobs SET phase = ?, status = ?, result_json = ?, updated_at = ? "
            "WHERE id = ?",
            (
                phase,
                status,
                result.model_dump_json() if result is not None else None,
                now,
                job_id,
            ),
        )

    def cache_read(
        self,
        cx: sqlite3.Connection,
        *,
        tenant: str,
        source_digest: str,
        reader_config: str,
        result: ReadResult,
        now: str,
    ) -> None:
        cx.execute(
            "INSERT OR REPLACE INTO read_cache (tenant, source_digest, reader_config, "
            "result_json, cached_at) VALUES (?, ?, ?, ?, ?)",
            (tenant, source_digest, reader_config, result.model_dump_json(), now),
        )

    def cached_read(
        self,
        cx: sqlite3.Connection,
        *,
        tenant: str,
        source_digest: str,
        reader_config: str,
    ) -> ReadResult | None:
        row = cx.execute(
            "SELECT result_json FROM read_cache WHERE tenant = ? AND source_digest = ? "
            "AND reader_config = ?",
            (tenant, source_digest, reader_config),
        ).fetchone()
        if row is None:
            return None
        return ReadResult.model_validate_json(row["result_json"])

    def recover_incomplete(
        self, cx: sqlite3.Connection, *, tenant: str, now: str
    ) -> list[str]:
        """Return incomplete job ids after a restart and requeue them (plan R4).

        A job left QUEUED/RUNNING by a crash is marked for recovery so the
        worker resumes it rather than duplicating its effect. Returns the ids.
        """
        rows = cx.execute(
            "SELECT id FROM jobs WHERE tenant = ? AND status IN ('QUEUED','RUNNING')",
            (tenant,),
        ).fetchall()
        ids = [str(row["id"]) for row in rows]
        for job_id in ids:
            cx.execute(
                "UPDATE jobs SET status = 'QUEUED', updated_at = ? WHERE id = ?",
                (now, job_id),
            )
        return ids


async def run_preview(
    store: JobStore,
    reader: object,
    *,
    tenant: str,
    root_id: str,
    sources: tuple[SourceRef, ...],
    requested_fields: tuple[str, ...],
    budget: RunBudget,
    now: str,
) -> ReadResult:
    """Read the root's sources with no financial effect; cache the result.

    Reuses a cached read for the same (tenant, digest, reader config); a cache
    miss calls the reader once. This is the preview path only.
    """
    config = _reader_config(reader)
    with store.db.transaction() as cx:
        job_id = store.enqueue(cx, tenant=tenant, root_id=root_id, kind="PREVIEW", now=now)
        store.mark(cx, job_id, phase="READING", status="RUNNING", now=now)

    merged_units = []
    merged_observations = []
    merged_pages: list[int] = []
    for source in sources:
        with store.db.transaction() as cx:
            cached = store.cached_read(
                cx, tenant=tenant, source_digest=source.digest, reader_config=config
            )
        if cached is not None:
            result = cached
        else:
            result = await reader.read(  # type: ignore[attr-defined]
                source, requested_fields, budget
            )
            with store.db.transaction() as cx:
                store.cache_read(
                    cx,
                    tenant=tenant,
                    source_digest=source.digest,
                    reader_config=config,
                    result=result,
                    now=now,
                )
        merged_units.extend(result.units)
        merged_observations.extend(result.observations)
        merged_pages.extend(result.page_coverage)

    merged = ReadResult(
        units=tuple(merged_units),
        observations=tuple(merged_observations),
        relations=(),
        page_coverage=tuple(merged_pages),
        problems=(),
    )
    with store.db.transaction() as cx:
        store.mark(cx, job_id, phase="DONE", status="COMPLETED", now=now, result=merged)
    return merged
