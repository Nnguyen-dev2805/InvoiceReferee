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
        "budget": [
            (b.id, b.amount, b.effect_range[0].isoformat()) for b in input.budget
        ],
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
        # Admission issues/problems are material conditions the evidence layer
        # found; they suppress any affirmative effect/conclusion until resolved
        # (plan A4). They are merged with the policy issues, not a second engine.
        # Deduplicate by (kind, field_or_rule): the admission issue is kept when
        # both layers raise the same condition (it carries the concrete basis).
        merged: list = list(input.admission_issues)
        seen = {(i.kind, i.field_or_rule) for i in merged}
        for issue in issues:
            key = (issue.kind, issue.field_or_rule)
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)
        merged_issues = tuple(merged)
        if input.admission_issues or input.admission_problems:
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
        )
