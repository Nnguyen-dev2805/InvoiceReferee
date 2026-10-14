"""xkiro structured-output adapter (contracts §5, §8; plan T5).

Validates the returned JSON against an expected shape and truncates oversized
payloads. A schema-valid output is still only an observation/proposal — never a
Fact, a grant or a money effect.
"""

from __future__ import annotations

from dataclasses import dataclass

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
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self.transport) as client:
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
        content = response.json()["choices"][0]["message"]["content"]
        if len(content) > self.max_output_chars:
            raise XkiroTransportError("LLM output exceeded the bounded size")
        import json

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise XkiroSchemaError("LLM returned non-JSON output", raw=content) from error
        if not isinstance(parsed, dict):
            raise XkiroSchemaError("LLM JSON must be an object", raw=content)
        return parsed
