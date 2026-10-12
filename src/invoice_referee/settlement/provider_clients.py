"""Provider transport clients (W03): Mistral OCR + xkiro chat JSON.

Thin HTTPX transports with no SDK; config constants live here and are
re-exported by ``reader.py``. Each raises ``DomainError`` (fail-closed) on
transport failure and never fabricates output.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from invoice_referee.shared.errors import DomainError

MISTRAL_OCR_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_OCR_MODEL = "mistral-ocr-latest"
XKIRO_BASE_URL = "https://api.xkiro.com/v1"
XKIRO_MODEL = "mistralai/mistral-small-2603"

OCR_TIMEOUT_SECONDS = 60.0
XKIRO_TIMEOUT_SECONDS = 80.0


class MistralOCRClient:
    """Thin transport for the Mistral OCR endpoint (no SDK)."""

    def __init__(self, api_key: str, base_url: str = MISTRAL_OCR_BASE_URL,
                 model: str = MISTRAL_OCR_MODEL,
                 timeout: float = OCR_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise DomainError("CONFIG_NOT_ACTIVE",
                              "MISTRAL_API_KEY chưa được cấu hình.")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            transport=self._transport)

    def ocr_document(self, document: dict[str, Any],
                     timeout: float) -> dict[str, Any]:
        body = {"model": self.model, "document": document, "include_blocks": True}
        with self._client() as client:
            try:
                response = client.post("/ocr", json=body, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except DomainError:
                raise
            except Exception as error:  # noqa: BLE001 — any transport failure
                raise DomainError(
                    "PROVIDER_FAILED",
                    f"OCR call thất bại kỹ thuật: {type(error).__name__}: {error}",
                ) from error


class XkiroClient:
    """OpenAI-compatible JSON chat client (full vendor model id, effort none)."""

    def __init__(self, api_key: str, base_url: str = XKIRO_BASE_URL,
                 model: str = XKIRO_MODEL, timeout: float = XKIRO_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not api_key:
            raise DomainError("CONFIG_NOT_ACTIVE", "XKIRO_API_KEY chưa được cấu hình.")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url,
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            transport=self._transport)

    def chat_json(self, system_prompt: str, user_payload: dict[str, Any],
                  max_tokens: int, timeout: float) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(
                    user_payload, ensure_ascii=False, sort_keys=True)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
        }
        with self._client() as client:
            try:
                response = client.post("/chat/completions", json=body,
                                        timeout=timeout)
                response.raise_for_status()
                data = response.json()
            except DomainError:
                raise
            except Exception as error:  # noqa: BLE001
                raise DomainError(
                    "PROVIDER_FAILED",
                    f"xkiro call thất bại kỹ thuật: {type(error).__name__}: {error}",
                ) from error
        try:
            content = data["choices"][0]["message"]["content"]
            finish_reason = data["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError) as error:
            raise DomainError(
                "PROVIDER_OUTPUT_INVALID",
                f"xkiro response thiếu choices/content: {error}",
            ) from error
        usage = data.get("usage")
        return {
            "content": content,
            "finish_reason": finish_reason,
            "requested_model": self.model,
            "response_model": data.get("model") if isinstance(
                data.get("model"), str) else None,
            "usage": usage if isinstance(usage, dict) else None,
        }
