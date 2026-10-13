"""The read->transcription extractor matches real document wording (plan R4).

The LIVE baseline showed the literal extractor missing fields because it stopped
at the first source with any field and its cues did not match the generated
documents. It must accumulate facts across the root's sources and recognise the
payer/receipt wording, without inventing a field that is absent.
"""

from __future__ import annotations

from invoice_referee.evidence.pipeline import transcribe_text


def test_reads_the_invoice_and_receipt_wording() -> None:
    text = (
        "HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nTổng chi 8.000.000 VND\n"
        "BIÊN NHẬN THANH TOÁN\nNgười thanh toán: Nguyễn Văn A\nĐã thanh toán 5.000.000 VND"
    )
    t = transcribe_text(text)
    fields = {f.field: f.value for f in t.facts}
    assert fields["incurred"] == 8_000_000


def test_advance_and_coverage_are_recognised() -> None:
    text = "PHIẾU TẠM ỨNG\nỨng 2.000.000 VND\nBẢNG KÊ HOẠT ĐỘNG\nĐối chiếu đủ giai đoạn"
    t = transcribe_text(text)
    fields = {f.field: f.value for f in t.facts}
    assert fields["advance"] == 2_000_000
    assert fields["coverage"] == 1


def test_blank_text_is_none() -> None:
    assert transcribe_text("   ") is None


async def test_transcribe_root_tags_data_origin_from_mode() -> None:
    # A LIVE read must not be mislabelled as a STUB hand-transcription
    # (contracts §5: the label reflects the reader that produced the reading).
    from invoice_referee.domain.evidence import SourceRef
    from invoice_referee.evidence.pipeline import transcribe_root
    from invoice_referee.evidence.trace import RunBudget

    class Reader:
        async def ocr_page(self, source, page):
            return "Tổng chi 8.000.000 VND"

    source = SourceRef(id="s", digest="a" * 64, tenant="t", media="PDF", storage_key="k")
    for mode, expected in (("LIVE", "LIVE_READ"), ("RECORDED_REPLAY", "RECORDED_REPLAY")):
        outcome = await transcribe_root(
            reader=Reader(), sources=(source,), budget=RunBudget(), provider_mode=mode
        )
        assert outcome.transcription.data_origin == expected, mode


async def test_transcribe_root_merges_facts_across_sources() -> None:
    # A root's documents carry different fields (invoice -> incurred, receipt ->
    # paid, advance slip -> advance); the pipeline must merge them, not stop at
    # the first source that yields any field.
    from invoice_referee.domain.evidence import SourceRef
    from invoice_referee.evidence.pipeline import transcribe_root
    from invoice_referee.evidence.trace import RunBudget

    class Reader:
        def __init__(self, texts):
            self.texts = texts

        async def ocr_page(self, source, page):
            return self.texts.get(source.id, "")

    sources = (
        SourceRef(id="s1", digest="a" * 64, tenant="t", media="PDF", storage_key="k1"),
        SourceRef(id="s2", digest="b" * 64, tenant="t", media="PDF", storage_key="k2"),
        SourceRef(id="s3", digest="c" * 64, tenant="t", media="PDF", storage_key="k3"),
    )
    reader = Reader({
        "s1": "HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nTổng chi 8.000.000 VND",
        "s2": "BIÊN NHẬN THANH TOÁN\nNgười thanh toán: Nguyễn Văn A\nĐã thanh toán 5.000.000 VND",
        "s3": "PHIẾU TẠM ỨNG\nỨng 2.000.000 VND",
    })
    outcome = await transcribe_root(
        reader=reader, sources=sources, budget=RunBudget(), provider_mode="LIVE"
    )
    assert outcome.transcription is not None
    fields = {f.field: f.value for f in outcome.transcription.facts}
    assert fields["incurred"] == 8_000_000
    assert fields["advance"] == 2_000_000
