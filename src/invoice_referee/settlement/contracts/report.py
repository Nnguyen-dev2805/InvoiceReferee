"""Report contracts (System §S3): checks, issues, money components."""
from __future__ import annotations

from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

from invoice_referee.settlement.contracts.b3_contracts import B3Proposal
from invoice_referee.settlement.contracts.base import Job
from invoice_referee.settlement.contracts.run import (
    RelationKind,
    RelationStatus,
)


# --- Report contracts (System §S3) -------------------------------------------

class MoneyComponents(BaseModel):
    """Arithmetic components: None means unknown, never 0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    e: StrictInt | None
    a: StrictInt | None
    ra: StrictInt | None
    p: StrictInt | None
    rp: StrictInt | None


class ComponentSlot(BaseModel):
    """One money component with its value-or-null, state and source refs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: StrictInt | None
    state: Literal["KNOWN", "UNKNOWN", "PENDING", "NOT_APPLICABLE"]
    refs: list[str] = Field(default_factory=list)


class ReportComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    t: ComponentSlot
    b: ComponentSlot
    e: ComponentSlot
    a: ComponentSlot
    ra: ComponentSlot
    p: ComponentSlot
    rp: ComponentSlot


class ExpenseRow(BaseModel):
    """One claimed expense with eligibility split and refs to open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expense_id: str
    claimed_amount_vnd: StrictInt | None
    eligible_employee_vnd: StrictInt | None = None
    company_direct_vnd: StrictInt | None = None
    state: Literal[
        "ELIGIBLE", "PERSONAL_EXCLUDED", "COMPANY_DIRECT", "UNKNOWN", "EXCLUDED"
    ]
    refs: list[str] = Field(default_factory=list)
    reason: str = ""


CheckStatus = Literal["PASS", "FAIL", "UNRESOLVED", "NOT_APPLICABLE"]


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule: str
    status: CheckStatus
    refs: list[str] = Field(default_factory=list)
    reason: str = ""


IssueType = Literal[
    "FACT", "POLICY", "AUTHORITY", "MONEY_INCIDENT", "TECHNICAL", "CONTROL"
]
IssueOwner = Literal["EMPLOYEE", "ACCOUNTANT", "APPROVER"]


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issue_id: str
    type: IssueType
    owner: IssueOwner
    message: str
    refs: list[str] = Field(default_factory=list)
    blocked: str | None = None
    unresolved: bool = True


class CriticalFact(BaseModel):
    """One consumed fact key with its resolved value and quality state.

    ``CONTRADICTED`` keeps ``None`` (no silent pick), ``UNUSABLE`` is a READ
    fact the quality gate refuses, ``UNCLEAR`` an unreadable extraction.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    value: StrictInt | str | None = None
    state: Literal["KNOWN", "UNKNOWN", "CONTRADICTED", "UNCLEAR", "UNUSABLE"]
    refs: list[str] = Field(default_factory=list)


class ReportLink(BaseModel):
    """One reconciliation relation exposed with its establishment status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relation_id: str
    kind: RelationKind
    from_id: str
    to_id: str
    portion_vnd: StrictInt | None = None
    status: RelationStatus


class ConditionalResult(BaseModel):
    """A policy scenario from verified facts, not an approved amount."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: str
    net_vnd: StrictInt | None
    components: MoneyComponents


class Report(BaseModel):
    """Sourced check report; proposed≠approved≠actual (those come later)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    job: Job
    completion: Literal["COMPLETE", "INCOMPLETE"]
    mode: str
    generated_at: AwareDatetime
    components: ReportComponents
    calculated_net_vnd: StrictInt | None
    proposed_net_vnd: StrictInt | None
    direction: Literal["COMPANY_TO_EMPLOYEE", "EMPLOYEE_TO_COMPANY",
                       "BALANCED"] | None = None
    conditional_results: list[ConditionalResult] = Field(default_factory=list)
    expense_rows: list[ExpenseRow] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    critical_facts: list[CriticalFact] = Field(default_factory=list)
    links: list[ReportLink] = Field(default_factory=list)
    b3: B3Proposal | None = None
    claim_comparisons: list[B7ClaimComparison] = Field(default_factory=list)
    next_step: str = ""
    source_refs: list[str] = Field(default_factory=list)
