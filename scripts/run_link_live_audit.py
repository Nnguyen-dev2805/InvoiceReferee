"""Playwright LIVE audit for backend settlement linking (14/10/2026).

Real frontend + LIVE backend (Mistral OCR / X-Kiro) + real pilot PDFs, isolated
DB under .runtime/. No STUB config is ever reported as LIVE.

Scenarios (frontend/e2e/live-link.spec.ts):
 1. link-history: settlement+invoice+transfer receipt with a recorded advance
    history -> LINKED panel, submit needs no activity choice.
 2. link-no-record: no advance history -> submit accepted, accountant records
    the advance from the voucher through the UI, A is established.
 3. link-ambiguous: two same-amount advances, weak-only basis -> the UI asks
    which advance; nothing is auto-linked.
 4. link-wrong-payee: voucher payee differs from the dossier employee ->
    recording stays OBSERVED, A is not established.
 5. link-reload: recording the same transaction twice stays idempotent.
 6. link-no-advance: an invoice-only dossier without any advance is accepted
    as a payment request (no forced advance, no fabricated budget).

Contexts are SIMULATED organization data (stated in the file + UI
diagnostics); the OCR/LLM calls are real. Coverage as_of is set past the run
so money projection is meaningful; the business clock is the pilot clock
(2026-10-10T18:00+07:00) used by the seeded data.
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
RUN_ID = f"link-live-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
BASE_DIR = PROJECT_ROOT / ".runtime" / "playwright-live-link" / RUN_ID
DB_PATH = BASE_DIR / "app.sqlite"
UPLOADS_DIR = BASE_DIR / "uploads"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
LOGS_DIR = BASE_DIR / "logs"
CONTEXT_PATH = BASE_DIR / "context.json"
PORT = int(os.environ.get("LINK_LIVE_PORT", "8096"))
# The browser demo session lives in tenant:demo, so the link fixtures are
# seeded there (isolated DB file per run).
TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
PURPOSE = "Làm việc với khách hàng tại Hà Nội"
COMPANY = "Công ty InvoiceReferee"
FUNDS = ["company:bank-demo"]
HORIZON = "2026-12-31T23:59:59+07:00"


def _interval() -> list[str]:
    return ["2026-10-01T00:00:00+07:00", HORIZON]


def _people() -> tuple[dict[str, str], ...]:
    return (
        {"id": EMPLOYEE, "name": "Nguyễn An"},
        {"id": ACCOUNTANT, "name": "Trần Thị B (kế toán)"},
        {"id": "employee:approver", "name": "Lê Văn C (người quyết định)"},
    )


def _grants(scope: str) -> tuple[dict[str, object], ...]:
    return (
        {
            "id": "g:recognize",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["RECOGNIZE_COST"],
            "scope": scope,
            "max_amount": 8_000_000,
            "effective_from": _interval()[0],
            "effective_to": _interval()[1],
            "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
        },
        {
            "id": "g:issue",
            "version": "v1",
            "actor": "system:referee",
            "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
            "scope": scope,
            "max_amount": 4_000_000,
            "effective_from": _interval()[0],
            "effective_to": _interval()[1],
            "allowed_profiles": ["TRAVEL", "WORK_EXPENSE"],
        },
    )


def _activity(activity_id: str, name: str, ref: str) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "name": name,
        "occurred_at": "2026-10-05T09:00:00+07:00",
        "purpose": PURPOSE,
        "profile": "TRAVEL",
        "status": "AUTHORIZED",
        "authorization": {"id": f"auth:{activity_id}"},
        "references": [ref],
    }


def _advance(key: str, activity: str, amount: int, ref: str) -> dict[str, object]:
    return {
        "id": f"adv:{ref}",
        "external_key": key,
        "kind": "ADVANCE_RECEIVED",
        "scope": activity,
        "payer": COMPANY,
        "payee": EMPLOYEE,
        "amount": amount,
        "event_at": "2026-10-05T09:00:00+07:00",
        "recorded_at": "2026-10-05T10:00:00+07:00",
        "verification_state": "CONFIRMED",
        "allocation_state": "ALLOCATED",
    }


def _coverage(activity: str) -> dict[str, object]:
    return {
        "activity": activity,
        "start": "2026-09-01T00:00:00+07:00",
        "as_of": HORIZON,
        "fund_ids": FUNDS,
        "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
        "opening_by_fund": {"company:bank-demo": 0},
        "ledger_version": "l:link",
        "witness_keys": ["cov:link"],
    }


def _context(
    tenant: str,
    activity_id: str,
    name: str,
    ref: str,
    *,
    ledger: list[dict[str, object]],
) -> OrganizationContext:
    scope = activity_id
    return OrganizationContext(
        tenant=tenant,
        organization_id=tenant,
        company_name=COMPANY,
        profile="TRAVEL",
        data_origin="SIMULATED",
        activity={
            "activity_id": activity_id,
            "name": name,
            "occurred_at": "2026-10-05T09:00:00+07:00",
            "purpose": PURPOSE,
            "profile": "TRAVEL",
            "status": "AUTHORIZED",
            "authorization": {"id": f"auth:{activity_id}"},
        },
        activities=(_activity(activity_id, name, ref),),
        people=_people(),
        budgets=(
            {
                "id": f"b:{activity_id}",
                "activity": activity_id,
                "amount": 8_000_000,
                "effect_range": _interval(),
                "actor": "employee:approver",
            },
        ),
        grants=_grants(scope),  # type: ignore[arg-type]
        ledger=tuple(ledger),  # type: ignore[arg-type]
        coverage=_coverage(activity_id),
        witnesses=(
            {
                "record_key": "cov:link",
                "quote": "Đối chiếu đủ lịch sử link-live",
                "kind": "LEDGER_COVERAGE",
            },
        ),
    )


def seed() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(DB_PATH)
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=UPLOADS_DIR)
    wf.enable_evidence_read(
        reader=object(), classifier=object(), artifacts_root=ARTIFACTS_DIR
    )
    history = [
        _advance(
            "transfer:ADV-UC03-F01", "activity:link-adv-a", 4_000_000, "ADV-UC03-F01"
        ),
        _advance("transfer:ADV-LIVE-B", "activity:link-adv-b", 4_000_000, "ADV-LIVE-B"),
    ]
    # Per-activity snapshots: adv-A carries the advance history, adv-B starts
    # with none (scenario 2 records it through the UI).
    wf.import_company_context(
        _context(
            TENANT,
            "activity:link-adv-a",
            "Tạm ứng A",
            "TU-LIVE-001",
            ledger=history,
        ),
        origin="SIMULATED",
    )
    wf.import_company_context(
        _context(TENANT, "activity:link-adv-b", "Tạm ứng B", "TU-LIVE-002", ledger=[]),
        origin="SIMULATED",
    )
    # The catalog dossier references used by DOCUMENT_REFERENCE linking.
    with wf.db.transaction() as cx:
        for activity_id, ref in (
            ("activity:link-adv-a", "TU-LIVE-001"),
            ("activity:link-adv-b", "TU-LIVE-002"),
        ):
            cx.execute(
                "UPDATE context_activities SET references_json = ? "
                "WHERE tenant = ? AND activity_id = ?",
                (json.dumps([ref]), TENANT, activity_id),
            )
    print("[link-live] seeded contexts for", TENANT)


def wait_for_server(url: str, timeout: int = 60) -> dict[str, object]:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not respond within {timeout}s.")


def main() -> int:
    settings = Settings()
    missing = settings.missing_for_live()
    if missing:
        print(f"[BLOCKED] Missing LIVE credentials: {', '.join(missing)}")
        return 2
    print("=== link-live audit ===")
    print("Run ID  :", RUN_ID)
    print("Base Dir:", BASE_DIR)
    print("Port    :", PORT)
    seed()
    backend_log = open(LOGS_DIR / "backend.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "scripts/dev.py",
            "--mode",
            "live",
            "--port",
            str(PORT),
            "--db",
            str(DB_PATH),
            "--uploads",
            str(UPLOADS_DIR),
            "--context",
            str(CONTEXT_PATH)
            if CONTEXT_PATH.exists()
            else "data/demo/company-context.json",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=backend_log,
        stderr=backend_log,
    )
    try:
        health = wait_for_server(f"http://127.0.0.1:{PORT}", timeout=60)
        print(
            "health:",
            {k: health.get(k) for k in ("mode", "live_ready", "langsmith_enabled")},
        )
        if health.get("mode") != "LIVE" or not health.get("live_ready"):
            raise RuntimeError(f"LIVE healthcheck failed: {health}")
        env = dict(os.environ, LINK_LIVE_PORT=str(PORT), LINK_LIVE_RUN=RUN_ID)
        res = subprocess.run(
            ["npx", "playwright", "test", "--config", "playwright.link-live.config.ts"],
            cwd=str(PROJECT_ROOT / "frontend"),
            env=env,
            capture_output=True,
            text=True,
        )
        (LOGS_DIR / "playwright.log").write_text(
            f"STDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}", encoding="utf-8"
        )
        print(res.stdout[-4000:])
        return res.returncode
    finally:
        print("[link-live] stopping server...")
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
