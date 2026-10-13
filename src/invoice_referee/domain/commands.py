"""The CaseCommand tagged union and CommandResult (contracts §9).

Every client mutation is one of these variants, addressed to a root and
guarded by CommandContext.expected_case_version, except STOP which may be
applied to the newest version after the actor and idempotency checks.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from invoice_referee.domain.case import CaseView
from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, UtcDatetime
from invoice_referee.domain.evidence import Media
from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.domain.issues import Answer, DecisionCommand

# contracts §9: MarkExecution reports an observed execution outcome. NOT_STARTED
# is an instruction's initial state, never something a client may reset to.
MarkExecutionState = Literal["OPEN", "CLOSED_CONFIRMED", "UNKNOWN"]


class ActivityData(StrictModel):
    """The activity a draft is filed against. A draft grants no authority."""

    activity_id: Id
    name: str
    occurred_at: UtcDatetime
    declared_purpose: str


class Declaration(StrictModel):
    activity_id: Id
    declared_purpose: str
    notes: str | None = None


class SourceUpload(StrictModel):
    filename: str
    media: Media
    digest: str = Field(min_length=1)
    storage_key: str = Field(min_length=1)


class CreateDraft(StrictModel):
    kind: Literal["CREATE_DRAFT"] = "CREATE_DRAFT"
    activity_data: ActivityData


class AttachSources(StrictModel):
    kind: Literal["ATTACH_SOURCES"] = "ATTACH_SOURCES"
    root_id: Id
    uploads: tuple[SourceUpload, ...]


class ReviseDeclaration(StrictModel):
    kind: Literal["REVISE_DECLARATION"] = "REVISE_DECLARATION"
    root_id: Id
    declaration: Declaration


class Submit(StrictModel):
    kind: Literal["SUBMIT"] = "SUBMIT"
    root_id: Id
    declaration: Declaration


class AnswerIssue(StrictModel):
    kind: Literal["ANSWER_ISSUE"] = "ANSWER_ISSUE"
    root_id: Id
    answer: Answer


class Decide(StrictModel):
    kind: Literal["DECIDE"] = "DECIDE"
    root_id: Id
    decision: DecisionCommand


class RecordActual(StrictModel):
    kind: Literal["RECORD_ACTUAL"] = "RECORD_ACTUAL"
    root_id: Id
    money: RecordMoneyInput


class Control(StrictModel):
    kind: Literal["CONTROL"] = "CONTROL"
    root_id: Id
    action: Literal["STOP", "RESUME"]
    reason: str


class Override(StrictModel):
    kind: Literal["OVERRIDE"] = "OVERRIDE"
    root_id: Id
    supersedes_decision_id: Id
    decision: DecisionCommand


class MarkExecution(StrictModel):
    kind: Literal["MARK_EXECUTION"] = "MARK_EXECUTION"
    root_id: Id
    instruction_id: Id
    execution_state: MarkExecutionState
    refs: tuple[EvidenceRef, ...] = ()
    reason: str


CaseCommand = Annotated[
    Union[
        CreateDraft,
        AttachSources,
        ReviseDeclaration,
        Submit,
        AnswerIssue,
        Decide,
        RecordActual,
        Control,
        Override,
        MarkExecution,
    ],
    Field(discriminator="kind"),
]


class CommandResult(StrictModel):
    case_view: CaseView
    job_id: Id | None = None
    duplicate_command: bool = False
