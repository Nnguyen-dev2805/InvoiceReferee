"""Application composition root for the FastAPI surface."""

from __future__ import annotations

import os
from dataclasses import dataclass

from invoice_referee.application import (
    ReviewSettlementService,
    SettlementProcessingService,
    SubmitSettlementService,
)
from invoice_referee.config import AppSettings
from invoice_referee.extraction import KimiReasoningAdapter, MistralOcrAdapter
from invoice_referee.storage import SQLiteSettlementRepository


@dataclass(frozen=True, slots=True)
class WebRuntime:
    settings: AppSettings
    repository: SQLiteSettlementRepository
    submit_service: SubmitSettlementService
    processor: SettlementProcessingService
    review_service: ReviewSettlementService


def build_runtime(settings: AppSettings) -> WebRuntime:
    repository = SQLiteSettlementRepository(
        settings.settlement_database_path,
        settings.settlement_artifacts_root,
    )
    document_pipeline_enabled = os.getenv(
        "UC03_DOCUMENT_PIPELINE_ENABLED",
        "1",
    ) == "1"
    ocr_adapter = None
    reasoning_adapter = None
    if document_pipeline_enabled:
        mistral_key = os.getenv("MISTRAL_API_KEY", "").strip()
        if mistral_key:
            ocr_adapter = MistralOcrAdapter(api_key=mistral_key)
        token = os.getenv("KIMI_TOKEN", "").strip()
        secret = os.getenv("KIMI_SECRET", "").strip()
        base_url = os.getenv("KIMI_BASE_URL", "").strip()
        model = os.getenv("KIMI_MODEL", "moonshotai/Kimi-K3").strip()
        if token and secret and base_url and model:
            reasoning_adapter = KimiReasoningAdapter(
                token=token,
                secret=secret,
                base_url=base_url,
                model=model,
            )

    return WebRuntime(
        settings=settings,
        repository=repository,
        submit_service=SubmitSettlementService(repository),
        processor=SettlementProcessingService(
            repository,
            ocr_adapter=ocr_adapter,
            reasoning_adapter=reasoning_adapter,
            enable_document_pipeline=document_pipeline_enabled,
            word_confidence_threshold=settings.ocr_word_review_threshold,
        ),
        review_service=ReviewSettlementService(repository),
    )
