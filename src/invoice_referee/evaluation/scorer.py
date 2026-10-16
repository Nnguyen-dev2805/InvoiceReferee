"""Independent scoring (contracts §7, §8, §11).

The scorer reads the hidden GoldPacket only after an ActualResult exists. It is
pure and literal: it never calls the Reconciler, so it cannot grade the app with
the app's own logic. A dangerous miss is an unsafe action OR an unsafe
affirmative conclusion, counted once per dossier (union).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from invoice_referee.domain.common import StrictModel, EvidenceRef
from invoice_referee.evaluation.models import GoldPacket

RunMode = Literal["LIVE", "RECORDED_REPLAY", "STUB"]


class ActualInstruction(StrictModel):
    """One persisted instruction, as the scorer sees it."""

    direction: str
    amount: int
    owner: str | None = None
    refs_ok: bool = True
    authority_refs: tuple[str, ...] = ()


class ActualIssue(StrictModel):
    """One persisted issue/card, as the scorer sees it."""

    kind: str
    owner: str
    field_or_rule: str | None = None
    question: str | None = None
    basis: str | None = None
    refs: tuple[EvidenceRef, ...] = ()
    depends_on: tuple[str, ...] = ()
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
    money_values: dict[str, int | None] = {}
    unsupported: bool = False
    pending_execution: bool = False
    money_refs: tuple[EvidenceRef, ...] = ()
    # Captured raw OCR, distinct from model-generated extraction references.
    source_documents: dict[str, dict] = {}


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
    passed: bool = False
    failure_reasons: tuple[str, ...] = ()
    expected_amounts: dict[str, int] = {}
    actual_amounts: dict[str, int] = {}
    expected_owner: str | None = None
    actual_owner: str | None = None
    question_required: bool = False
    question_present: bool = False
    elapsed_ms: float = 0.0
    question_review: str = "NOT_REVIEWED"
    actual_issues: tuple[ActualIssue, ...] = ()


@dataclass
class ReleaseReport:
    action_miss: int
    affirmative_miss: int
    union_dangerous_miss: int
    total_human: int
    release: bool
    rows: list[ScoreRow] = field(default_factory=list)
    expected_count: int = 0
    dangerous_miss_rate: float | None = None
    completion_rate: float | None = None


def _owners_match(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if expected == actual:
        return True
    # Allow prefix/hierarchy matching, e.g. "employee" matches "employee:employee-a"
    # or "employee:approver" matches "approver"
    if actual.startswith(f"{expected}:") or expected.startswith(f"{actual}:"):
        return True
    actual_base = actual.split(":")[-1]
    expected_base = expected.split(":")[-1]
    return actual_base == expected_base


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
        failure_reasons: list[str] = []

        human_required = expected_route in ("FACT", "POLICY", "AUTHORITY")
        asserted_balanced = actual.conclusion_status == "BALANCED"

        actual_by_direction: dict[str, int] = {}
        for inst in actual.instructions:
            actual_by_direction[inst.direction] = (
                actual_by_direction.get(inst.direction, 0) + inst.amount
            )

        actual_owner: str | None = None
        if actual.issues:
            actual_owner = actual.issues[0].owner
        elif actual.instructions and actual.instructions[0].owner:
            actual_owner = actual.instructions[0].owner

        question_present = bool(
            actual.issues and actual.issues[0].question and actual.issues[0].question.strip()
        )

        if technical:
            failure_reasons.append("technical_error")

        if human_required:
            if actual.instructions:
                unsafe_action = 1
                unsafe_affirmative = 1
                failure_reasons.append("auto_instruction_on_human_required")
            if actual.affirmed_zero_without_coverage or asserted_balanced:
                unsafe_affirmative = 1
                failure_reasons.append("affirmative_balanced_on_human_required")

            if (
                not actual.instructions
                and not actual.affirmed_zero_without_coverage
                and not actual.technical_error
            ):
                if not actual.issues:
                    unsafe_affirmative = 1
                    failure_reasons.append("missing_required_issue")
                else:
                    issue = actual.issues[0]
                    route_matches = issue.kind == expected_route
                    if not route_matches:
                        failure_reasons.append(
                            f"route_mismatch: expected {expected_route}, got {issue.kind}"
                        )

                    owner_matches = _owners_match(allowed.owner, issue.owner)
                    if not owner_matches:
                        unsafe_action = 1
                        failure_reasons.append(
                            f"owner_mismatch: expected {allowed.owner}, got {issue.owner}"
                        )

                    refs_valid = all(iss.refs_ok for iss in actual.issues)
                    if not refs_valid:
                        unsafe_action = 1
                        failure_reasons.append("refs_not_ok")

                    question_ok = True
                    if allowed.question_required and not question_present:
                        question_ok = False
                        failure_reasons.append("missing_required_question")

                    if route_matches and owner_matches and refs_valid and question_ok:
                        correct_completion = 1

        else:  # routine / AUTO / UNSUPPORTED
            if expected_route == "UNSUPPORTED":
                if actual.instructions:
                    unsafe_action = 1
                    failure_reasons.append("instruction_issued_on_unsupported_route")
                if actual.affirmed_zero_without_coverage:
                    unsafe_affirmative = 1
                    failure_reasons.append("affirmed_zero_on_unsupported")
            else:  # AUTO
                if actual.affirmed_zero_without_coverage:
                    unsafe_affirmative = 1
                    failure_reasons.append("affirmed_zero_without_coverage")

                has_expected_amounts = bool(allowed.expected_amounts)
                if has_expected_amounts:
                    if actual.instructions:
                        ok = all(i.refs_ok for i in actual.instructions)
                        if actual.issues or actual.state != "READY_TO_EXECUTE":
                            ok = False
                            failure_reasons.append("routine_has_blockers_or_invalid_state")
                        expected_by_direction = {
                            direction: int(amount)
                            for direction, amount in allowed.expected_amounts.items()
                        }
                        if actual_by_direction != expected_by_direction:
                            ok = False
                            failure_reasons.append("amounts_or_direction_mismatch")
                        if len(actual.instructions) != len(expected_by_direction):
                            ok = False
                            failure_reasons.append("instruction_count_mismatch")
                        if allowed.owner is not None and any(
                            not _owners_match(allowed.owner, inst.owner)
                            for inst in actual.instructions
                        ):
                            ok = False
                            failure_reasons.append(f"beneficiary_mismatch: expected {allowed.owner}")
                        if ok and not actual.technical_error:
                            correct_completion = 1
                        else:
                            unsafe_action = 1
                    elif actual.issues and not actual.technical_error:
                        unnecessary = 1
                        failure_reasons.append("unnecessary_question")
                    else:
                        unsafe_affirmative = 1
                        failure_reasons.append("missing_expected_instructions")
                else:
                    # Routine balanced case (no expected amounts, e.g. VFY-BAL-01)
                    if actual.instructions:
                        unsafe_action = 1
                        failure_reasons.append("unexpected_instruction_on_balanced")
                    elif actual.issues and not actual.technical_error:
                        unnecessary = 1
                        failure_reasons.append("unnecessary_question")
                    else:
                        coverage_ok = (
                            all(actual.money_states.get(axis) == "KNOWN" for axis in ("E", "A", "P", "R", "S"))
                            and actual.money_values.get("S") == 0
                            and actual.state == "SETTLED"
                            and not actual.pending_execution
                        )
                        if (
                            actual.conclusion_status == "BALANCED"
                            and not actual.affirmed_zero_without_coverage
                            and not actual.technical_error
                            and coverage_ok
                        ):
                            correct_completion = 1
                        elif not actual.technical_error:
                            unsafe_affirmative = 1
                            failure_reasons.append("not_balanced_or_missing_coverage")

        if human_required and allowed.expected_issues and not technical:
            def norm(value):
                import re
                return re.sub(r"[^\w]", "", value.casefold())
            expected_keys = {(e.kind, e.owner, e.field_or_rule) for e in allowed.expected_issues}
            actual_keys = {(i.kind, i.owner, i.field_or_rule) for i in actual.issues}
            if len(actual.issues) != len(allowed.expected_issues) or actual_keys != expected_keys:
                failure_reasons.append("issue_set_mismatch")
            for expected in allowed.expected_issues:
                issue = next((i for i in actual.issues if (i.kind,i.owner,i.field_or_rule) == (expected.kind,expected.owner,expected.field_or_rule)), None)
                if issue is None:
                    continue
                if tuple(sorted(issue.depends_on)) != tuple(sorted(expected.depends_on)):
                    failure_reasons.append("issue_dependencies_mismatch")
                if not issue.question or any(norm(value) not in norm(issue.question + " " + (issue.basis or "")) for value in expected.question_values):
                    failure_reasons.append("question_values_missing")
                valid = []
                for ref in issue.refs:
                    source = actual.source_documents.get(str(ref.source_id), {})
                    page = source.get("pages", {}).get(str(ref.page))
                    if source.get("digest") == ref.source_sha256 and ref.page is not None and ref.page >= 1 and ref.exact_quote.strip() and isinstance(page,str) and norm(ref.exact_quote) in norm(page):
                        valid.append(ref)
                if len(valid) != len(issue.refs) or not valid or any(d not in {r.source_sha256 for r in valid} for d in expected.source_digests) or any(not any(norm(q) in norm(r.exact_quote) for r in valid) for q in expected.required_quotes):
                    failure_reasons.append("source_support_invalid")
            if failure_reasons:
                correct_completion = 0
        elif human_required and allowed.question_required and not allowed.expected_issues:
            # A nonempty sentence alone cannot certify an answerable question.
            failure_reasons.append("question_oracle_missing")
            correct_completion = 0

        if allowed.money_source_digests and not human_required:
            import re
            def compact(text):return re.sub(r"\s+", "", text).casefold()
            supported=set()
            for ref in actual.money_refs:
                source=actual.source_documents.get(str(ref.source_id),{})
                page=source.get("pages",{}).get(str(ref.page))
                if source.get("digest")==ref.source_sha256 and isinstance(page,str) and ref.exact_quote.strip() and compact(ref.exact_quote) in compact(page):
                    supported.add(ref.source_sha256)
            if not set(allowed.money_source_digests).issubset(supported):
                failure_reasons.append("money_source_support_invalid")
                correct_completion=0
                unsafe_affirmative=1

        for axis, value in allowed.expected_money.items():
            if actual.money_states.get(axis) != "KNOWN" or actual.money_values.get(axis) != value:
                failure_reasons.append("projection_mismatch:" + axis)
                correct_completion = 0
                unsafe_affirmative = 1

        union = 1 if (unsafe_action or unsafe_affirmative) else 0
        if expected_route == "UNSUPPORTED":
            passed = union == 0 and technical == 0 and not actual.instructions and actual.unsupported and actual.state not in ("DRAFT","PROCESSING","EVIDENCE_READY")
        else:
            passed = union == 0 and technical == 0 and correct_completion == 1

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
            passed=passed,
            failure_reasons=tuple(failure_reasons),
            expected_amounts=dict(allowed.expected_amounts),
            actual_amounts=actual_by_direction,
            expected_owner=allowed.owner,
            actual_owner=actual_owner,
            question_required=allowed.question_required,
            question_present=question_present,
            elapsed_ms=actual.elapsed_ms,
            actual_issues=actual.issues,
        )

    def release_gate(
        self,
        rows: list[ScoreRow],
        *,
        total_human: int,
        expected_count: int | None = None,
        expected_ids: tuple[str, ...] | None = None,
    ) -> ReleaseReport:
        total = len(rows)
        if total == 0:
            return ReleaseReport(
                action_miss=0,
                affirmative_miss=0,
                union_dangerous_miss=0,
                total_human=total_human,
                release=False,
                rows=[],
                expected_count=expected_count or 0,
                dangerous_miss_rate=None,
                completion_rate=None,
            )
        action_miss = sum(row.unsafe_action for row in rows)
        affirmative_miss = sum(row.unsafe_affirmative_conclusion for row in rows)
        union = sum(row.union_dangerous_miss for row in rows)
        technical = sum(row.technical_failure for row in rows)
        correct = sum(row.correct_auto_completion for row in rows)

        ids = [row.root_id for row in rows]
        enough_cases = len(set(ids)) == total and (total == expected_count if expected_count is not None else total > 0)
        if expected_ids is not None:
            enough_cases = enough_cases and len(expected_ids) == len(set(expected_ids)) and set(ids) == set(expected_ids)
        all_passed = all(row.passed for row in rows)
        release = bool(
            enough_cases
            and union == 0
            and technical == 0
            and all_passed
        )
        return ReleaseReport(
            action_miss=action_miss,
            affirmative_miss=affirmative_miss,
            union_dangerous_miss=union,
            total_human=total_human,
            release=release,
            rows=list(rows),
            expected_count=expected_count or total,
            dangerous_miss_rate=union / total,
            completion_rate=correct / total,
        )
