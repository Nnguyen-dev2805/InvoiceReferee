"""Run budget, manifest and provider modes (contracts §6, §9; plan T5).

Finite, lead-chosen pilot ceilings declared before any call. A budget is
charged as attempts happen; an unresolved model alias or missing usage is
disclosed, never faked as a resolved version or a zero cost.
"""

from __future__ import annotations

import time
import uuid
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

# App-size character caps for X-Kiro (contracts §12.3, plan E3). These are
# lead-chosen pilot limits, NOT a claim about the model context window.
DEFAULT_MAX_LLM_INPUT_CHARS = 120_000
DEFAULT_MAX_LLM_OUTPUT_CHARS = 20_000


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
    # App-size caps (contracts §12.3). limit_origin names the source so a
    # missing/unknown cap config fails closed rather than claiming a default.
    max_llm_input_chars: int = DEFAULT_MAX_LLM_INPUT_CHARS
    max_llm_output_chars: int = DEFAULT_MAX_LLM_OUTPUT_CHARS
    limit_version: str | None = None
    limit_origin: Literal["LEAD_PILOT", "MEASURED_M0"] | None = None


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
    """Opt-in LangSmith adapter (contracts §9).

    Spans carry run/basis/prompt/model; the payload is filtered before it is
    sent (no bank PDF/secrets/private raw data). The local span is always kept,
    and a tracing failure never affects a business conclusion.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        project: str = "invoice-referee",
        endpoint: str | None = None,
        agent_id: str | None = None,
        agent_environment: str | None = None,
        client: object | None = None,
    ) -> None:
        self.enabled = api_key is not None
        self.project = project
        self.endpoint = endpoint
        self.agent_id = agent_id
        self.agent_environment = agent_environment
        self.local = LocalTrace()
        self._client = client
        self._api_key = api_key

    def _ensure_client(self) -> object | None:
        if self._client is not None:
            return self._client
        if not self.enabled:
            return None
        from langsmith import Client  # imported lazily; SDK is opt-in

        self._client = Client(
            api_url=self.endpoint,
            api_key=self._api_key,
        )
        return self._client

    def record(self, span: TraceSpan, *, payload: dict[str, object] | None = None) -> None:
        # Local audit first and unconditionally — telemetry is optional on top.
        self.local.record(span)
        if not self.enabled:
            return
        try:
            self._send(span, filter_payload(payload or {}))
        except Exception:
            # Telemetry failure is not a business failure; the local span stands.
            pass

    def _send(self, span: TraceSpan, payload: dict[str, object]) -> None:
        from datetime import UTC, datetime

        client = self._ensure_client()
        if client is None:
            return
        # LangSmith requires a UUID run id; the domain's logical span id (a
        # business key) is kept as metadata, not used as the UUID.
        run_uuid = uuid.uuid5(uuid.NAMESPACE_URL, span.run_id)
        now = datetime.now(UTC)
        # A completed run needs both a start and an end time; an open run is not
        # persisted, so a single span is written as an ended run.
        client.create_run(  # type: ignore[attr-defined]
            id=str(run_uuid),
            name=span.name,
            run_type="chain",
            project_name=self.project,
            inputs=payload,
            start_time=span.started_at or now,
            extra={
                "logical_run_id": span.run_id,
                "basis": span.basis,
                "prompt_version": span.prompt_version,
                "model": span.model,
                "agent_id": self.agent_id,
                "agent_environment": self.agent_environment,
            },
        )
        client.update_run(  # type: ignore[attr-defined]
            str(run_uuid),
            end_time=span.ended_at or now,
            outputs={"detail": span.detail} if span.detail else {},
        )


def build_trace(settings: object) -> LangSmithTrace:
    """Build a trace adapter from Settings. Off unless explicitly enabled."""
    enabled = getattr(settings, "langsmith_ready", False)
    return LangSmithTrace(
        api_key=getattr(settings, "langsmith_api_key", None) if enabled else None,
        project=getattr(settings, "langsmith_project", "invoice-referee"),
        endpoint=getattr(settings, "langsmith_endpoint", None),
        agent_id=getattr(settings, "langsmith_agent_id", None),
        agent_environment=getattr(settings, "langsmith_agent_environment", None),
    )
