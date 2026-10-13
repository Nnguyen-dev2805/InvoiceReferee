"""Expenses, money events, coverage and the projection (contracts §2–§4).

T, E, C, A, P, R and unpaid are Facts: an unresolved figure stays UNKNOWN
rather than being defaulted to zero. S = E − A − P + R as a signed integer.
"""

from __future__ import annotations

from typing import Literal

from invoice_referee.domain.common import (
    EvidenceRef,
    Fact,
    Id,
    SignedVnd,
    StrictModel,
    UtcDatetime,
    Vnd,
)
from invoice_referee.domain.evidence import ReadState

ExpenseEligibility = Literal["ELIGIBLE", "INELIGIBLE", "UNKNOWN"]
MoneyKind = Literal[
    "ADVANCE_RECEIVED",
    "REIMBURSEMENT_RECEIVED",
    "EMPLOYEE_RETURN",
    "REVERSAL",
    "OBSERVED_UNALLOCATED",
]
VerificationState = Literal["OBSERVED", "CONFIRMED", "REJECTED"]
AllocationState = Literal["UNALLOCATED", "ALLOCATED", "UNKNOWN"]


class ExpensePayment(StrictModel):
    """A verified payment portion of one expense (payer/amount/binding)."""

    external_key: str
    payer: Id
    payee: Id
    amount: Vnd
    expense_id: Id
    received_state: ReadState
    refs: tuple[EvidenceRef, ...] = ()


class Expense(StrictModel):
    """A verified business cost. `incurred` is T, not the cash already moved."""

    id: Id
    economic_key: str
    activity: Id
    incurred: Fact[Vnd]
    incurred_at: UtcDatetime
    payments: tuple[ExpensePayment, ...] = ()
    eligibility: ExpenseEligibility
    refs: tuple[EvidenceRef, ...] = ()


class RecordMoneyInput(StrictModel):
    """A client's claim about money that moved. The server verifies it."""

    external_key: str
    claimed_kind: str
    claimed_scope: str
    payer: Id
    payee: Id
    amount: Vnd
    event_at: UtcDatetime
    completion_claim: str | None = None
    reverses_event_id: Id | None = None
    refs: tuple[EvidenceRef, ...] = ()
    reason: str


class MoneyEvent(StrictModel):
    """A recorded, verified money movement in this scope's ledger."""

    id: Id
    external_key: str
    kind: MoneyKind
    scope: str
    payer: Id
    payee: Id
    amount: Vnd
    event_at: UtcDatetime
    recorded_at: UtcDatetime
    verification_state: VerificationState
    allocation_state: AllocationState
    reverses_event_id: Id | None = None
    refs: tuple[EvidenceRef, ...] = ()


class CoverageRecord(StrictModel):
    """What history a negative claim rests on (contracts §3).

    A zero flow is only established when scope, time, funds, flow kinds and
    the opening balance are covered.
    """

    scope: str
    start: UtcDatetime
    as_of: UtcDatetime
    funds: tuple[Id, ...] = ()
    flow_kinds: tuple[MoneyKind, ...] = ()
    opening_balance: Fact[Vnd] | None = None
    ledger_version: str | None = None
    witness_refs: tuple[EvidenceRef, ...] = ()


class Projection(StrictModel):
    """The settled arithmetic. Every figure is a Fact, never a bare number."""

    T: Fact[Vnd]
    E: Fact[Vnd]
    C: Fact[Vnd]
    A: Fact[Vnd]
    P: Fact[Vnd]
    R: Fact[Vnd]
    unpaid: Fact[Vnd]
    S: Fact[SignedVnd]
    issues: tuple[Id, ...] = ()
