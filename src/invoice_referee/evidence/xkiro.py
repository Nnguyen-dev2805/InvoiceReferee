"""xkiro structured-output adapter (contracts §5, §8; plan T5).

Validates the returned JSON against an expected shape and truncates oversized
payloads. A schema-valid output is still only an observation/proposal — never a
Fact, a grant or a money effect.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from invoice_referee.evidence.trace import RunBudget

MAX_OUTPUT_CHARS = 20_000


class XkiroError(RuntimeError):
    """A provider call failed (transport, status, truncation or schema)."""


@dataclass
class XkiroClient:
    api_key: str
    model: str
    base_url: str
    timeout_s: float = 20.0

    async def complete_json(
        self, *, system: str, user: str, budget: RunBudget
    ) -> dict[str, object]:
        if not budget.can_call_llm():
            raise XkiroError("LLM budget exhausted")
        budget.charge_llm()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
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
            raise XkiroError(f"LLM HTTP {response.status_code}")
        content = response.json()["choices"][0]["message"]["content"]
        if len(content) > MAX_OUTPUT_CHARS:
            raise XkiroError("LLM output exceeded the bounded size")
        import json

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise XkiroError("LLM returned non-JSON output") from error
        if not isinstance(parsed, dict):
            raise XkiroError("LLM JSON must be an object")
        return parsed
