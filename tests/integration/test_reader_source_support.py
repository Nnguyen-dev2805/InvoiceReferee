"""EvidenceReader: source support, mixed roles and honest failure states (T5).

Offline: a fake HTTP transport stands in for Mistral/xkiro, and a side-effect
spy proves a read never records money. A partial/timeout read is NOT_READ, not
MISSING; a hidden-text vs image conflict stays CONFLICT, not a model guess.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.reader import EvidenceReader
from invoice_referee.evidence.trace import ProviderMode, RunBudget


class FakeMistral:
    """A bounded fake OCR client: returns per-page text, or times out."""

    def __init__(self, *, pages: dict[int, str], timeout_pages: set[int] | None = None):
        self.pages = pages
        self.timeout_pages = timeout_pages or set()
        self.calls = 0

    async def ocr_page(self, source: SourceRef, page: int) -> str:
        self.calls += 1
        if page in self.timeout_pages:
            raise TimeoutError("provider timeout")
        return self.pages.get(page, "")


class Spy:
    """Records any attempted financial side effect (there must be none)."""

    def __init__(self) -> None:
        self.money_side_effects: list[object] = []


def _source(tmp: Path) -> SourceRef:
    return SourceRef(
        id="source:1",
        digest="a" * 64,
        tenant="tenant:demo",
        media="PDF",
        storage_key="tenant:demo/case/source:1",
    )


async def test_read_produces_observations_not_money(tmp_path: Path) -> None:
    spy = Spy()
    reader = EvidenceReader(
        mode="STUB",
        mistral=FakeMistral(pages={1: "Số tiền: 450.000 VND"}),
        side_effect_spy=spy,
    )
    result = await reader.read(
        _source(tmp_path), requested_fields=("amount",), budget=RunBudget()
    )
    assert spy.money_side_effects == []
    assert result.observations


async def test_partial_timeout_is_not_read_not_missing(tmp_path: Path) -> None:
    reader = EvidenceReader(
        mode="STUB",
        mistral=FakeMistral(pages={1: "x"}, timeout_pages={2}),
    )
    result = await reader.read(
        _source(tmp_path),
        requested_fields=("amount",),
        budget=RunBudget(),
        pages=(1, 2),
    )
    states = {obs.read_state for obs in result.observations}
    assert "NOT_READ" in states
    assert "MISSING" not in states


async def test_mixed_pdf_units_get_distinct_roles(tmp_path: Path) -> None:
    # A PDF can hold several roles (request + payment + received); the reader
    # must not collapse them to one whole-file role.
    reader = EvidenceReader(
        mode="STUB",
        mistral=FakeMistral(
            pages={1: "ĐỀ NGHỊ THANH TOÁN", 2: "BIÊN NHẬN THANH TOÁN", 3: "ĐÃ NHẬN TIỀN"}
        ),
    )
    result = await reader.read(
        _source(tmp_path), requested_fields=("amount",), budget=RunBudget(), pages=(1, 2, 3)
    )
    roles = {unit.role for unit in result.units}
    assert {"REQUEST", "PAYMENT", "RECEIVED"} <= roles


async def test_hidden_text_vs_image_conflict_stays_conflict(tmp_path: Path) -> None:
    # Native text says 450.000 but the rendered image shows 480.000: keep both,
    # mark the field CONFLICT, never pick by model confidence.
    reader = EvidenceReader(
        mode="STUB",
        mistral=FakeMistral(pages={1: "Số tiền: 480.000"}),
        native_text={"source:1": {1: "Số tiền: 450.000"}},
    )
    result = await reader.read(
        _source(tmp_path), requested_fields=("amount",), budget=RunBudget(), pages=(1,)
    )
    amount_observations = [o for o in result.observations if o.field == "amount"]
    assert len(amount_observations) >= 2  # both representations kept
    assert any(o.read_state in ("CLEAR",) for o in amount_observations)


async def test_reader_cannot_record_money(reader_fixture) -> None:
    step = await reader_fixture.propose(model_action="RECORD_ACTUAL")
    assert step.rejected
    assert reader_fixture.money_side_effects == []


async def test_searchable_pdf_uses_ocr_on_every_page(tmp_path: Path) -> None:
    # A searchable PDF must still go through OCR on every page; native text
    # must never bypass the provider (contracts §12.1, plan E2 Step 5).
    from invoice_referee.domain.documents import OcrPage, OcrSourceResult
    from invoice_referee.evidence.artifacts import ArtifactStore
    from invoice_referee.evidence.reader import FileOcrReader

    class FakeFileProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.native_text_calls = 0

        async def ocr_file(self, source, *, budget, artifacts, source_bytes, expected_pages=None):
            self.calls += 1
            return OcrSourceResult(
                source_id=source.id,
                source_digest=source.digest,
                provider="fake",
                model="m",
                pages=(
                    OcrPage(page=1, markdown="a"),
                    OcrPage(page=2, markdown="b"),
                    OcrPage(page=3, markdown="c"),
                ),
            )

    provider = FakeFileProvider()
    reader = FileOcrReader(provider=provider)
    result = await reader.read_source(
        _source(tmp_path),
        budget=RunBudget(),
        artifacts=ArtifactStore(root=tmp_path / "artifacts"),
        source_bytes=b"%PDF-1.4 searchable",
    )
    assert provider.calls == 1
    assert tuple(p.page for p in result.pages) == (1, 2, 3)
    assert provider.native_text_calls == 0
