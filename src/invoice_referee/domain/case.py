"""Case scope, assessment input/result, instructions and the case view (contracts §2, §6, §9).

AssessmentInput is an immutable snapshot: the Reconciler is a pure function of
it, so it carries observations and relations rather than positional extras.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from invoice_referee.domain.common import (
    EvidenceRef,
    Fact,
    Id,
    StrictModel,
    UtcDatetime,
    Vnd,
)
from invoice_referee.domain.evidence import (
    Confirmation,
    Observation,
    ReadResult,
    Relation,
    SourceRef,
)
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    MoneyEvent,
    PaymentBasisView,
    Projection,
)
from invoice_referee.domain.issues import BusinessIssue, ProcessingProblem
from invoice_referee.domain.policy import (
    BudgetDecision,
    CategoryPolicy,
    ExceptionDecision,
    Grant,
    PolicyVersion,
)

CaseState = Literal[
    "DRAFT",
    "PROCESSING",
    "EVIDENCE_READY",
    "WAITING",
    "TECHNICAL_ERROR",
    "READY_TO_EXECUTE",
    "SETTLED",
    "STOPPED",
]
InstructionStatus = Literal[
    "ISSUED",
    "PARTIAL",
    "FULFILLED",
    "SUSPENDED",
    "SUPERSEDED",
    "EXECUTION_UNKNOWN",
]
ExecutionState = Literal["NOT_STARTED", "OPEN", "CLOSED_CONFIRMED", "UNKNOWN"]
Direction = Literal["PAY", "COLLECT"]
ConclusionStatus = Literal["BALANCED", "OUTSTANDING", "BLOCKED"]
Disposition = Literal["ACCEPTED", "EXCLUDED", "UNRESOLVED"]


class CaseScope(StrictModel):
    tenant: Id
    employee: Id
    activity: Id
    profile: str


class ReadSet(StrictModel):
    """The versions a commit re-checks before it may persist a decision."""

    input_revision: int
    control_epoch: int
    context_version: int
    ledger_version: int
    usage_version: int


class EligibilityDecision(StrictModel):
    """A prior E recognition. Reusable only while its cost basis holds."""

    E: Fact[Vnd]
    cost_basis: str
    actor_or_system: str
    grant_refs: tuple[Id, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()


class AssessmentInput(StrictModel):
    scope: CaseScope
    expense_facts: tuple[Expense, ...] = ()
    observations: tuple[Observation, ...] = ()
    relations: tuple[Relation, ...] = ()
    confirmations: tuple[Confirmation, ...] = ()
    ledger: tuple[MoneyEvent, ...] = ()
    coverage: CoverageRecord | None = None
    policy: tuple[PolicyVersion, ...] = ()
    grants: tuple[Grant, ...] = ()
    budget: tuple[BudgetDecision, ...] = ()
    # Versioned per-item category caps + submission window (T3). Empty means no
    # category policy is in force for this scope.
    category_policy: tuple[CategoryPolicy, ...] = ()
    exceptions: tuple[ExceptionDecision, ...] = ()
    previous_eligibility: EligibilityDecision | None = None
    read_set: ReadSet
    as_of: UtcDatetime
    # Admission outputs (plan A0/A3): unresolved material conditions that must
    # suppress effects/affirmative conclusion, and whether the typed expense set
    # is complete. When incomplete, T/E and affected S stay UNKNOWN — sum(empty)
    # must never become a known zero.
    admission_issues: tuple[BusinessIssue, ...] = ()
    admission_problems: tuple[ProcessingProblem, ...] = ()
    expense_set_complete: bool = False
    # Costs whose amount is in dispute (a source over-allocation, TC08). These
    # carry a specific admission FACT that names both numbers and the difference,
    # so the policy engine does not also raise the generic T/payer facts for
    # them (the payer basis is known; only the amount is unresolved).
    disputed_expense_ids: tuple[Id, ...] = ()


class FinancialEffect(StrictModel):
    """A proposed effect. The workflow re-checks it; it is not an instruction."""

    direction: Direction
    amount: Vnd
    employee: Id
    activity: Id
    basis: str


class AssessmentResult(StrictModel):
    projection: Projection
    issues: tuple[BusinessIssue, ...] = ()
    problems: tuple[ProcessingProblem, ...] = ()
    required_authorizations: tuple[str, ...] = ()
    allowed_effect: FinancialEffect | None = None
    cost_basis: str
    money_basis: str
    # Per-expense paid basis/actor/refs (plan A0/A4). The reconciler fills this
    # from the admitted expenses; the persisted conclusion carries it and the
    # view exposes it. Default empty keeps STUB/legacy snapshots compatible.
    payment_basis: tuple[PaymentBasisView, ...] = ()
    # The distinct canonical economic identities of the admitted costs (the
    # document bound to each expense). Persisted with the conclusion so the
    # usage/anti-duplicate consumer sees the SAME identity the evidence path
    # admitted (§10.2). Default empty keeps STUB/legacy snapshots compatible.
    economic_keys: tuple[str, ...] = ()


class CommandContext(StrictModel):
    session_id: Id
    actor_id: Id
    command_id: Id
    expected_case_version: int


class ExpenseDisposition(StrictModel):
    expense_id: Id
    disposition: Disposition
    amount: Vnd
    rule: str | None = None
    reason: str
    refs: tuple[EvidenceRef, ...] = ()


class SettlementConclusion(StrictModel):
    status: ConclusionStatus
    projection: Projection
    expense_dispositions: tuple[ExpenseDisposition, ...] = ()
    read_set: ReadSet
    basis: str
    refs: tuple[EvidenceRef, ...] = ()
    actor_or_system: str
    decided_at: UtcDatetime
    # Per-expense paid basis/actor/refs (plan A0/A8). Derived from the admitted
    # expenses; Q32 is a responsible employee confirmation, not a bank fact.
    payment_basis: tuple[PaymentBasisView, ...] = ()


class Instruction(StrictModel):
    """A pending order to pay or collect. It is not evidence that money moved."""

    id: Id
    root_id: Id
    direction: Direction
    amount: Vnd
    status: InstructionStatus
    basis: str
    authority_refs: tuple[Id, ...] = ()
    supersedes_id: Id | None = None
    fulfilled_amount: Vnd = 0
    remaining: Vnd
    execution_state: ExecutionState

    @model_validator(mode="after")
    def _remaining_matches_fulfillment(self) -> Instruction:
        # contracts §4: remaining is the net uncovered amount; fulfillment can
        # never exceed the instruction amount.
        if self.fulfilled_amount > self.amount:
            raise ValueError("fulfilled_amount must not exceed amount")
        if self.remaining != max(self.amount - self.fulfilled_amount, 0):
            raise ValueError("remaining must equal max(amount - fulfilled_amount, 0)")
        return self


class CaseView(StrictModel):
    id: Id
    version: int
    state: CaseState
    # The dossier's activity/employee scope (server-owned). A client uses it to
    # address the right scope; the server still re-checks it (§4, plan D).
    activity: Id | None = None
    employee: Id | None = None
    summary: str
    sources: tuple[SourceRef, ...] = ()
    issues: tuple[BusinessIssue, ...] = ()
    problems: tuple[ProcessingProblem, ...] = ()
    conclusion: SettlementConclusion | None = None
    instructions: tuple[Instruction, ...] = ()
    actual_money: Projection
    audit: tuple[str, ...] = ()
    # Typed evidence report (contracts §12.5). Present after a LIVE/REPLAY read;
    # it is pipeline completion only, never a financial conclusion.
    evidence_report: "ReadResult | None" = None
    assessment_ready: bool = True
    assessment_blocker: str | None = None
    # Per-expense paid basis/actor/refs (plan A0/A8); empty until a typed
    # admission has produced a conclusion.
    payment_basis: tuple[PaymentBasisView, ...] = ()
