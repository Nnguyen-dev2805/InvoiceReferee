"""LLM configuration from environment / .env file.

Provider-agnostic OpenAI-compatible setup. Set these in a `.env` at the repo root
(or as real environment variables):

    LLM_BASE_URL=https://api.xkiro.com/v1
    LLM_API_KEY=sk-...
    LLM_MODEL=claude-opus-4.8
    LLM_TIMEOUT=30

Without ``LLM_API_KEY`` no client is created and the agent uses the deterministic
fallback, so the system runs with or without a provider.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from invoice_referee.agent.llm_client import LLMClient
from invoice_referee.agent.openai_client import OpenAICompatibleClient

DEFAULT_BASE_URL = "https://api.xkiro.com/v1"
DEFAULT_MODEL = "claude-opus-4.8"
DEFAULT_TIMEOUT = 30.0

_REPO_ROOT = Path(__file__).resolve().parents[3]


def load_env_file(path: Optional[str] = None) -> dict[str, str]:
    """Parse a minimal KEY=VALUE .env file. Missing file -> empty dict."""
    env_path = Path(path) if path else _REPO_ROOT / ".env"
    if not env_path.is_file():
        return {}

    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def _resolve(env: dict[str, str], key: str) -> Optional[str]:
    # Explicit env dict wins; otherwise fall back to the real environment.
    if key in env:
        return env[key]
    return os.environ.get(key)


def client_from_env(env: Optional[dict[str, str]] = None) -> Optional[LLMClient]:
    """Build an OpenAI-compatible client from config, or ``None`` if no API key.

    When ``env`` is omitted, values come from the process environment merged over
    a repo-root ``.env`` file.
    """
    if env is None:
        env = {**load_env_file(), **{k: v for k, v in os.environ.items() if k.startswith("LLM_")}}

    api_key = _resolve(env, "LLM_API_KEY")
    if not api_key:
        return None

    timeout_raw = _resolve(env, "LLM_TIMEOUT")
    try:
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    return OpenAICompatibleClient(
        base_url=_resolve(env, "LLM_BASE_URL") or DEFAULT_BASE_URL,
        api_key=api_key,
        model=_resolve(env, "LLM_MODEL") or DEFAULT_MODEL,
        timeout=timeout,
    )
