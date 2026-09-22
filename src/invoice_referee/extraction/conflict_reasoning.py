"""Prompt contract for cross-source accounting conflict analysis."""

from __future__ import annotations

from .prompts import load_prompt

CONFLICT_SYSTEM_PROMPT = load_prompt("conflict_system_prompt.md")
