"""LIVE submit reads the uploaded sources, never a seeded STUB transcription.

A judge uploads a new document: the decision must come from reading *that*
document (contracts §5, §8, §9). A read failure is not a zero — it stays
unresolved and blocks a money conclusion rather than settling on nothing.
"""

from __future__ import annotations

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import Declaration, Submit
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evaluation.models import Transcription


class FakePageReader:
    """A reader whose page text is fixed per source (no provider)."""

    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts
        self.calls: list[tuple[str, int]] = []

    async def ocr_page(self, source: SourceRef, page: int) -> str:
        self.calls.append((source.id, page))
        return self.texts.get(source.id, "")


class RecordingTranscriber:
    """Wraps a reader and counts how many times the pipeline read a source."""

    def __init__(self, reader: FakePageReader) -> None:
        self.reader = reader
        self.reads = 0

    async def __call__(self, **kwargs):
        from invoice_referee.evidence.pipeline import transcribe_root

        self.reads += 1
        return await transcribe_root(reader=self.reader, **kwargs)


def _ctx(workflow, root_id: str, version: int) -> CommandContext:
    session = workflow.start_session(
        tenant="tenant:demo", persona="employee", actor_id="employee:employee-a"
    )
    return CommandContext(
        session_id=session.session_id,
        actor_id="employee:employee-a",
        command_id=f"cmd:live:{root_id}",
        expected_case_version=version,
    )


async def _attach(app_fixture, root: str, text: str) -> str:
    """Attach one source and return its storage_key; the fake reader maps it."""
    from invoice_referee.domain.commands import AttachSources, SourceUpload

    ctx = app_fixture.ctx(actor="employee:employee-a", expected_case_version=1)
    upload = SourceUpload(
        filename="hoadon.pdf", media="PDF", digest="a" * 64, storage_key=f"tenant:demo/{root}/hoadon.pdf"
    )
    result = await app_fixture.workflow.execute(ctx, AttachSources(root_id=root, uploads=(upload,)))
    # The stored source id is what the reader is keyed by.
    return result.case_view.sources[0].id


async def test_live_submit_reads_the_uploaded_source(app_fixture):
    created = await app_fixture.create(employee="employee:employee-a", activity="activity:travel-a")
    root = created.case_view.id
    source_id = await _attach(app_fixture, root, "x")

    # The source text (as a reader would return it) encodes the real amounts.
    reader = FakePageReader(
        {
            source_id: (
                "HÓA ĐƠN\nTổng chi 8.000.000\nNhân viên trả 5.000.000\n"
                "Công ty trả 3.000.000\nỨng 2.000.000\nĐối chiếu đủ giai đoạn\n"
                "Số hóa đơn invoice:live-1"
            )
        }
    )
    transcriber = RecordingTranscriber(reader)
    app_fixture.workflow.enable_live_read(transcriber, provider_mode="LIVE")

    ctx = _ctx(app_fixture.workflow, root, app_fixture._version(root))
    result = await app_fixture.workflow.execute(
        ctx, Submit(root_id=root, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="Công tác"))
    )
    view = result.case_view
    assert transcriber.reads == 1, "LIVE submit must read the source exactly once"
    assert reader.calls, "the reader must be called on the uploaded source"
    # T8/E5/C3/A2 => S3 => one PAY 3m, derived from the *read* text.
    assert view.state == "READY_TO_EXECUTE"
    assert len(view.instructions) == 1
    assert view.instructions[0].amount == 3_000_000


async def test_live_does_not_use_the_seeded_stub_transcription(app_fixture):
    # A root carries a STUB transcription that would produce a different
    # decision; in LIVE mode the read result must win.
    created = await app_fixture.create(employee="employee:employee-a", activity="activity:travel-a")
    root = created.case_view.id
    source_id = await _attach(app_fixture, root, "x")

    # Seed a STUB transcription that would settle at S=0 (E2/A2).
    from invoice_referee.evaluation.models import Transcription, TranscriptionFact

    stub = Transcription(
        facts=(
            TranscriptionFact(field="incurred", value=2_000_000, role="INVOICE"),
            TranscriptionFact(field="paid_employee", value=2_000_000, role="PAYMENT"),
            TranscriptionFact(field="advance", value=2_000_000, role="ADVANCE"),
            TranscriptionFact(field="coverage", value=1, role="LEDGER"),
        )
    )
    conn = app_fixture.db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO case_transcriptions (root_id, transcription_json, created_at) "
            "VALUES (?, ?, ?)",
            (root, stub.model_dump_json(), "2026-10-13T00:00:00+00:00"),
        )
    finally:
        conn.close()

    # The read text says S=3m; that must drive the decision, not the STUB row.
    reader = FakePageReader(
        {
            source_id: (
                "Tổng chi 8.000.000\nNhân viên trả 5.000.000\nCông ty trả 3.000.000\n"
                "Ứng 2.000.000\nĐối chiếu đủ giai đoạn"
            )
        }
    )
    app_fixture.workflow.enable_live_read(RecordingTranscriber(reader), provider_mode="LIVE")

    ctx = _ctx(app_fixture.workflow, root, app_fixture._version(root))
    result = await app_fixture.workflow.execute(
        ctx, Submit(root_id=root, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="Công tác"))
    )
    assert result.case_view.instructions[0].amount == 3_000_000
    assert result.case_view.state == "READY_TO_EXECUTE"


async def test_read_failure_does_not_become_zero(app_fixture):
    # No readable text: the decision stays unresolved (WAITING / no instruction),
    # never a settled zero.
    created = await app_fixture.create(employee="employee:employee-a", activity="activity:travel-a")
    root = created.case_view.id
    await _attach(app_fixture, root, "x")

    reader = FakePageReader({})  # every page returns ""
    app_fixture.workflow.enable_live_read(RecordingTranscriber(reader), provider_mode="LIVE")

    ctx = _ctx(app_fixture.workflow, root, app_fixture._version(root))
    result = await app_fixture.workflow.execute(
        ctx, Submit(root_id=root, declaration=Declaration(activity_id="activity:travel-a", declared_purpose="Công tác"))
    )
    view = result.case_view
    assert view.instructions == ()
    assert view.state != "SETTLED"
    assert view.actual_money.S.state != "KNOWN" or int(view.actual_money.S.value or 0) != 0
