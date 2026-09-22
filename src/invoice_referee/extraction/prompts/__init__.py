"""Prompt templates for the Kimi reasoning agents, kept as plain text files.

Business rules embedded in these prompts (canonical fields, comparison fields,
formatting conventions) live here instead of as Python string literals so they
can be reviewed/edited without touching adapter logic.
"""

from __future__ import annotations

from importlib import resources


def load_prompt(filename: str) -> str:
    return resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
