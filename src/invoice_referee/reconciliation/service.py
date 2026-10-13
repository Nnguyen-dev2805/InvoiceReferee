"""Reconciler.assess(input) -> AssessmentResult (contracts §9, §10.2–§10.3).

Pure and synchronous: a function of the immutable AssessmentInput alone. It
projects money, evaluates policy/authority, and returns a proposal the
workflow re-checks before it commits anything.
"""

from __future__ import annotations

import hashlib
import json

from invoice_referee.domain.case import AssessmentInput, AssessmentResult
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


class Reconciler:
    """Pure projection + policy assessment over an immutable snapshot."""

    def assess(self, input: AssessmentInput) -> AssessmentResult:
        projection = project_finance(
            input.scope, input.expense_facts, input.ledger, input.coverage
        )
        issues, authorizations, allowed_effect = evaluate_policy(input, projection)
        return AssessmentResult(
            projection=projection,
            issues=issues,
            problems=(),
            required_authorizations=authorizations,
            allowed_effect=allowed_effect,
            cost_basis=_cost_basis(input),
            money_basis=_money_basis(input),
        )
