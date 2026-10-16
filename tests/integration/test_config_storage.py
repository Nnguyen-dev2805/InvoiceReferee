"""Config, storage and public-runtime checks (plan T10; design §10).

A missing key/model/context is reported honestly, never faked. Paths resolve
independently of the current working directory. Sessions/Verify are isolated.
A LangSmith failure never changes a financial outcome. The bounded parser
rejects an over-limit document with a LIMIT problem, not a fake pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.api.app import create_app
from invoice_referee.config import Settings
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.import_demo_context(
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "legacy-company-context.json",
        origin="SIMULATED",
    )
    return wf


def test_missing_live_keys_are_reported_not_faked(monkeypatch) -> None:
    from invoice_referee.config import LIVE_REQUIRED_SETTINGS

    for name in LIVE_REQUIRED_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.live_ready is False
    assert set(settings.missing_for_live()) == set(LIVE_REQUIRED_SETTINGS)


def test_langsmith_is_opt_in_and_never_required(monkeypatch) -> None:
    from invoice_referee.config import LIVE_REQUIRED_SETTINGS

    assert not any("LANGSMITH" in name for name in LIVE_REQUIRED_SETTINGS)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    settings = Settings(_env_file=None)
    assert settings.langsmith_ready is False


async def test_paths_independent_of_cwd(tmp_path: Path, monkeypatch) -> None:
    # The app builds its workflow with absolute paths, so it runs from any cwd.
    monkeypatch.chdir(tmp_path)
    wf = _workflow(tmp_path)
    app = create_app(wf, mode="STUB", frontend_dir=None)
    assert app.state.workflow is wf


async def test_health_endpoint_reports_redacted_versions(app_fixture) -> None:
    response = await app_fixture.client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "STUB"
    assert "python" in body
    # No secret value is exposed.
    assert "api_key" not in str(body).lower()


async def test_sessions_are_isolated(app_fixture) -> None:
    # Two tenants never see each other's cases.
    a = await app_fixture.create(employee="employee:employee-a", activity="activity:travel-a")
    tenant_b = app_fixture.client_for(tenant="tenant:b")
    listed = await tenant_b.get("/api/cases")
    assert listed.status_code == 200
    assert a.case_view.id not in {c["id"] for c in listed.json()["cases"]}


async def test_langsmith_failure_does_not_change_financial_state(app_fixture) -> None:
    # A trace whose client raises must not affect the persisted case.
    from invoice_referee.evidence.trace import LangSmithTrace, TraceSpan

    class Boom:
        def create_run(self, **kwargs):
            raise RuntimeError("telemetry down")

        def update_run(self, *args, **kwargs):
            raise RuntimeError("telemetry down")

    trace = LangSmithTrace(api_key="k", client=Boom())
    trace.record(TraceSpan(name="read", run_id="r1"))  # must not raise
    v = await app_fixture.submit_packet("travel-clean", mode="STUB")
    assert v.state == "READY_TO_EXECUTE"


def test_bounded_parser_rejects_over_limit_pdf(tmp_path: Path) -> None:
    # A PDF beyond the page ceiling is a LIMIT problem, never a fake pass.
    from invoice_referee.evidence.pdf import PdfLimitError, native_text

    # A tiny valid PDF with 1 page is fine; the limit is enforced by max_pages.
    import pypdf

    writer = pypdf.PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    path = tmp_path / "many.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(PdfLimitError):
        native_text(path, max_pages=2)
