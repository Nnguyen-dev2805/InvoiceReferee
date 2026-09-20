"""Select the OCR engine from environment configuration.

Default is the local PaddleOCR engine (offline, no per-call cost, private). Set
``OCR_ENGINE=mistral`` with ``MISTRAL_API_KEY`` to use the hosted Mistral
Document AI OCR instead — useful to test the end-to-end architecture without
downloading/warming local model weights.

Reads the repo-root ``.env`` (same minimal parser as the LLM config) merged over
the real environment. Secrets are never logged.
"""

from __future__ import annotations

import os
from typing import Optional

from invoice_referee.agent.config import load_env_file
from invoice_referee.ingestion.ocr import MistralOCREngine, OCREngine, PaddleOCREngine


def _resolve(env: dict[str, str], key: str) -> Optional[str]:
    if key in env:
        return env[key]
    return os.environ.get(key)


def engine_from_env(env: Optional[dict[str, str]] = None) -> OCREngine:
    """Return the configured OCR engine (Paddle local by default)."""
    if env is None:
        merged = {**load_env_file()}
        merged.update({k: v for k, v in os.environ.items() if k.startswith(("OCR_", "MISTRAL_"))})
        env = merged

    choice = (_resolve(env, "OCR_ENGINE") or "paddle").strip().lower()

    if choice == "mistral":
        api_key = _resolve(env, "MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("OCR_ENGINE=mistral requires MISTRAL_API_KEY")
        model = _resolve(env, "MISTRAL_OCR_MODEL") or "mistral-ocr-latest"
        timeout_raw = _resolve(env, "MISTRAL_OCR_TIMEOUT")
        try:
            timeout = float(timeout_raw) if timeout_raw else 60.0
        except ValueError:
            timeout = 60.0
        return MistralOCREngine(api_key=api_key, model=model, timeout=timeout)

    return PaddleOCREngine()
