#!/usr/bin/env python3
"""Build the synthetic travel-settlement demo recipe (fake/replay only).

This is a tracked *generator*, never an application module and never a provider
client. It writes a self-contained demo under ``data/settlement/travel-demo-v1``
(Git-ignored) that a person can drive end-to-end through the settlement UI in
FAKE mode, using only sources the existing fake reader already parses
(structured ledger text) plus typed JSON for the company side.

Design (matches PRODUCT/RULEBOOK and the B6–B9 plans):

- One employee NV-DEMO-01, one work, one trip; company personas as configured.
- Employee actual costs: 3.0M + 1.0M + 1.0M = E 5.0M (PERSONAL declared payer).
- Company direct flight 3.0M (COMPANY_DIRECT) → whole-work T 8.0M.
- Advance actually received 2.0M (A), same economic identity used at B5.
- Returns: RA 0, P 0, RP 0 → S = E - (A-RA) - (P-RP) = 3.0M (company pays
  employee). After a 3.0M receipt, S = 0.

The generator writes ``employee-input`` (what the employee uploads),
``company-input`` (what the accountant records), ``followup`` (a later
reimbursement the employee may submit — NOT part of the initial B7 run),
``expected`` (the literal oracle; never an input), and ``manifest.json``.

It never writes to worked-example-v1 or any frozen dataset, and never mixes
gold/followup into the input partition.

Usage:
    python3 scripts/build_travel_demo.py \
        --work-ref WORK-DEMO-TRAVEL --settlement-as-of 2026-10-14T23:59:59+07:00
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "data" / "settlement" / "travel-demo-v1"

EMPLOYEE = "NV-DEMO-01"
ACCOUNTANT = "ACC-DEMO-01"
APPROVER = "APR-DEMO-01"
COMPANY_REF = "COMPANY-INVREF"

# Employee actual costs (PERSONAL declared payer).
EMPLOYEE_EXPENSES = [
    ("EXP-TAXI", "Di chuyển tại Hà Nội", 1_000_000),
    ("EXP-MEAL", "Bữa ăn phục vụ công việc", 1_000_000),
    ("EXP-HOTEL", "Khách sạn 1 đêm", 3_000_000),
]
COMPANY_FLIGHT_VND = 3_000_000
ADVANCE_RECEIVED_VND = 2_000_000
EMPLOYEE_TOTAL = sum(v for _, _, v in EMPLOYEE_EXPENSES)
TOTAL_WORK = EMPLOYEE_TOTAL + COMPANY_FLIGHT_VND
NET_S = EMPLOYEE_TOTAL - ADVANCE_RECEIVED_VND


def _employee_ledger() -> str:
    """Structured-ledger text the fake reader parses (one source, three items)."""
    lines: list[str] = []
    for expense_id, purpose, amount in EMPLOYEE_EXPENSES:
        payment_id = f"PAY-{expense_id.split('-', 1)[1]}"
        lines.append(f"fact {expense_id}-amount expense.{expense_id}.amount {amount}")
        lines.append(f"fact {expense_id}-purpose expense.{expense_id}.purpose BUSINESS")
        lines.append(f"fact {payment_id}-amount payment.{payment_id}.amount {amount}")
        lines.append(f"fact {payment_id}-payer payment.{payment_id}.payer EMPLOYEE")
        lines.append(f"fact {payment_id}-status payment.{payment_id}.status RECEIVED")
        lines.append(f"rel R-{expense_id} EXPENSE_PAYMENT {expense_id} {payment_id}")
        lines.append(f"rel RC-{expense_id} CLAIM_EXPENSE CL-{expense_id} {expense_id}")
    return "\n".join(lines) + "\n"


def _b3_context() -> dict:
    return {
        "schema_version": "b3-company-context-v1",
        "version": "synthetic-travel-demo-v1",
        "activated": True,
        "synthetic": True,
        "demo_clock": "2026-10-10T09:00:00+07:00",
        "people": [
            {"actor_ref": EMPLOYEE, "role": "EMPLOYEE",
             "name": "Nguyễn An", "department": "Kinh doanh"},
            {"actor_ref": ACCOUNTANT, "role": "ACCOUNTANT",
             "name": "Trần Bình", "department": "Kế toán"},
            {"actor_ref": APPROVER, "role": "APPROVER",
             "name": "Lê Chi", "department": "Quản lý"},
        ],
        "routes": [{"employee_ref": EMPLOYEE, "accountant_ref": ACCOUNTANT,
                    "approver_ref": APPROVER}],
        "grants": [{
            "actor_ref": APPROVER, "employee_ref": EMPLOYEE, "work_ref": None,
            "allow_work": True, "max_budget_vnd": 10_000_000,
            "max_advance_vnd": 5_000_000,
            "effective_from": "2026-10-01T00:00:00+07:00",
            "effective_to": "2026-10-31T23:59:59+07:00",
            "ref": "company:grant-01"}],
        "coverage": [{
            "employee_ref": EMPLOYEE, "work_ref": None,
            "from": "2026-10-01T00:00:00+07:00", "to": "2026-10-10T09:00:00+07:00",
            "complete_prior_history": True,
            "groups": ["ADVANCE", "ADVANCE_RETURN", "ADVANCE_APPROVAL",
                       "PENDING_ADVANCE", "WORK_DECISION", "BUDGET_DECISION"],
            "methods": ["CASH", "BANK_TRANSFER", "OTHER_COMPANY_CHANNELS"],
            "missing_ranges": [], "owner_ref": ACCOUNTANT,
            "origin": "Explicit synthetic company register covering all works "
                      "for this employee, including opening balances.",
            "ref": "company:coverage-01"}],
        "history": [],
    }


def _b7_config(as_of: str) -> dict:
    return {
        "schema_version": "b7-company-config-v1",
        "version": "b7-travel-demo-v1",
        "activated": True,
        "synthetic": True,
        "demo_clock": "2026-10-14T09:00:00+07:00",
        "company_ref": COMPANY_REF,
        "ref": "company:b7-config-demo",
        "grants": [{
            "actor_ref": APPROVER, "employee_ref": EMPLOYEE, "work_ref": None,
            "max_settlement_vnd": 8_000_000, "max_employee_cost_vnd": 8_000_000,
            "effective_from": "2026-10-10T00:00:00+07:00",
            "effective_until": "2026-10-31T23:59:59+07:00"}],
    }


def _company_packet(as_of: str) -> dict:
    """Company register: advance2 (same identity as B5) + direct flight3.

    ``document_ref`` values are placeholders; the accountant binds the real
    retained source ids after upload. The generator never fabricates a
    ``company:ref`` source that would falsely claim the packet is self-trusting.
    """
    return {
        "schema_version": "b7-company-packet-v1",
        "coverage": {
            "employee_ref": EMPLOYEE, "work_ref": None,
            "from": "2026-10-01T00:00:00+07:00", "to": as_of,
            "complete_prior_history": True,
            "groups": ["ADVANCE", "ADVANCE_RETURN", "REIMBURSEMENT_RECEIVED",
                       "REIMBURSEMENT_RETURN", "COMPANY_DIRECT",
                       "DUPLICATE_CLAIMS"],
            "methods": ["CASH", "BANK_TRANSFER", "OTHER_COMPANY_CHANNELS"],
            "missing_ranges": [], "owner_ref": ACCOUNTANT,
            "origin": "Synthetic company register for the travel demo; bind "
                      "retained source ids before relying on it.",
            "ref": "company:coverage-travel-demo"},
        "events": [
            {"event_namespace": "BANK:DEMO-ACCOUNT", "event_ref": "TX-ADV-01",
             "kind": "ADVANCE_RECEIVED", "amount_vnd": ADVANCE_RECEIVED_VND,
             "payer_ref": "COMPANY", "payee_ref": EMPLOYEE,
             "employee_ref": EMPLOYEE, "work_ref": None, "outcome": "RECEIVED",
             "event_at": "2026-10-11T10:00:00+07:00",
             "refs": ["company:TX-ADV-01"]},
            {"event_namespace": "VENDOR:VNA", "event_ref": "PAY-F1",
             "kind": "COMPANY_DIRECT", "amount_vnd": COMPANY_FLIGHT_VND,
             "payer_ref": "COMPANY", "payee_ref": "VNA",
             "employee_ref": EMPLOYEE, "work_ref": None, "outcome": "RECEIVED",
             "event_at": "2026-10-12T08:00:00+07:00",
             "refs": ["company:PAY-F1"]},
        ],
        "expenses": [
            {"expense_ref": "EXP-FLIGHT", "issuer_ref": "VNA",
             "document_ref": "BIND_AFTER_UPLOAD", "amount_vnd": COMPANY_FLIGHT_VND,
             "purpose": "BUSINESS", "expense_date": "2026-10-12",
             "refs": ["company:EXP-FLIGHT"],
             "payment_event_refs": ["VENDOR:VNA:PAY-F1"]}],
        "refs": ["company:coverage-travel-demo"],
        "reading_note": "Kế toán đọc sổ công ty tới mốc quyết toán; bind source "
                        "id đã giữ thay cho BIND_AFTER_UPLOAD.",
    }


def _expected() -> dict:
    return {
        "status": "single-author synthetic business oracle; not measured gold",
        "employee_cost_vnd": EMPLOYEE_TOTAL,       # E
        "company_direct_vnd": COMPANY_FLIGHT_VND,
        "total_work_cost_vnd": TOTAL_WORK,         # T
        "advance_received_vnd": ADVANCE_RECEIVED_VND,  # A
        "advance_returned_vnd": 0,                 # RA
        "reimbursement_received_vnd": 0,           # P
        "reimbursement_returned_vnd": 0,           # RP
        "settlement_net_vnd": NET_S,               # S = 3.0M company→employee
        "direction": "PAY_EMPLOYEE",
        "after_receipt_3m_net_vnd": 0,
        "must_not": [
            "Treat the forecast or approved advance as an actual receipt",
            "Merge the follow-up reimbursement into the initial B7 run",
            "Record a receipt automatically from approval",
            "Close on S=0 alone without revalidation/coverage/Stop checks",
        ],
    }


def _readme() -> str:
    return f"""# Travel demo v1 — synthetic, fake/replay only

