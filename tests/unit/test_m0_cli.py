"""M0 CLI: offline stub run writes an honest manifest (plan T5).

In STUB mode there is no provider call, so no attempt is faked as a successful
LIVE read; the manifest records the mode and the unresolved model honestly.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.cli import main


def test_m0_stub_writes_manifest(tmp_path: Path) -> None:
    inp = tmp_path / "input"
    inp.mkdir()
    out = tmp_path / "out"
    code = main(["m0", "--input", str(inp), "--output", str(out), "--mode", "stub"])
    assert code == 0
    report = json.loads((out / "m0-manifest.json").read_text(encoding="utf-8"))
    assert report["mode"] == "STUB"
    assert len(report["attempts"]) == 4
    assert {a["kind"] for a in report["attempts"]} == {
        "text",
        "clear_scan",
        "unclear_scan",
        "non_document",
    }


def test_m0_live_without_credentials_fails_clearly(tmp_path: Path, monkeypatch) -> None:
    from invoice_referee.config import LIVE_REQUIRED_SETTINGS

    for name in LIVE_REQUIRED_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    inp = tmp_path / "input"
    inp.mkdir()
    code = main(["m0", "--input", str(inp), "--output", str(tmp_path / "o"), "--mode", "live"])
    assert code == 2  # named missing-config gap, not a silent pass


def test_unknown_command_returns_error() -> None:
    assert main(["nope"]) == 2
