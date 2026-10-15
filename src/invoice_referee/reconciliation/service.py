"""Reconciler.assess(input) -> AssessmentResult (contracts §9, §10.2–§10.3).

Pure and synchronous: a function of the immutable AssessmentInput alone. It
projects money, evaluates policy/authority, and returns a proposal the
workflow re-checks before it commits anything.
"""

from __future__ import annotations

import hashlib
import json

from invoice_referee.domain.case import AssessmentInput, AssessmentResult
from invoice_referee.domain.finance import PaymentBasisView
from invoice_referee.reconciliation.finance import project_finance
from invoice_referee.reconciliation.category import evaluate_categories
from invoice_referee.reconciliation.policy import evaluate_policy


def _cost_basis(input: AssessmentInput) -> str:
    payload = {
        "expenses": [
            {
                "id": expense.id,
                "economic_key": expense.economic_key,
                "incurred": expense.incurred.value,
                "incurred_state": expense.incurred.state,
                "eligibility": expense.eligibility,
                "payments": sorted(
                    (p.payer, p.amount, p.expense_id) for p in expense.payments
                ),
            }
            for expense in input.expense_facts
        ],
        "activity": input.scope.activity,
        "profile": input.scope.profile,
        "activity_acceptances": sorted(
            (
                acceptance.advance_external_key,
                acceptance.actor,
                tuple((ref.source_id, ref.source_sha256, ref.page) for ref in acceptance.refs),
            )
            for acceptance in input.activity_acceptances
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _money_basis(input: AssessmentInput) -> str:
    payload = {
        "ledger": sorted(
            (event.id, event.kind, event.amount) for event in input.ledger
        ),
        "coverage": input.coverage.ledger_version if input.coverage else None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _economic_keys(input: AssessmentInput) -> tuple[str, ...]:
    """The distinct canonical identities of the admitted costs (§10.2).

    Each expense carries the identity of the document bound to it; the distinct
    set is persisted with the conclusion so the usage/anti-duplicate consumer
    keys on the same identity the evidence path admitted. A disputed/ref-less
    cost's `expense:<n>` marker is kept too (it is a real per-row identity), but
    an empty set stays empty (never a fabricated key).
    """
    seen: list[str] = []
    for expense in input.expense_facts:
        key = expense.economic_key
        if key and key not in seen:
            seen.append(key)
    return tuple(seen)


def _payment_basis(input: AssessmentInput) -> tuple[PaymentBasisView, ...]:
    """Per-expense paid basis from the admitted payments (plan A0/A4).

    Only an explicit non-legacy basis is reported: an UNSPECIFIED_LEGACY portion
    (a STUB/test compatibility record) is never presented as a verified basis.
    """
    views: list[PaymentBasisView] = []
    for expense in input.expense_facts:
        for portion in expense.payments:
            if portion.basis_kind == "UNSPECIFIED_LEGACY":
                continue
            views.append(
                PaymentBasisView(
                    expense_id=expense.id,
                    kind=portion.basis_kind,
                    actor=portion.responsible_actor,
                    refs=portion.refs,
                    rule_id="Q32" if portion.basis_kind == "EMPLOYEE_DECLARATION_Q32" else None,
                )
            )
    return tuple(views)


def _excepted_missing_evidence(input: AssessmentInput) -> set[str]:
    """Expense ids cleared by a scoped `expense:missing_required_evidence` exception.

    Only an EXCEPT_POLICY exception for the exact rule, in this activity, naming
    the expense, with a positive max effect, counts. A refusal (no matching
    exception) leaves the FACT/POLICY in place (T5).
    """
    cleared: set[str] = set()
    for exception in input.exceptions:
        if exception.rule_id != "expense:missing_required_evidence":
            continue
        if exception.activity != input.scope.activity:
            continue
        if "EXCEPT_POLICY" not in exception.actions:
            continue
        if exception.max_effect <= 0:
            continue
        cleared.update(str(e) for e in exception.expense_ids)
    return cleared


class Reconciler:
    """Pure projection + policy assessment over an immutable snapshot."""

    def assess(self, input: AssessmentInput) -> AssessmentResult:
        projection = project_finance(
            input.scope,
            input.expense_facts,
            input.ledger,
            input.coverage,
            expense_set_complete=input.expense_set_complete,
        )
        issues, authorizations, allowed_effect = evaluate_policy(input, projection)
        # Category/deadline/personal-exclusion decisions (T3) append to the same
        # outcome; the Reconciler remains the single financial owner.
        category_issues = evaluate_categories(input, as_of=input.as_of)
        # A scoped exception for `expense:missing_required_evidence` on an expense
        # clears that expense's missing-evidence FACT/POLICY (T5). The exception is
        # an EXCEPT_POLICY decision bound to the exact rule/expense/scope/effect.
        excepted = _excepted_missing_evidence(input)
        admission_issues = tuple(
            i for i in input.admission_issues
            if not (i.field_or_rule.startswith("expense:")
                    and i.field_or_rule.endswith(":missing_evidence")
                    and ":".join(i.field_or_rule.split(":")[:2]) in excepted)
        )
        # Admission issues/problems are material conditions the evidence layer
        # found; they suppress any affirmative effect/conclusion until resolved
        # (plan A4). They are merged with the policy issues, not a second engine.
        # Deduplicate by (kind, field_or_rule): the admission issue is kept when
        # both layers raise the same condition (it carries the concrete basis).
        merged: list = list(admission_issues)
        seen = {(i.kind, i.field_or_rule) for i in merged}
        for issue in (*issues, *category_issues):
            key = (issue.kind, issue.field_or_rule)
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)
        merged_issues = tuple(merged)
        # A category FACT/POLICY issue also suppresses the effect (it is a gate).
        if admission_issues or input.admission_problems or category_issues:
            allowed_effect = None
        return AssessmentResult(
            projection=projection,
            issues=merged_issues,
            problems=tuple(input.admission_problems),
            required_authorizations=authorizations,
            allowed_effect=allowed_effect,
            cost_basis=_cost_basis(input),
            money_basis=_money_basis(input),
            payment_basis=_payment_basis(input),
            economic_keys=_economic_keys(input),
        )
