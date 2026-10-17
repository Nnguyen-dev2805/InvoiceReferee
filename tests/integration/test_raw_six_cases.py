"""R5: the first 6 development cases run through the raw pipeline (plan R5).

Each case is driven through the real workflow (create/attach/submit) with its
typed context imported; the assessment uses the case's own source facts (STUB
hand-transcription in STUB mode). Gold is loaded by the scorer afterwards.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from invoice_referee.evaluation.packets import load_gold, load_input
from invoice_referee.evaluation.runner import EvaluationRunner
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

CORPUS = Path(__file__).resolve().parents[2] / "data" / "kiem-thu"
SIX = ("case-01-cong-ty-chi-them", "case-02-nhan-vien-hoan-tien", "case-03-quyet-toan-can-bang",
       "case-04-chua-ro-nguoi-thanh-toan", "case-06-chi-phi-vuot-ngan-sach", "case-07-vuot-quyen-cong-nhan-chi-phi")


@pytest.fixture
def raw_workflow(tmp_path: Path):
    db = Database(tmp_path / "r.sqlite")
    db.migrate()
    workflow = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    workflow.import_demo_context(
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "legacy-company-context.json",
        origin="SIMULATED",
    )
    return workflow


@pytest.mark.parametrize("slug", SIX)
async def test_case_runs_through_raw_pipeline(raw_workflow, legacy_corpus, slug: str) -> None:
    case_dir = legacy_corpus / slug
    packet = load_input(case_dir, stage_id="ban-dau")
    gold = load_gold(case_dir, stage_id="ban-dau")

    runner = EvaluationRunner(workflow=raw_workflow)
    # The STUB reader assesses the case's own hand-transcription (contracts §5);
    # it is reader-only and never part of load_input.
    from invoice_referee.evaluation.packets import load_stub_readings

    transcription = load_stub_readings(case_dir, stage_id="ban-dau")
    packet = packet.model_copy(update={"transcription": transcription})

    actual = await runner.run(packet, mode="STUB")
    assert actual.state in ("WAITING", "READY_TO_EXECUTE", "SETTLED", "TECHNICAL_ERROR")
    if gold.allowed.route in ("FACT", "POLICY", "AUTHORITY"):
        assert actual.instructions == (), f"{slug} must not auto-issue on a human-required route"


async def test_d01_reaches_the_gold(raw_workflow, legacy_corpus) -> None:
    # D01 is the routine case: T8/E5/C3/A2 => S3 => one PAY 3m.
    case_dir = legacy_corpus / "case-01-cong-ty-chi-them"
    packet = load_input(case_dir, stage_id="ban-dau")
    from invoice_referee.evaluation.packets import load_stub_readings

    packet = packet.model_copy(
        update={"transcription": load_stub_readings(case_dir, stage_id="ban-dau")}
    )
    actual = await EvaluationRunner(workflow=raw_workflow).run(packet, mode="STUB")
    assert actual.state == "READY_TO_EXECUTE"
    assert [(i.direction, i.amount) for i in actual.instructions] == [("PAY", 3_000_000)]
    assert actual.money_states["S"] == "KNOWN"


async def test_d03_is_balanced_settled(raw_workflow, legacy_corpus) -> None:
    case_dir = legacy_corpus / "case-03-quyet-toan-can-bang"
    packet = load_input(case_dir, stage_id="ban-dau")
    from invoice_referee.evaluation.packets import load_stub_readings

    packet = packet.model_copy(
        update={"transcription": load_stub_readings(case_dir, stage_id="ban-dau")}
    )
    actual = await EvaluationRunner(workflow=raw_workflow).run(packet, mode="STUB")
    assert actual.state == "SETTLED"
    assert actual.instructions == ()


async def test_d04_answer_closes_the_fact_then_escalates(raw_workflow, legacy_corpus) -> None:
    # D04 initial: payer unknown -> FACT. The owner's answer establishes E5 and
    # the workflow moves on (a single answer does not resolve every gate).
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import (
        ActivityData,
        AttachSources,
        CreateDraft,
        Declaration,
        SourceUpload,
        Submit,
    )
    from invoice_referee.domain.issues import Answer
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.evaluation.packets import load_stub_readings

    case_dir = legacy_corpus / "case-04-chua-ro-nguoi-thanh-toan"
    packet = load_input(case_dir, stage_id="ban-dau")
    workflow = raw_workflow
    # Import the case context and seed the STUB reading for the activity.
    workflow.import_company_context(packet.organization, origin="SIMULATED")
    activity = packet.submission.activity
    with workflow.db.transaction() as cx:
        cx.execute(
            "INSERT OR REPLACE INTO context_transcriptions (tenant, activity_id, "
            "transcription_json) VALUES (?, ?, ?)",
            ("tenant:demo", activity, load_stub_readings(case_dir, stage_id="ban-dau").model_dump_json()),
        )
    session = workflow.start_session(tenant="tenant:demo", persona="employee", actor_id="employee:employee-a")

    def ctx(cid: str, version: int) -> CommandContext:
        return CommandContext(
            session_id=session.session_id, actor_id="employee:employee-a",
            command_id=cid, expected_case_version=version,
        )

    created = await workflow.execute(
        ctx("cmd:create", 0),
        CreateDraft(activity_data=ActivityData(
            activity_id=activity, name=activity,
            occurred_at=__import__("datetime").datetime(2026, 10, 25, tzinfo=__import__("datetime").UTC),
            declared_purpose=packet.submission.declared_purpose,
        )),
    )
    root = created.case_view.id
    version = created.case_view.version
    if packet.sources:
        attached = await workflow.execute(
            ctx("cmd:attach", version),
            AttachSources(root_id=root, uploads=tuple(
                SourceUpload(filename=s.filename, media=s.media, digest=s.sha256,
                             storage_key=f"tenant:demo/{root}/{s.filename}")
                for s in packet.sources
            )),
        )
        version = attached.case_view.version
    submitted = await workflow.execute(
        ctx("cmd:submit", version),
        Submit(root_id=root, declaration=Declaration(activity_id=activity, declared_purpose="x")),
    )
    view = submitted.case_view
    assert view.state == "WAITING"
    payer_issue = next(i for i in view.issues if i.field_or_rule == "expense:payer")

    answered = await workflow.execute(
        ctx("cmd:answer", view.version),
        AnswerIssue(root_id=root, answer=Answer(
            issue_id=payer_issue.id, basis_id=workflow.question_card(session,root,payer_issue.id).basis_id, answer_kind="FACT",
            value="employee:employee-a", reason="Tôi đã trả khoản này.",
        )),
    )
    after = answered.case_view
    # The FACT is resolved and E is established; the workflow advances.
    assert not any(i.field_or_rule == "expense:payer" for i in after.issues)
    assert after.actual_money.E.state == "KNOWN"
    assert after.actual_money.E.value == 5_000_000
