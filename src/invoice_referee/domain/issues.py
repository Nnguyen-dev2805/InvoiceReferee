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


class QuestionCard(StrictModel):
    """Everything one owner needs to answer this issue in one response."""

    issue_id: Id
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
