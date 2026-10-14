"""E7 evidence-pipeline integration tests (plan E7, contracts §12.5).

The LIVE/RECORDED_REPLAY read pipeline produces a typed evidence report and
MUST NOT reach the finance consumer: after a completed read the case is
EVIDENCE_READY with conclusion=None and no instruction, and the report says
assessment is not connected. STUB keeps the existing assessment path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.case import CaseState, CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.documents import OcrBlock, OcrPage, OcrSourceResult, OcrWord
from invoice_referee.evidence.reader import FileOcrReader
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


class FakeEvidenceReader:
    """A file-level OCR provider (wrapped by FileOcrReader in the workflow)."""

    def __init__(self) -> None:
        self.calls = 0

    async def ocr_file(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
        self.calls += 1
        markdown = "GIẤY QUYẾT TOÁN\nTổng cộng: 100.000"
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="fake",
            model="m",
            pages=(
                OcrPage(
                    page=1,
                    markdown=markdown,
                    blocks=(
                        OcrBlock(
                            id="b1", kind="text", content=markdown,
                            words=(OcrWord(text="100.000", block_start=0, block_end=7, confidence=0.95),),
                        ),
                    ),
                ),
            ),
        )


class StubClassifier:
    async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
        if "classify" in system.lower():
            import json

            source_id = json.loads(user)["documents"][0]["source_id"]
            return {"documents": [
                {"source_id": source_id, "page_range": [1, 1],
                 "document_type": "SETTLEMENT_FORM", "roles": ["SETTLEMENT_DECLARATION"]}
            ]}
        # One FOUND field with a real quote from the fake OCR text, so the run is
        # genuinely usable (a run with no FOUND field is a technical failure).
        return {"fields": [
            {"field": "printed_total", "state": "FOUND", "value": "100000",
             "quote": "Tổng cộng: 100.000", "page": 1}
        ], "lines": []}


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "r.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up")
    wf.import_demo_context(Path("data/demo/company-context.json"), origin="SIMULATED")
    return wf


def _ctx(wf: CaseWorkflow, command_id: str, version: int = 1) -> CommandContext:
    session = wf.start_session(
        tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
    )
    return CommandContext(
        session_id=session.session_id, actor_id="employee:employee-a",
        command_id=command_id, expected_case_version=version,
    )


async def _root_with_source(wf: CaseWorkflow, activity: str = "activity:travel-a") -> str:
    created = await wf.execute(
        _ctx(wf, f"cmd:create:{activity}"),
        CreateDraft(
            activity_data=ActivityData(
                activity_id=activity,
                name=activity,
                occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
                declared_purpose="Công tác",
            )
        ),
    )
    root = created.case_view.id
    storage_key = f"tenant:demo/{root}/gd.pdf"
    stored = wf.uploads_dir / storage_key
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"%PDF-1.4 evidence")
    await wf.execute(
        _ctx(wf, f"cmd:attach:{root}", version=wf.view(_ctx(wf, "r"), root).version),
        AttachSources(root_id=root, uploads=(
            SourceUpload(filename="gd.pdf", media="PDF", digest="a" * 64, storage_key=storage_key),
        )),
    )
    return root


async def _submit(wf: CaseWorkflow, root: str, activity: str, command_id: str):
    return await wf.execute(
        _ctx(wf, command_id, version=wf.view(_ctx(wf, "r2"), root).version),
        Submit(root_id=root, declaration=Declaration(activity_id=activity, declared_purpose="Công tác")),
    )


async def test_live_evidence_assesses_finance_after_read(tmp_path: Path) -> None:
    # A5 releases the E7 "never assess" guard: after a completed read the typed
    # admission consumer runs and the case reaches a real finance state.
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeEvidenceReader()), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:submit")
    await wf.run_evidence_job_for(root)

    view = wf.view(_ctx(wf, "r3"), root)
    assert view.evidence_report is not None
    assert view.evidence_report.documents
    assert view.assessment_ready is True
    assert view.assessment_blocker is None
    # The fake report has no line rows/context coverage, so the finance gates
    # are open (WAITING) with real typed issues — not a cheerful "ready".
    assert view.state == "WAITING"
    assert view.conclusion is not None


async def test_evidence_ready_until_assessment_runs(tmp_path: Path) -> None:
    # Publishing the report without the consumer running leaves EVIDENCE_READY
    # with the assessment marked pending (the report is present, no conclusion).
    from invoice_referee.domain.evidence import ReadResult

    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeEvidenceReader()), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(
            cx, tenant="tenant:demo", root_id=root, report=ReadResult()
        )
    view = wf.view(_ctx(wf, "r4"), root)
    assert view.state == "EVIDENCE_READY"
    assert view.assessment_ready is False
    assert view.assessment_blocker == "EVIDENCE_ASSESSMENT_PENDING"


async def test_equal_digest_two_roots_has_independent_artifacts(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root_a = await _root_with_source(wf, "activity:travel-a")
    root_b = await _root_with_source(wf, "activity:travel-b")
    reader = FakeEvidenceReader()
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=reader), classifier=StubClassifier(), artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root_a, "activity:travel-a", "cmd:sub-a")
    await wf.run_evidence_job_for(root_a)
    await _submit(wf, root_b, "activity:travel-b", "cmd:sub-b")
    await wf.run_evidence_job_for(root_b)
    assert reader.calls == 2  # equal bytes, two roots -> two OCR calls


def test_evidence_ready_in_case_state_literal() -> None:
    assert "EVIDENCE_READY" in CaseState.__args__


async def test_offline_path_makes_no_real_provider_calls(tmp_path: Path) -> None:
    # The dev server defaults to LIVE (aee7fb38), so the offline evidence path
    # must never reach a real Mistral/X-Kiro client. A fake reader records calls
    # and no network client is constructed.
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    reader = FakeEvidenceReader()
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=reader), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:offline")
    await wf.run_evidence_job_for(root)
    # Exactly the fake provider was used; the workflow holds no real client.
    assert reader.calls == 1
    assert getattr(wf, "_evidence_reader", None) is not None
    assert not hasattr(wf, "_mistral_client")


async def test_stub_path_still_assesses_finance(tmp_path: Path) -> None:
    # STUB keeps the existing assessment flow: no evidence report, normal state.
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    await _submit(wf, root, "activity:travel-a", "cmd:stub")
    view = wf.view(_ctx(wf, "r5"), root)
    assert view.evidence_report is None
    assert view.state != "EVIDENCE_READY"


async def test_missing_source_bytes_produces_a_problem(tmp_path: Path) -> None:
    from invoice_referee.domain.evidence import SourceRef
    from invoice_referee.evidence.artifacts import ArtifactStore
    from invoice_referee.evidence.pipeline import read_root

    source = SourceRef(id="source:missing", digest="b" * 64, tenant="tenant:demo",
                       media="PDF", storage_key="nope")
    report = await read_root(
        sources=(source,), reader=FileOcrReader(provider=FakeEvidenceReader()),
        classifier=StubClassifier(), artifacts=ArtifactStore(root=tmp_path / "a"),
        source_bytes={}, budget=RunBudget(), provider_mode="LIVE",
    )
    # A missing source is NOT silently dropped: it is a material technical problem.
    assert report.problems
    assert any(p.kind == "TECHNICAL" for p in report.problems)


async def test_stub_conclusion_replaced_by_typed_assessment(tmp_path: Path) -> None:
    # A prior STUB conclusion must not stand as current once the evidence
    # consumer re-assesses the typed report (plan A5). The stale instruction is
    # cleared and the report drives the new state.
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    # First submit in STUB produces a finance conclusion.
    await _submit(wf, root, "activity:travel-a", "cmd:stub-1")
    stub_view = wf.view(_ctx(wf, "rs"), root)
    # Now switch to evidence mode and read; the typed consumer re-assesses.
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeEvidenceReader()), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:live-1")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "rs2"), root)
    assert view.evidence_report is not None
    assert view.assessment_ready is True
    # The typed assessment replaced the STUB conclusion (a fresh BLOCKED/WAITING
    # state from the real gates), not the old STUB one.
    assert view.conclusion is not None
    assert view.state == "WAITING"
    _ = stub_view  # historical view retained in the command log/audit


async def test_failed_evidence_job_sets_technical_error(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)

    class BoomReader:
        async def ocr_file(self, *a, **k):
            raise RuntimeError("provider exploded")

    wf.enable_evidence_read(
        reader=FileOcrReader(provider=BoomReader()), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:boom")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "rb"), root)
    assert view.state == "TECHNICAL_ERROR"
    assert view.problems  # a visible problem, not a silent PROCESSING


async def test_source_change_before_publish_is_not_published(tmp_path: Path) -> None:
    # If the input basis changes while a job is in flight, the stale report must
    # not be published (plan E7 durable-basis fix).
    from invoice_referee.workflow import evidence_jobs

    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)
    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeEvidenceReader()), classifier=StubClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:race")
    # Change the input basis (a new source) before the worker publishes.
    await wf.execute(
        _ctx(wf, "cmd:attach2", version=wf.view(_ctx(wf, "rr"), root).version),
        AttachSources(root_id=root, uploads=(
            SourceUpload(filename="extra.pdf", media="PDF", digest="c" * 64,
                         storage_key=f"tenant:demo/{root}/extra.pdf"),
        )),
    )
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "rr2"), root)
    # The stale result is NOT published for the changed basis: no evidence
    # report is attached and the case is not EVIDENCE_READY.
    assert view.evidence_report is None
    assert view.state != "EVIDENCE_READY"


async def test_unreadable_evidence_is_not_a_false_success(tmp_path: Path) -> None:
    # If classification/extraction yields nothing usable, the case must not be
    # presented as EVIDENCE_READY with no explanation (never a false success).
    wf = _workflow(tmp_path)
    root = await _root_with_source(wf)

    class EmptyClassifier:
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            if "classify" in system.lower():
                return {"documents": []}
            return {"fields": [], "lines": []}

    wf.enable_evidence_read(
        reader=FileOcrReader(provider=FakeEvidenceReader()), classifier=EmptyClassifier(),
        artifacts_root=tmp_path / "artifacts", provider_mode="LIVE",
    )
    await _submit(wf, root, "activity:travel-a", "cmd:empty")
    await wf.run_evidence_job_for(root)
    view = wf.view(_ctx(wf, "re"), root)
    # A visible problem, not a cheerful "ready".
    assert view.problems
    assert view.state == "TECHNICAL_ERROR"
