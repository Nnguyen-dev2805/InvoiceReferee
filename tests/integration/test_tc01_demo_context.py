"""Portable TC01 context must reach the actual dev composition root."""

from datetime import datetime
import json
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.runtime import build_workflow
from invoice_referee.workflow.context_records import load_context
from invoice_referee.workflow.db import Database

AS_OF = datetime.fromisoformat("2026-10-14T23:00:00+07:00")


def _typed_file(tmp_path: Path) -> Path:
    path = tmp_path / "company.json"
    path.write_text(json.dumps({
        "organization_id": "tenant:demo",
        "company_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "data_origin": "SIMULATED",
        "profile": "WORK_EXPENSE",
        "activity": {"activity_id": "activity:tc01", "name": "Tiếp khách", "status": "AUTHORIZED"},
        "people": [{"id": "employee:employee-a", "name": "NGUYỄN MINH AN"}],
        "ledger": [{
            "id": "advance:tc01", "external_key": "company:bank-demo:ADV-TC01",
            "kind": "ADVANCE_RECEIVED", "scope": "activity:tc01",
            "payer": "company:demo", "payee": "employee:employee-a", "amount": 4_000_000,
            "event_at": "2026-10-05T09:00:00+07:00", "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED",
        }],
    }), encoding="utf-8")
    return path


def test_typed_context_startup_preserves_identity_and_actual_advance(tmp_path):
    # Removing typed import support would lose the independent company ledger.
    path = _typed_file(tmp_path)
    kwargs = dict(settings=Settings(_env_file=None), mode="STUB", db=Database(tmp_path / "app.sqlite"),
                  uploads_dir=tmp_path / "uploads", context_path=path)
    wf = build_workflow(**kwargs)
    restarted = build_workflow(**kwargs)
    with restarted.db.connect() as cx:
        context = load_context(cx, "tenant:demo", "activity:tc01", AS_OF)
        assert cx.execute("SELECT COUNT(*) FROM context_snapshots").fetchone()[0] == 1
    assert context is not None
    assert context.company_name == "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
    assert context.ledger[0]["amount"] == 4_000_000
    assert wf.display_name("tenant:demo", "employee:employee-a") == "NGUYỄN MINH AN"


def test_legacy_company_identity_survives_import(tmp_path):
    path = Path("tests/fixtures/legacy-company-context.json")
    name = json.loads(path.read_text())["organization"]["name"]
    wf = build_workflow(Settings(_env_file=None), "STUB", db=Database(tmp_path / "app.sqlite"),
                        uploads_dir=tmp_path / "uploads", context_path=path)
    with wf.db.connect() as cx:
        context = load_context(cx, "tenant:demo", "activity:travel-a", AS_OF)
    assert context is not None
    assert context.company_name == name


def test_explicit_demo_clock_reaches_workflow(tmp_path):
    from scripts.dev import build_parser, build_workflow as build_dev

    args = build_parser().parse_args(["--demo-as-of", "2026-10-14T23:00:00+07:00"])
    wf, _ = build_dev(str(tmp_path / "dev.sqlite"), str(tmp_path / "uploads"),
                      "tests/fixtures/legacy-company-context.json", settings=Settings(_env_file=None),
                      demo_as_of=args.demo_as_of)
    assert wf._clock() == AS_OF


def test_demo_clock_rejects_missing_timezone():
    import pytest
    from scripts.dev import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["--demo-as-of", "2026-10-14T23:00:00"])
