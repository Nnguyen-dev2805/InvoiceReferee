"""Business issues, questions and answers (contracts §2, §7).

A question must be answerable from its card by the right owner; a processing
problem is a technical condition, never a business escalation.
"""

from __future__ import annotations

from typing import Literal

from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, Vnd

IssueKind = Literal["FACT", "POLICY", "AUTHORITY"]
IssueStatus = Literal["OPEN", "ANSWERED", "RESOLVED", "SUPERSEDED"]
ProblemKind = Literal["TECHNICAL", "LIMIT", "UNSUPPORTED"]
ProblemRelevance = Literal["MATERIAL", "UNRELATED", "UNKNOWN"]


class BusinessIssue(StrictModel):
    id: Id
    kind: IssueKind
    field_or_rule: str
    owner: str
    depends_on: tuple[Id, ...] = ()
    status: IssueStatus = "OPEN"
    basis: str
    refs: tuple[EvidenceRef, ...] = ()
    question: str


class ProcessingProblem(StrictModel):
    kind: ProblemKind
    affected_fields: tuple[str, ...] = ()
    message: str
    relevance: ProblemRelevance = "UNKNOWN"
    blocking: bool = True
    next_action: str


class QuestionAction(StrictModel):
    issue_id: Id
    action: str
    label: str
    scope: Id
    amount: Vnd
    limit: Vnd | None = None
    authorized: bool = False
    unavailable_reason: str | None = None


class DeclaredChange(StrictModel):
    field: str
    row_id: str | None = None
    before: int
    after: int


class DeclarationCorrectionOption(StrictModel):
    id: str
    label: str
    changes: tuple[DeclaredChange, ...]


class QuestionCard(StrictModel):
    """Everything one owner needs to answer this issue in one response."""

    issue_id: Id
    case_version: int = 0
    basis_id: str = ""
    kind: IssueKind = "FACT"
    scope: str = ""
    title: str = ""
    response_kind: Literal["FACT", "DECISION", "CORRECT_DECLARATION", "REPLACE_SOURCE", "HISTORY"] = "FACT"
    actions: tuple[QuestionAction, ...] = ()
    corrections: tuple[DeclarationCorrectionOption, ...] = ()
    known_facts: tuple[str, ...] = ()
    excerpt_refs: tuple[EvidenceRef, ...] = ()
    required_answer: str
    effects: str
    owner: str


class Answer(StrictModel):
    issue_id: Id
    basis_id: Id
    answer_kind: str
    value: str | int | None = None
    refs: tuple[EvidenceRef, ...] = ()
    reason: str


class DecisionCommand(StrictModel):
    """A compound, granted decision. It never rewrites facts or actual money."""

    issue_ids: tuple[Id, ...]
    basis_id: Id
    actions: tuple[str, ...]
    effect_scope: str
    amount: Vnd | None = None
    reason: str
    refs: tuple[EvidenceRef, ...] = ()
