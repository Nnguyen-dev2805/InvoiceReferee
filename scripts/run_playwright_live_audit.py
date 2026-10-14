"""Playwright LIVE Audit Runner for TC02 and TC03.

Spins up an isolated LIVE dev server with typed OrganizationContext snapshots
for TC02 and TC03, runs Playwright E2E tests, and records full audit evidence.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = f"tc02-tc03-live-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
BASE_DIR = PROJECT_ROOT / ".runtime" / "playwright-live" / RUN_ID
DB_PATH = BASE_DIR / "app.sqlite"
UPLOADS_DIR = BASE_DIR / "uploads"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
LOGS_DIR = BASE_DIR / "logs"
CONTEXT_PATH = BASE_DIR / "context.json"
PORT = 8095


def setup_directories() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def build_demo_context_file() -> None:
    demo_context = {
        "data_origin": "SIMULATED",
        "note": "Context test TC02 & TC03",
        "organization": {
            "id": "tenant:demo",
            "name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        },
        "people": [
            {"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},
            {"id": "employee:accountant-demo", "name": "Trần Thị B (kế toán)"},
            {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
        ],
        # The typed TC02/TC03 snapshots are seeded separately below. If this
        # later startup import names those activities, load_context selects its
        # newer demo snapshot and loses the company, ledger, and coverage data.
        "activities": [],
        "grants": [
            {
                "id": "grant:approver",
                "version": "v1",
                "actor": "employee:approver",
                "actions": ["AUTHORIZE_EXPENSE", "EXCEPTION_POLICY", "AUTHORIZE_PAYMENT"],
                "scope": "*",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
                "max_amount": 20_000_000,
                "effective_from": "2026-01-01T00:00:00+07:00",
                "effective_to": "2026-12-31T23:59:59+07:00",
            }
        ],
        "witnesses": [],
    }
    CONTEXT_PATH.write_text(json.dumps(demo_context, indent=2, ensure_ascii=False), encoding="utf-8")


def seed_typed_organization_contexts() -> None:
    db = Database(DB_PATH)
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=UPLOADS_DIR)

    # 1. Typed context for TC02: Advance 5.000.000 đ
    ctx_tc02 = OrganizationContext(
        tenant="tenant:demo",
        organization_id="tenant:demo",
        company_name="CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        profile="WORK_EXPENSE",
        data_origin="SIMULATED",
        activity={
            "activity_id": "activity:tc02",
            "name": "Mua thiết bị văn phòng phục vụ hoạt động công ty",
            "purpose": "Mua thiết bị văn phòng phục vụ hoạt động công ty",
            "occurred_at": "2026-10-10T09:00:00+07:00",
            "profile": "WORK_EXPENSE",
            "status": "AUTHORIZED",
            "authorization": {"id": "auth:tc02"},
        },
        people=(
            {"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},
            {"id": "employee:accountant-demo", "name": "Trần Thị B (kế toán)"},
            {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
        ),
        budgets=(
            {
                "id": "b:tc02",
                "activity": "activity:tc02",
                "amount": 10_000_000,
                "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                "actor": "employee:approver",
            },
        ),
        grants=(
            {
                "id": "grant:approver",
                "actor": "employee:approver",
                "actions": ["AUTHORIZE_EXPENSE", "EXCEPTION_POLICY", "AUTHORIZE_PAYMENT"],
                "scope": "*",
                "max_amount": 20_000_000,
                "effective_from": "2026-01-01T00:00:00+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
        ),
        ledger=(
            {
                "id": "adv:tc02",
                "external_key": "bank:ADV-TC02",
                "kind": "ADVANCE_RECEIVED",
                "scope": "activity:tc02",
                "payer": "company:demo",
                "payee": "employee:employee-a",
                "amount": 5_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "recorded_at": "2026-10-05T10:00:00+07:00",
                "verification_state": "CONFIRMED",
                "allocation_state": "ALLOCATED",
            },
        ),
        coverage={
            "activity": "activity:tc02",
            "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-12-31T23:59:59+07:00",
            "fund_ids": ["company:bank"],
            "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
            "opening_by_fund": {"company:bank": 0},
            "ledger_version": "l:tc02",
            "witness_keys": ["cov:tc02"],
        },
        witnesses=({"record_key": "cov:tc02", "quote": "Đối chiếu đủ lịch sử TC02", "kind": "LEDGER_COVERAGE"},),
    )

    # 2. Typed context for TC03: Advance 4.320.000 đ
    ctx_tc03 = OrganizationContext(
        tenant="tenant:demo",
        organization_id="tenant:demo",
        company_name="CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        profile="TRAVEL",
        data_origin="SIMULATED",
        activity={
            "activity_id": "activity:tc03",
            "name": "Chi phí lưu trú trong chuyến công tác",
            "purpose": "Chi phí lưu trú trong chuyến công tác",
            "occurred_at": "2026-10-10T09:00:00+07:00",
            "profile": "TRAVEL",
            "status": "AUTHORIZED",
            "authorization": {"id": "auth:tc03"},
        },
        people=(
            {"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},
            {"id": "employee:accountant-demo", "name": "Trần Thị B (kế toán)"},
            {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
        ),
        budgets=(
            {
                "id": "b:tc03",
                "activity": "activity:tc03",
                "amount": 8_000_000,
                "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                "actor": "employee:approver",
            },
        ),
        grants=(
            {
                "id": "grant:approver",
                "actor": "employee:approver",
                "actions": ["AUTHORIZE_EXPENSE", "EXCEPTION_POLICY", "AUTHORIZE_PAYMENT"],
                "scope": "*",
                "max_amount": 20_000_000,
                "effective_from": "2026-01-01T00:00:00+07:00",
                "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
            },
        ),
        ledger=(
            {
                "id": "adv:tc03",
                "external_key": "bank:ADV-TC03",
                "kind": "ADVANCE_RECEIVED",
                "scope": "activity:tc03",
                "payer": "company:demo",
                "payee": "employee:employee-a",
                "amount": 4_320_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "recorded_at": "2026-10-05T10:00:00+07:00",
                "verification_state": "CONFIRMED",
                "allocation_state": "ALLOCATED",
            },
        ),
        coverage={
            "activity": "activity:tc03",
            "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-12-31T23:59:59+07:00",
            "fund_ids": ["company:bank"],
            "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
            "opening_by_fund": {"company:bank": 0},
            "ledger_version": "l:tc03",
            "witness_keys": ["cov:tc03"],
        },
        witnesses=({"record_key": "cov:tc03", "quote": "Đối chiếu đủ lịch sử TC03", "kind": "LEDGER_COVERAGE"},),
    )

    wf.import_company_context(ctx_tc02)
    wf.import_company_context(ctx_tc03)
    print("[Harness] Seeded typed OrganizationContext for TC02 and TC03.")


def wait_for_server(url: str, timeout: int = 30) -> dict[str, object]:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not respond within {timeout}s.")


def main() -> int:
    settings = Settings()
    missing = settings.missing_for_live()
    if missing:
        print(f"[BLOCKED] Missing LIVE credentials: {', '.join(missing)}")
        return 2

    print(f"=== Starting Isolated Playwright LIVE Audit ===")
    print(f"Run ID    : {RUN_ID}")
    print(f"Base Dir  : {BASE_DIR}")
    print(f"Port      : {PORT}")
    print(f"Model     : {settings.invoice_referee_llm_model}")
    print(f"Base URL  : {settings.xkiro_base_url}")

    setup_directories()
    build_demo_context_file()
    seed_typed_organization_contexts()

    backend_log = open(LOGS_DIR / "backend.log", "w", encoding="utf-8")
    server_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "dev.py"),
        "--mode",
        "live",
        "--port",
        str(PORT),
        "--db",
        str(DB_PATH),
        "--uploads",
        str(UPLOADS_DIR),
        "--context",
        str(CONTEXT_PATH),
    ]

    print("[Harness] Launching LIVE dev server...")
    proc = subprocess.Popen(server_cmd, cwd=str(PROJECT_ROOT), stdout=backend_log, stderr=backend_log)

    try:
        health = wait_for_server(f"http://127.0.0.1:{PORT}", timeout=30)
        print(f"[Harness] Server is UP: mode={health.get('mode')}, live_ready={health.get('live_ready')}")
        if health.get("mode") != "LIVE" or not health.get("live_ready"):
            raise RuntimeError(f"Server failed LIVE healthcheck: {health}")

        # Run Playwright tests
        test_env = dict(os.environ)
        test_env["LIVE_PORT"] = str(PORT)

        playwright_cmd = [
            "npx",
            "playwright",
            "test",
            "--config",
            "playwright.live.config.ts",
        ]
        print(f"[Harness] Running Playwright E2E: {' '.join(playwright_cmd)}")
        playwright_res = subprocess.run(
            playwright_cmd,
            cwd=str(PROJECT_ROOT / "frontend"),
            env=test_env,
            capture_output=True,
            text=True,
        )

        test_log_path = LOGS_DIR / "playwright.log"
        test_log_path.write_text(
            f"STDOUT:\n{playwright_res.stdout}\n\nSTDERR:\n{playwright_res.stderr}",
            encoding="utf-8",
        )
        print(f"[Harness] Playwright finished with exit code {playwright_res.returncode}")
        print(playwright_res.stdout)
        if playwright_res.stderr:
            print(f"STDERR:\n{playwright_res.stderr}")

        return playwright_res.returncode

    finally:
        print("[Harness] Shutting down LIVE dev server...")
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        backend_log.close()
        print("[Harness] Dev server stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
