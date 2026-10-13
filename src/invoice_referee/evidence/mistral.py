"""Mistral OCR HTTP adapter (contracts §5, §8; plan T5).

Sends the correct payload for a scan/hybrid page and returns page text. No
source instruction becomes a prompt or permission. Errors are raised, not
swallowed into a false success; usage that could not be observed stays unknown.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from invoice_referee.evidence.trace import RunBudget


class MistralError(RuntimeError):
    """A provider call failed (transport, status or schema)."""


@dataclass
class MistralOcrClient:
    """Thin HTTP client. `base_url` defaults to the public API."""

    api_key: str
    model: str
    base_url: str = "https://api.mistral.ai/v1"
    timeout_s: float = 20.0
    _client: httpx.AsyncClient | None = None

    async def ocr_image(self, image_bytes: bytes, *, budget: RunBudget) -> str:
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
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/ocr",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        if response.status_code >= 400:
            raise MistralError(f"OCR HTTP {response.status_code}")
        data = response.json()
        # OCR returns per-page markdown; a single image page yields one entry.
        pages = data.get("pages") or []
        return "\n".join(page.get("markdown", "") for page in pages)
