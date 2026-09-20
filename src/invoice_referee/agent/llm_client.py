"""LLM provider boundary.

Sprint 1 keeps this abstract so the review pipeline works with or without a real
provider. Tests inject fakes; a real HTTP/SDK client can subclass ``LLMClient``
later. When no client is configured the agent service uses the deterministic
fallback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    """Provider returned an error."""


class LLMTimeout(LLMError):
    """Provider timed out."""


class LLMClient(ABC):
    """Minimal completion interface: prompt in, raw text out."""

    @abstractmethod
    def complete(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError
