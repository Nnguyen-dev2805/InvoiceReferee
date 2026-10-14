"""The CaseCommand tagged union and CommandResult (contracts §9).

Every client mutation is one of these variants, addressed to a root and
guarded by CommandContext.expected_case_version, except STOP which may be
applied to the newest version after the actor and idempotency checks.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field

from invoice_referee.domain.case import CaseView
from invoice_referee.domain.common import EvidenceRef, Id, StrictModel, UtcDatetime, Vnd
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
    # The activity the dossier is filed against. Optional since 14/10/2026:
    # the backend links the settlement to its dossier (LINKED), and only asks
    # the employee to confirm when the basis is weak/conflicting. An explicit
    # id from an old client is treated as the employee's confirmation.
    activity_id: Id | None = None
    # The employee's confirmation/correction of the backend link: must be one
    # of the link candidates (or a catalog activity in scope). Never a grant,
    # budget or confirmed money.
    confirmed_activity_id: Id | None = None
    declared_purpose: str
    notes: str | None = None
    # The employee-confirmed draft (W4). These are the values the employee saw
    # and possibly corrected on the review screen. They are DECLARATIONS, not
    # verified facts: the server stores both the confirmed value and the original
    # OCR value, and reconciliation compares the declaration against company
    # history rather than overwriting it. All optional for backward compatibility.
    declared_name: str | None = None
    destination: str | None = None
    trip_start: str | None = None
    trip_end: str | None = None
    declared_advance: Vnd | None = None
    incurred_total: Vnd | None = None
    # The OCR value the employee reviewed, kept so a correction is auditable.
    original_declared_advance: Vnd | None = None


class EmployeePaidClaim(StrictModel):
    """A responsible employee's claim that they paid one invoice (ADR0007, Q32).

    The client states the claim (invoice reference, integer VND amount, the
    evidence refs, and a reason). It may NOT supply the actor, verifier or any
    known/verified state — the server derives those from the session and the
    uploaded source bytes. A claim is a bounded employee declaration, never an
    independently verified bank fact.
    """

    invoice_reference: str = Field(min_length=1)
    amount: Vnd
    refs: tuple[EvidenceRef, ...] = ()
    reason: str


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
    # Q32 typed claims the responsible employee states at submit (plan A0/A2).
    employee_paid_claims: tuple[EmployeePaidClaim, ...] = ()


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
