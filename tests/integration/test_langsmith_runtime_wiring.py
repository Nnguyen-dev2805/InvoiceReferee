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

DEMO_CONTEXT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "legacy-company-context.json"
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
    assert ocr["inputs"]["source_id"]
    assert len(ocr["inputs"]["source_digest"]) == 64
    assert ocr["inputs"]["media"] == "PDF"
    assert ocr["outputs"]["pages_read"] == 1
    assert ocr["outputs"]["provider"] == "fake"
    assert "markdown" not in str(ocr["outputs"]).lower()

    classified = next(r for r in client.runs if r["name"] == "classify")
    assert classified["outputs"]["documents"][0]["document_type"] == "SETTLEMENT_FORM"
    extracted = next(r for r in client.runs if str(r["name"]).startswith("extract:"))
    assert extracted["outputs"]["fields"][0]["field"] == "printed_total"
    assert extracted["outputs"]["fields"][0]["state"] == "FOUND"
    validated = next(r for r in client.runs if str(r["name"]).startswith("validate:"))
    assert isinstance(validated["outputs"]["findings"], list)
    assert job_root["outputs"]["document_count"] == 1
    assert job_root["outputs"]["status"] == "COMPLETED"
    assert job_root["outputs"]["documents"][0]["fields"][0]["field"] == "printed_total"
    assert job_root["outputs"]["state_after"]
    assert job_root["outputs"]["version_after"] >= 1
    admission = next(r for r in client.runs if r["name"] == "admission")
    assert admission["outputs"]["status"] == "ASSEMBLED"
    assert admission["outputs"]["employee_paid_state"] == "NOT_INDEPENDENTLY_BANK_VERIFIED"
    assert set(admission["outputs"]["read_set"]) == {
        "input_revision", "control_epoch", "context_version", "ledger_version", "usage_version"
    }
    reconcile = next(r for r in client.runs if r["name"] == "reconcile")
    assert set(reconcile["outputs"]["axes"]) == {"T", "E", "C", "A", "P", "R", "unpaid", "S"}
    assert all("state" in fact for fact in reconcile["outputs"]["axes"].values())
    commit = next(r for r in client.runs if r["name"] == "commit")
    assert commit["outputs"]["committed"] is True
    assert "state_before" in commit["outputs"] and "state_after" in commit["outputs"]
    command_root = next(r for r in client.runs if r["name"] == "command:submit")
    assert command_root["outputs"]["command"] == "SUBMIT"
    assert command_root["outputs"]["state"]
    assert not [r for r in client.runs if r["run_type"] == "llm"]
    handler = next(
        run for run in client.runs
        if run["name"] == "handler" and run.get("parent_run_id") == command_root["id"]
    )
    assert handler["outputs"]["command"] == "SUBMIT"
    assert handler["outputs"]["status"] == "HANDLED"
    assert handler["outputs"]["job_id"]


async def test_sink_failure_does_not_change_the_business_result(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    _wire(wf, BoomClient())
    root = await _seed(wf, tmp_path)
    await _submit(wf, root)
    await wf.run_evidence_job_for(root)
    view = _view(wf, root)
    assert view.conclusion is not None, "a tracing failure must not lose the conclusion"
    assert wf.trace.export_errors, "the export failure must be visible"


async def test_settlement_draft_root_contains_the_returned_draft(tmp_path: Path) -> None:
    client = FakeClient()
    wf = _workflow(tmp_path)
    _wire(wf, client)
    root = await _seed(wf, tmp_path)
    session_id = str(wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"])
    draft = await wf.read_settlement_draft(wf.session(session_id), root, uploads=())

    trace = next(run for run in client.runs if run["name"] == "settlement-draft-read")
    assert trace["outputs"]["status"] == "COMPLETED"
    assert trace["outputs"]["document_count"] == 1
    assert trace["outputs"]["draft"]["declared_advance"] == draft["declared_advance"]
    assert trace["outputs"]["draft"]["warnings"] == draft["warnings"]
    assert trace["extra"]["metadata"]["trace_output_state"] == "COLLECTED"


async def test_validation_trace_surfaces_shared_arithmetic_findings(tmp_path: Path) -> None:
    import json

    from invoice_referee.domain.documents import OcrBlock, OcrPage, OcrSourceResult
    from invoice_referee.domain.evidence import SourceRef
    from invoice_referee.evidence.artifacts import ArtifactStore
    from invoice_referee.evidence.pipeline import read_root
    from invoice_referee.evidence.trace import RunBudget

    markdown = (
        "GIẤY QUYẾT TOÁN\nSố tiền đã tạm ứng: 4.000.000\n"
        "Tổng cộng: 3.240.000\nSố tiền nhân viên hoàn trả công ty: 700.000"
    )

    class ArithmeticOcr:
        async def ocr_file(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
            return OcrSourceResult(
                source_id=source.id,
                source_digest=source.digest,
                provider="fake",
                model="fake-ocr",
                pages=(OcrPage(page=1, markdown=markdown, blocks=(OcrBlock(
                    id="b1", kind="text", content=markdown, words=()
                ),)),),
            )

    class ArithmeticLlm:
        async def complete_json(self, *, system: str, user: str, budget):
            if "classify" in system.lower():
                source_id = json.loads(user)["documents"][0]["source_id"]
                return {"documents": [{
                    "source_id": source_id,
                    "page_range": [1, 1],
                    "document_type": "SETTLEMENT_FORM",
                    "roles": ["SETTLEMENT_DECLARATION"],
                }]}
            return {"fields": [
                {"field": "declared_advance", "state": "FOUND", "value": "4000000", "quote": "4.000.000", "page": 1},
                {"field": "printed_total", "state": "FOUND", "value": "3240000", "quote": "3.240.000", "page": 1},
                {"field": "printed_return", "state": "FOUND", "value": "700000", "quote": "700.000", "page": 1},
            ], "line_items": []}

    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    source = SourceRef(
        id="source:arithmetic",
        digest="a" * 64,
        tenant="tenant:demo",
        media="PDF",
        storage_key="tenant:demo/case:arithmetic/source.pdf",
        filename="source.pdf",
    )
    with recorder.operation("settlement-draft-read"):
        await read_root(
            sources=(source,),
            reader=FileOcrReader(provider=ArithmeticOcr()),
            classifier=ArithmeticLlm(),
            artifacts=ArtifactStore(root=tmp_path / "artifacts"),
            source_bytes={source.id: b"synthetic pdf"},
            budget=RunBudget(),
            provider_mode="LIVE",
            root_id="case:arithmetic",
        )

    validation = next(run for run in client.runs if run["name"] == "validate:SETTLEMENT_FORM")
    arithmetic = validation["outputs"]["arithmetic_checks"]
    assert arithmetic["state"] == "CHECKED_BY_SHARED_RULE"
    assert arithmetic["findings"][0]["code"] == "settlement-return"
    assert "760000" in arithmetic["findings"][0]["basis"]
    assert "700000" in arithmetic["findings"][0]["basis"]
    assert "60000" in arithmetic["findings"][0]["basis"]


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
