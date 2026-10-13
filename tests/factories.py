"""Unit-only test factories (contracts §9).

These build literal, already-verified domain objects directly. They never
simulate OCR quality, never call the Reconciler, and never appear in the
application runtime or the live evaluation path.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from invoice_referee.domain.case import (
    AssessmentInput,
    CaseScope,
    ReadSet,
)
from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    ExpensePayment,
    MoneyEvent,
    MoneyKind,
)
from invoice_referee.domain.policy import BudgetDecision, Grant, PolicyVersion

TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
APPROVER = "employee:approver"
COMPANY = "company:demo"
VENDOR = "vendor:demo"
ACTIVITY = "activity:travel-a"
PROFILE = "TRAVEL"

DEFAULT_AS_OF = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)

ALL_MONEY_KINDS: tuple[MoneyKind, ...] = (
    "ADVANCE_RECEIVED",
    "REIMBURSEMENT_RECEIVED",
    "EMPLOYEE_RETURN",
    "REVERSAL",
    "OBSERVED_UNALLOCATED",
)


def digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def ref(seed: str, *, page: int = 1, quote: str = "literal evidence") -> EvidenceRef:
    return EvidenceRef(
        source_id=f"source:{seed}",
        source_sha256=digest(seed),
        page=page,
        exact_quote=quote,
    )


def known(key: str, value: int, seed: str = "seed") -> Fact[int]:
    return Fact[int](key=key, value=value, state="KNOWN", refs=(ref(seed),))


def unknown(key: str, seed: str = "seed") -> Fact[int]:
    return Fact[int](key=key, state="UNKNOWN", refs=(ref(seed),))


def money_event(
    event_id: str,
    kind: MoneyKind,
    amount: int,
    *,
    payer: str,
    payee: str,
    as_of: datetime = DEFAULT_AS_OF,
    scope: str = ACTIVITY,
) -> MoneyEvent:
    return MoneyEvent(
        id=event_id,
        external_key=f"external:{event_id}",
        kind=kind,
        scope=scope,
        payer=payer,
        payee=payee,
        amount=amount,
        event_at=as_of,
        recorded_at=as_of,
        verification_state="CONFIRMED",
        allocation_state="ALLOCATED",
        refs=(ref(event_id),),
    )


def default_grants() -> tuple[Grant, ...]:
    """The committed demo fixture (contracts §5): system 8/4, approver 20."""
    start = DEFAULT_AS_OF - timedelta(days=1)
    return (
        Grant(
            id="grant:system:recognize",
            version="v1",
            actor="system:referee",
            actions=("RECOGNIZE_COST",),
            scope=ACTIVITY,
            max_amount=8_000_000,
            effective_from=start,
        ),
        Grant(
            id="grant:system:issue",
            version="v1",
            actor="system:referee",
            actions=("ISSUE_PAYMENT", "ISSUE_COLLECTION"),
            scope=ACTIVITY,
            max_amount=4_000_000,
            effective_from=start,
        ),
        Grant(
            id="grant:approver:20m",
            version="v1",
            actor=APPROVER,
            actions=(
                "AUTHORIZE_ACTIVITY",
                "SET_BUDGET",
                "RECOGNIZE_COST",
                "EXCEPT_POLICY",
                "ISSUE_PAYMENT",
                "ISSUE_COLLECTION",
                "OVERRIDE",
            ),
            scope=ACTIVITY,
            max_amount=20_000_000,
            effective_from=start,
        ),
    )


def snapshot(
    T: int,
    E: int,
    C: int,
    A: int,
    P: int,
    R: int,
    B: int,
    coverage: bool = True,
    **overrides: object,
) -> AssessmentInput:
    """Build an AssessmentInput from literal figures (contracts §9).

    T is the verified incurred cost; E the eligible employee-paid portion and
    C the company-direct portion are carried as verified payment portions on
    the expense. A, P and R arrive as confirmed ledger events. When coverage
    is False, no zero figure is asserted: the amounts stay UNKNOWN so a caller
    cannot read an unestablished zero as a settled one.
    """
    scope = CaseScope(
        tenant=TENANT,
        employee=EMPLOYEE,
        activity=ACTIVITY,
        profile=PROFILE,
    )
    established = coverage or T > 0

    payments: list[ExpensePayment] = []
    if E > 0:
        payments.append(
            ExpensePayment(
                external_key="payment:employee",
                payer=EMPLOYEE,
                payee=VENDOR,
                amount=E,
                expense_id="expense:1",
                received_state="CLEAR",
                refs=(ref("payment-employee"),),
            )
        )
    if C > 0:
        payments.append(
            ExpensePayment(
                external_key="payment:company",
                payer=COMPANY,
                payee=VENDOR,
                amount=C,
                expense_id="expense:1",
                received_state="CLEAR",
                refs=(ref("payment-company"),),
            )
        )

    expense = Expense(
        id="expense:1",
        economic_key="invoice:demo:1",
        activity=ACTIVITY,
        incurred=(
            known("expense:1:incurred", T, "expense-1")
            if established
            else unknown("expense:1:incurred", "expense-1")
        ),
        incurred_at=DEFAULT_AS_OF - timedelta(days=2),
        payments=tuple(payments),
        eligibility="ELIGIBLE" if E > 0 else "INELIGIBLE",
        refs=(ref("expense-1"),),
    )

    ledger: list[MoneyEvent] = []
    if A > 0:
        ledger.append(
            money_event(
                "advance:1",
                "ADVANCE_RECEIVED",
                A,
                payer=COMPANY,
                payee=EMPLOYEE,
            )
        )
    if P > 0:
        ledger.append(
            money_event(
                "reimbursement:1",
                "REIMBURSEMENT_RECEIVED",
                P,
                payer=COMPANY,
                payee=EMPLOYEE,
            )
        )
    if R > 0:
        ledger.append(
            money_event(
                "return:1",
                "EMPLOYEE_RETURN",
                R,
                payer=EMPLOYEE,
                payee=COMPANY,
            )
        )

    coverage_record = (
        CoverageRecord(
            scope=ACTIVITY,
            start=DEFAULT_AS_OF - timedelta(days=30),
            as_of=DEFAULT_AS_OF,
            funds=(COMPANY,),
            flow_kinds=ALL_MONEY_KINDS,
            opening_balance=known("ledger:opening", 0, "ledger-opening"),
            ledger_version="ledger:v1",
            witness_refs=(ref("ledger-witness"),),
        )
        if coverage
        else None
    )

    fields: dict[str, object] = {
        "scope": scope,
        "expense_facts": (expense,),
        "observations": (),
        "relations": (),
        "confirmations": (),
        "ledger": tuple(ledger),
        "coverage": coverage_record,
        "policy": (
            PolicyVersion(
                id="policy:v1",
                version="v1",
                effective_from=DEFAULT_AS_OF - timedelta(days=60),
                profile=PROFILE,
                rules=("TRAVEL_CORE", "INVOICE_REQUIRED"),
            ),
        ),
        "grants": default_grants(),
        "budget": (
            BudgetDecision(
                id="budget:1",
                activity=ACTIVITY,
                amount=B,
                effect_range=(DEFAULT_AS_OF - timedelta(days=30), None),
                actor=APPROVER,
                grant_ref="grant:approver:20m",
                refs=(ref("budget-1"),),
            ),
        ),
        "exceptions": (),
        "previous_eligibility": None,
        "read_set": ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=1,
        ),
        "as_of": DEFAULT_AS_OF,
    }
    fields.update(overrides)
    return AssessmentInput(**fields)
