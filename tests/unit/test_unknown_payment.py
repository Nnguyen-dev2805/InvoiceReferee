"""Unknown payment state must not become a verified unpaid amount (contracts §3–§4).

Missing evidence of payment does not prove a supplier debt. `unpaid` is KNOWN
only when the basis establishes both what was paid and what is still owed;
otherwise it stays UNKNOWN. Payment status is its own axis — it is never
inferred from eligibility.
"""

from __future__ import annotations

from invoice_referee.reconciliation.finance import project_finance
from tests.factories import (
    EMPLOYEE,
    coverage,
    expense,
    payment,
    scope,
)


def _project(expenses, cov=coverage()):
    return project_finance(scope(), tuple(expenses), (), cov)


def test_unknown_payer_leaves_unpaid_unknown() -> None:
    # F01: a verified 3.24m cost with no admitted payment and an unknown payer
    # must not report a known 3.24m unpaid (missing evidence != paid 0).
    p = _project((expense("expense:1", 3_240_000, eligibility="UNKNOWN", payment_state="UNKNOWN"),))
    assert p.T.state == "KNOWN"
    assert p.T.value == 3_240_000
    assert p.unpaid.state == "UNKNOWN"


def test_verified_full_payment_leaves_unpaid_known_zero() -> None:
    p = _project(
        (
            expense(
                "expense:1", 3_240_000,
                payments=(payment("p:1", EMPLOYEE, "vendor:demo", 3_240_000),),
                payment_state="PAID",
            ),
        )
    )
    assert p.unpaid.state == "KNOWN"
    assert p.unpaid.value == 0


def test_verified_partial_payment_leaves_unpaid_correct() -> None:
    p = _project(
        (
            expense(
                "expense:1", 10_000_000,
                payments=(payment("p:1", EMPLOYEE, "vendor:demo", 6_000_000),),
                payment_state="PAID",
            ),
        )
    )
    assert p.unpaid.state == "KNOWN"
    assert p.unpaid.value == 4_000_000


def test_verified_unpaid_differs_from_missing_data() -> None:
    # A source that establishes "nothing paid yet" is a KNOWN unpaid; a missing
    # basis is UNKNOWN. The two must not collapse to the same figure.
    verified = _project((expense("expense:1", 3_240_000, payment_state="UNPAID"),))
    assert verified.unpaid.state == "KNOWN"
    assert verified.unpaid.value == 3_240_000
    unknown = _project((expense("expense:1", 3_240_000, payment_state="UNKNOWN"),))
    assert unknown.unpaid.state == "UNKNOWN"


def test_s_stays_unknown_without_enough_basis() -> None:
    p = _project((expense("expense:1", 3_240_000, eligibility="UNKNOWN", payment_state="UNKNOWN"),))
    assert p.S.state == "UNKNOWN"
