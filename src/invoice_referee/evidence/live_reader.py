"""Real provider-backed readers for LIVE mode (contracts §5, §8; plan T5).

`MistralPageReader` reads one page: native PDF text when present, else a
rendered page OCR'd by Mistral. It satisfies the pipeline's `ocr_page(source,
page)` seam. It never records money, grants authority or follows a source
instruction — it returns page text only.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.domain.evidence import SourceRef
from invoice_referee.evidence.mistral import MistralOcrClient
from invoice_referee.evidence.pdf import native_text, render_page_png


class MistralPageReader:
    """Read one page of one stored source as text (native text, else OCR)."""

    def __init__(self, *, uploads_dir: str | Path, settings, budget) -> None:
        self.uploads_dir = Path(uploads_dir)
        self.settings = settings
        self.budget = budget

    def _path(self, source: SourceRef) -> Path:
        return self.uploads_dir / source.storage_key

    async def ocr_page(self, source: SourceRef, page: int) -> str:
        path = self._path(source)
        if source.media == "PDF":
            try:
                pages = native_text(path)
            except Exception:
                pages = {}
            text = pages.get(page, "")
            if text.strip():
                return text
        # A scan/hybrid page or a non-PDF image: OCR the rendered page.
        if not self.budget.can_call_ocr():
            return ""
        client = MistralOcrClient(
            api_key=getattr(self.settings, "mistral_api_key", "") or "",
            model=getattr(self.settings, "mistral_ocr_model", "") or "",
            timeout_s=self.budget.http_timeout_s,
        )
        if source.media == "PDF":
            image_bytes = render_page_png(path, page)
        else:
            image_bytes = path.read_bytes()
        return await client.ocr_image(image_bytes, budget=self.budget)
