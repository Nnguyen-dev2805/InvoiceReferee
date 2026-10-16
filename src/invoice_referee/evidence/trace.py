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
    max_schema_repairs: int = 1
    schema_repairs: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def can_call_llm(self) -> bool:
        return self.llm_attempts < self.max_llm_attempts and not self.expired()

    def can_call_ocr(self) -> bool:
        return self.ocr_attempts < self.max_ocr_attempts and not self.expired()

    def charge_llm(self) -> None:
        self.llm_attempts += 1

    def claim_schema_repair(self) -> bool:
        if self.schema_repairs >= self.max_schema_repairs or not self.can_call_llm():
            return False
        self.schema_repairs += 1
        return True

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
    output_state: Literal["COLLECTED", "EMPTY", "NOT_COLLECTED", "REDACTED"] | None = (
        None
    )
    error: str | None = None
    metadata: dict[str, object] = {}
    tags: tuple[str, ...] = ()


# Keys that must never be sent to telemetry (bank PDFs, secrets, private raw).
# Substring match on the key name; numeric metrics whose name merely CONTAINS a
# sensitive word (e.g. ``token_count``) are NOT dropped — only real secrets and
# private content are.
_SENSITIVE_SUBSTRINGS = (
    "raw",
    "content",
    "payload",
    "pdf",
    "image",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "password",
    "credential",
    "bearer",
    "cookie",
    "header",
    "base64",
)
# Exact secret key names that contain a sensitive word but are not metrics.
_SECRET_EXACT = frozenset(
    {
        "token",
        "access_token",
        "auth_token",
        "id_token",
        "refresh_token",
        "tenant",
        "actor",
        "actor_id",
        "employee",
        "employee_id",
        "person",
    }
)
_PRIVATE_VALUE_KEYS = (
    "name",
    "account",
    "identity",
    "citizen",
    "passport",
    "phone",
    "email",
    "address",
    "tax_code",
    "personal_id",
    "person_id",
    "employee_id",
    "actor_id",
)
_ALWAYS_DROP_KEYS = frozenset(
    {"quote", "exact_quote", "raw_quote", "ocr_text", "markdown"}
)
_TRACE_MAX_DEPTH = 7
_TRACE_MAX_ITEMS = 40
_TRACE_MAX_STRING_CHARS = 1200
_TRACE_MAX_TOTAL_CHARS = 20000


class _PayloadLimits:
    def __init__(self) -> None:
        self.omitted_items = 0
        self.omitted_chars = 0
        self.omitted_depth = 0
        self.remaining_chars = _TRACE_MAX_TOTAL_CHARS

    @property
    def truncated(self) -> bool:
        return bool(self.omitted_items or self.omitted_chars or self.omitted_depth)


_DROP = object()


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _SECRET_EXACT:
        return True
    # A numeric metric (token_count, total_tokens, latency_ms) is kept even when
    # its name contains a sensitive substring.
    if lowered.endswith(
        ("_count", "_tokens", "_ms", "_s", "_bytes", "_chars", "_seconds")
    ):
        return False
    return any(sensitive in lowered for sensitive in _SENSITIVE_SUBSTRINGS)


def filter_payload(payload: dict[str, object]) -> dict[str, object]:
    """Recursively redact and bound trace data before it leaves the process.

    This is an observability-only copy; caller payloads are never mutated.
    Numeric metrics (``token_count`` …) are preserved. Source quotes and raw OCR
    are removed; personal values in structured fields are replaced with a marker.
    """
    limits = _PayloadLimits()
    result = _sanitize_value(payload, key="", field_name=None, depth=0, limits=limits)
    if not isinstance(result, dict):
        return {}
    if limits.truncated:
        result["truncated"] = True
        result["truncated_counts"] = {
            "items": limits.omitted_items,
            "chars": limits.omitted_chars,
            "depth": limits.omitted_depth,
        }
    return result


def _is_private_field(field_name: str | None) -> bool:
    lowered = (field_name or "").lower()
    return any(marker in lowered for marker in _PRIVATE_VALUE_KEYS)


