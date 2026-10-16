"""E2 OCR-every-page tests (plan E2, contracts §12.1).

Offline: a fake HTTP transport stands in for Mistral. The reader must submit
every accepted page to OCR (native PDF text never bypasses it), retain blocks
and word-level confidence, write raw JSON to a bounded private artifact, and
turn any persistence/schema failure into a technical unresolved result — never
a silent empty success.
"""

from __future__ import annotations


def test_page_word_scores_bind_to_their_own_block_offsets():
    from invoice_referee.evidence.mistral import _parse_blocks
    page = {"markdown": "Tiêu đề\nTổng: 120.000", "blocks": [
        {"content": "Tiêu đề", "type": "text"}, {"content": "Tổng: 120.000", "type": "text"}],
        "confidence_scores": {"word_confidence_scores": [
            {"text": "Tiêu đề", "start_index": 0, "confidence": 0.97},
            {"text": "Tổng:", "start_index": 8, "confidence": 0.99},
            {"text": " 120.000", "start_index": 13, "confidence": 0.4}]}}
    blocks = _parse_blocks(page)
    assert [w.text for w in blocks[1].words] == ["Tổng:", " 120.000"]
    assert blocks[1].words[1].confidence == 0.4
    assert blocks[1].words[1].block_start == 5
    assert blocks[1].words[1].block_end == 13
    assert all(w.text != "Tiêu đề" for w in blocks[1].words)


def test_page_score_with_mismatching_offset_is_not_assigned():
    from invoice_referee.evidence.mistral import _parse_blocks
    blocks = _parse_blocks({"markdown": "Tổng: 120.000", "blocks": [{"content": "Tổng: 120.000"}],
        "confidence_scores": {"word_confidence_scores": [
            {"text": "999.000", "start_index": 6, "confidence": 0.99}]}})
    assert blocks[0].words == ()

import json
from pathlib import Path

import httpx
import pytest

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.artifacts import ArtifactStore, ArtifactWriteError
from invoice_referee.evidence.mistral import MistralError, MistralOcrClient
from invoice_referee.evidence.trace import RunBudget

SHA = "a" * 64


def _source(media: str = "PDF", tenant: str = "tenant:demo") -> SourceRef:
    return SourceRef(
        id="source:1",
        digest=SHA,
        tenant=tenant,
        media=media,  # type: ignore[arg-type]
        storage_key=f"{tenant}/root/source:1",
    )


def _ocr_json(pages: list[dict]) -> dict:
    return {"model": "mistral-ocr-1", "pages": pages}


def _page(index: int, markdown: str, words: list[dict] | None = None) -> dict:
    blocks = []
    if words is not None:
        blocks.append(
            {"id": f"b{index}", "type": "text", "content": markdown, "words": words}
        )
    return {"index": index, "markdown": markdown, "blocks": blocks}


def _client(handler) -> MistralOcrClient:
    transport = httpx.MockTransport(handler)
    return MistralOcrClient(
        api_key="k",
        model="mistral-ocr-1",
        base_url="https://api.mistral.ai/v1",
        transport=transport,
    )


async def test_searchable_pdf_uses_ocr_on_every_page(tmp_path: Path) -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=_ocr_json(
                [
                    _page(0, "Trang 1"),
                    _page(1, "Trang 2"),
                    _page(2, "Trang 3"),
                ]
            ),
        )

    client = _client(handler)
    store = ArtifactStore(root=tmp_path / "artifacts")
    result = await client.ocr_file(
        _source("PDF"), budget=RunBudget(), artifacts=store, source_bytes=b"%PDF-1.4 x"
    )

    assert len(calls) == 1, "one file-level OCR call, not per-page"
    assert [p.page for p in result.pages] == [1, 2, 3]
    assert result.pages[0].markdown == "Trang 1"


async def test_ocr_returns_blocks_and_word_confidence(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_ocr_json(
                [
                    _page(
                        0,
                        "Tổng 450.000",
                        words=[
                            {"text": "Tổng", "start": 0, "end": 4, "confidence": 0.99},
                            {"text": "450.000", "start": 5, "end": 12, "confidence": 0.42},
                        ],
                    )
                ]
            ),
        )

    client = _client(handler)
    result = await client.ocr_file(
        _source(), budget=RunBudget(), artifacts=ArtifactStore(root=tmp_path / "a"),
        source_bytes=b"%PDF-1.4 x",
    )
    word = result.pages[0].blocks[0].words[1]
    assert word.text == "450.000"
    assert word.confidence == 0.42


