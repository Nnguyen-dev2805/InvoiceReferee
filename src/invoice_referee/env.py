"""Minimal ``.env`` loader (T15 fix).

The runtime reads configuration from the process environment. Operators keep a
``.env`` file (Git-ignored) next to the repo; this loader copies its ``KEY=VALUE``
entries into ``os.environ`` so the app can be started with a real provider key
without exporting every variable by hand.

Rules:
- Existing environment variables WIN (``setdefault`` semantics): an explicit
  ``export`` always overrides the file, so CI/production secrets are never
  clobbered by a stray ``.env``.
- Blank lines and ``#`` comments are ignored; a trailing ``#`` comment after a
  value is stripped. Surrounding single/double quotes are removed.
- A missing file is a no-op (the app still runs; the provider reports
  ``CONFIG_NOT_ACTIVE`` when a key is genuinely required).

This deliberately has no third-party dependency (stdlib only) so the toolchain
stays small.
"""
from __future__ import annotations

import os
from pathlib import Path


def parse_env_text(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines into a dict (comments/blank lines ignored)."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        if '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        if not key:
            continue
        value = _strip_inline_comment(value.strip())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    return values


def _strip_inline_comment(value: str) -> str:
    """Drop a trailing ``# comment`` that is not inside quotes."""
    quote: str | None = None
    for index, char in enumerate(value):
        if char in ('"', "'"):
            quote = None if quote == char else (char if quote is None else quote)
        elif char == '#' and quote is None and index > 0 and value[index - 1].isspace():
            return value[:index].rstrip()
    return value


def load_env_file(path: Path) -> dict[str, str]:
    """Load ``path`` into ``os.environ`` (existing vars win); return what was set."""
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    values = parse_env_text(file_path.read_text(encoding='utf-8'))
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return values


def load_repo_env(start: Path | None = None) -> dict[str, str]:
    """Load the repo-root ``.env`` (idempotent). ``start`` overrides the search base."""
    base = Path(start) if start is not None else Path(__file__).resolve().parents[2]
    return load_env_file(base / '.env')
