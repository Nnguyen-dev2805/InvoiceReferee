"""Run the 3 hard test cases through the full LIVE pipeline (OCR + LLM + Matcher + Assessment).

Outputs complete trace, DB records, extraction results, matching findings,
and financial adjudication results to .runtime/hard_cases_live/
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

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
from invoice_referee.workflow.evidence_jobs import run_evidence_job

CASES_CONFIG = [
    {
        "id": "HARD-01",
        "name": "Bẫy Thuế suất hỗn hợp (8% & 10%) và Chiết khấu thương mại",
        "dir": Path(".runtime/hard_cases/HARD01"),
        "purpose": "Mua sắm máy chủ và thiết bị nâng cấp hạ tầng",
        "profile": "WORK_EXPENSE",
        "activity_id": "activity:hard:01",
        "sources": ["report_hoan_ung.pdf", "hoa_don_dien_tu.pdf"],
    },
    {
        "id": "HARD-02",
        "name": "Bẫy Chi phí cá nhân/Cấm khấu trừ (Rượu mạnh, Thuốc lá) trong Tiệc tiếp khách",
        "dir": Path(".runtime/hard_cases/HARD02"),
        "purpose": "Tiếp khách đối tác nghiệm thu giai đoạn dự án",
        "profile": "CLIENT_MEAL",
        "activity_id": "activity:hard:02",
        "sources": ["report_hoan_ung.pdf", "hoa_don_dien_tu.pdf"],
    },
    {
        "id": "HARD-03",
        "name": "Bẫy Va chạm ghép nối Hóa đơn song sinh (Twin Invoices 340k vs 345k cùng ngày)",
        "dir": Path(".runtime/hard_cases/HARD03"),
        "purpose": "Chi phí taxi di chuyển công tác trong thành phố",
        "profile": "TRAVEL",
        "activity_id": "activity:hard:03",
        "sources": ["report_hoan_ung.pdf", "hoa_don_taxi_01.pdf", "hoa_don_taxi_02.pdf"],
    },
]


def role_for(filename: str) -> str:
    return "paper" if filename == "report_hoan_ung.pdf" else "evidence"


async def execute_case(cfg: dict, settings: Settings, output_base: Path) -> dict:
    case_id = cfg["id"]
    print(f"\n=======================================================")
    print(f"▶ EXECUTING LIVE: {case_id} — {cfg['name']}")
    print(f"=======================================================")

    case_out = output_base / case_id
    case_out.mkdir(parents=True, exist_ok=True)
    uploads_dir = case_out / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    db_path = case_out / "app.sqlite"
    if db_path.exists():
        db_path.unlink()

    db = Database(str(db_path))
    wf = runtime.build_workflow(
        settings,
        "LIVE",
        db=db,
        uploads_dir=str(uploads_dir),
        context_path="data/demo/company-context.json",
    )

    tenant = "tenant:demo"
    actor = "employee:an-thinh:nguyen-minh-an"
    session = wf.start_session(tenant=tenant, persona="employee", actor_id=actor)

    def cmd(ver: int) -> CommandContext:
        return CommandContext(
            session_id=session.session_id,
            actor_id=actor,
            command_id=uuid.uuid4().hex,
            expected_case_version=ver,
        )

    t0 = time.monotonic()
    # 1. CreateDraft
    print("  1. Creating draft case...")
    created = await wf.execute(
        cmd(0),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=cfg["activity_id"],
                name=cfg["purpose"],
                occurred_at="2026-10-15T10:00:00+07:00",
                declared_purpose=cfg["purpose"],
            )
        ),
    )
    root_id = created.case_view.id
    version = created.case_view.version
    print(f"     Case ID: {root_id}, Version: {version}")

    # 2. Attach Sources
    print("  2. Attaching sources with roles...")
    uploads = []
    for fname in cfg["sources"]:
        fpath = cfg["dir"] / fname
        data = fpath.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        key = f"{tenant}/{root_id}/{fname}"
        target = Path(wf.uploads_dir) / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        role = role_for(fname)
        uploads.append(
            SourceUpload(
                filename=fname,
                media="PDF",
                digest=digest,
                storage_key=key,
                upload_role=role,
            )
        )
        print(f"     Attached: {fname} (role: {role}, size: {len(data)} bytes)")

    attached = await wf.execute(
        cmd(version),
        AttachSources(root_id=root_id, uploads=tuple(uploads)),
    )
    version = attached.case_view.version

    # 3. Read draft
    print("  3. Reading draft via LIVE reader (Mistral OCR + LLM)...")
    draft = await wf.read_settlement_draft(session, root_id, ())
    (case_out / "draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"     Draft read done! Processing status: {draft.get('processing_status')}")

    # 4. Submit
    print("  4. Submitting case for assessment...")
    view = wf.view(cmd(0), root_id)
    submitted = await wf.execute(
        cmd(view.version),
        Submit(
            root_id=root_id,
            declaration=Declaration(
                activity_id=cfg["activity_id"],
                declared_purpose=cfg["purpose"],
            ),
        ),
    )
    version = submitted.case_view.version

    # 5. Run Evidence Job & Financial Assessment
    print("  5. Running evidence job & financial assessment engine...")
    job = wf._query_one(
        "SELECT id FROM jobs WHERE root_id=? AND status='QUEUED' ORDER BY created_at LIMIT 1",
        (root_id,),
    )
    if job:
        await run_evidence_job(wf, str(job["id"]))
        print("     Evidence job completed!")
    else:
        print("     Warning: No queued evidence job found.")

    elapsed = round(time.monotonic() - t0, 2)
    print(f"  ✓ Case {case_id} finished in {elapsed}s")

    # 6. Extract comprehensive results from DB
    cx = db.connect()
    final_case = cx.execute("SELECT * FROM cases WHERE id=?", (root_id,)).fetchone()
    report_row = cx.execute("SELECT report_json FROM case_evidence_reports WHERE root_id=?", (root_id,)).fetchone()
    report = json.loads(report_row[0]) if report_row else {}

    issues_rows = cx.execute("SELECT kind, field_or_rule, owner, status, payload_json FROM case_issues WHERE root_id=?", (root_id,)).fetchall()
    issues = [{
        "kind": r[0],
        "field_or_rule": r[1],
        "owner": r[2],
        "status": r[3],
        "payload": json.loads(r[4]),
    } for r in issues_rows]

    concl_rows = cx.execute("SELECT revision, status, payload_json, decided_at FROM case_conclusions WHERE root_id=?", (root_id,)).fetchall()
    conclusions = [{
        "revision": r[0],
        "status": r[1],
        "payload": json.loads(r[2]),
        "decided_at": r[3],
    } for r in concl_rows]

    instr_rows = cx.execute(
        "SELECT id, direction, amount, status, basis, cost_basis, execution_state FROM instructions WHERE root_id=?",
        (root_id,),
    ).fetchall()
    instructions = [{
        "id": r[0],
        "direction": r[1],
        "amount": r[2],
        "status": r[3],
        "basis": r[4],
        "cost_basis": r[5],
        "execution_state": r[6],
    } for r in instr_rows]

    summary = {
        "case_id": case_id,
        "name": cfg["name"],
        "elapsed_seconds": elapsed,
        "final_state": final_case["state"] if final_case else "UNKNOWN",
        "version": final_case["version"] if final_case else -1,
        "report_summary": {
            "documents_count": len(report.get("documents", [])),
            "documents": [
                {
                    "document_id": d.get("document_id"),
                    "type": d.get("document_type"),
                    "profile_status": d.get("profile_status"),
                    "fields": {f["field"]: f.get("value") for f in d.get("fields", [])},
                    "line_items_count": len(d.get("line_items", [])),
                    "line_items": [
                        {f["field"]: f.get("value") for f in li.get("fields", [])}
                        for li in d.get("line_items", [])
                    ],
                    "issues": d.get("issues", []),
                }
                for d in report.get("documents", [])
            ],
            "links": report.get("links", []),
            "row_matches": report.get("row_matches", []),
            "match_findings": report.get("match_findings", []),
            "problems": report.get("problems", []),
        },
        "issues_count": len(issues),
        "issues": issues,
        "conclusions": conclusions,
        "instructions": instructions,
    }
    cx.close()
    (case_out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


async def main():
    settings = Settings()
    output_base = Path(".runtime/hard_cases_live")
    output_base.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    for cfg in CASES_CONFIG:
        res = await execute_case(cfg, settings, output_base)
        all_summaries.append(res)

    (output_base / "all_results.json").write_text(
        json.dumps(all_summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=======================================================")
    print("ALL 3 HARD CASES EXECUTED LIVE SUCCESSFULLY!")
    print(f"Results written to: {output_base}")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(main())