async def test_raw_artifact_is_written_atomically(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ocr_json([_page(0, "x")]))

    client = _client(handler)
    store = ArtifactStore(root=tmp_path / "artifacts")
    result = await client.ocr_file(
        _source(), budget=RunBudget(), artifacts=store, source_bytes=b"%PDF-1.4 x"
    )
    assert result.raw_artifact_ref
    path = store.path_for(result.raw_artifact_ref)
    assert path.is_file()
    # No leftover temp files from the atomic write.
    assert not list(path.parent.glob("*.tmp"))


async def test_failed_artifact_write_is_technical(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ocr_json([_page(0, "x")]))

    class BoomStore(ArtifactStore):
        def write(self, *args, **kwargs):  # type: ignore[override]
            raise ArtifactWriteError("disk full")

    client = _client(handler)
    with pytest.raises(ArtifactWriteError):
        await client.ocr_file(
            _source(), budget=RunBudget(), artifacts=BoomStore(root=tmp_path),
            source_bytes=b"%PDF-1.4 x",
        )


async def test_oversized_provider_json_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"{" + b" " * (21 * 1024 * 1024) + b"}"
        )

    client = _client(handler)
    with pytest.raises(MistralError):
        await client.ocr_file(
            _source(), budget=RunBudget(), artifacts=ArtifactStore(root=tmp_path / "a"),
            source_bytes=b"%PDF-1.4 x",
        )


async def test_page_count_mismatch_is_a_problem(tmp_path: Path) -> None:
    # PDF says 3 pages (page_count), provider returns 2 -> technical problem.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ocr_json([_page(0, "a"), _page(1, "b")]))

    client = _client(handler)
    result = await client.ocr_file(
        _source(),
        budget=RunBudget(),
        artifacts=ArtifactStore(root=tmp_path / "a"),
        source_bytes=b"%PDF-1.4 x",
        expected_pages=3,
    )
    assert result.problems
    assert result.pages  # OCR is retained, not dropped


async def test_ocr_budget_exhausted_raises(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("must not call the provider when budget is spent")

    client = _client(handler)
    budget = RunBudget(max_ocr_attempts=0)
    with pytest.raises(MistralError):
        await client.ocr_file(
            _source(), budget=budget, artifacts=ArtifactStore(root=tmp_path / "a"),
            source_bytes=b"%PDF-1.4 x",
        )


async def test_artifact_path_is_tenant_scoped(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ocr_json([_page(0, "x")]))

    store = ArtifactStore(root=tmp_path / "artifacts")
    client = _client(handler)
    await client.ocr_file(
        _source(tenant="tenant:a"), budget=RunBudget(), artifacts=store,
        source_bytes=b"%PDF-1.4 x",
    )
    await client.ocr_file(
        _source(tenant="tenant:b"), budget=RunBudget(), artifacts=store,
        source_bytes=b"%PDF-1.4 x",
    )
    tenants = {p.name for p in (tmp_path / "artifacts").iterdir() if p.is_dir()}
    assert tenants == {"tenant:a", "tenant:b"}


async def test_artifact_root_id_is_in_the_path_and_capped(tmp_path: Path) -> None:
    from invoice_referee.evidence.artifacts import MAX_ARTIFACT_BYTES_PER_ROOT, ArtifactWriteError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ocr_json([_page(0, "x")]))

    store = ArtifactStore(root=tmp_path / "artifacts")
    client = _client(handler)
    result = await client.ocr_file(
        _source(), budget=RunBudget(), artifacts=store,
        source_bytes=b"%PDF-1.4 x", root_id="case:1",
    )
    # The opaque ref is scoped by tenant AND root.
    assert "case_1" in result.raw_artifact_ref.split("/")

    # A per-root aggregate cap is enforced.
    store2 = ArtifactStore(root=tmp_path / "a2", max_root_bytes=10)
    with pytest.raises(ArtifactWriteError):
        await client.ocr_file(
            _source(), budget=RunBudget(), artifacts=store2,
            source_bytes=b"%PDF-1.4 x", root_id="case:1",
        )
