"""dev.py entry: the server defaults to LIVE, and LIVE never silently degrades.

A missing live credential must stop the launcher (exit 2), not fall back to a
fake provider; STUB/REPLAY stay available as explicit opt-ins.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _dev_module():
    spec = importlib.util.spec_from_file_location(
        "dev_entry", PROJECT_ROOT / "scripts" / "dev.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_mode_is_live() -> None:
    dev = _dev_module()
    parser = dev.build_parser()
    assert parser.parse_args([]).mode == "live"


def test_mode_choices_include_all_three() -> None:
    dev = _dev_module()
    parser = dev.build_parser()
    for mode in ("live", "replay", "stub"):
        assert parser.parse_args(["--mode", mode]).mode == mode


def test_live_without_credentials_exits_two(monkeypatch, capsys) -> None:
    dev = _dev_module()
    from invoice_referee.config import Settings

    # Isolate from any real .env so the missing-credential path is exercised.
    blank = Settings(_env_file=None)  # type: ignore[call-arg]
    monkeypatch.setattr(dev, "Settings", lambda *a, **k: blank)
    code = dev.main(["--mode", "live"])
    assert code == 2
    out = capsys.readouterr().out
    assert "MISTRAL_API_KEY" in out


def test_compose_does_not_set_a_dead_mode_override() -> None:
    # compose.yaml must not declare a mode env var the app never reads.
    text = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "INVOICE_REFEREE_MODE" not in text
