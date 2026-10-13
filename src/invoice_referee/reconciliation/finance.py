"""Pure projection of T/E/C/A/P/R/S/unpaid (contracts §3–§4, §10.2).

No persistence, no I/O. Every figure is a Fact: an unestablished value stays
UNKNOWN rather than defaulting to zero. T is the incurred cost and is never
clipped to B; E is the eligible employee-paid portion; C the company-direct
portion; S = E - A - P + R. unpaid is verified outstanding against gross paid
(T minus every payment portion), not T - E - C.
"""

from __future__ import annotations

from invoice_referee.domain.case import CaseScope
from invoice_referee.domain.common import Fact, SignedVnd, Vnd
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    MoneyEvent,
    Projection,
)

_MONEY_KINDS = {
    "A": ("ADVANCE_RECEIVED",),
    "P": ("REIMBURSEMENT_RECEIVED",),
    "R": ("EMPLOYEE_RETURN",),
}


def _known(key: str, value: int) -> Fact[int]:
    return Fact[int](key=key, value=value, state="KNOWN")


def _unknown(key: str) -> Fact[int]:
    return Fact[int](key=key, state="UNKNOWN")


def _sum_ledger(ledger: tuple[MoneyEvent, ...], kinds: tuple[str, ...]) -> int:
    return sum(event.amount for event in ledger if event.kind in kinds)


def project_finance(
    scope: CaseScope,
    expenses: tuple[Expense, ...],
    ledger: tuple[MoneyEvent, ...],
    coverage: CoverageRecord | None,
) -> Projection:
    # T: total verified incurred cost; UNKNOWN if any expense cost is unresolved.
    t_unknown = any(expense.incurred.state != "KNOWN" for expense in expenses)
    T: Fact[Vnd] = (
        _unknown("projection:T")
        if t_unknown
        else _known("projection:T", sum(int(expense.incurred.value or 0) for expense in expenses))
    )

    # E: eligible employee-paid portions. C: company-direct portions.
    e_unknown = any(expense.eligibility == "UNKNOWN" for expense in expenses)
    eligible_paid = 0
    company_direct = 0
    gross_paid = 0
    for expense in expenses:
        for portion in expense.payments:
            gross_paid += portion.amount
            if portion.payer == scope.employee:
                if expense.eligibility == "ELIGIBLE":
                    eligible_paid += portion.amount
            else:
                company_direct += portion.amount
    E: Fact[Vnd] = _unknown("projection:E") if e_unknown else _known("projection:E", eligible_paid)
    C: Fact[Vnd] = _unknown("projection:C") if e_unknown else _known("projection:C", company_direct)

    # A/P/R come from the scoped ledger; without coverage they are UNKNOWN, not 0.
    if coverage is None:
        A: Fact[Vnd] = _unknown("projection:A")
        P: Fact[Vnd] = _unknown("projection:P")
        R: Fact[Vnd] = _unknown("projection:R")
    else:
        A = _known("projection:A", _sum_ledger(ledger, _MONEY_KINDS["A"]))
        P = _known("projection:P", _sum_ledger(ledger, _MONEY_KINDS["P"]))
        R = _known("projection:R", _sum_ledger(ledger, _MONEY_KINDS["R"]))

    # unpaid: verified outstanding against gross paid (never T - E - C).
    if T.state != "KNOWN":
        unpaid: Fact[Vnd] = _unknown("projection:unpaid")
    else:
        unpaid = _known("projection:unpaid", max(int(T.value or 0) - gross_paid, 0))

    if E.state == "KNOWN" and A.state == "KNOWN" and P.state == "KNOWN" and R.state == "KNOWN":
        S: Fact[SignedVnd] = Fact[SignedVnd](
            key="projection:S",
            value=int(E.value or 0) - int(A.value or 0) - int(P.value or 0) + int(R.value or 0),
            state="KNOWN",
        )
    else:
        S = Fact[SignedVnd](key="projection:S", state="UNKNOWN")

    return Projection(T=T, E=E, C=C, A=A, P=P, R=R, unpaid=unpaid, S=S)
