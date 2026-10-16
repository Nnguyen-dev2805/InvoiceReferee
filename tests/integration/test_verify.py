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


async def test_non_stub_run_does_not_use_seeded_transcription(app_fixture, tmp_path: Path):
    # A LIVE/RECORDED_REPLAY run without a real reader must not consume the
    # packet's seeded STUB transcription: it reads nothing and stays unresolved
    # (contracts §5, §8), rather than settling on fake input.
    packet = app_fixture.write_packet(tmp_path, name="travel-clean")
    packet_input = load_input(packet)
    runner = EvaluationRunner(workflow=app_fixture.workflow)  # no transcriber
    actual = await runner.run(packet_input, mode="LIVE")
    assert actual.instructions == ()
    assert actual.state != "SETTLED"


async def test_core_and_escalation_suites_pass_on_the_corpus(legacy_corpus) -> None:
    # The R7 gate: Core4 and Escalation5 select the right cases and the release
    # gate is union=0 (independent gold, real command surface).
    from pathlib import Path

    from invoice_referee.evaluation.packets import load_gold, load_input, load_stub_readings
    from invoice_referee.evaluation.runner import EvaluationRunner
    from invoice_referee.evaluation.scorer import IndependentScorer
    from invoice_referee.evaluation.suites import select_suite
    from invoice_referee.workflow.db import Database
    from invoice_referee.workflow.service import CaseWorkflow

    corpus = legacy_corpus
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    db = Database(tmp / "r.sqlite")
    db.migrate()
    workflow = CaseWorkflow(db, uploads_dir=tmp / "up")
    workflow.import_demo_context(
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "legacy-company-context.json",
        origin="SIMULATED",
    )
    runner = EvaluationRunner(workflow=workflow)
    scorer = IndependentScorer()
    for suite, count in (("core", 4), ("escalation", 5)):
        packets = select_suite(suite, corpus)
        assert len(packets) == count, suite
        rows = []
        for packet_dir in packets:
            packet = load_input(packet_dir, stage_id="ban-dau").model_copy(
                update={"transcription": load_stub_readings(packet_dir, stage_id="ban-dau")}
            )
            actual = await runner.run(packet, mode="STUB")
            gold = load_gold(packet_dir, stage_id="ban-dau")
            rows.append(scorer.score(actual, gold))
        report = scorer.release_gate(rows, total_human=sum(
            1 for r in rows if r.expected_route in ("FACT", "POLICY", "AUTHORITY")
        ))
        assert report.union_dangerous_miss == 0, (suite, [r.model_dump() for r in rows])
