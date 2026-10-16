"""Isolated paired LIVE audit. Expected outcomes live only in parent scoring."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CASES = ("TC01", "TC02", "TC03", "TC05", "TC06", "TC11", "TC15", "TC22")


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def source_code_digest(source_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((source_root / "src").rglob("*.py")):
        digest.update(path.relative_to(source_root).as_posix().encode())
        digest.update(bytes.fromhex(hashlib.sha256(path.read_bytes()).hexdigest()))
    return digest.hexdigest()


async def worker(args, entry):
    from invoice_referee import runtime
    from invoice_referee.config import Settings
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, AttachSources, CreateDraft, Declaration, SourceUpload, Submit
    from invoice_referee.workflow.db import Database

    source_root = Path(args.source_root).resolve()
    runtime_path = Path(runtime.__file__).resolve()
    if not runtime_path.is_relative_to(source_root):
        raise RuntimeError("worker imported a different source revision")
    settings = Settings(_env_file=args.env_file)
    if not settings.live_ready:
        raise RuntimeError("LIVE credentials unavailable")
    case_dir = Path(args.output_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=False)
    context_path = Path(args.manifest).parent / entry["context"]
    context = json.loads(context_path.read_text())
    when = datetime.fromisoformat(args.as_of)
    wf = runtime.build_workflow(settings, "LIVE", db=Database(case_dir / "app.sqlite"),
        uploads_dir=case_dir / "uploads", context_path=context_path, clock=lambda: when)
    tenant = context["organization_id"]
    actor = "employee:employee-a"
    activity = context["activity"]
    session = wf.start_session(tenant=tenant, persona="employee", actor_id=actor)

    def command(version):
        return CommandContext(session_id=session.session_id, actor_id=actor,
                              command_id=uuid.uuid4().hex, expected_case_version=version)

    created = await wf.execute(command(0), CreateDraft(activity_data=ActivityData(
        activity_id=activity["activity_id"], name=activity["name"],
        occurred_at=activity["occurred_at"], declared_purpose=activity["purpose"])))
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
        uploads.append(SourceUpload(filename=source_path.name, media="PDF", digest=digest, storage_key=key))
    await wf.execute(command(created.case_view.version), AttachSources(root_id=root_id, uploads=tuple(uploads)))
    failure = None
    code_digest = source_code_digest(source_root)
    started = time.monotonic()
    try:
        draft = await wf.read_settlement_draft(session, root_id, ())
        write(case_dir / "draft.json", draft)
        view = wf.view(command(0), root_id)
        await wf.execute(command(view.version), Submit(root_id=root_id, declaration=Declaration(
            activity_id=activity["activity_id"], declared_purpose=activity["purpose"])))
        job = wf._query_one("SELECT id FROM jobs WHERE root_id=? AND status='QUEUED' ORDER BY created_at LIMIT 1", (root_id,))
        if job:
            await wf.run_evidence_job(str(job["id"]))
    except Exception as error:
        failure = {"type": type(error).__name__, "message": str(error)[:500]}
    view = wf.view(command(0), root_id)
    write(case_dir / "case.json", view.model_dump(mode="json"))
    spans = [span.model_dump(mode="json") for operation in wf.trace.operations for span in operation.spans]
    write(case_dir / "spans.json", spans)
    result = {"case_id": entry["case_id"], "mode": "LIVE", "context_origin": "SIMULATED",
        "assessment_at": args.as_of, "source_module": str(runtime_path),
        "source_revision": args.revision, "code_sha256": code_digest,
        "source_sha256": input_source_hashes,
        "context_sha256": hashlib.sha256(context_path.read_bytes()).hexdigest(),
        "model": settings.invoice_referee_llm_model, "elapsed_s": round(time.monotonic()-started, 3),
        "state": view.state, "root_id": root_id, "error": failure,
        "instructions": [{"direction": i.direction, "amount": i.amount} for i in view.instructions],
        "issues": [{"kind": i.kind, "field": i.field_or_rule, "basis": i.basis} for i in view.issues],
        "actual_money": view.actual_money.model_dump(mode="json"),
        "conclusion": view.conclusion.status if view.conclusion else None,
        "provider_calls": sum(span.get("run_type") == "llm" for span in spans if isinstance(span, dict)),
        "trace_export_errors": len(wf.trace.export_errors)}
    write(case_dir / "result.json", result)
    return result


def score(case_id: str, result: dict) -> bool:
    """Check the expected outcome independently; this function is parent-only."""
    if result.get("error") or result.get("state") == "TECHNICAL_ERROR":
        return False
    expected = {"TC01": [{"direction": "COLLECT", "amount": 760000}],
                "TC02": [{"direction": "PAY", "amount": 400000}]}
    if case_id in expected:
        return result["instructions"] == expected[case_id] and not result["issues"]
    if case_id == "TC03":
        return (result.get("conclusion") == "BALANCED" and result.get("state") == "SETTLED"
                and not result["instructions"] and not result["issues"]
                and result["actual_money"].get("S", {}).get("state") == "KNOWN"
                and result["actual_money"]["S"].get("value") == 0)
    expected = {
        "TC05": ("expense:arithmetic:line_total", "500000"),
        "TC06": ("expense:arithmetic:return", "60000"),
        "TC11": ("expense:arithmetic:total", "100000"),
        "TC15": ("expense:relevance", ""),
        "TC22": ("expense:allocation", "2160000"),
    }.get(case_id)
    if expected is None or result["instructions"]:
        return False
    field_fragment, basis_fragment = expected
    return any(issue["kind"] == "FACT" and field_fragment in issue["field"]
        and (not basis_fragment or int(basis_fragment) in {
            int(token.replace(".", "").replace(" ", ""))
            for token in re.findall(r"(?<!\w)\d+(?:[. ]\d{3})*(?!\w)", issue.get("basis", ""))
        }) for issue in result["issues"])


def required_cases() -> tuple[str, ...]:
    return REQUIRED_CASES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["LIVE"], default="LIVE")
    parser.add_argument("--manifest", default=str(ROOT / "data/demo/manifest.json"))
    parser.add_argument("--cases", nargs="+", default=list(REQUIRED_CASES))
    parser.add_argument("--as-of", default="2026-10-16T12:00:00+07:00")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--source-root", default=str(ROOT))
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--revision", default="candidate", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.manifest = str(Path(args.manifest).resolve())
    manifest = json.loads(Path(args.manifest).read_text())
    entries = {entry["case_id"]: entry for entry in manifest["cases"]}
    if not set(args.cases) <= entries.keys():
        parser.error("Unknown cases: " + ", ".join(sorted(set(args.cases)-entries.keys())))
    if args.worker:
        asyncio.run(worker(args, entries[args.cases[0]]))
        return 0
    if set(args.cases) != set(REQUIRED_CASES) or len(args.cases) != len(REQUIRED_CASES):
        parser.error("audit requires all required cases exactly once: " + ", ".join(REQUIRED_CASES))
    from invoice_referee.config import Settings
    settings = Settings(_env_file=args.env_file)
    if not settings.live_ready:
        print(json.dumps({"status": "NOT_RUN", "missing": settings.missing_for_live()}))
        return 3
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidate_root = Path(args.source_root).resolve()
    revisions = [("candidate", candidate_root, candidate_root / "scripts/run_prompt_hardening_audit.py")]
    if args.baseline_ref:
        frozen = output / "baseline-source"
        frozen.mkdir()
        archive = output / "baseline.tar"
        with archive.open("wb") as stream:
            subprocess.run(["git", "archive", "--format=tar", args.baseline_ref], cwd=ROOT, stdout=stream, check=True)
        with tarfile.open(archive) as stream:
            stream.extractall(frozen, filter="data")
        archive.unlink()
        frozen_harness = frozen / "scripts/run_prompt_hardening_audit.py"
        frozen_harness.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve(), frozen_harness)
        revisions.insert(0, ("baseline", frozen, frozen_harness))
    results = []
    for revision, source_root, harness in revisions:
        for case_id in REQUIRED_CASES:
            case_dir = output / revision / case_id
            case_dir.parent.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, "PYTHONPATH": str(source_root / "src") + os.pathsep + str(source_root)}
            command = [sys.executable, str(harness), "--worker", "--mode", args.mode,
                "--manifest", args.manifest, "--cases", case_id, "--as-of", args.as_of,
                "--env-file", str(Path(args.env_file).resolve()), "--source-root", str(source_root),
                "--output-dir", str(case_dir), "--revision", revision]
            with (case_dir.parent / f"{case_id}.log").open("w") as log:
                run = subprocess.run(command, cwd=source_root, env=env, stdout=log, stderr=subprocess.STDOUT)
            result_file = case_dir / "result.json"
            result = json.loads(result_file.read_text()) if result_file.exists() else {
                "case_id": case_id, "error": "WORKER_ERROR", "exit": run.returncode,
                "log": str((case_dir.parent / f"{case_id}.log").relative_to(output))}
            result.update(revision=revision, passed=score(case_id, result))
            results.append(result)
            write(output / "summary.json", results)
            print(json.dumps({"revision": revision, "case": case_id, "passed": result["passed"],
                              "state": result.get("state"), "error": bool(result.get("error"))}), flush=True)
    return 0 if len(results) == len(REQUIRED_CASES) * len(revisions) and all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
