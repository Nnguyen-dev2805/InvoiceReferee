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
# The LLM (a free/slow model in the pilot) needs a longer bounded budget than
# OCR; a 20s cap timed out real classification calls (lead call, plan E3).
DEFAULT_LLM_TIMEOUT_S = 60
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
    # Topology + observed data (contracts §9; 14/10/2026 LangSmith wiring).
    # Each span carries its OWN run id and an optional parent so a processing
    # operation is a tree, not a flat list of runs that reuse one id.
    parent_run_id: str | None = None
    run_type: str = "chain"
    inputs: dict[str, object] = {}
    outputs: dict[str, object] = {}
    error: str | None = None
    metadata: dict[str, object] = {}
    tags: tuple[str, ...] = ()


# Keys that must never be sent to telemetry (bank PDFs, secrets, private raw).
# Substring match on the key name; numeric metrics whose name merely CONTAINS a
# sensitive word (e.g. ``token_count``) are NOT dropped — only real secrets and
# private content are.
_SENSITIVE_SUBSTRINGS = (
    "raw", "content", "payload", "pdf", "image", "api_key", "apikey",
    "secret", "authorization", "password", "credential", "bearer",
)
# Exact secret key names that contain a sensitive word but are not metrics.
_SECRET_EXACT = frozenset({"token", "access_token", "auth_token", "id_token", "refresh_token"})


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SECRET_EXACT:
        return True
    # A numeric metric (token_count, total_tokens, latency_ms) is kept even when
    # its name contains a sensitive substring.
    if lowered.endswith(("_count", "_tokens", "_ms", "_s", "_bytes", "_chars", "_seconds")):
        return False
    return any(sensitive in lowered for sensitive in _SENSITIVE_SUBSTRINGS)


def filter_payload(payload: dict[str, object]) -> dict[str, object]:
    """Drop sensitive keys before anything leaves the process (§9).

    Local audit does not depend on telemetry; this only guards the opt-in path.
    Numeric metrics (``token_count`` …) are preserved; only secrets and private
    content are removed.
    """
    return {key: value for key, value in payload.items() if not _is_sensitive_key(key)}



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
        # Diagnostics for export failures — a failed send is visible, not
        # silently swallowed while the system still claims tracing is healthy.
        self.export_errors: list[str] = []

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
        except Exception as error:
            # Telemetry failure is not a business failure; the local span stands
            # and the failure is recorded for diagnostics (never silently lost).
            self.export_errors.append(f"{type(error).__name__}: {error}"[:300])

    def _run_uuid(self, run_id: str) -> str:
        """A deterministic LangSmith UUID for a logical span id."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, run_id))

    def _send(self, span: TraceSpan, payload: dict[str, object]) -> None:
        client = self._ensure_client()
        if client is None:
            return
        # LangSmith requires a UUID run id; the domain's logical span id (a
        # business key) is kept as metadata, not used as the UUID.
        run_uuid = self._run_uuid(span.run_id)
        start = span.started_at
        end = span.ended_at
        # Real timings only: an open run is closed at the observed end; a span
        # with no explicit end is left open (LangSmith accepts a null end). We do
        # NOT set start==end==now by default, which would fabricate latency 0.
        extra = {
            "logical_run_id": span.run_id,
            "basis": span.basis,
            "prompt_version": span.prompt_version,
            "model": span.model,
            "agent_id": self.agent_id,
            "agent_environment": self.agent_environment,
            "metadata": dict(span.metadata),
        }
        inputs = {**filter_payload(span.inputs), **filter_payload(payload)}
        create_kwargs: dict[str, object] = {
            "id": run_uuid,
            "name": span.name,
            "run_type": span.run_type,
            "project_name": self.project,
            "inputs": inputs,
            "extra": extra,
        }
        if start is not None:
            create_kwargs["start_time"] = start
        if end is not None:
            create_kwargs["end_time"] = end
        if span.parent_run_id is not None:
            create_kwargs["parent_run_id"] = self._run_uuid(span.parent_run_id)
        if span.tags:
            create_kwargs["tags"] = list(span.tags)
        client.create_run(**create_kwargs)  # type: ignore[attr-defined]
        # Close the run with outputs/error when we have them (update_run is the
        # SDK's way to attach an end/error/outputs after create).
        update_kwargs: dict[str, object] = {}
        if span.outputs or span.detail:
            update_kwargs["outputs"] = {**span.outputs, **({"detail": span.detail} if span.detail else {})}
        if span.error is not None:
            update_kwargs["error"] = span.error
        if end is not None:
            update_kwargs["end_time"] = end
        if update_kwargs:
            client.update_run(run_uuid, **update_kwargs)  # type: ignore[attr-defined]



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
