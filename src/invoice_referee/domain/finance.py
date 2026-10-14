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
# Whether the expense's payment status is established by the basis (contracts §3).
# PAID = the paid portions are verified; UNPAID = the basis establishes nothing
# has been paid yet; UNKNOWN = there is not enough basis to tell (missing
# evidence of payment never proves a zero). Eligibility is a separate axis.
PaymentState = Literal["PAID", "UNPAID", "UNKNOWN"]
MoneyKind = Literal[
    "ADVANCE_RECEIVED",
    "REIMBURSEMENT_RECEIVED",
    "EMPLOYEE_RETURN",
    "REVERSAL",
    "OBSERVED_UNALLOCATED",
]
VerificationState = Literal["OBSERVED", "CONFIRMED", "REJECTED"]
AllocationState = Literal["UNALLOCATED", "ALLOCATED", "UNKNOWN"]

# How an employee-paid portion is established (ADR0007 + 14/10/2026 chốt). In
# the demo policy a valid invoice bound to the right employee and dossier is
# accepted as the employee-paid basis (EMPLOYEE_PAID_INVOICE) with no separate
# payer confirmation; a Q32 employee declaration (EMPLOYEE_DECLARATION_Q32) is a
# bounded responsible confirmation. Neither is an independently verified bank
# fact. LIVE admission must never present UNSPECIFIED_LEGACY as a verified basis.
PaymentBasisKind = Literal[
    "INDEPENDENT_PAYMENT",
    "FINANCIAL_CONFIRMATION",
    "EMPLOYEE_PAID_INVOICE",
    "EMPLOYEE_DECLARATION_Q32",
    "UNSPECIFIED_LEGACY",
]


class ExpensePayment(StrictModel):
    """A verified payment portion of one expense (payer/amount/binding)."""

    external_key: str
    payer: Id
    payee: Id
    amount: Vnd
    expense_id: Id
    received_state: ReadState
    refs: tuple[EvidenceRef, ...] = ()
    # The confirmation basis and the responsible actor. A compatibility
    # constructor (STUB/test) leaves the basis UNSPECIFIED_LEGACY; LIVE/REPLAY
    # admission must set an explicit basis and actor (plan A0/A3).
    basis_kind: PaymentBasisKind = "UNSPECIFIED_LEGACY"
    responsible_actor: Id | None = None


class PaymentBasisView(StrictModel):
    """A read-only view of how one expense's paid portion is established.

    This is derived from the admitted expenses, not a separate ledger event: no
    money moves because a basis view exists. Q32 is labelled a responsible
    employee confirmation, never an independent bank fact (ADR0007).
    """

    expense_id: Id
    kind: PaymentBasisKind
    actor: Id | None = None
    refs: tuple[EvidenceRef, ...] = ()
    rule_id: str | None = None


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
    # Whether the basis establishes the payment status of this cost. A cost with
    # no admitted payment is UNKNOWN (not proven-unpaid); a source that states
    # "nothing paid yet" is UNPAID (a verified zero); PAID means the paid
    # portions are verified. Defaults to UNKNOWN so a new/typed expense is never
    # silently treated as paid or as a proven debt (contracts §3).
    payment_state: PaymentState = "UNKNOWN"
    # Source-backed business category (T3). A code-owned proposal from the source
    # text; None when the category is not established. The category decides which
    # per-item cap applies (never a keyword substring in the policy engine).
    category: str | None = None
    # The established expense date from the source/validated context. Distinct
    # from `incurred_at` (the assessment instant); a missing source date is a
    # FACT, never substituted with the report submit date (T3).
    source_date: UtcDatetime | None = None


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
    # Observed source metadata for the "record actual money" form (plan D). The
    # client reports what the document says (a transfer/cash instrument's method
    # and status); the SERVER still decides verification_state. A source status
    # that is not COMPLETED (pending/failed/unclear) never becomes confirmed
    # received money. Defaults None keep every existing caller unchanged.
    instrument_method: Literal["TRANSFER", "CASH"] | None = None
    instrument_status: Literal["COMPLETED", "PENDING", "FAILED", "UNKNOWN"] | None = None
    instrument_reference: str | None = None


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
    # Source-reported instrument metadata retained for audit (plan D). None for
    # events recorded before the advance form existed.
    instrument_method: Literal["TRANSFER", "CASH"] | None = None
    instrument_status: Literal["COMPLETED", "PENDING", "FAILED", "UNKNOWN"] | None = None
    instrument_reference: str | None = None


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
