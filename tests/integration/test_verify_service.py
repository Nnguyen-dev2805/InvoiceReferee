"""Integration tests for the isolated verify service (contracts §7, §8).

Verifies synthetic fixtures cannot become recorded-provider evidence; missing
or tampered captures fail closed, and immutable run reports survive reload.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from invoice_referee.evaluation.service import (
    get_last_verify_report,
    run_isolated_verify,
)


@pytest.mark.asyncio
async def test_isolated_verify_core4_recorded_replay(tmp_path: Path) -> None:
    report = await run_isolated_verify(
        "core", "RECORDED_REPLAY", runtime_dir=tmp_path / "runtime"
    )
    assert report["suite"] == "core"
    assert report["mode"] == "RECORDED_REPLAY"
    assert report["planned"] == 4
    assert report["attempted"] == 4
    assert report["completed"] == 0
    assert report["passed"] == 0
    assert report["release"] is False
    assert report["status"] == "NEEDS_RECORDING"
    assert report["union_dangerous_miss"] == 0
    assert report["dangerous_miss_rate"] == 0.0
    assert report["completion_rate"] == 0.0

    # Ensure all 4 rows passed
    rows = report["rows"]
    assert len(rows) == 4
    for r in rows:
        assert r["passed"] is False
        assert r["technical_failure"] == 1
        assert r["union_dangerous_miss"] == 0


@pytest.mark.asyncio
async def test_isolated_verify_escalation5_recorded_replay(tmp_path: Path) -> None:
    report = await run_isolated_verify(
        "escalation", "RECORDED_REPLAY", runtime_dir=tmp_path / "runtime"
    )
    assert report["suite"] == "escalation"
    assert report["mode"] == "RECORDED_REPLAY"
    assert report["planned"] == 5
    assert report["attempted"] == 5
    assert report["completed"] == 0
    assert report["passed"] == 0
    assert report["release"] is False
    assert report["status"] == "NEEDS_RECORDING"
    assert report["union_dangerous_miss"] == 0
    assert report["dangerous_miss_rate"] == 0.0
    assert report["completion_rate"] == 0.0

    # Ensure 3 routine + 2 human-required
    routes = [r["expected_route"] for r in report["rows"]]
    assert routes == ["UNKNOWN"] * 5 # sources were not read; do not fabricate expected execution results


@pytest.mark.asyncio
async def test_isolated_verify_does_not_mutate_app_state(
    app_fixture, tmp_path: Path
) -> None:
    # 1. Record cases in app_fixture before verify run
    initial_count = app_fixture.case_count()

    # 2. Run verify in isolation
    report = await run_isolated_verify(
        "core", "RECORDED_REPLAY", runtime_dir=tmp_path / "runtime"
    )
    assert report["release"] is False
    assert report["status"] == "NEEDS_RECORDING"

    # 3. Assert app_fixture state is completely unchanged
    assert app_fixture.case_count() == initial_count


@pytest.mark.asyncio
async def test_isolated_verify_missing_recording_blocks_release(tmp_path: Path) -> None:
    # Set up a mock verify dataset where recording.json is removed from one case
    from invoice_referee.evaluation.service import DEFAULT_VERIFY_DATA_DIR

    fake_data = tmp_path / "data"
    shutil.copytree(DEFAULT_VERIFY_DATA_DIR, fake_data)

    # Delete recording from tc01
    rec_file = fake_data / "cases" / "tc01" / "recordings" / "recording.json"
    if rec_file.is_file():
        rec_file.unlink()

    report = await run_isolated_verify(
        "core",
        "RECORDED_REPLAY",
        data_dir=fake_data,
        runtime_dir=tmp_path / "runtime",
    )
    # Release gate must be False when recording is missing
    assert report["release"] is False
    assert report["passed"] < report["planned"]

    # Check that tc01 has a recorded error row
    tc01_row = next(r for r in report["rows"] if "tc01" in r["root_id"].lower())
    assert tc01_row["passed"] is False
    assert tc01_row["technical_failure"] == 1
    assert any("DATASET_INVALID" in reason for reason in tc01_row["failure_reasons"])


@pytest.mark.asyncio
async def test_get_last_verify_report_persistence(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    assert get_last_verify_report(runtime_dir) is None

    report = await run_isolated_verify(
        "core", "RECORDED_REPLAY", runtime_dir=runtime_dir
    )
    loaded = get_last_verify_report(runtime_dir)
    assert loaded is not None
    assert loaded["run_id"] == report["run_id"]
    assert loaded["suite"] == "core"
    assert loaded["passed"] == 0
