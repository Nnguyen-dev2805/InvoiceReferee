"""T3: per-item category caps, submission window, personal exclusion.

Imported Hoangha rules (user-approved): work/client meal <=5,000,000 VND per
canonical expense; taxi/ride <=2,000,000 VND per canonical expense; submission
within 30 calendar days of the established expense date; personal expense is not
recognized as business expense. A category with no explicit cap still passes the
ordinary gates — it is never an implicit unlimited PASS. A missing source date is
a FACT, never substituted by the submit date.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import Expense
from invoice_referee.domain.policy import CategoryPolicy
from invoice_referee.reconciliation.category import evaluate_categories

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref() -> EvidenceRef:
    return EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x")


def _expense(amount: int, *, category: str | None, source_date: datetime | None) -> Expense:
    return Expense(
        id="expense:1", economic_key="invoice:x:1", activity="activity:1",
        incurred=Fact[int](key="expense:1:incurred", value=amount, state="KNOWN", refs=(_ref(),)),
        incurred_at=AS_OF, payments=(), eligibility="ELIGIBLE", refs=(_ref(),),
        category=category, source_date=source_date,
    )


def _policy(**over: object) -> CategoryPolicy:
    base = dict(
        id="cat:1", version="v1", effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        per_item_caps={"WORK_CLIENT_MEAL": 5_000_000, "TAXI": 2_000_000},
        submission_window_days=30,
        excluded_categories=("PERSONAL",),
    )
    base.update(over)
    return CategoryPolicy(**base)  # type: ignore[arg-type]


def _input(expenses, policy) -> AssessmentInput:
    return AssessmentInput(
        scope=CaseScope(tenant="t", employee="employee:a", activity="activity:1", profile="WORK_EXPENSE"),
        expense_facts=tuple(expenses), read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF, category_policy=(policy,),
    )


def _evaluate(expenses, policy=None):
    inp = _input(expenses, policy or _policy())
    return evaluate_categories(inp, as_of=AS_OF)


def test_meal_at_cap_passes() -> None:
    issues = _evaluate((_expense(5_000_000, category="WORK_CLIENT_MEAL", source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    assert not any(i.field_or_rule == "category:WORK_CLIENT_MEAL" for i in issues)


def test_meal_over_cap_is_policy() -> None:
    issues = _evaluate((_expense(5_000_001, category="WORK_CLIENT_MEAL", source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    issue = next((i for i in issues if i.field_or_rule == "category:WORK_CLIENT_MEAL"), None)
    assert issue is not None and issue.kind == "POLICY"


def test_taxi_over_2m_is_policy() -> None:
    issues = _evaluate((_expense(2_200_000, category="TAXI", source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    assert any(i.field_or_rule == "category:TAXI" and i.kind == "POLICY" for i in issues)


def test_category_without_cap_passes_amount_rule() -> None:
    # OFFICE_PURCHASE has no separate cap: no category POLICY issue at 7.5m.
    issues = _evaluate((_expense(7_500_000, category="OFFICE_PURCHASE", source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    assert not any(i.field_or_rule.startswith("category:") for i in issues)


def test_late_submission_is_policy() -> None:
    # Established date 31 days before as_of (10/10) -> 09/09 -> 31 days.
    issues = _evaluate((_expense(1_000_000, category="WORK_CLIENT_MEAL", source_date=datetime(2026, 9, 9, tzinfo=UTC)),))
    assert any(i.field_or_rule == "expense:deadline" and i.kind == "POLICY" for i in issues)


def test_within_window_passes() -> None:
    issues = _evaluate((_expense(1_000_000, category="WORK_CLIENT_MEAL", source_date=datetime(2026, 9, 20, tzinfo=UTC)),))
    assert not any(i.field_or_rule == "expense:deadline" for i in issues)


def test_missing_source_date_is_fact() -> None:
    issues = _evaluate((_expense(1_000_000, category="WORK_CLIENT_MEAL", source_date=None),))
    assert any(i.field_or_rule == "expense:source_date" and i.kind == "FACT" for i in issues)


def test_personal_category_is_excluded() -> None:
    issues = _evaluate((_expense(1_000_000, category="PERSONAL", source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    assert any(i.field_or_rule == "category:PERSONAL" for i in issues)


def test_unknown_category_is_fact() -> None:
    issues = _evaluate((_expense(1_000_000, category=None, source_date=datetime(2026, 10, 1, tzinfo=UTC)),))
    assert any(i.field_or_rule == "expense:category" and i.kind == "FACT" for i in issues)
