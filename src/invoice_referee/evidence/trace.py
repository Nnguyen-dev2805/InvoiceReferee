"""Run budget, manifest and provider modes (contracts §6, §9; plan T5).

Finite, lead-chosen pilot ceilings declared before any call. A budget is
charged as attempts happen; an unresolved model alias or missing usage is
disclosed, never faked as a resolved version or a zero cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from invoice_referee.domain.common import StrictModel, UtcDatetime

ProviderMode = Literal["LIVE", "RECORDED_REPLAY", "STUB"]

# Pilot ceilings (contracts §6), lead-chosen before M0.
DEFAULT_MAX_LLM_ATTEMPTS = 12
DEFAULT_MAX_OCR_ATTEMPTS = 10
DEFAULT_HTTP_TIMEOUT_S = 20
DEFAULT_PROCESSING_DEADLINE_S = 90
DEFAULT_THRESHOLD = 0.75


@dataclass
class RunBudget:
    """Counters and a deadline for one read pass. Declared before calls."""

    max_llm_attempts: int = DEFAULT_MAX_LLM_ATTEMPTS
    max_ocr_attempts: int = DEFAULT_MAX_OCR_ATTEMPTS
    http_timeout_s: int = DEFAULT_HTTP_TIMEOUT_S
    processing_deadline_s: int = DEFAULT_PROCESSING_DEADLINE_S
    threshold: float = DEFAULT_THRESHOLD
    llm_attempts: int = 0
    ocr_attempts: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def can_call_llm(self) -> bool:
        return self.llm_attempts < self.max_llm_attempts and not self.expired()

    def can_call_ocr(self) -> bool:
        return self.ocr_attempts < self.max_ocr_attempts and not self.expired()

    def charge_llm(self) -> None:
        self.llm_attempts += 1

    def charge_ocr(self) -> None:
        self.ocr_attempts += 1

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    def expired(self) -> bool:
        return self.elapsed_s() >= self.processing_deadline_s


class RunManifest(StrictModel):
    """What one run actually did: mode, models, usage and trace refs (§9)."""

    mode: ProviderMode
    requested_model: str | None = None
    returned_model: str | None = None
    resolved_model: str | None = None
    prompt_version: str | None = None
    schema_version: str | None = None
    trace_refs: tuple[str, ...] = ()
    usage_unknown: bool = True
    notes: str | None = None


class TraceSpan(StrictModel):
    """One read/extract/reconcile/recovery span, for local audit and tracing."""

    name: str
    run_id: str
    basis: str | None = None
    prompt_version: str | None = None
    model: str | None = None
    started_at: UtcDatetime | None = None
    ended_at: UtcDatetime | None = None
    detail: str | None = None


# Keys that must never be sent to telemetry (bank PDFs, secrets, private raw).
_SENSITIVE_KEYS = ("raw", "content", "payload", "pdf", "image", "api_key", "secret", "token")


def filter_payload(payload: dict[str, object]) -> dict[str, object]:
    """Drop sensitive keys before anything leaves the process (§9).

    Local audit does not depend on telemetry; this only guards the opt-in path.
    """
    return {
        key: value
        for key, value in payload.items()
        if not any(sensitive in key.lower() for sensitive in _SENSITIVE_KEYS)
    }


class LocalTrace:
    """An always-available local span sink. Telemetry is opt-in on top."""

    def __init__(self) -> None:
        self.spans: list[TraceSpan] = []

    def record(self, span: TraceSpan) -> None:
        self.spans.append(span)


class LangSmithTrace:
    """Opt-in LangSmith adapter. A failure here never blocks the local audit."""

    def __init__(self, *, api_key: str | None, project: str = "invoice-referee") -> None:
        self.enabled = api_key is not None
        self.project = project
        self.local = LocalTrace()

    def record(self, span: TraceSpan, *, payload: dict[str, object] | None = None) -> None:
        self.local.record(span)
        if not self.enabled:
            return
        try:
            self._send(span, filter_payload(payload or {}))
        except Exception:
            # Telemetry failure is not a business failure; the local span stands.
            pass

    def _send(self, span: TraceSpan, payload: dict[str, object]) -> None:
        # Real SDK wiring arrives when a key is configured; kept isolated so a
        # missing/failed telemetry never affects a conclusion.
        return None
