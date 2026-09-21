"""Mistral OCR adapter isolated from UI and workflow code."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VIETNAM_TZ = timezone(timedelta(hours=7))


@dataclass(frozen=True, slots=True)
class OcrExecution:
    provider: str
    model: str
    processed_at: str
    response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "processed_at": self.processed_at,
            "response": self.response,
        }


class MistralOcrAdapter:
    """Send one persisted image/PDF to Mistral OCR and normalize its response."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistral-ocr-latest",
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("MISTRAL_API_KEY chưa được cấu hình.")
        if client is None:
            from mistralai.client import Mistral

            client = Mistral(api_key=api_key)
        self.client = client
        self.model = model

    def process(self, file_path: Path, mime_type: str | None = None) -> OcrExecution:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Không tìm thấy evidence: {path}")

        detected_mime = mime_type or mimetypes.guess_type(path.name)[0]
        detected_mime = detected_mime or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        data_url = f"data:{detected_mime};base64,{encoded}"

        if path.suffix.lower() == ".pdf" or detected_mime == "application/pdf":
            document = {"type": "document_url", "document_url": data_url}
        else:
            document = {"type": "image_url", "image_url": data_url}

        response = self.client.ocr.process(
            model=self.model,
            document=document,
            include_image_base64=False,
            include_blocks=True,
            confidence_scores_granularity="word",
            timeout_ms=120_000,
        )
        raw_response = response.model_dump(mode="json", exclude_none=True)
        return OcrExecution(
            provider="mistral",
            model=self.model,
            processed_at=datetime.now(tz=VIETNAM_TZ).isoformat(),
            response=raw_response,
        )
