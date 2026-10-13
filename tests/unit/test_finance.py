"""Finance projection: T/E/C/A/P/R/S/unpaid from verified literals (contracts §3–§4, §10.2).

Every figure is a Fact: an unestablished zero stays UNKNOWN, never a fabricated
0. T is the incurred cost (not clipped to B); E the eligible employee-paid
portion; C the company-direct portion; S = E - A - P + R. unpaid comes from
verified outstanding against gross paid, not T - E - C.
"""

from __future__ import annotations

from invoice_referee.reconciliation.finance import project_finance
from tests.factories import (
    COMPANY,
    EMPLOYEE,
    coverage,
    expense,
    money_event,
    payment,
    scope,
)


def _project(expenses, ledger=(), cov=coverage()):
    return project_finance(scope(), expenses, tuple(ledger), cov)


def test_projection_derives_T_E_C_A_P_R_S() -> None:
    expenses = (
        expense(
            "expense:1",
            10_000_000,
            payments=(
                payment("p:emp", EMPLOYEE, "vendor:demo", 5_000_000),
                payment("p:co", COMPANY, "vendor:demo", 3_000_000),
            ),
        ),
    )
    ledger = (
        money_event("adv:1", "ADVANCE_RECEIVED", 2_000_000, payer=COMPANY, payee=EMPLOYEE),
        money_event("ret:1", "EMPLOYEE_RETURN", 500_000, payer=EMPLOYEE, payee=COMPANY),
    )
    p = _project(expenses, ledger)
    assert p.T.value == 10_000_000
    assert p.E.value == 5_000_000
    assert p.C.value == 3_000_000
    assert p.A.value == 2_000_000
    assert p.R.value == 500_000
    assert p.S.value == 5_000_000 - 2_000_000 - 0 + 500_000


def test_missing_coverage_leaves_advances_unknown() -> None:
    p = _project((expense("expense:1", 10_000_000),), cov=None)
    assert p.A.state == "UNKNOWN"
    assert p.P.state == "UNKNOWN"
    assert p.R.state == "UNKNOWN"
    assert p.T.value == 10_000_000


def test_paid_ineligible_is_not_unpaid() -> None:
    # T10 / employee paid 7m gross (5m eligible + 2m ineligible) / company 3m
    # => unpaid 0, because unpaid is T minus GROSS paid (7+3), not T - E - C.
    expenses = (
        expense(
            "expense:1",
            5_000_000,
            payments=(payment("p:emp-eligible", EMPLOYEE, "vendor:demo", 5_000_000),),
        ),
        expense(
            "expense:2",
            2_000_000,
            eligibility="INELIGIBLE",
            payments=(payment("p:emp-ineligible", EMPLOYEE, "vendor:demo", 2_000_000),),
        ),
        expense(
            "expense:3",
            3_000_000,
            payments=(payment("p:co", COMPANY, "vendor:demo", 3_000_000),),
        ),
    )
    p = _project(expenses)
    assert p.T.value == 10_000_000
    assert p.E.value == 5_000_000
    assert p.C.value == 3_000_000
    assert p.unpaid.value == 0


def test_business_incurred_excluded_from_E_stays_in_T() -> None:
    # A cost excluded from E (ineligible) still counts toward T (§10.2).
    expenses = (
        expense(
            "expense:1",
            8_000_000,
            payments=(payment("p:1", EMPLOYEE, "vendor:demo", 8_000_000),),
        ),
        expense(
            "expense:2",
            2_000_000,
            eligibility="INELIGIBLE",
            payments=(payment("p:2", EMPLOYEE, "vendor:demo", 2_000_000),),
        ),
    )
    p = _project(expenses)
    assert p.T.value == 10_000_000
    assert p.E.value == 8_000_000


def test_unknown_incurred_is_not_a_zero() -> None:
    p = _project((expense("expense:1", None),))
    assert p.T.state == "UNKNOWN"


def test_unpaid_unknown_when_incurred_unknown() -> None:
    p = _project((expense("expense:1", None),))
    assert p.unpaid.state == "UNKNOWN"
