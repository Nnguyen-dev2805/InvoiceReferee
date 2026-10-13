"""Verify: run a suite through the same workflow and score with gold (contracts §8, §9).

The runner only receives PacketInput; gold is loaded by the scorer afterwards.
The report distinguishes modes/times and expected-vs-actual per root.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.evaluation.packets import load_gold, load_input
from invoice_referee.evaluation.runner import EvaluationRunner
from invoice_referee.evaluation.scorer import IndependentScorer


async def test_run_returns_actual_then_scores(app_fixture, tmp_path: Path):
    packet = app_fixture.write_packet(tmp_path, name="travel-clean")
    packet_input = load_input(packet)
    runner = EvaluationRunner(workflow=app_fixture.workflow)
    actual = await runner.run(packet_input, mode="STUB")
    # Gold is loaded only after the actual result exists.
    gold = load_gold(packet)
    row = IndependentScorer().score(actual, gold)
    assert actual.mode == "STUB"
    assert row.root_id == packet_input.root_id


async def test_run_does_not_accept_gold(app_fixture, tmp_path: Path):
    # EvaluationRunner.run takes only PacketInput; a gold value never enters.
    packet = app_fixture.write_packet(tmp_path, name="travel-clean")
    packet_input = load_input(packet)
    assert not hasattr(packet_input, "latent")
    assert not hasattr(packet_input, "allowed")


async def test_run_suite_reports_counts(app_fixture, tmp_path: Path):
    from invoice_referee.evaluation.reports import SuiteReport

    packets = [
        app_fixture.write_packet(tmp_path, name="travel-clean"),
    ]
    runner = EvaluationRunner(workflow=app_fixture.workflow)
    report = await runner.run_suite(packets, suite="core", mode="STUB")
    assert isinstance(report, SuiteReport)
    assert report.suite == "core"
    assert report.total == 1
