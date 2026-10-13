"""Case scope, assessment input/result, instructions and the case view (contracts §2, §6, §9).

AssessmentInput is an immutable snapshot: the Reconciler is a pure function of
it, so it carries observations and relations rather than positional extras.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from invoice_referee.domain.common import EvidenceRef, Fact, Id, StrictModel, Vnd
from invoice_referee.domain.evidence import (
    Confirmation,
    Observation,
    Relation,
    SourceRef,
)
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    MoneyEvent,
    Projection,
)
from invoice_referee.domain.issues import BusinessIssue, ProcessingProblem
from invoice_referee.domain.policy import (
    BudgetDecision,
    ExceptionDecision,
    Grant,
    PolicyVersion,
)

CaseState = Literal[
    "DRAFT",
    "PROCESSING",
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
    exceptions: tuple[ExceptionDecision, ...] = ()
    previous_eligibility: EligibilityDecision | None = None
    read_set: ReadSet
    as_of: datetime


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
    decided_at: datetime


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


class CaseView(StrictModel):
    id: Id
    version: int
    state: CaseState
    summary: str
    sources: tuple[SourceRef, ...] = ()
    issues: tuple[BusinessIssue, ...] = ()
    problems: tuple[ProcessingProblem, ...] = ()
    conclusion: SettlementConclusion | None = None
    instructions: tuple[Instruction, ...] = ()
    actual_money: Projection
    audit: tuple[str, ...] = ()