def _sanitize_value(
    value: object,
    *,
    key: str,
    field_name: str | None,
    depth: int,
    limits: _PayloadLimits,
) -> object:
    if key and (_is_sensitive_key(key) or key.lower() in _ALWAYS_DROP_KEYS):
        return _DROP
    if depth > _TRACE_MAX_DEPTH:
        limits.omitted_depth += 1
        return _DROP
    if isinstance(value, dict):
        item_field = value.get("field")
        child_field = item_field if isinstance(item_field, str) else field_name
        result: dict[str, object] = {}
        for index, (child_key, child_value) in enumerate(value.items()):
            if index >= _TRACE_MAX_ITEMS or limits.remaining_chars <= 0:
                limits.omitted_items += len(value) - index
                break
            lowered = str(child_key).lower()
            if _is_private_field(lowered):
                result[str(child_key)] = "[REDACTED]"
                continue
            if _is_private_field(child_field) and lowered in {
                "value",
                "normalized",
                "description",
                "party",
                "quote",
                "observed_text",
            }:
                result[str(child_key)] = "[REDACTED]"
                continue
            safe = _sanitize_value(
                child_value,
                key=str(child_key),
                field_name=child_field,
                depth=depth + 1,
                limits=limits,
            )
            if safe is not _DROP:
                safe_key = _bounded_trace_text(str(child_key), limits)
                if safe_key:
                    result[safe_key] = safe
        return result
    if isinstance(value, (list, tuple)):
        result_list: list[object] = []
        for index, item in enumerate(value):
            if index >= _TRACE_MAX_ITEMS or limits.remaining_chars <= 0:
                limits.omitted_items += len(value) - index
                break
            safe = _sanitize_value(
                item,
                key="",
                field_name=field_name,
                depth=depth + 1,
                limits=limits,
            )
            if safe is not _DROP:
                result_list.append(safe)
        return result_list
    if isinstance(value, str):
        return _bounded_trace_text(value, limits)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_TRACE_MAX_STRING_CHARS]


def _bounded_trace_text(value: str, limits: _PayloadLimits) -> str:
    allowed = min(_TRACE_MAX_STRING_CHARS, limits.remaining_chars)
    if len(value) > allowed:
        limits.omitted_chars += len(value) - allowed
    result = value[:allowed]
    limits.remaining_chars -= len(result)
    return result


_TRACE_STAGE_KEYS: dict[str, frozenset[str]] = {
    "ocr": frozenset(
        {
            "source_id",
            "source_digest",
            "media",
            "expected_pages",
            "provider",
            "model",
            "pages_read",
            "coverage",
            "read_state",
            "review_regions",
            "artifact_ref",
            "complete",
        }
    ),
    "confidence": frozenset(
        {"candidate_count", "candidates", "status", "decisions", "findings", "skipped"}
    ),
    "classification": frozenset(
        {
            "status",
            "skipped",
            "source_count",
            "sources",
            "count",
            "documents",
        }
    ),
    "extraction": frozenset(
        {
            "document_id",
            "document_type",
            "source_id",
            "source_digest",
            "page_range",
            "confidence_status",
            "ocr_page_count",
            "classification_confidence",
            "parse_status",
            "field_count",
            "line_item_count",
            "fields",
            "line_items",
            "source_refs",
            "provenance_findings",
            "repair_attempts",
            "llm_attempts",
        }
    ),
    "validation": frozenset(
        {
            "document_id",
            "document_type",
            "source_id",
            "profile_status",
            "confidence_status",
            "input_fields",
            "findings",
            "fields",
            "blocking_count",
            "arithmetic_checks",
        }
    ),
    "matching": frozenset(
        {
            "method",
            "paper_document_id",
            "document_count",
            "row_count",
            "links",
            "rows",
            "findings",
            "suggestions",
            "llm_called",
            "resolver_skipped",
            "resolved_suggestions",
        }
    ),
    "admission": frozenset(
        {
            "status",
            "accepted_facts",
            "unverified_facts",
            "blocked_facts",
            "fact_count",
            "issue_count",
            "issues",
            "read_set",
            "money_basis",
            "employee_paid_state",
            "binding",
            "money_history",
            "relations",
            "confirmations",
            "problems",
            "arithmetic_findings",
        }
    ),
    "reconcile": frozenset(
        {
            "axes",
            "issues",
            "authorizations",
            "allowed_effect",
            "effect_blockers",
            "decision_state",
            "state",
            "cost_basis",
            "money_basis",
        }
    ),
    "commit": frozenset(
        {
            "state_before",
            "state_after",
            "version_before",
            "version_after",
            "input_revision",
            "instruction",
            "conclusion_status",
            "committed",
        }
    ),
    "command": frozenset(
        {
            "command",
            "status",
            "duplicate_command",
            "state",
            "case_version",
            "job_id",
            "input_revision",
            "state_before",
            "state_after",
            "version_before",
            "version_after",
            "instructions",
            "conclusion_status",
            "axes",
            "issues",
            "issue_count",
        }
    ),
    "read_root": frozenset(
        {
            "status",
            "outcome",
            "provider_mode",
            "document_count",
            "link_count",
            "row_match_count",
            "problem_count",
            "documents",
            "findings",
            "draft",
            "state_after",
            "version_after",
        }
    ),
    "llm": frozenset(
        {
            "status",
            "response_format",
            "parsed_json_summary",
            "parsed_json_sha256",
            "requested_model",
            "returned_model",
            "requested_effort",
            "observed_effort",
            "usage",
            "prompt_version",
            "schema_version",
            "attempt_index",
            "attempt_kind",
            "stage_instance",
            "system_chars",
            "user_chars",
            "system_sha256",
            "user_sha256",
        }
    ),
}


