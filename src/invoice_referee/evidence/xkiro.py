"""xkiro structured-output adapter (contracts §5, §8; plan T5).

Validates the returned JSON against an expected shape and truncates oversized
payloads. A schema-valid output is still only an observation/proposal — never a
Fact, a grant or a money effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from invoice_referee.evidence.trace import (
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_MAX_LLM_INPUT_CHARS,
    DEFAULT_MAX_LLM_OUTPUT_CHARS,
    RunBudget,
)

MAX_OUTPUT_CHARS = DEFAULT_MAX_LLM_OUTPUT_CHARS


class XkiroError(RuntimeError):
    """A provider call failed (transport, status, truncation or schema)."""


class XkiroTransportError(XkiroError):
    """Transport/HTTP/oversize failure — no schema repair applies."""


class XkiroSchemaError(XkiroError):
    """Non-JSON / wrong-shape output — eligible for the single repair slot."""

    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        # The bounded raw response is kept for the private repair context only.
        self.raw = raw


@dataclass
class XkiroClient:
    api_key: str
    model: str
    base_url: str
    provider_name: str = "xkiro"
    timeout_s: float = DEFAULT_LLM_TIMEOUT_S
    transport: httpx.AsyncBaseTransport | None = None
    max_input_chars: int = DEFAULT_MAX_LLM_INPUT_CHARS
    max_output_chars: int = DEFAULT_MAX_LLM_OUTPUT_CHARS

    async def complete_json(
        self, *, system: str, user: str, budget: RunBudget
    ) -> dict[str, object]:
        if not budget.can_call_llm():
            raise XkiroError("LLM budget exhausted")
        # Preflight the app-size input cap BEFORE any network I/O (plan E3).
        serialized = system + user
        if len(serialized) > self.max_input_chars:
            raise XkiroTransportError(
                f"LLM input {len(serialized)} chars exceeds cap {self.max_input_chars}"
            )
        budget.charge_llm()
        started_at = datetime.now(UTC)
        attempted = False
        returned_model: str | None = None
        usage: dict[str, object] = {}
        parsed: dict[str, object] | None = None
        trace_error: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_s, transport=self.transport
            ) as client:
                attempted = True
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
            if response.status_code >= 400:
                raise XkiroTransportError(f"LLM HTTP {response.status_code}")
            body = response.json()
            model_value = body.get("model")
            returned_model = model_value if isinstance(model_value, str) else None
            usage = _trace_usage(body.get("usage"))
            content = body["choices"][0]["message"]["content"]
            if len(content) > self.max_output_chars:
                raise XkiroTransportError("LLM output exceeded the bounded size")
            import json

            try:
                parsed_value = json.loads(content)
            except json.JSONDecodeError as error:
                raise XkiroSchemaError(
                    "LLM returned non-JSON output", raw=content
                ) from error
            if not isinstance(parsed_value, dict):
                raise XkiroSchemaError("LLM JSON must be an object", raw=content)
            parsed = parsed_value
            return parsed_value
        except Exception as error:
            trace_error = f"{type(error).__name__}: {error}"
            raise
        finally:
            if attempted:
                try:
                    from invoice_referee.evidence.telemetry import record_llm_call

                    record_llm_call(
                        started_at=started_at,
                        ended_at=datetime.now(UTC),
                        system=system,
                        user=user,
                        requested_model=self.model,
                        returned_model=returned_model,
                        parsed_response=parsed,
                        usage=usage,
                        error=trace_error,
                        provider=self.provider_name,
                    )
                except Exception:
                    # Instrumentation never changes the provider result or failure.
                    pass


def _trace_usage(value: object) -> dict[str, object]:
    """Keep only provider-reported counters; do not infer missing usage.

    Reasoning/cached tokens are kept under their own namespaced keys when the
    response provides them (flat or OpenAI-style `*_tokens_details` nesting).
    Absent means UNKNOWN (key missing), never zero; reasoning tokens are never
    added into completion tokens because containment is unknown.
    """
    if not isinstance(value, dict):
        return {}
    keys = {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cached_tokens",
    }
    usage = {
        key: count
        for key, count in value.items()
        if key in keys and isinstance(count, int) and not isinstance(count, bool)
    }
    details = value.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
        usage.setdefault("reasoning_tokens", details["reasoning_tokens"])
    details = value.get("prompt_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("cached_tokens"), int):
        usage.setdefault("cached_tokens", details["cached_tokens"])
    return usage
