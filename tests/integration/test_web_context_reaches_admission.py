"""The web entry's imported context must reach the typed admission (plan D).

`build_workflow` imports the demo context; the typed admission reads
`context_snapshots`. The catalog budget/grants and the typed assessment must
come from the SAME stored context, scoped to the activity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.runtime import build_workflow
from invoice_referee.workflow.context_records import (
    context_budgets,
    context_grants,
    load_context,
)
from invoice_referee.workflow.db import Database

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo" / "company-context.json"


def test_build_workflow_context_reaches_typed_loader(tmp_path: Path) -> None:
    wf = build_workflow(
        Settings(),
        "STUB",
        db=Database(tmp_path / "app.sqlite"),
        uploads_dir=tmp_path / "uploads",
        context_path=DEMO,
    )
    cx = wf.db.connect()
    try:
        ctx = load_context(cx, "tenant:demo", "activity:travel-a", datetime(2026, 10, 13, tzinfo=UTC))
    finally:
        cx.close()
    assert ctx is not None, "the web entry's context must be visible to the typed loader"
    # The catalog budget/grants must be visible to the typed consumer too.
    budgets = context_budgets(ctx, activity="activity:travel-a", digest="a" * 64)
    grants = context_grants(ctx, digest="a" * 64)
    assert budgets, "the demo activity budget must reach admission"
    assert grants, "the demo tenant grants must reach admission"


def test_typed_loader_does_not_leak_across_activities(tmp_path: Path) -> None:
    wf = build_workflow(
        Settings(),
        "STUB",
        db=Database(tmp_path / "app.sqlite"),
        uploads_dir=tmp_path / "uploads",
        context_path=DEMO,
    )
    cx = wf.db.connect()
    try:
        unknown = load_context(cx, "tenant:demo", "activity:does-not-exist", datetime(2026, 10, 13, tzinfo=UTC))
    finally:
        cx.close()
    assert unknown is None