One employee ({EMPLOYEE}), one work, one trip. This recipe drives B3 → B5 →
B6→B7 → B8 → B9 in FAKE mode. It is a demonstration packet, **not** a measured
baseline, gold label, or holdout. Source ids are issued by the API on upload.

## Partitions (keep them separate)

- `employee-input/` — what the employee uploads/declares. Never contains gold.
- `company-input/` — what the accountant records (packet template + B7 rights).
- `followup/` — a LATER reimbursement; do **not** merge into the initial B7 run.
- `expected/` — the literal oracle. Never an input to the app.

## 1. Start the app (fake)

```bash
rtk proxy env SETTLEMENT_PROVIDER_MODE=fake \\
  SETTLEMENT_B3_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b3-context.json \\
  SETTLEMENT_B7_CONTEXT_PATH=data/settlement/travel-demo-v1/company-input/b7-config.json \\
  SETTLEMENT_DB_PATH=data/settlement/travel-demo-v1/cases.sqlite \\
  SETTLEMENT_ARTIFACT_ROOT=data/settlement/travel-demo-v1/artifacts \\
  .venv/bin/uvicorn invoice_referee.api.settlement:create_runtime_app \\
  --factory --host 127.0.0.1 --port 8010
```

## 2. Steps (employee → accountant → approver)

