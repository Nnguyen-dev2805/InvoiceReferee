"""Kimi-K3 LLM adapter (OpenAI-compatible, contracts §12.3).

Same wire shape as Hoangha: token + secret joined as ``token.secret`` Bearer,
POST ``{base_url}/chat/completions`` with ``response_format json_object``.
No silent fallback: missing config raises, a Kimi failure raises and is never
retried as xKiro by this adapter.

Requested vs returned model: telemetry records both; callers must not claim
the actual model without provider evidence.
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


class KimiError(RuntimeError):
    """A Kimi provider call failed (transport, status, truncation or schema)."""


class KimiTransportError(KimiError):
    """Transport/HTTP/oversize failure — no schema repair applies."""


class KimiSchemaError(KimiError):
    """Non-JSON / wrong-shape output — eligible for the single repair slot."""

    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


@dataclass
class KimiClient:
    """OpenAI-compatible Kimi client with the Hoangha auth shape."""

    token: str
    secret: str
    base_url: str
    model: str = "moonshotai/Kimi-K3"
    provider_name: str = "kimi"
    # Reasoning budget requested from Kimi (Hoangha uses "low"). Sent as-is in
    # the OpenAI-compatible body; a provider rejection surfaces loudly, never
    # silently dropped. The response does not confirm execution, so observed
    # effort stays UNKNOWN.
    reasoning_effort: str = "low"
    timeout_s: float = DEFAULT_LLM_TIMEOUT_S
    transport: httpx.AsyncBaseTransport | None = None
    max_input_chars: int = DEFAULT_MAX_LLM_INPUT_CHARS
    max_output_chars: int = DEFAULT_MAX_LLM_OUTPUT_CHARS

    def _api_key(self) -> str:
        return f"{self.token}.{self.secret}"

    async def complete_json(
        self, *, system: str, user: str, budget: RunBudget
    ) -> dict[str, object]:
        if not budget.can_call_llm():
            raise KimiError("LLM budget exhausted")
        serialized = system + user
        if len(serialized) > self.max_input_chars:
            raise KimiTransportError(
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
                    headers={"Authorization": f"Bearer {self._api_key()}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                        "reasoning_effort": self.reasoning_effort,
                    },
                )
            if response.status_code >= 400:
                raise KimiTransportError(f"LLM HTTP {response.status_code}")
            body = response.json()
            model_value = body.get("model")
            returned_model = model_value if isinstance(model_value, str) else None
            usage = _trace_usage(body.get("usage"))
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                import json as _json

                content = _json.dumps(content, ensure_ascii=False, default=str)
            if len(content) > self.max_output_chars:
                raise KimiTransportError("LLM output exceeded the bounded size")
            import json

            try:
                parsed_value = json.loads(content)
            except json.JSONDecodeError as error:
                raise KimiSchemaError(
                    "LLM returned non-JSON output", raw=content
                ) from error
            if not isinstance(parsed_value, dict):
                raise KimiSchemaError("LLM JSON must be an object", raw=content)
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
                        requested_effort=self.reasoning_effort,
                        observed_effort="UNKNOWN",
                    )
                except Exception:
                    pass


def _trace_usage(value: object) -> dict[str, object]:
    """Keep only provider-reported counters; never infer or total them.

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
