"""A4 admitted finance/policy tests (plan A4; contracts §3–§5).

The Reconciler must honor the admission result: unresolved material conditions
suppress any effect, an incomplete expense set keeps T/E/S UNKNOWN (never
sum(empty)=0), per-expense paid basis survives into the conclusion, and the
boundaries (E 8m, abs(S) 4m, approver 20m) gate the effect exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import Expense, ExpensePayment, PaymentBasisView
from invoice_referee.domain.issues import BusinessIssue
from invoice_referee.reconciliation.finance import project_finance
from invoice_referee.reconciliation.service import Reconciler

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref() -> EvidenceRef:
    return EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x")


def _scope() -> CaseScope:
    return CaseScope(tenant="t", employee="employee:a", activity="activity:1", profile="TRAVEL")


def _read_set() -> ReadSet:
    return ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0)


def _expense(amount: int, *, paid: int | None = None, basis: str = "EMPLOYEE_DECLARATION_Q32",
             eligibility: str = "ELIGIBLE") -> Expense:
    payments = ()
    if paid is not None:
        payments = (
            ExpensePayment(
                external_key="q32:1", payer="employee:a", payee="vendor:1", amount=paid,
                expense_id="expense:1", received_state="CLEAR", refs=(_ref(),),
                basis_kind=basis, responsible_actor="employee:a",  # type: ignore[arg-type]
            ),
        )
    return Expense(
        id="expense:1", economic_key="invoice:x:IR1", activity="activity:1",
        incurred=Fact[int](key="expense:1:incurred", value=amount, state="KNOWN", refs=(_ref(),)),
        incurred_at=AS_OF, payments=payments, eligibility=eligibility, refs=(_ref(),),  # type: ignore[arg-type]
    )


def _input(expenses, *, complete=True, ledger=(), coverage=None, budget=None, grants=()):
    from invoice_referee.domain.policy import BudgetDecision, Grant

    return AssessmentInput(
        scope=_scope(), expense_facts=tuple(expenses), read_set=_read_set(), as_of=AS_OF,
        ledger=tuple(ledger), coverage=coverage, budget=tuple(budget or ()), grants=tuple(grants or ()),
        expense_set_complete=complete,
    )


# --- incomplete set trap ----------------------------------------------------


def test_incomplete_expense_set_keeps_t_and_e_unknown() -> None:
    proj = project_finance(_scope(), (), (), None, expense_set_complete=False)
    assert proj.T.state == "UNKNOWN"
    assert proj.E.state == "UNKNOWN"
    assert proj.S.state == "UNKNOWN"


def test_empty_set_with_legacy_complete_true_is_known_zero() -> None:
    # STUB/legacy builders set complete=True explicitly; only then is sum(empty)=0.
    proj = project_finance(_scope(), (), (), None, expense_set_complete=True)
    assert proj.T.state == "KNOWN"
    assert proj.T.value == 0


# --- basis survives into the conclusion ------------------------------------


def test_payment_basis_survives_into_result() -> None:
    inp = _input([_expense(3_240_000, paid=3_240_000)])
    result = Reconciler().assess(inp)
    assert result.payment_basis
    assert result.payment_basis[0].kind == "EMPLOYEE_DECLARATION_Q32"
    assert result.payment_basis[0].actor == "employee:a"


def test_unspecified_legacy_basis_is_not_reported_as_verified() -> None:
    inp = _input([_expense(3_240_000, paid=3_240_000, basis="UNSPECIFIED_LEGACY")])
    result = Reconciler().assess(inp)
    kinds = {v.kind for v in result.payment_basis}
    assert "EMPLOYEE_DECLARATION_Q32" not in kinds


# --- admission issues suppress effects -------------------------------------


def test_admission_issue_suppresses_allowed_effect() -> None:
    inp = _input([_expense(3_240_000, paid=3_240_000)]).model_copy(
        update={
            "admission_issues": (
                BusinessIssue(
                    id="issue:fact:x", kind="FACT", field_or_rule="expense:1:paid_basis",
                    owner="employee", basis="b", question="q",
                ),
            )
        }
    )
    result = Reconciler().assess(inp)
    assert result.allowed_effect is None


# --- boundaries -------------------------------------------------------------


def _pilot_grants(issue_max: int = 4_000_000, recognize_max: int = 8_000_000):
    from invoice_referee.domain.policy import Grant

    def _grant(gid, actions, maximum):
        return Grant(
            id=gid, version="v1", actor="system:referee", actions=actions,
            scope="activity:1", max_amount=maximum,
            effective_from=datetime(2026, 10, 1, tzinfo=UTC),
            effective_to=datetime(2026, 12, 31, tzinfo=UTC),
            allowed_profiles=("TRAVEL",),
        )

    return (
        _grant("grant:recognize", ("RECOGNIZE_COST",), recognize_max),
        _grant("grant:issue", ("ISSUE_PAYMENT", "ISSUE_COLLECTION"), issue_max),
    )


def test_e_at_recognize_limit_is_allowed() -> None:
    inp = _input([_expense(8_000_000, paid=8_000_000)], grants=_pilot_grants())
    result = Reconciler().assess(inp)
    assert not any(i.field_or_rule == "RECOGNIZE_COST" for i in result.issues)


def test_e_over_recognize_limit_needs_authority() -> None:
    inp = _input([_expense(8_000_001, paid=8_000_001)], grants=_pilot_grants())
    result = Reconciler().assess(inp)
    assert any(i.field_or_rule == "RECOGNIZE_COST" for i in result.issues)
    assert result.allowed_effect is None


def _budget():
    from invoice_referee.domain.policy import BudgetDecision

    return (
        BudgetDecision(
            id="budget:1", activity="activity:1", amount=20_000_000,
            effect_range=(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC)),
            actor="employee:approver",
        ),
    )


def test_abs_s_at_issue_limit_is_allowed() -> None:
    # E=4m, A=0 -> S=4m; the system issue grant is exactly 4m.
    from invoice_referee.domain.finance import CoverageRecord

    coverage = CoverageRecord(
        scope="activity:1", start=datetime(2026, 9, 1, tzinfo=UTC), as_of=AS_OF,
        funds=("company:bank",), flow_kinds=("ADVANCE_RECEIVED",),
    )
    inp = _input(
        [_expense(4_000_000, paid=4_000_000)], coverage=coverage,
        budget=_budget(), grants=_pilot_grants(),
    )
    result = Reconciler().assess(inp)
    assert result.allowed_effect is not None
    assert result.allowed_effect.direction == "PAY"
    assert result.allowed_effect.amount == 4_000_000


def test_abs_s_over_issue_limit_needs_authority() -> None:
    from invoice_referee.domain.finance import CoverageRecord

    coverage = CoverageRecord(
        scope="activity:1", start=datetime(2026, 9, 1, tzinfo=UTC), as_of=AS_OF,
        funds=("company:bank",), flow_kinds=("ADVANCE_RECEIVED",),
    )
    inp = _input(
        [_expense(4_000_001, paid=4_000_001)], coverage=coverage,
        budget=_budget(), grants=_pilot_grants(),
    )
    result = Reconciler().assess(inp)
    assert result.allowed_effect is None
    assert any(i.field_or_rule == "ISSUE_PAYMENT" for i in result.issues)
