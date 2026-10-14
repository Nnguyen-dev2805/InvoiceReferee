"""A1 organization-context import/load tests (plan A1).

The importer must persist the FULL validated payload (policies, budgets, ledger,
coverage, witnesses), so a restart loads the exact context an assessment rested
on — not just activity/people/grants. A context without coverage must not imply
A/P/R=0, and a new version must not overwrite the older snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.context_records import (
    context_budgets,
    context_coverage,
    context_ledger,
    context_policies,
    load_context,
    merge_ledger,
)
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PILOT_ORG = (
    Path(__file__).resolve().parents[2]
    / "data" / "test-kit" / "uc03-pilot" / "f01-cong-tac-thu-lai-tien-thua"
    / "input" / "organization.json"
)


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    return CaseWorkflow(db, uploads_dir=tmp_path / "uploads")


def _pilot() -> OrganizationContext:
    return OrganizationContext.model_validate_json(PILOT_ORG.read_text(encoding="utf-8"))


def test_pilot_context_survives_restart(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    digest = workflow.import_company_context(_pilot(), origin="SIMULATED")

    # A "restart": a fresh connection reads the stored snapshot, not memory.
    cx = workflow.db.connect()
    try:
        loaded = load_context(cx, "tenant:uc03-pilot", "activity:uc03-f01", datetime.now(UTC))
    finally:
        cx.close()
    assert loaded is not None
    assert loaded.organization_id == "tenant:uc03-pilot"
    # The fields the old importer dropped are all present after reload.
    assert loaded.policies and loaded.budgets and loaded.ledger and loaded.coverage
    assert loaded.financial_as_of == "2026-10-10T18:00:00+07:00"
    assert digest


def test_ledger_amount_and_coverage_preserved(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    workflow.import_company_context(_pilot(), origin="SIMULATED")
    cx = workflow.db.connect()
    try:
        loaded = load_context(cx, "tenant:uc03-pilot", "activity:uc03-f01", datetime.now(UTC))
        assert loaded is not None
        ledger = context_ledger(loaded, digest="a" * 64)
        assert [e.kind for e in ledger] == ["ADVANCE_RECEIVED"]
        assert ledger[0].amount == 4_000_000
        assert ledger[0].external_key == "company:bank-demo:ADV-UC03-F01"
        coverage = context_coverage(loaded, digest="a" * 64)
        assert coverage is not None
        assert coverage.as_of.isoformat().startswith("2026-10-10T11:00:00")
        assert "ADVANCE_RECEIVED" in coverage.flow_kinds
        assert coverage.opening_balance is not None
        assert coverage.opening_balance.value == 0
        policies = context_policies(loaded, digest="a" * 64, profile="TRAVEL")
        assert policies and policies[0].rules == ("EMPLOYEE_PAID_Q32_BOUNDED",)
        budgets = context_budgets(loaded, activity="activity:uc03-f01", digest="a" * 64)
        assert budgets and budgets[0].amount == 8_000_000
        assert budgets[0].actor == "employee:approver"
        assert budgets[0].grant_ref == "grant:UC03-F01:approver"
    finally:
        cx.close()


def test_context_without_coverage_does_not_imply_zero(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    context = _pilot().model_copy(update={"coverage": None, "ledger": ()})
    workflow.import_company_context(context, origin="SIMULATED")
    cx = workflow.db.connect()
    try:
        loaded = load_context(cx, "tenant:uc03-pilot", "activity:uc03-f01", datetime.now(UTC))
        assert loaded is not None
        assert context_coverage(loaded, digest="a" * 64) is None
        assert context_ledger(loaded, digest="a" * 64) == ()
    finally:
        cx.close()


def test_new_version_does_not_overwrite_older_snapshot(tmp_path: Path) -> None:
    workflow = _workflow(tmp_path)
    first = workflow.import_company_context(_pilot(), origin="SIMULATED")
    changed = _pilot().model_copy(update={"financial_as_of": "2026-10-14T18:00:00+07:00"})
    second = workflow.import_company_context(changed, origin="SIMULATED")
    assert first != second
    cx = workflow.db.connect()
    try:
        rows = cx.execute(
            "SELECT digest, version FROM context_snapshots WHERE tenant = ? ORDER BY version",
            ("tenant:uc03-pilot",),
        ).fetchall()
    finally:
        cx.close()
    assert [r["digest"] for r in rows] == [first, second]
    assert [int(r["version"]) for r in rows] == [1, 2]


def test_merge_ledger_dedupes_and_flags_conflict() -> None:
    from invoice_referee.domain.finance import MoneyEvent

    def _event(key: str, amount: int, kind: str = "ADVANCE_RECEIVED") -> MoneyEvent:
        return MoneyEvent(
            id=f"id:{key}", external_key=key, kind=kind, scope="activity:1",
            payer="company:demo", payee="employee:a", amount=amount,
            event_at=datetime(2026, 10, 5, tzinfo=UTC),
            recorded_at=datetime(2026, 10, 5, tzinfo=UTC),
            verification_state="CONFIRMED", allocation_state="ALLOCATED",
        )

    ctx = (_event("bank:ADV-1", 4_000_000),)
    # Same external key, same amount: one event, no conflict.
    merged, conflicts = merge_ledger(ctx, (_event("bank:ADV-1", 4_000_000),))
    assert len(merged) == 1
    assert conflicts == ()
    # Same external key, different amount: keep the first, report the conflict.
    merged, conflicts = merge_ledger(ctx, (_event("bank:ADV-1", 9_000_000),))
    assert len(merged) == 1
    assert merged[0].amount == 4_000_000
    assert conflicts == ("bank:ADV-1",)
    # A distinct key is a distinct event.
    merged, conflicts = merge_ledger(ctx, (_event("bank:RET-1", 760_000, "EMPLOYEE_RETURN"),))
    assert len(merged) == 2
    assert conflicts == ()


def test_relational_projection_still_authorizes(tmp_path: Path) -> None:
    # The existing authorization commands read the relational projection; the
    # new snapshot path must still populate activity/people/grants.
    workflow = _workflow(tmp_path)
    workflow.import_company_context(_pilot(), origin="SIMULATED")
    cx = workflow.db.connect()
    try:
        activity = cx.execute(
            "SELECT status, budget_amount FROM context_activities WHERE tenant = ? AND activity_id = ?",
            ("tenant:uc03-pilot", "activity:uc03-f01"),
        ).fetchone()
        grants = cx.execute(
            "SELECT COUNT(*) AS n FROM context_grants WHERE tenant = ?", ("tenant:uc03-pilot",)
        ).fetchone()
    finally:
        cx.close()
    assert activity["status"] == "AUTHORIZED"
    assert int(activity["budget_amount"]) == 8_000_000
    assert int(grants["n"]) == 4
