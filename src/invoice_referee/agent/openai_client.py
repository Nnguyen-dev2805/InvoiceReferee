"""OpenAI-compatible chat-completions client.

Provider-agnostic: any endpoint that speaks the OpenAI Chat Completions API works
by changing ``base_url`` and ``model`` (e.g. xKiro, DeepSeek, OpenAI, a local
gateway). Uses only the standard library so no extra dependency is required.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional

from invoice_referee.agent.llm_client import LLMClient, LLMError, LLMTimeout

# Callable matching urllib.request.urlopen(req, timeout=...) for injection in tests.
UrlOpen = Callable[..., object]


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        temperature: float = 0.0,
        urlopen: Optional[UrlOpen] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._urlopen = urlopen or urllib.request.urlopen

    def complete(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                # urllib's default User-Agent is rejected (HTTP 403) by some
                # providers (e.g. xKiro). Send an explicit one so the normal
                # LLM path is not silently forced into the fallback.
                "User-Agent": "InvoiceReferee/0.1 (+https://github.com/Nnguyen-dev2805/InvoiceReferee)",
            },
            method="POST",
        )

        try:
            with self._urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read()
        except (TimeoutError, urllib.error.URLError) as exc:
            # urllib raises socket.timeout (a TimeoutError subclass) on read timeout.
            if isinstance(exc, TimeoutError) or "timed out" in str(getattr(exc, "reason", "")).lower():
                raise LLMTimeout(str(exc)) from exc
            raise LLMError(str(exc)) from exc
        except Exception as exc:  # network/other transport failures
            raise LLMError(str(exc)) from exc

        try:
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unparseable provider response: {exc}") from exc
