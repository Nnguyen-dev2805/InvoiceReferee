"""Independent scoring (contracts §7, §8, §11).

The scorer reads the hidden GoldPacket only after an ActualResult exists. It is
pure and literal: it never calls the Reconciler, so it cannot grade the app with
the app's own logic. A dangerous miss is an unsafe action OR an unsafe
affirmative conclusion, counted once per dossier (union).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from invoice_referee.domain.common import StrictModel
from invoice_referee.evaluation.models import GoldPacket

RunMode = Literal["LIVE", "RECORDED_REPLAY", "STUB"]


class ActualInstruction(StrictModel):
    """One persisted instruction, as the scorer sees it."""

    direction: str
    amount: int
    owner: str | None = None
    refs_ok: bool = True


class ActualIssue(StrictModel):
    """One persisted issue/card, as the scorer sees it."""

    kind: str
    owner: str
    refs_ok: bool = True


class ActualResult(StrictModel):
    """What the app actually produced for one root (contracts §9).

    This is the only thing the scorer receives besides gold; it is produced by
    EvaluationRunner and never contains an expected value.
    """

    root_id: str
    mode: RunMode
    state: str
    instructions: tuple[ActualInstruction, ...] = ()
    issues: tuple[ActualIssue, ...] = ()
    conclusion_status: str | None = None
    affirmed_zero_without_coverage: bool = False
    technical_error: bool = False
    elapsed_ms: float = 0.0
    # Projection Fact states (KNOWN/UNKNOWN) for the money figures, so the
    # scorer can tell a coverage-backed zero from an unestablished one.
    money_states: dict[str, str] = {}


class ScoreRow(StrictModel):
    """Per-dossier score (contracts §7 metrics)."""

    root_id: str
    unsafe_action: int = 0
    unsafe_affirmative_conclusion: int = 0
    union_dangerous_miss: int = 0
    unnecessary_question: int = 0
    correct_auto_completion: int = 0
    technical_failure: int = 0
    expected_route: str
    actual_route: str


@dataclass
class ReleaseReport:
    action_miss: int
    affirmative_miss: int
    union_dangerous_miss: int
    total_human: int
    release: bool
    rows: list[ScoreRow] = field(default_factory=list)


class IndependentScorer:
    """Scores an ActualResult against an independent GoldPacket."""

    def score(self, actual: ActualResult, gold: GoldPacket) -> ScoreRow:
        allowed = gold.allowed
        expected_route = allowed.route
        # The app's route is derived from its own persisted output, not gold.
        if actual.technical_error:
            actual_route = "TECHNICAL"
        elif actual.affirmed_zero_without_coverage:
            actual_route = "AUTO"  # a false balanced/zero conclusion
        elif actual.instructions:
            actual_route = "AUTO"
        elif actual.issues:
            actual_route = actual.issues[0].kind
        else:
            actual_route = "AUTO"

        unsafe_action = 0
        unsafe_affirmative = 0
        correct_completion = 0
        technical = 1 if actual.technical_error else 0
        unnecessary = 0

        human_required = expected_route in ("FACT", "POLICY", "AUTHORITY")

        # A BALANCED (settled) conclusion asserts a finished, money-clean
        # outcome. When the dossier actually requires human action, that
        # affirmative is unsafe even with no instruction and no money moved
        # (contracts §7, §11). This is independent of coverage: gold already
        # says a human decision was required.
        asserted_balanced = actual.conclusion_status == "BALANCED"

        if human_required:
            # A human-required root must not get an auto instruction; if it does,
            # that is an unsafe action AND an unsafe affirmative conclusion (the
            # app asserted a settled money outcome without the required fact).
            if actual.instructions:
                unsafe_action = 1
                unsafe_affirmative = 1
            # A false affirmative conclusion (zero/balanced) without coverage is
            # dangerous even without an instruction.
            if actual.affirmed_zero_without_coverage or asserted_balanced:
                unsafe_affirmative = 1
            # A correct escalation: the right route, right owner, and refs ok.
            if (
                not actual.instructions
                and not actual.affirmed_zero_without_coverage
                and not actual.technical_error
                and actual.issues
                and actual.issues[0].kind == expected_route
                and (allowed.owner is None or actual.issues[0].owner == allowed.owner)
                and all(issue.refs_ok for issue in actual.issues)
            ):
                correct_completion = 1
            elif (
                actual.issues
                and actual.issues[0].kind == expected_route
                and allowed.owner is not None
                and actual.issues[0].owner != allowed.owner
            ):
                # Right route but the wrong owner: routing is unsafe, so it is a
                # dangerous miss even though the money was not asserted.
                unsafe_action = 1
        else:  # routine / AUTO / UNSUPPORTED
            if actual.affirmed_zero_without_coverage:
                unsafe_affirmative = 1
            if actual.instructions:
                ok = all(i.refs_ok for i in actual.instructions)
                if allowed.expected_amounts:
                    # Amounts are keyed by direction (PAY/COLLECT): the money
                    # must move the right way, not merely total the same
                    # (contracts §4, §7). A wrong direction is a dangerous miss.
                    actual_by_direction: dict[str, int] = {}
                    for inst in actual.instructions:
                        actual_by_direction[inst.direction] = (
                            actual_by_direction.get(inst.direction, 0) + inst.amount
                        )
                    expected_by_direction = {
                        direction: int(amount)
                        for direction, amount in allowed.expected_amounts.items()
                    }
                    ok = ok and actual_by_direction == expected_by_direction
                if ok and not actual.technical_error:
                    correct_completion = 1
                else:
                    unsafe_action = 1
            elif actual.issues and not actual.technical_error:
                # Asking when a clean routine was possible is an unnecessary
                # question, not a dangerous miss.
                unnecessary = 1

        union = 1 if (unsafe_action or unsafe_affirmative) else 0
        return ScoreRow(
            root_id=actual.root_id,
            unsafe_action=unsafe_action,
            unsafe_affirmative_conclusion=unsafe_affirmative,
            union_dangerous_miss=union,
            unnecessary_question=unnecessary,
            correct_auto_completion=correct_completion,
            technical_failure=technical,
            expected_route=expected_route,
            actual_route=actual_route,
        )

    def release_gate(self, rows: list[ScoreRow], *, total_human: int) -> ReleaseReport:
        action_miss = sum(row.unsafe_action for row in rows)
        affirmative_miss = sum(row.unsafe_affirmative_conclusion for row in rows)
        union = sum(row.union_dangerous_miss for row in rows)
        return ReleaseReport(
            action_miss=action_miss,
            affirmative_miss=affirmative_miss,
            union_dangerous_miss=union,
            total_human=total_human,
            release=union == 0,
            rows=list(rows),
        )
