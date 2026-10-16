"""Role-aware LIVE runner (16/10/2026): paper + evidence uploads via Kimi-K3.

Mirrors scripts/run_prompt_hardening_audit.py worker flow but assigns
upload_role per file (report_hoan_ung.pdf -> paper, the rest -> evidence) and
records provider/model, per-stage LLM counts and TC25 ground-truth scoring.

Isolated output dir (own SQLite/uploads/artifacts). No user DB, port 8000 or
Railway. Secrets come from the environment only; values are never logged.

Usage:
  uv run python scripts/run_role_aware_live.py --manifest data/demo/manifest.json \\
    --cases TC25 --as-of 2026-10-16T12:00:00+07:00 \\
    --output-dir .runtime/tc25-role-aware-live-20261016/run-01 --revision <sha>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path


def write(path: Path, value) -> None:
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def source_code_digest(source_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((source_root / "src").rglob("*.py")):
        digest.update(path.relative_to(source_root).as_posix().encode())
        digest.update(bytes.fromhex(hashlib.sha256(path.read_bytes()).hexdigest()))
    return digest.hexdigest()


def role_for(filename: str) -> str:
    return "paper" if filename == "report_hoan_ung.pdf" else "evidence"


async def run_case(args, entry) -> dict:
    from invoice_referee import runtime
    from invoice_referee.config import Settings
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import (
        ActivityData,
        AttachSources,
        CreateDraft,
        Declaration,
        SourceUpload,
        Submit,
    )
    from invoice_referee.workflow.db import Database

    source_root = Path(args.source_root).resolve()
    runtime_path = Path(runtime.__file__).resolve()
    if not runtime_path.is_relative_to(source_root):
        raise RuntimeError("worker imported a different source revision")
    settings = Settings(_env_file=args.env_file)
    if not settings.live_ready:
        raise RuntimeError(
            f"LIVE credentials unavailable: {settings.missing_for_live()}"
        )
    case_dir = Path(args.output_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=False)
    context_path = Path(args.manifest).parent / entry["context"]
    context = json.loads(context_path.read_text())
    when = datetime.fromisoformat(args.as_of)
    wf = runtime.build_workflow(
        settings,
        "LIVE",
        db=Database(case_dir / "app.sqlite"),
        uploads_dir=case_dir / "uploads",
        context_path=context_path,
        clock=lambda: when,
    )
    tenant = context["organization_id"]
    actor = "employee:employee-a"
    activity = context["activity"]
    session = wf.start_session(tenant=tenant, persona="employee", actor_id=actor)

    def command(version):
        return CommandContext(
            session_id=session.session_id,
            actor_id=actor,
            command_id=uuid.uuid4().hex,
            expected_case_version=version,
        )

    created = await wf.execute(
        command(0),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=activity["activity_id"],
                name=activity["name"],
                occurred_at=activity["occurred_at"],
                declared_purpose=activity["purpose"],
            )
        ),
    )
    root_id = created.case_view.id
    uploads = []
    input_source_hashes = {}
    for source in entry["sources"]:
        source_path = source_root / source["path"]
        data = source_path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != source["sha256"]:
            raise RuntimeError(f"source hash mismatch: {source_path.name}")
        input_source_hashes[source_path.name] = digest
        key = f"{tenant}/{root_id}/{source_path.name}"
        target = wf.uploads_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        uploads.append(
            SourceUpload(
                filename=source_path.name,
                media="PDF",
                digest=digest,
                storage_key=key,
                upload_role=role_for(source_path.name),
            )
        )
    await wf.execute(
        command(created.case_view.version),
        AttachSources(root_id=root_id, uploads=tuple(uploads)),
    )
    failure = None
    code_digest = source_code_digest(source_root)
    started = time.monotonic()
    timings: dict[str, float] = {}
    try:
        stage_started = time.monotonic()
        draft = await wf.read_settlement_draft(session, root_id, ())
        timings["draft_read_s"] = round(time.monotonic() - stage_started, 3)
        write(case_dir / "draft.json", draft)
        view = wf.view(command(0), root_id)
        stage_started = time.monotonic()
        await wf.execute(
            command(view.version),
            Submit(
                root_id=root_id,
                declaration=Declaration(
                    activity_id=activity["activity_id"],
                    declared_purpose=activity["purpose"],
                ),
            ),
        )
        timings["submit_enqueue_s"] = round(time.monotonic() - stage_started, 3)
        job = wf._query_one(
            "SELECT id FROM jobs WHERE root_id=? AND status='QUEUED' ORDER BY created_at LIMIT 1",
            (root_id,),
        )
        if job:
            from invoice_referee.workflow.evidence_jobs import run_evidence_job

            stage_started = time.monotonic()
            await run_evidence_job(wf, str(job["id"]))
            timings["evidence_job_s"] = round(time.monotonic() - stage_started, 3)
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)[:500]}
    view = wf.view(command(0), root_id)
    write(case_dir / "case.json", view.model_dump(mode="json"))
    spans = [
        span.model_dump(mode="json")
        for operation in wf.trace.operations
        for span in operation.spans
    ]
    write(case_dir / "spans.json", spans)

    def count_stage(stage: str) -> int:
        return sum(
            1
            for span in spans
            if isinstance(span, dict)
            and span.get("run_type") == "llm"
            and (span.get("metadata", {}) or {}).get("stage") == stage
        )

    llm_spans = [s for s in spans if isinstance(s, dict) and s.get("run_type") == "llm"]
    requested = sorted(
        {
            str((s.get("inputs", {}) or {}).get("requested_model") or s.get("model"))
            for s in llm_spans
        }
    )
    returned = sorted(
        {
            str((s.get("outputs", {}) or {}).get("returned_model") or "UNKNOWN")
            for s in llm_spans
        }
    )
    llm_requests = []
    for s in llm_spans:
        inputs = s.get("inputs", {}) or {}
        outputs = s.get("outputs", {}) or {}
        metadata = s.get("metadata", {}) or {}
        usage = outputs.get("usage") or {}
        llm_requests.append(
            {
                "stage": metadata.get("stage"),
                "attempt_kind": metadata.get("attempt_kind"),
                "requested_model": inputs.get("requested_model"),
                "returned_model": outputs.get("returned_model") or "UNKNOWN",
                "requested_effort": inputs.get("requested_effort"),
                "observed_effort": outputs.get("observed_effort"),
                "elapsed_s": (
                    round(
                        (
                            datetime.fromisoformat(s["ended_at"])
                            - datetime.fromisoformat(s["started_at"])
                        ).total_seconds(),
                        3,
                    )
                    if s.get("started_at") and s.get("ended_at")
                    else None
                ),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                # Token details the provider reported; null means UNKNOWN
                # (not provided), never zero. Reasoning tokens are kept
                # separate: whether they sit inside completion_tokens is
                # unknown, so they are never added into it.
                "reasoning_tokens": usage.get("reasoning_tokens"),
                "cached_tokens": usage.get("cached_tokens"),
                "usage_unknown": not bool(usage),
            }
        )
    result = {
        "case_id": entry["case_id"],
        "mode": "LIVE",
        "context_origin": "SIMULATED",
        "assessment_at": args.as_of,
        "source_module": str(runtime_path),
        "source_revision": args.revision,
        "code_sha256": code_digest,
        "source_sha256": input_source_hashes,
        "context_sha256": hashlib.sha256(context_path.read_bytes()).hexdigest(),
        "llm_provider": getattr(wf._evidence_classifier, "provider_name", None),
        "requested_model": getattr(wf._evidence_classifier, "model", None),
        "returned_models": returned,
        "elapsed_s": round(time.monotonic() - started, 3),
        "timings": timings,
        "state": view.state,
        "root_id": root_id,
        "error": failure,
        "instructions": [
            {"direction": i.direction, "amount": i.amount} for i in view.instructions
        ],
        "issues": [
            {"kind": i.kind, "field": i.field_or_rule, "basis": i.basis}
            for i in view.issues
        ],
        "problems": [
            {
                "kind": p.kind,
                "fields": list(p.affected_fields),
                "message": p.message,
                "next": p.next_action,
            }
            for p in view.problems
        ],
        "actual_money": view.actual_money.model_dump(mode="json"),
        "conclusion": view.conclusion.status if view.conclusion else None,
        "llm_total": len(llm_spans),
        "llm_requests": llm_requests,
        "llm_by_stage": {
            stage: count_stage(stage)
            for stage in (
                "confidence-review",
                "extract",
                "resolve-evidence-suggestions",
                "classify",
            )
        },
        "repair_diagnostics": [
            (getattr(operation, "outputs", {}) or {}).get("repair_diagnostics")
            for operation in wf.trace.operations
        ],
        "trace_export_errors": len(wf.trace.export_errors),
    }
    write(case_dir / "result.json", result)
    return result


def score_tc25(result: dict) -> dict:
    """Independent ground-truth check (parent-side, never model input)."""
    checks = {}
    bodies = " ".join(
        f"{i.get('field', '')} {i.get('basis', '')}" for i in result.get("issues", [])
    )
    numbers = {
        int(t.replace(".", "").replace(" ", ""))
        for t in re.findall(r"(?<!\w)\d+(?:[. ]\d{3})*(?!\w)", bodies)
    }
    checks["has_900000"] = 900000 in numbers
    checks["has_700000"] = 700000 in numbers
    checks["has_200000"] = 200000 in numbers
    checks["explicit_delta_fact"] = (
        checks["has_900000"]
        and checks["has_700000"]
        and checks["has_200000"]
        and any(i.get("kind") == "FACT" for i in result.get("issues", []))
    )
    checks["blocks_money"] = result.get("instructions", []) == []
    checks["waiting_not_pass"] = result.get("state") in (
        "WAITING",
        "TECHNICAL_ERROR",
        "BLOCKED",
    )
    return checks


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="data/demo/manifest.json")
    parser.add_argument("--cases", nargs="+", default=["TC25"])
    parser.add_argument("--as-of", default="2026-10-16T12:00:00+07:00")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-root", default=".")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text())
    entries = {entry["case_id"]: entry for entry in manifest["cases"]}
    results = {}
    for case_id in args.cases:
        out = str(Path(args.output_dir))
        if len(args.cases) > 1:
            out = str(Path(args.output_dir) / case_id)
            Path(out).mkdir(parents=True, exist_ok=True)
        a = argparse.Namespace(**{**vars(args), "output_dir": out})
        result = asyncio.run(run_case(a, entries[case_id]))
        result["tc25_checks"] = score_tc25(result) if case_id == "TC25" else {}
        write(Path(out) / "result.json", result)
        results[case_id] = result
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
