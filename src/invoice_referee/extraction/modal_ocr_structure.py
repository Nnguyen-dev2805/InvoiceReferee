"""Client adapter for the deployed Modal OCR structure service."""

from __future__ import annotations

from typing import Any


class ModalOcrStructureAdapter:
    """Invoke the hybrid PaddleOCR class deployed in Modal."""

    def __init__(
        self,
        *,
        app_name: str = "invoice-referee-paddleocr-vl",
        class_name: str = "PaddleOCRStructureService",
        environment_name: str | None = None,
    ) -> None:
        self.app_name = app_name
        self.class_name = class_name
        self.environment_name = environment_name

    def process(
        self,
        *,
        file_name: str,
        mime_type: str,
        content: bytes,
        review_threshold: float = 0.85,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Tệp OCR không được rỗng.")

        import modal

        remote_class = modal.Cls.from_name(
            self.app_name,
            self.class_name,
            environment_name=self.environment_name,
        )
        result = remote_class().scan.remote(
            file_name,
            mime_type,
            content,
            review_threshold,
        )
        if not isinstance(result, dict):
            raise RuntimeError("Modal OCR structure không trả về JSON object.")
        return result


__all__ = ["ModalOcrStructureAdapter"]