def stage_payload(stage: str, payload: dict[str, object]) -> dict[str, object]:
    """Apply a stage-specific top-level allowlist and attach its schema version."""
    allowed = _TRACE_STAGE_KEYS.get(stage)
    if allowed is None:
        raise ValueError(f"Unknown trace stage: {stage}")
    selected = {key: value for key, value in payload.items() if key in allowed}
    return filter_payload(
        {"schema_version": f"invoice_referee.trace.{stage}.v1", **selected}
    )


def sanitize_trace_error(error: object, *, max_chars: int = 300) -> str:
    """Remove common credentials from exception text and keep diagnostics bounded."""
    import re

    value = str(error)
    value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [REDACTED]", value)
    value = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|cookie)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        value,
    )
    value = re.sub(r"(?i)(authorization\s*[:=]\s*)[^\r\n]+", r"\1[REDACTED]", value)
    value = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[REDACTED_EMAIL]", value, flags=re.I
    )
    value = re.sub(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)", "[REDACTED_NUMBER]", value)
    return value[:max_chars]


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

    def record(
        self, span: TraceSpan, *, payload: dict[str, object] | None = None
    ) -> None:
        # Local audit first and unconditionally — telemetry is optional on top.
        self.local.record(span)
        if not self.enabled:
            return
        try:
            self._send(span, filter_payload(payload or {}))
        except Exception as error:
            # Telemetry failure is not a business failure; the local span stands
            # and the failure is recorded for diagnostics (never silently lost).
            self.export_errors.append(
                sanitize_trace_error(f"{type(error).__name__}: {error}")
            )

    def flush(self, *, timeout: float = 5.0) -> None:
        """Wait briefly for the SDK's buffered creates to reach its transport."""
        if not self.enabled:
            return
        try:
            client = self._ensure_client()
            flush = getattr(client, "flush", None) if client is not None else None
            if callable(flush):
                flush(timeout=timeout)
        except Exception as error:
            self.export_errors.append(
                sanitize_trace_error(f"{type(error).__name__}: {error}")
            )

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
        span_outputs = dict(span.outputs)
        if span.detail is not None:
            span_outputs["detail"] = sanitize_trace_error(span.detail)
        output_state = span.output_state or (
            "COLLECTED" if span_outputs else "NOT_COLLECTED"
        )
        metadata = filter_payload(
            {
                **span.metadata,
                "trace_output_state": output_state,
            }
        )
        extra = {
            "logical_run_id": span.run_id,
            "basis": span.basis,
            "prompt_version": span.prompt_version,
            "model": span.model,
            "agent_id": self.agent_id,
            "agent_environment": self.agent_environment,
            "metadata": metadata,
        }
        inputs = filter_payload({**span.inputs, **payload})
        create_kwargs: dict[str, object] = {
            "id": run_uuid,
            "name": span.name,
            "run_type": span.run_type,
            "project_name": self.project,
            "inputs": inputs,
            "extra": extra,
        }
        if output_state != "NOT_COLLECTED":
            filtered_outputs = filter_payload(span_outputs)
            if output_state == "COLLECTED" and not filtered_outputs:
                metadata["trace_output_state"] = "REDACTED"
            create_kwargs["outputs"] = filtered_outputs
        if span.error is not None:
            create_kwargs["error"] = sanitize_trace_error(span.error)
        if start is not None:
            create_kwargs["start_time"] = start
        if end is not None:
            create_kwargs["end_time"] = end
        if span.parent_run_id is not None:
            create_kwargs["parent_run_id"] = self._run_uuid(span.parent_run_id)
        if span.tags:
            create_kwargs["tags"] = list(span.tags)
        client.create_run(**create_kwargs)  # type: ignore[attr-defined]


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
