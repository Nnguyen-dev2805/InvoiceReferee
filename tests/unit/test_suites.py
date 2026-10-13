"""Named evaluation suites select the right packets (contracts §7; plan T9).

`core` must be Core4 and `escalation` Escalation5, not the whole development
split; `development` is everything.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.evaluation.suites import CORE, ESCALATION, select_suite


def _make_dataset(tmp_path: Path) -> Path:
    for name in (*CORE, *ESCALATION, "dev-extra"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_core_selects_four_packets(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("core", dataset)
    assert [p.name for p in packets] == list(CORE)
    assert len(packets) == 4


def test_escalation_selects_five_packets(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("escalation", dataset)
    assert [p.name for p in packets] == list(ESCALATION)
    assert len(packets) == 5


def test_development_selects_everything(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    packets = select_suite("development", dataset)
    unique = len(set(CORE) | set(ESCALATION)) + 1  # + dev-extra
    assert len(packets) == unique


def test_core_is_not_the_whole_development_split(tmp_path: Path) -> None:
    dataset = _make_dataset(tmp_path)
    assert len(select_suite("core", dataset)) < len(select_suite("development", dataset))