1. **Employee**: nộp B3 (form web), work ref `{EMPLOYEE}`'s work; approve + record
   advance 2.0M (B5) with the same identity as the company packet
   (`BANK:DEMO-ACCOUNT:TX-ADV-01`).
2. **Employee**: mở hồ sơ quyết toán liên kết, khai 3 khoản thực tế (3.0M/1.0M/1.0M)
   và upload `employee-input/employee-ledger.txt`; **Xác nhận nộp**.
3. **Accountant**: ghi company packet (`company-input/company-packet-template.json`;
   bind retained source id for `BIND_AFTER_UPLOAD`), chạy kiểm tra → report.
4. **Accountant**: trình; **Approver**: phê duyệt (S = 3.0M chi cho nhân viên).
5. **Accountant**: ghi receipt 3.0M (B9), cập nhật đối chiếu + kiểm tra lại,
   đóng hồ sơ.

## 3. Expected (from `expected/oracle.json`)

E 5.0M · T 8.0M · A 2.0M · RA/P/RP 0 · **S 3.0M** → sau receipt 3.0M: S 0.

## 4. Limits

- Fake reader only; PDF/image/scan paths would need the LIVE reader (not here).
- Packet document refs are placeholders until the accountant binds real ids.
- Synthetic; no bank authentication; no bank transfer.
"""


def _write(path: Path, text: str) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    data = text.encode("utf-8")
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _js(path: Path, obj) -> dict:
    return _write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def build(work_ref: str, out_dir: Path, settlement_as_of: str) -> dict:
    # Guard against clobbering frozen datasets or an existing recipe.
    for protected in ("worked-example-v1", "b3-verbal-v2"):
        if out_dir.name == protected:
            raise SystemExit(f"Refusing to overwrite frozen dataset {protected}.")
    if (out_dir / "manifest.json").exists():
        raise SystemExit(
            f"Refusing to overwrite existing recipe at {out_dir}; "
            f"remove it explicitly first.")
    # Validate the cutoff is a real timestamp.
    datetime.fromisoformat(settlement_as_of)

    files: list[dict] = []

    def record(rel: str, meta: dict, role: str, actor: str, date: str,
               variants: list[str] | None = None):
        files.append({"path": rel, "role": role, "actor": actor, "date": date,
                      "duplicate_variants": variants or [], **meta})

    # employee-input
    record("employee-input/employee-ledger.txt",
           _write(out_dir / "employee-input/employee-ledger.txt",
                  _employee_ledger()),
           "employee-actual-expenses", EMPLOYEE, "2026-10-13",
           variants=["same-bytes-different-name:employee-ledger-copy.txt"])

    # company-input
    record("company-input/b3-context.json",
           _js(out_dir / "company-input/b3-context.json", _b3_context()),
           "company-context", ACCOUNTANT, "2026-10-10")
    record("company-input/b7-config.json",
           _js(out_dir / "company-input/b7-config.json",
               _b7_config(settlement_as_of)),
           "b7-rights", ACCOUNTANT, "2026-10-10")
    record("company-input/company-packet-template.json",
           _js(out_dir / "company-input/company-packet-template.json",
               _company_packet(settlement_as_of)),
           "company-register-template", ACCOUNTANT, "2026-10-14")

    # followup (separate partition — do NOT feed into the initial run)
    record("followup/reimbursement-note.md",
           _write(out_dir / "followup/reimbursement-note.md",
                  "# Follow-up reimbursement (do not merge into initial B7)\n\n"
                  "Synthetic placeholder for a LATER 3.0M reimbursement the "
                  "employee might submit after the initial run.\n"),
           "followup", EMPLOYEE, "2026-10-20")

    # expected (never an input)
    record("expected/oracle.json",
           _js(out_dir / "expected/oracle.json", _expected()),
           "expected-oracle", "SYSTEM", "2026-10-14")

    # README + manifest
    _write(out_dir / "README.md", _readme())
    manifest = {
        "version": "travel-demo-v1",
        "synthetic": True,
        "work_ref": work_ref,
        "settlement_as_of": settlement_as_of,
        "employee_ref": EMPLOYEE,
        "company_ref": COMPANY_REF,
        "input_partition": "employee-input",
        "company_partition": "company-input",
        "followup_partition": "followup",
        "excluded_from_model": ["expected", "README.md", "manifest.json"],
        "files": files,
    }
    _js(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-ref", required=True,
                        help="Work ref of the linked case the user will enter.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--settlement-as-of", required=True,
                        help="Coverage cutoff, e.g. 2026-10-14T23:59:59+07:00")
    args = parser.parse_args()
    manifest = build(args.work_ref, Path(args.output_dir),
                     args.settlement_as_of)
    print(json.dumps({"output_dir": args.output_dir,
                      "files": len(manifest["files"]),
                      "work_ref": manifest["work_ref"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
