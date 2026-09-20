"""Tests for OCR engine selection from environment."""

from __future__ import annotations

import pytest

from invoice_referee.ingestion.ocr import MistralOCREngine, PaddleOCREngine
from invoice_referee.ingestion.ocr_config import engine_from_env


def test_defaults_to_paddle():
    engine = engine_from_env(env={})
    assert isinstance(engine, PaddleOCREngine)


def test_paddle_explicit():
    engine = engine_from_env(env={"OCR_ENGINE": "paddle"})
    assert isinstance(engine, PaddleOCREngine)


def test_mistral_requires_key():
    with pytest.raises(ValueError):
        engine_from_env(env={"OCR_ENGINE": "mistral"})


def test_mistral_selected_with_key():
    engine = engine_from_env(env={"OCR_ENGINE": "mistral", "MISTRAL_API_KEY": "sk-x"})
    assert isinstance(engine, MistralOCREngine)


def test_mistral_model_and_timeout_overrides():
    engine = engine_from_env(
        env={
            "OCR_ENGINE": "mistral",
            "MISTRAL_API_KEY": "sk-x",
            "MISTRAL_OCR_MODEL": "mistral-ocr-2512",
            "MISTRAL_OCR_TIMEOUT": "30",
        }
    )
    assert isinstance(engine, MistralOCREngine)
    assert engine._model == "mistral-ocr-2512"
    assert engine._timeout == 30.0
