"""Runtime wiring: the composition root builds a recorder and real operations
emit root/child spans over the actual web workflow.

These exercise the SAME CaseWorkflow the web uses (submit → evidence job →
admission → reconcile → commit; draft read), not a separate observation pipeline.
Tracing is injected through a fake SDK client so no network is touched; a sink
failure must not change the business result, and cache reuse must not add an OCR
call.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

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
from invoice_referee.evidence.reader import FileOcrReader
from invoice_referee.evidence.telemetry import TraceRecorder
from invoice_referee.evidence.trace import LangSmithTrace
from invoice_referee.runtime import build_workflow
from invoice_referee.workflow.db import Database

DEMO_CONTEXT = Path(__file__).resolve().parents[2] / "data" / "demo" / "company-context.json"
TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
ACTIVITY = "activity:travel-a"
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


class FakeClient:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []

    def create_run(self, **kwargs: object) -> None:
        self.runs.append(kwargs)

    def update_run(self, run_id: str, **kwargs: object) -> None:
        self.updates.append({"run_id": run_id, **kwargs})


class BoomClient:
    def create_run(self, **kwargs: object) -> None:
        raise RuntimeError("langsmith down")

    def update_run(self, run_id: str, **kwargs: object) -> None:
        raise RuntimeError("langsmith down")


class FakeOcr:
    async def ocr_file(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
        from invoice_referee.domain.documents import OcrBlock, OcrPage, OcrSourceResult, OcrWord

        markdown = "GIẤY QUYẾT TOÁN\nTổng cộng: 3.240.000\nỨng: 4.000.000"
        return OcrSourceResult(
            source_id=source.id, source_digest=source.digest, provider="fake", model="m",
            pages=(OcrPage(page=1, markdown=markdown, blocks=(
                OcrBlock(id="b1", kind="text", content=markdown,
                         words=(OcrWord(text="3.240.000", block_start=0, block_end=9, confidence=0.95),)),
            )),),
        )


class StubClassifier:
    async def complete_json(self, *, system: str, user: str, budget):
        import json

        if "classify" in system.lower():
            sid = json.loads(user)["documents"][0]["source_id"]
            return {"documents": [{"source_id": sid, "page_range": [1, 1],
                                   "document_type": "SETTLEMENT_FORM",
                                   "roles": ["SETTLEMENT_DECLARATION"]}]}
        return {"fields": [{"field": "printed_total", "state": "FOUND",
                            "value": "3240000", "quote": "Tổng cộng: 3.240.000", "page": 1}],
                "lines": []}


def _settings() -> Settings:
    return Settings(_env_file=None, mistral_api_key="x", mistral_ocr_model="x",
                    xkiro_api_key="x", xkiro_base_url="http://x", invoice_referee_llm_model="x")


def _workflow(tmp_path: Path) -> object:
    return build_workflow(_settings(), "STUB", db=Database(tmp_path / "r.sqlite"),
                          uploads_dir=tmp_path / "up", context_path=DEMO_CONTEXT, clock=lambda: CLOCK)


def _wire(workflow, client) -> None:
    workflow.enable_evidence_read(
        reader=FileOcrReader(provider=FakeOcr()), classifier=StubClassifier(),
        artifacts_root=Path(workflow.uploads_dir).parent / "artifacts", provider_mode="LIVE",
    )
    workflow.enable_trace(TraceRecorder(LangSmithTrace(api_key="k", client=client)))


async def _seed(wf, tmp_path: Path) -> str:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="Công tác",
                                               occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    storage_key = f"{TENANT}/{root}/hd.pdf"
    stored = wf.uploads_dir / storage_key
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"%PDF-1.4 evidence")
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="c2",
                       expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(
            filename="hd.pdf", media="PDF", digest=hashlib.sha256(b"pdf").hexdigest(),
            storage_key=storage_key),)),
    )
    return root


async def _submit(wf, root: str) -> None:
    session_id = str(wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"])
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    await wf.execute(
        CommandContext(session_id=session_id, actor_id=EMPLOYEE, command_id="c3", expected_case_version=version),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="p")),
    )


def _view(wf, root: str):
    session_id = str(wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"])
    return wf.view(CommandContext(session_id=session_id, actor_id=EMPLOYEE,
                                  command_id="v", expected_case_version=0), root)


async def test_runtime_builds_a_recorder_even_when_tracing_off(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    assert wf.trace is not None
    assert wf.trace.enabled is False


async def test_submit_and_evidence_job_emit_root_and_child_spans(tmp_path: Path) -> None:
    client = FakeClient()
    wf = _workflow(tmp_path)
    _wire(wf, client)
    root = await _seed(wf, tmp_path)
    await _submit(wf, root)
    await wf.run_evidence_job_for(root)

    names = [r["name"] for r in client.runs]
    assert "command:submit" in names, names
    assert "evidence-job" in names, names
    assert any(n.startswith("ocr:") for n in names), names
    assert "confidence-review" in names
    assert "classify" in names
    assert any(n.startswith("extract:") for n in names), names
    assert any(n.startswith("validate:") for n in names), names
    assert "match" in names
    assert "admission" in names
    assert "reconcile" in names
    assert "commit" in names
    ids = [r["id"] for r in client.runs]
    assert len(set(ids)) == len(ids), "every span must have its own id"
    job_root = next(r for r in client.runs if r["name"] == "evidence-job")
    ocr = next(r for r in client.runs if str(r["name"]).startswith("ocr:"))
    assert ocr["parent_run_id"] == job_root["id"]


async def test_sink_failure_does_not_change_the_business_result(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    _wire(wf, BoomClient())
    root = await _seed(wf, tmp_path)
    await _submit(wf, root)
    await wf.run_evidence_job_for(root)
    view = _view(wf, root)
    assert view.conclusion is not None, "a tracing failure must not lose the conclusion"
    assert wf.trace.export_errors, "the export failure must be visible"


async def test_each_command_gets_its_own_operation_root(tmp_path: Path) -> None:
    # A human response/re-assessment and an accountant actual-money record are
    # separate operations, each with its own root span (never one root open over
    # the whole case lifetime).
    from invoice_referee.domain.commands import Control, RecordActual
    from invoice_referee.domain.finance import RecordMoneyInput

    client = FakeClient()
    wf = _workflow(tmp_path)
    _wire(wf, client)
    root = await _seed(wf, tmp_path)
    await _submit(wf, root)
    await wf.run_evidence_job_for(root)
    before = len(client.runs)

    accountant = wf.start_session(tenant=TENANT, persona="accountant", actor_id="employee:accountant-demo")
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    await wf.execute(
        CommandContext(session_id=accountant.session_id, actor_id="employee:accountant-demo",
                       command_id="rec1", expected_case_version=version),
        RecordActual(root_id=root, money=RecordMoneyInput(
            external_key="bank:ADV-1", claimed_kind="ADVANCE_RECEIVED", claimed_scope=ACTIVITY,
            payer="company:demo", payee=EMPLOYEE, amount=4_000_000,
            event_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
            completion_claim="Kế toán xác nhận", reason="ghi nhận")),
    )
    names = [r["name"] for r in client.runs[before:]]
    assert "command:record_actual" in names, names
    # Distinct root ids across the operations.
    roots = [r["id"] for r in client.runs if r["name"] in ("command:submit", "command:record_actual")]
    assert len(set(roots)) == len(roots)


async def test_cache_reuse_does_not_add_ocr_calls(tmp_path: Path) -> None:
    client = FakeClient()
    wf = _workflow(tmp_path)
    provider = FakeOcr()
    calls = {"n": 0}

    class CountingOcr:
        async def ocr_file(self, *a, **k):
            calls["n"] += 1
            return await provider.ocr_file(*a, **k)

    wf.enable_evidence_read(reader=FileOcrReader(provider=CountingOcr()), classifier=StubClassifier(),
                            artifacts_root=tmp_path / "artifacts", provider_mode="LIVE")
    wf.enable_trace(TraceRecorder(LangSmithTrace(api_key="k", client=client)))
    root = await _seed(wf, tmp_path)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    await wf.read_settlement_draft(session, root, ())
    first = calls["n"]
    await _submit(wf, root)
    await wf.run_evidence_job_for(root)
    assert calls["n"] == first, "reuse must not add an OCR call"
