"""One context import path for catalog and typed admission (plan A5/A1/D).

The web entry imports the demo context via `import_demo_context`; the typed
admission reads `context_snapshots`. If the two disagree, the catalog shows a
budget/grants the assessment never sees. Both must read the same stored context,
scoped per tenant/activity, and survive a restart.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.context_records import load_context
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo" / "company-context.json"


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    return CaseWorkflow(db, uploads_dir=tmp_path / "uploads")


def test_demo_import_creates_a_typed_snapshot(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    wf.import_demo_context(DEMO, origin="SIMULATED")
    cx = wf.db.connect()
    try:
        n = cx.execute("SELECT COUNT(*) AS n FROM context_snapshots WHERE tenant = ?", ("tenant:demo",)).fetchone()["n"]
    finally:
        cx.close()
    assert int(n) >= 1, "the demo import must create a typed snapshot admission can read"


def test_demo_snapshot_reaches_typed_admission(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    wf.import_demo_context(DEMO, origin="SIMULATED")
    cx = wf.db.connect()
    try:
        ctx = load_context(cx, "tenant:demo", "activity:travel-a", datetime(2026, 10, 13, tzinfo=UTC))
    finally:
        cx.close()
    assert ctx is not None, "admission must see the demo activity context"
    # The catalog budget/grants must be visible to the typed consumer too.
    assert ctx.budgets, "the activity budget must survive to admission"
    assert ctx.grants, "the tenant grants must survive to admission"


def test_load_context_is_scoped_to_the_activity(tmp_path: Path) -> None:
    # The newest tenant snapshot must not be used for an activity it does not
    # contain: a different activity must not inherit another's budget.
    wf = _workflow(tmp_path)
    wf.import_demo_context(DEMO, origin="SIMULATED")
    cx = wf.db.connect()
    try:
        known = load_context(cx, "tenant:demo", "activity:travel-a", datetime(2026, 10, 13, tzinfo=UTC))
        unknown = load_context(cx, "tenant:demo", "activity:does-not-exist", datetime(2026, 10, 13, tzinfo=UTC))
    finally:
        cx.close()
    assert known is not None
    # An activity the snapshot does not contain yields no activity context.
    assert unknown is None or unknown.activity is None


def test_demo_snapshot_survives_restart(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    wf.import_demo_context(DEMO, origin="SIMULATED")
    # A fresh workflow/connection sees the same stored snapshot.
    wf2 = CaseWorkflow(Database(tmp_path / "app.sqlite"), uploads_dir=tmp_path / "uploads")
    cx = wf2.db.connect()
    try:
        ctx = load_context(cx, "tenant:demo", "activity:travel-a", datetime(2026, 10, 13, tzinfo=UTC))
    finally:
        cx.close()
    assert ctx is not None
    assert ctx.budgets
