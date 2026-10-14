"""Evidence worker: drain durable evidence jobs (contracts §12.5; plan E7).

One background worker (owned by the FastAPI lifespan) claims QUEUED evidence
jobs transactionally and runs them one at a time. The worker runs the evidence
pipeline (OCR → classify → extract → validate → match), persists the typed
`ReadResult`, and sets the case to `EVIDENCE_READY` — it never calls the finance
assessment consumer. A Stop or changed basis prevents publication of the
result; private artifacts and audit are retained.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from invoice_referee.evidence.trace import RunBudget


async def run_evidence_job(workflow, job_id: str) -> None:
    """Run one evidence job and publish its typed report (plan E7).

    Delegates to the workflow's wired evidence reader/classifier. Provider I/O
    runs outside any SQLite transaction.
    """
    from invoice_referee.evidence.pipeline import read_root

    context = workflow._evidence_context(job_id)
    if context is None:
        return
    tenant, root_id, sources, source_bytes = context
    reader, classifier, artifacts, provider_mode = workflow._evidence_wiring()

    with workflow.db.transaction() as cx:
        workflow._mark_evidence_job(cx, job_id, phase="READING", status="RUNNING")
    try:
        report = await read_root(
            sources=sources,
            reader=reader,
            classifier=classifier,
            artifacts=artifacts,
            source_bytes=source_bytes,
            budget=RunBudget(),
            provider_mode=provider_mode,
            root_id=root_id,
        )
    except Exception as error:  # provider failure -> technical, never a fake success
        with workflow.db.transaction() as cx:
            workflow._fail_evidence_job(cx, job_id, error)
        return

    with workflow.db.transaction() as cx:
        # A Stop or changed input basis invalidates publication (contracts §6,
        # §12.5): a stale result must not be presented as current.
        row = cx.execute("SELECT state FROM cases WHERE id = ?", (root_id,)).fetchone()
        if row is not None and str(row["state"]) == "STOPPED":
            workflow._mark_evidence_job(cx, job_id, phase="DONE", status="CANCELLED")
            return
        job = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is not None and not workflow._evidence_basis_current(cx, job):
            workflow._mark_evidence_job(cx, job_id, phase="DONE", status="CANCELLED")
            return
        # A run that produced nothing usable (no documents, or no FOUND field at
        # all) is a technical failure, not a cheerful "ready" (never a false
        # success). The report is still stored so the reason is inspectable.
        if not _evidence_usable(report):
            workflow._fail_evidence_job(
                cx, job_id, "không đọc/trích xuất được dữ liệu dùng được từ chứng từ"
            )
            return
        workflow._publish_evidence_report(cx, tenant=tenant, root_id=root_id, report=report)
        workflow._mark_evidence_job(cx, job_id, phase="DONE", status="COMPLETED")


def _evidence_usable(report) -> bool:
    """True when the read produced at least one document with a FOUND field."""
    for document in getattr(report, "documents", ()):
        if any(field.state == "FOUND" for field in getattr(document, "fields", ())):
            return True
    return False


async def drain_evidence_jobs(workflow, stop: asyncio.Event) -> None:
    """Claim and run QUEUED evidence jobs one at a time until stopped (plan E7)."""
    while not stop.is_set():
        job_id = workflow._claim_next_evidence_job()
        if job_id is None:
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            continue
        await run_evidence_job(workflow, job_id)
