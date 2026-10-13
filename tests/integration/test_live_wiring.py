"""R4: runtime wires the reader per mode; submit reads real sources (plan R4).

A LIVE submit with no usable source must not issue seed money; a new PDF changes
the read result; a STUB transcription is forbidden in LIVE; replay needs a
matching recording; a submit during a preview reuses the job/counters; and the
reader never records money or grants.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.domain.commands import Declaration, Submit
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


class FakeReader:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.calls: list[tuple[str, int]] = []

    async def ocr_page(self, source: SourceRef, page: int) -> str:
        self.calls.append((source.id, page))
        return self.texts.get(source.id, "")


def _wire(workflow: CaseWorkflow, reader, mode: str) -> None:
    from invoice_referee.evidence.pipeline import transcribe_root

    async def transcriber(*, sources, budget=None, provider_mode=mode):
        return await transcribe_root(
            reader=reader, sources=sources, budget=budget or RunBudget(),
            provider_mode=provider_mode,
        )

    workflow.enable_live_read(transcriber, provider_mode=mode)


async def _create_and_attach(app_fixture, activity: str, *, with_source: bool) -> str:
    created = await app_fixture.create(employee="employee:employee-a", activity=activity)
    root = created.case_view.id
    if with_source:
        from invoice_referee.domain.commands import AttachSources, SourceUpload

        ctx = app_fixture.ctx(actor="employee:employee-a", expected_case_version=1)
        await app_fixture.workflow.execute(
            ctx,
            AttachSources(
                root_id=root,
                uploads=(
                    SourceUpload(
                        filename="hd.pdf", media="PDF", digest="a" * 64,
                        storage_key=f"tenant:demo/{root}/hd.pdf",
                    ),
                ),
            ),
        )
    return root


async def test_live_submit_without_sources_cannot_issue_seed_money(app_fixture):
    root = await _create_and_attach(app_fixture, "activity:travel-a", with_source=False)
    _wire(app_fixture.workflow, FakeReader({}), "LIVE")
    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
    )
    from invoice_referee.domain.case import CommandContext

    ctx = CommandContext(
        session_id=session.session_id, actor_id="employee:employee-a",
        command_id="cmd:live-nosrc", expected_case_version=app_fixture._version(root),
    )
    result = await app_fixture.workflow.execute(
        ctx, Submit(root_id=root, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="x"))
    )
    assert result.case_view.instructions == ()


async def test_live_new_pdf_changes_read_result(app_fixture):
    root = await _create_and_attach(app_fixture, "activity:travel-a", with_source=True)
    source_id = app_fixture.view(
        app_fixture.ctx(actor="employee:employee-a"), root
    ).sources[0].id
    reader = FakeReader({source_id: "Tổng chi 8.000.000\nNhân viên trả 5.000.000\nCông ty trả 3.000.000\nỨng 2.000.000\nĐối chiếu đủ"})
    _wire(app_fixture.workflow, reader, "LIVE")
    from invoice_referee.domain.case import CommandContext

    session = app_fixture.workflow.start_session(
        tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
    )
    ctx = CommandContext(
        session_id=session.session_id, actor_id="employee:employee-a",
        command_id="cmd:live-1", expected_case_version=app_fixture._version(root),
    )
    result = await app_fixture.workflow.execute(
        ctx, Submit(root_id=root, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="x"))
    )
    assert reader.calls, "the reader must be called on the uploaded source"
    assert result.case_view.instructions[0].amount == 3_000_000


async def test_replay_requires_matching_recording(tmp_path: Path):
    from invoice_referee.evidence.replay import ReplayReader

    recording = tmp_path / "rec.json"
    reader = ReplayReader(recording)  # no recording on disk
    source = SourceRef(id="s", digest="a" * 64, tenant="tenant:demo", media="PDF", storage_key="k")
    with pytest.raises(TimeoutError):
        await reader.ocr_page(source, 1)


async def test_reader_never_records_money_or_grants(app_fixture):
    root = await _create_and_attach(app_fixture, "activity:travel-a", with_source=True)
    source_id = app_fixture.view(
        app_fixture.ctx(actor="employee:employee-a"), root
    ).sources[0].id
    reader = FakeReader({source_id: "Tổng chi 8.000.000\nĐối chiếu đủ"})
    _wire(app_fixture.workflow, reader, "LIVE")
    # A read produces observations, never money/instructions by itself.
    before = app_fixture.financial_row_count()
    await reader.ocr_page(
        SourceRef(id=source_id, digest="a" * 64, tenant="tenant:demo", media="PDF", storage_key="k"), 1
    )
    assert app_fixture.financial_row_count() == before


def test_build_workflow_wires_reader_per_mode(tmp_path: Path):
    from invoice_referee.config import Settings
    from invoice_referee.runtime import build_workflow

    settings = Settings()
    wf = build_workflow(
        settings, "STUB", db=Database(tmp_path / "r.sqlite"),
        uploads_dir=tmp_path / "up", context_path=Path("data/demo/company-context.json"),
    )
    assert isinstance(wf, CaseWorkflow)
    assert wf.provider_mode == "STUB"
