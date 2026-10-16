"""Evidence worker: drain durable evidence jobs (contracts §12.5; plan E7).

One background worker (owned by the FastAPI lifespan) claims QUEUED evidence
jobs transactionally and runs them one at a time. The worker runs the evidence
pipeline (OCR → classify → extract → validate → match), persists the typed
`ReadResult`, and sets the case to `EVIDENCE_READY` — it never calls the finance
assessment consumer. A Stop or changed basis prevents publication of the
result; private artifacts and audit are retained.

16/10/2026 refinement: role-aware reads (paper/evidence extraction without a
standalone whole-set classification call) when every source carries an
upload_role; legacy classify-then-extract otherwise. Budget counters and
finished-doc checkpoints persist in jobs.attempts_json so a retry/resume
continues the same logical pass without resetting quota. A partial pass with
blocking TECHNICAL problems stores its checkpoint as TECHNICAL_ERROR — never
assessed, never money.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

from invoice_referee.evidence.trace import RunBudget


def _load_checkpoint(job_row) -> tuple[RunBudget, dict[str, object], dict]:
    """Restore budget counters + finished docs from jobs.attempts_json."""
    budget = RunBudget()
    docs: dict[str, object] = {}
    try:
        data = json.loads(job_row["attempts_json"] or "{}")
    except (TypeError, ValueError):
        return budget, docs, {}
    if not isinstance(data, dict):
        return budget, docs, {}
    try:
        budget.llm_attempts = int(data.get("llm_attempts", 0))
        budget.ocr_attempts = int(data.get("ocr_attempts", 0))
        budget.schema_repairs = int(data.get("schema_repairs", 0))
    except (TypeError, ValueError):
        pass
    raw_docs = data.get("docs")
    if isinstance(raw_docs, dict):
        from invoice_referee.domain.documents import DocumentAnalysis

        for source_id, payload in raw_docs.items():
            try:
                if isinstance(payload, str):
                    docs[str(source_id)] = DocumentAnalysis.model_validate_json(payload)
                else:
                    docs[str(source_id)] = DocumentAnalysis.model_validate(payload)
            except Exception:
                continue
    return budget, docs, data if isinstance(data, dict) else {}


def _save_checkpoint(
    workflow, job_id: str, budget: RunBudget, docs: dict[str, object]
) -> None:
    """Persist budget counters + finished docs (outside any business txn)."""
    try:
        from invoice_referee.domain.documents import DocumentAnalysis

        # Strict DTOs roundtrip through JSON text (a plain dict keeps lists
        # where frozen tuples belong and fails strict validation).
        encoded = {
            source_id: doc.model_dump_json()
            if isinstance(doc, DocumentAnalysis)
            else doc
            for source_id, doc in docs.items()
        }
    except Exception:
        encoded = {}
    with workflow.db.transaction() as cx:
        row = cx.execute(
            "SELECT attempts_json FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        try:
            data = json.loads(row["attempts_json"] or "{}") if row is not None else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.update(
            {
                "llm_attempts": budget.llm_attempts,
                "ocr_attempts": budget.ocr_attempts,
                "schema_repairs": budget.schema_repairs,
                "docs": encoded,
            }
        )
        cx.execute(
            "UPDATE jobs SET attempts_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), workflow._now_iso(), job_id),
        )


def _has_blocking_technical(report) -> bool:
    for problem in getattr(report, "problems", ()):
        if getattr(problem, "kind", None) == "TECHNICAL" and getattr(
            problem, "blocking", False
        ):
            return True
    return False


async def run_evidence_job(workflow, job_id: str) -> None:
    """Run one evidence job and publish its typed report (plan E7).

    Delegates to the workflow's wired evidence reader/classifier. Provider I/O
    runs outside any SQLite transaction.
    """
    from invoice_referee.evidence.pipeline import (
        read_root,
        read_root_role_aware,
        trace_read_report,
    )
    from invoice_referee.evidence.trace import stage_payload

    context = workflow._evidence_context(job_id)
    if context is None:
        return
    tenant, root_id, sources, source_bytes, activity_profile = context
    reader, classifier, artifacts, provider_mode = workflow._evidence_wiring()

    with workflow.db.transaction() as cx:
        job_row = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    budget, cached_docs, _ = (
        _load_checkpoint(job_row) if job_row is not None else (RunBudget(), {}, {})
    )
    role_aware = bool(sources) and all(
        getattr(s, "upload_role", None) in ("paper", "evidence") for s in sources
    )
    done: dict[str, object] = dict(cached_docs)

    def _on_doc_done(source_id: str, analysis: object) -> None:
        done[str(source_id)] = analysis
        _save_checkpoint(workflow, job_id, budget, done)

    # One operation root for the processing job; spans buffer locally and flush
    # when the operation exits (after the DB transaction), so no network runs
    # inside a mutation transaction.
    with workflow._trace_operation(
        "evidence-job",
        metadata={
            "job_id": job_id,
            "root_id": root_id,
            "provider_mode": provider_mode,
            "pipeline": "role-aware" if role_aware else "legacy",
        },
        tags=("operation", "evidence-job"),
    ) as operation:
        with workflow.db.transaction() as cx:
            workflow._mark_evidence_job(cx, job_id, phase="READING", status="RUNNING")
        try:
            if role_aware:
                report = await read_root_role_aware(
                    sources=sources,
                    reader=reader,
                    classifier=classifier,
                    artifacts=artifacts,
                    source_bytes=source_bytes,
                    budget=budget,
                    provider_mode=provider_mode,
                    root_id=root_id,
                    activity_profile=activity_profile,
                    cached_docs=dict(done),
                    on_doc_done=_on_doc_done,
                )
            else:
                report = await read_root(
                    sources=sources,
                    reader=reader,
                    classifier=classifier,
                    artifacts=artifacts,
                    source_bytes=source_bytes,
                    budget=budget,
                    provider_mode=provider_mode,
                    root_id=root_id,
                    activity_profile=activity_profile,
                )
        except (
            Exception
        ) as error:  # provider failure -> technical, never a fake success
            operation.error = f"{type(error).__name__}: {error}"[:300]
            operation.outputs.update(
                stage_payload(
                    "read_root",
                    {
                        "status": "FAILED",
                        "outcome": "PROVIDER_ERROR",
                        "provider_mode": provider_mode,
                    },
                )
            )
            _save_checkpoint(workflow, job_id, budget, done)
            with workflow.db.transaction() as cx:
                workflow._fail_evidence_job(cx, job_id, error)
            return

        _save_checkpoint(workflow, job_id, budget, done)
        with workflow.db.transaction() as cx:
            # A Stop or changed input basis invalidates publication (contracts §6,
            # §12.5): a stale result must not be presented as current.
            row = cx.execute(
                "SELECT state, version FROM cases WHERE id = ?", (root_id,)
            ).fetchone()
            if row is not None and str(row["state"]) == "STOPPED":
                operation.outputs.update(
                    trace_read_report(
                        report,
                        status="CANCELLED",
                        state_after=str(row["state"]),
                        version_after=int(row["version"]),
                    )
                )
                operation.outputs["outcome"] = "CANCELLED_STOPPED"
                workflow._mark_evidence_job(
                    cx, job_id, phase="DONE", status="CANCELLED"
                )
                return
            job = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if job is not None and not workflow._evidence_basis_current(cx, job):
                operation.outputs.update(
                    trace_read_report(
                        report,
                        status="CANCELLED",
                        state_after=str(row["state"]) if row is not None else None,
                        version_after=int(row["version"]) if row is not None else None,
                    )
                )
                operation.outputs["outcome"] = "CANCELLED_STALE_BASIS"
                workflow._mark_evidence_job(
                    cx, job_id, phase="DONE", status="CANCELLED"
                )
                return
            # A partial pass with blocking TECHNICAL problems (e.g. extraction
            # not run for some source) keeps its checkpoint as TECHNICAL_ERROR:
            # the missing docs are resumed, never presented as missing-source
            # FACTs and never assessed into money.
            if _has_blocking_technical(report):
                workflow._store_evidence_report(
                    cx, tenant=tenant, root_id=root_id, report=report
                )
                cx.execute(
                    "UPDATE cases SET state = 'TECHNICAL_ERROR', updated_at = ? WHERE id = ?",
                    (workflow._now_iso(), root_id),
                )
                workflow._mark_evidence_job(cx, job_id, phase="DONE", status="FAILED")
                operation.error = "partial read with blocking technical problems"
                operation.outputs.update(
                    trace_read_report(report, status="FAILED_TECHNICAL_INCOMPLETE")
                )
                return
            # A run that produced nothing usable (no documents, or no FOUND field at
            # all) is a technical failure, not a cheerful "ready" (never a false
            # success). The report is still stored so the reason is inspectable.
            if not _evidence_usable(report):
                operation.error = "no usable evidence read"
                operation.outputs.update(
                    trace_read_report(report, status="FAILED_NO_USABLE_EVIDENCE")
                )
                workflow._fail_evidence_job(
                    cx,
                    job_id,
                    "không đọc/trích xuất được dữ liệu dùng được từ chứng từ",
                )
                return
            workflow._publish_evidence_report(
                cx, tenant=tenant, root_id=root_id, report=report
            )
            # After publishing, the typed finance consumer assesses the admission
            # input built from the CURRENT stored state (plan A5). A Stop or a
            # changed basis is re-checked here so a stale report is not assessed.
            workflow._assess_and_commit(
                cx,
                workflow._system_session(tenant),
                workflow._reload(
                    cx,
                    cx.execute(
                        "SELECT * FROM cases WHERE id = ?", (root_id,)
                    ).fetchone(),
                ),
                workflow._now_iso(),
            )
            workflow._mark_evidence_job(cx, job_id, phase="DONE", status="COMPLETED")
            result_row = cx.execute(
                "SELECT state, version FROM cases WHERE id = ?", (root_id,)
            ).fetchone()
            operation.outputs.update(
                trace_read_report(
                    report,
                    status="COMPLETED",
                    state_after=str(result_row["state"])
                    if result_row is not None
                    else None,
                    version_after=int(result_row["version"])
                    if result_row is not None
                    else None,
                )
            )
        workflow._record_trace_ref(root_id, operation)


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
