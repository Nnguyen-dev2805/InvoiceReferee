"""Mistral OCR HTTP adapter (contracts §5, §8, §12.1; plan T5/E2).

Sends the correct payload for a PDF (document_url) or an image (image_url) and
returns structured pages with blocks and word-level confidence. No source
instruction becomes a prompt or permission. Errors are raised, not swallowed
into a false success; usage that could not be observed stays unknown.

E2 adds `ocr_file`: a file-level call that OCRs every accepted page (native PDF
text never bypasses OCR), retains blocks/word confidence, and writes the raw
provider response to a bounded private artifact. The old `ocr_image` is kept for
the legacy per-page seam that E7 replaces.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field

import httpx

from invoice_referee.domain.documents import OcrBlock, OcrPage, OcrSourceResult, OcrWord
from invoice_referee.domain.evidence import SourceRef
from invoice_referee.domain.issues import ProcessingProblem
from invoice_referee.evidence.artifacts import ArtifactStore
from invoice_referee.evidence.trace import RunBudget

# Bounded provider response (lead-chosen, plan E2). Not a model context window.
MAX_PROVIDER_RESPONSE_BYTES = 20 * 1024 * 1024


class MistralError(RuntimeError):
    """A provider call failed (transport, status or schema)."""


def _parse_words(block: dict) -> tuple[OcrWord, ...]:
    out: list[OcrWord] = []
    for word in block.get("words") or []:
        text = str(word.get("text") or "")
        confidence = word.get("confidence")
        out.append(
            OcrWord(
                text=text,
                block_start=word.get("start_index", word.get("block_start")),
                block_end=word.get("end_index", word.get("block_end")),
                confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
            )
        )
    return tuple(out)


def _parse_blocks(page: dict) -> tuple[OcrBlock, ...]:
    out: list[OcrBlock] = []
    for index, block in enumerate(page.get("blocks") or []):
        out.append(
            OcrBlock(
                id=str(block.get("block_id") or f"b{index}"),
                kind=str(block.get("type") or "text"),
                content=str(block.get("content") or ""),
                bbox=None,
                words=_parse_words(block),
            )
        )
    return tuple(out)


@dataclass
class MistralOcrClient:
    """Thin HTTP client. `base_url` defaults to the public API."""

    api_key: str
    model: str
    base_url: str = "https://api.mistral.ai/v1"
    timeout_s: float = 20.0
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient | None = None

    async def ocr_image(self, image_bytes: bytes, *, budget: RunBudget) -> str:
        """Legacy per-page seam: returns joined page markdown (E7 replaces it)."""
        if not budget.can_call_ocr():
            raise MistralError("OCR budget exhausted")
        budget.charge_ocr()
        payload = {
            "model": self.model,
            "document": {
                "type": "image_url",
                "image_url": "data:image/png;base64,"
                + base64.b64encode(image_bytes).decode("ascii"),
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
            response = await client.post(
                f"{self.base_url}/ocr",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise MistralError(f"OCR HTTP {response.status_code}")
        data = response.json()
        pages = data.get("pages") or []
        return "\n".join(page.get("markdown", "") for page in pages)

    async def ocr_file(
        self,
        source: SourceRef,
        *,
        budget: RunBudget,
        artifacts: ArtifactStore,
        source_bytes: bytes | None = None,
        expected_pages: int | None = None,
        artifact_version: str = "ocr-v1",
        root_id: str = "",
    ) -> OcrSourceResult:
        """OCR every page of one file and retain the raw response.

        `source_bytes` is the persisted PDF/image; when omitted it is read from
        the artifact store's sibling upload path is not known here, so callers
        pass it. A PDF uses a document_url payload; an image uses image_url.
        """
        if not budget.can_call_ocr():
            raise MistralError("OCR budget exhausted")
        if source_bytes is None:
            raise MistralError("ocr_file requires the persisted source bytes")
        budget.charge_ocr()

        mime = {
            "PDF": "application/pdf",
            "PNG": "image/png",
            "JPEG": "image/jpeg",
        }[source.media]
        data_url = f"data:{mime};base64," + base64.b64encode(source_bytes).decode("ascii")
        if source.media == "PDF":
            document = {"type": "document_url", "document_url": data_url}
        else:
            document = {"type": "image_url", "image_url": data_url}
        payload = {
            "model": self.model,
            "document": document,
            "include_image_base64": False,
            "include_blocks": True,
            "confidence_scores_granularity": "word",
        }

        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
            response = await client.post(
                f"{self.base_url}/ocr",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise MistralError(f"OCR HTTP {response.status_code}")
        if len(response.content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise MistralError("OCR response exceeded the bounded size")
        data = response.json()

        raw_ref = artifacts.write(
            tenant=source.tenant,
            root_id=root_id,
            source_id=source.id,
            source_digest=source.digest,
            version=artifact_version,
            payload=data,
        )

        raw_pages = data.get("pages") or []
        pages = tuple(
            OcrPage(
                page=index,
                markdown=str(page.get("markdown") or ""),
                blocks=_parse_blocks(page),
            )
            for index, page in enumerate(raw_pages, start=1)
        )
        problems: list[ProcessingProblem] = []
        if expected_pages is not None and len(pages) != expected_pages:
            problems.append(
                ProcessingProblem(
                    kind="TECHNICAL",
                    affected_fields=("page_coverage",),
                    message=(
                        f"provider returned {len(pages)} pages, expected {expected_pages}"
                    ),
                    relevance="MATERIAL",
                    blocking=True,
                    next_action="retry_read_or_report_technical",
                )
            )
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="mistral",
            model=str(data.get("model") or self.model),
            pages=pages,
            raw_artifact_ref=raw_ref,
            problems=tuple(problems),
            complete=not problems,
        )
