"""Groq LLM adapter (OpenAI-compatible, contracts §12.3).

Serves open-weight reasoning models (such as `openai/gpt-oss-20b`) on Groq LPU.
Wire shape: standard Bearer token authorization, POST `{base_url}/chat/completions`
with `response_format={"type": "json_object"}`, `reasoning_format="parsed"`,
and configurable `reasoning_effort` ("low" by default).

No silent fallback: missing config raises; a Groq failure raises and is never
silently retried as Kimi or xKiro by this adapter.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import math
from email.utils import parsedate_to_datetime

import httpx

from invoice_referee.evidence.trace import (
    DEFAULT_LLM_TIMEOUT_S,
    DEFAULT_MAX_LLM_INPUT_CHARS,
    DEFAULT_MAX_LLM_OUTPUT_CHARS,
    RunBudget,
)


class GroqError(RuntimeError):
    """A Groq provider call failed (transport, status, truncation or schema)."""


class GroqTransportError(GroqError):
    """Transport/HTTP/oversize failure — no schema repair applies."""


class GroqSchemaError(GroqError):
    """Non-JSON / wrong-shape output — eligible for the single repair slot."""

    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def _parse_retry_after(response: httpx.Response) -> float:
    """Read bounded HTTP Retry-After or compound rate-limit durations."""
    header = response.headers.get("retry-after")
    if header:
        try:
            seconds = float(header)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = math.nan
        if math.isfinite(seconds):
            return max(0.0, seconds)
    reset = response.headers.get("x-ratelimit-reset-tokens", "")
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", reset)
    if parts:
        return sum(float(v) * {"ms": .001, "h": 3600, "m": 60, "s": 1}[unit] for v, unit in parts)
    return 10.0


def _clean_json_content(content: str) -> str:
    """Remove outer wrappers only; never remove source text inside JSON values."""
    cleaned = content.strip()
    if cleaned.startswith("<think>"):
        end = cleaned.find("</think>")
        if end < 0:
            return ""
        cleaned = cleaned[end + len("</think>"):].strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            cleaned = "\n".join(lines[1:-1]).strip()
    return cleaned


class _RateLimited(GroqTransportError):
    def __init__(self, response: httpx.Response):
        super().__init__("LLM HTTP 429")
        self.response = response


@dataclass
class GroqClient:
    """OpenAI-compatible Groq client with reasoning effort support."""

    api_key: str
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "openai/gpt-oss-20b"
    provider_name: str = "groq"
    reasoning_effort: str = "low"
    reasoning_format: str = "parsed"
    timeout_s: float = DEFAULT_LLM_TIMEOUT_S
    transport: httpx.AsyncBaseTransport | None = None
    max_input_chars: int = DEFAULT_MAX_LLM_INPUT_CHARS
    max_output_chars: int = DEFAULT_MAX_LLM_OUTPUT_CHARS
    max_rate_limit_retries: int = 5

    async def complete_json(
        self, *, system: str, user: str, budget: RunBudget
    ) -> dict[str, object]:
        if not budget.can_call_llm():
            raise GroqError("LLM budget exhausted")
        if len(system) + len(user) > self.max_input_chars:
            raise GroqTransportError("LLM input exceeds bounded size")
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, "temperature": .1,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.reasoning_format:
            payload["reasoning_format"] = self.reasoning_format
        async with httpx.AsyncClient(transport=self.transport) as client:
            for retry in range(self.max_rate_limit_retries + 1):
                if not budget.can_call_llm():
                    raise GroqTransportError("LLM retry budget/deadline exhausted")
                try:
                    return await self._attempt(client, payload, system, user, budget)
                except _RateLimited as error:
                    if retry >= self.max_rate_limit_retries or not budget.can_call_llm():
                        raise
                    wait_s = _parse_retry_after(error.response) + .5
                    remaining = budget.processing_deadline_s - budget.elapsed_s()
                    if not math.isfinite(wait_s) or wait_s >= remaining or wait_s > 60:
                        raise GroqTransportError("Rate-limit wait exceeds remaining deadline") from error
                    await asyncio.sleep(wait_s)
        raise GroqTransportError("LLM retry limit exhausted")

    async def _attempt(self, client, payload, system, user, budget) -> dict[str, object]:
        # One charge and one trace for every actual HTTP request, including429.
        remaining = budget.processing_deadline_s - budget.elapsed_s()
        timeout = min(self.timeout_s, remaining)
        if timeout <= 0:
            raise GroqTransportError("LLM deadline exhausted before request")
        budget.charge_llm()
        started_at = datetime.now(UTC)
        returned_model = None
        usage = {}
        parsed = None
        trace_error = None
        try:
            try:
                async with asyncio.timeout(timeout):
                    response = await client.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload, timeout=timeout,
                    )
            except (TimeoutError, httpx.HTTPError) as error:
                raise GroqTransportError("LLM request transport/timeout failure") from error
            if response.status_code == 429:
                raise _RateLimited(response)
            if response.status_code >= 400:
                raise GroqTransportError(f"LLM HTTP {response.status_code}")
            if budget.expired():
                raise GroqTransportError("LLM response arrived after deadline")
            try:
                body = response.json()
                model = body.get("model")
                returned_model = model if isinstance(model, str) else None
                usage = _trace_usage(body.get("usage"))
                choice = body["choices"][0]
                message = choice["message"]
                if choice.get("finish_reason") not in (None, "stop") or message.get("refusal"):
                    raise GroqTransportError("LLM response incomplete or refused")
                content = message["content"]
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
                raise GroqTransportError("LLM invalid response envelope") from error
            if not isinstance(content, str) or len(content) > self.max_output_chars:
                raise GroqTransportError("LLM invalid/oversize content")
            try:
                value = json.loads(_clean_json_content(content))
            except json.JSONDecodeError as error:
                raise GroqSchemaError("LLM returned non-JSON output", raw=content) from error
            if not isinstance(value, dict):
                raise GroqSchemaError("LLM JSON must be an object", raw=content)
            parsed = value
            return value
        except Exception as error:
            trace_error = f"{type(error).__name__}: {error}"
            raise
        finally:
            try:
                from invoice_referee.evidence.telemetry import record_llm_call
                record_llm_call(
                    started_at=started_at, ended_at=datetime.now(UTC),
                    system=system, user=user, requested_model=self.model,
                    returned_model=returned_model, parsed_response=parsed,
                    usage=usage, error=trace_error, provider=self.provider_name,
                    requested_effort=self.reasoning_effort, observed_effort="UNKNOWN",
                )
            except Exception:
                pass


def _trace_usage(value: object) -> dict[str, object]:
    """Keep only provider-reported counters; never infer or total them."""
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
