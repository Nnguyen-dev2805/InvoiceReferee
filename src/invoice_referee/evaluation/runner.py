"""Evaluation runner: run one packet through the real workflow (contracts §7, §9).

`run(packet, mode)` accepts only a PacketInput (never gold) and drives the same
CaseWorkflow the app uses: create the root, attach the raw sources, submit, and
read the persisted result into an ActualResult. No observations are injected and
gold corrections never enter. Gold is loaded separately by the scorer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.evaluation.models import PacketInput
from invoice_referee.evaluation.scorer import (
    ActualInstruction,
    ActualIssue,
    ActualResult,
)
from invoice_referee.evaluation.reports import SuiteReport


def actual_from_view(view, packet: PacketInput, *, mode: str, elapsed_ms: float) -> ActualResult:
    """Read what the app actually persisted into an ActualResult (contracts §9).

    `refs_ok` reflects whether the issue/instruction actually carries evidence
    refs; it is never defaulted to True, so an ungrounded output is scored as
    such rather than passed.
    """
    instructions = tuple(
        ActualInstruction(
            direction=inst.direction,
            amount=inst.amount,
            owner=None,
            refs_ok=bool(inst.authority_refs) or bool(getattr(inst, "refs", ())),
        )
        for inst in view.instructions
    )
    issues = tuple(
        ActualIssue(kind=issue.kind, owner=issue.owner, refs_ok=bool(issue.refs))
        for issue in view.issues
    )
    technical = view.state == "TECHNICAL_ERROR"
    # A false affirmative is a BALANCED conclusion reached without coverage:
    # the projection's A/P/R must be KNOWN (established by coverage), not
    # merely "no instruction issued". A legitimate S=0 with coverage is fine.
    money = view.actual_money
    money_states = {
        "A": money.A.state,
        "P": money.P.state,
        "R": money.R.state,
        "S": money.S.state,
    }
    affirmed_zero = (
        view.conclusion is not None
        and view.conclusion.status == "BALANCED"
        and not view.instructions
        and (money.A.state != "KNOWN" or money.P.state != "KNOWN")
    )
    return ActualResult(
        root_id=packet.root_id,
        mode=mode,  # type: ignore[arg-type]
        state=view.state,
        instructions=instructions,
        issues=issues,
        conclusion_status=view.conclusion.status if view.conclusion else None,
        affirmed_zero_without_coverage=affirmed_zero,
        technical_error=technical,
        elapsed_ms=elapsed_ms,
        money_states=money_states,
    )


class EvaluationRunner:
    """Runs packets through the application workflow and reports actual results."""

    def __init__(self, *, workflow, transcription_for=None) -> None:
        self.workflow = workflow
        self._transcription_for = transcription_for

    async def run(self, packet: PacketInput, mode: str) -> ActualResult:
        """Run one packet; returns what the app actually produced."""
        import time

        start = time.monotonic()
        # The runner uses the workflow's own submit path via the app fixture
        # contract: it never injects observations or gold corrections.
        view = await self._drive(packet)
        return actual_from_view(
            view, packet, mode=mode, elapsed_ms=(time.monotonic() - start) * 1000
        )

    async def _drive(self, packet: PacketInput):
        """Drive the workflow for a packet using its real command surface.

        Creates the root for the packet's activity, attaches the raw sources,
        and submits — the same path the app uses. No observation or gold value
        is injected.
        """
        from invoice_referee.domain.case import CommandContext
        from invoice_referee.domain.commands import (
            ActivityData,
            AttachSources,
            CreateDraft,
            Declaration,
            SourceUpload,
            Submit,
        )

        import uuid

        session = self.workflow.start_session()
        actor = session.actor_id
        tenant = session.tenant
        run_id = uuid.uuid4().hex

        def ctx(version: int) -> CommandContext:
            return CommandContext(
                session_id=session.session_id,
                actor_id=actor,
                command_id=f"eval:{run_id}:{version}",
                expected_case_version=version,
            )

        activity_id = packet.submission.activity
        # Seed the packet's observable organization context (budget + the STUB
        # hand-transcription) so a STUB run assesses real input. This is
        # input-layer data, never a gold/expected value.
        self._seed_context(packet, tenant)

        created = await self.workflow.execute(
            ctx(0),
            CreateDraft(
                activity_data=ActivityData(
                    activity_id=activity_id,
                    name=activity_id,
                    occurred_at=datetime.now(UTC),
                    declared_purpose=packet.submission.declared_purpose,
                )
            ),
        )
        root = created.case_view.id
        version = created.case_view.version

        if packet.sources:
            uploads = tuple(
                SourceUpload(
                    filename=source.filename,
                    media=source.media,
                    digest=source.sha256,
                    storage_key=f"{tenant}/{root}/{source.filename}",
                )
                for source in packet.sources
            )
            attached = await self.workflow.execute(
                ctx(version), AttachSources(root_id=root, uploads=uploads)
            )
            version = attached.case_view.version

        submitted = await self.workflow.execute(
            ctx(version),
            Submit(
                root_id=root,
                declaration=Declaration(
                    activity_id=activity_id,
                    declared_purpose=packet.submission.declared_purpose,
                ),
            ),
        )
        return submitted.case_view

    def _seed_context(self, packet: PacketInput, tenant: str) -> None:
        """Seed the packet's observable context: an authorized activity with its
        budget and its STUB hand-transcription (contracts §5, §7)."""
        import json

        from invoice_referee.evaluation.models import Transcription

        activity_id = packet.submission.activity
        with self.workflow.db.transaction() as cx:
            cx.execute(
                "INSERT OR REPLACE INTO context_activities (activity_id, tenant, name, "
                "occurred_at, purpose, budget_amount, budget_effect_from, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'AUTHORIZED')",
                (
                    activity_id,
                    tenant,
                    activity_id,
                    "2026-10-05T09:00:00+00:00",
                    packet.submission.declared_purpose,
                    packet.organization.budget_amount,
                    "2026-10-01T00:00:00+00:00" if packet.organization.budget_amount else None,
                ),
            )
            if packet.transcription is not None:
                cx.execute(
                    "INSERT OR REPLACE INTO context_transcriptions (tenant, activity_id, "
                    "transcription_json) VALUES (?, ?, ?)",
                    (tenant, activity_id, packet.transcription.model_dump_json()),
                )

    async def run_suite(
        self, packets: list[Path] | list[PacketInput], *, suite: str, mode: str
    ) -> SuiteReport:
        from invoice_referee.evaluation.packets import load_input

        actuals = []
        for item in packets:
            packet_input = item if isinstance(item, PacketInput) else load_input(item)
            actuals.append(await self.run(packet_input, mode))
        return SuiteReport(suite=suite, mode=mode, total=len(actuals), actuals=tuple(actuals))
