"""Named evaluation suites select the right cases (contracts §7; plan T9/R7).

`core` must be Core4 and `escalation` Escalation5, not the whole corpus;
`development` is everything. Selection is by case_id from each case's kich-ban.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.evaluation.suites import CORE, ESCALATION, select_suite


def _make_dataset(tmp_path: Path) -> Path:
    for i in range(1, 16):
        case = tmp_path / f"case-{i:02d}-x"
        (case / "cau-hinh").mkdir(parents=True)
        (case / "cau-hinh" / "kich-ban.json").write_text(
            json.dumps({"case_id": f"D{i:02d}", "stages": []}), encoding="utf-8"
        )
    return tmp_path


def test_core_selects_four_cases(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("core", dataset)
    assert len(packets) == 4
    assert CORE == ("D01", "D02", "D03", "D11")


def test_escalation_selects_five_cases(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("escalation", dataset)
    assert len(packets) == 5
    assert ESCALATION == ("D01", "D02", "D03", "D04", "D07")


def test_development_selects_everything(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("development", dataset)
    assert len(packets) == 15


def test_core_is_not_the_whole_development_split(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    assert len(select_suite("core", dataset)) < len(select_suite("development", dataset))
