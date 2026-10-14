from __future__ import annotations

from datetime import UTC, datetime

import scripts.run_playwright_live_audit as harness
from invoice_referee.workflow.context_records import load_context
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


def test_live_startup_import_keeps_typed_tc02_tc03_contexts(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "app.sqlite"
    uploads_dir = tmp_path / "uploads"
    context_path = tmp_path / "context.json"
    monkeypatch.setattr(harness, "DB_PATH", db_path)
    monkeypatch.setattr(harness, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(harness, "CONTEXT_PATH", context_path)

    harness.setup_directories()
    harness.build_demo_context_file()
    harness.seed_typed_organization_contexts()

    # scripts/dev.py imports this same context after the typed fixture was seeded.
    workflow = CaseWorkflow(Database(db_path), uploads_dir=uploads_dir)
    workflow.import_demo_context(context_path, origin="SIMULATED")

    cx = workflow.db.connect()
    try:
        tc02 = load_context(
            cx,
            "tenant:demo",
            "activity:tc02",
            datetime(2026, 10, 14, tzinfo=UTC),
        )
        tc03 = load_context(
            cx,
            "tenant:demo",
            "activity:tc03",
            datetime(2026, 10, 14, tzinfo=UTC),
        )
    finally:
        cx.close()

    assert tc02 is not None
    assert tc02.company_name == "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
    assert len(tc02.ledger) == 1
    assert tc02.ledger[0]["id"] == "adv:tc02"
    assert tc02.coverage is not None
    assert tc02.coverage["witness_keys"] == ["cov:tc02"]

    assert tc03 is not None
    assert tc03.company_name == "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
    assert len(tc03.ledger) == 1
    assert tc03.ledger[0]["id"] == "adv:tc03"
    assert tc03.coverage is not None
    assert tc03.coverage["witness_keys"] == ["cov:tc03"]

    assert {item.activity_id for item in workflow.catalog()} >= {
        "activity:tc02",
        "activity:tc03",
    }
