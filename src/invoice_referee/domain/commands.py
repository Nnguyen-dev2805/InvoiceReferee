"""The CaseCommand tagged union and CommandResult (contracts §9).

Every client mutation is one of these variants, addressed to a root and
guarded by CommandContext.expected_case_version, except STOP which may be
applied to the newest version after the actor and idempotency checks.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

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
    # S6 (18/10/2026): Hoangha intake kinds. Defaults keep every old caller on
    # the paper advance-settlement path; new clients set these explicitly.
    settlement_type: Literal["ADVANCE_SETTLEMENT", "EMPLOYEE_REIMBURSEMENT"] = (
        "ADVANCE_SETTLEMENT"
    )
    submission_source: Literal["PAPER_SCAN", "DIGITAL_FORM"] = "PAPER_SCAN"
    # Web-form declared rows (DIGITAL_FORM only). The server validates each row
    # and resolves source_ids against attached case sources.
    digital_lines: tuple[DigitalExpenseLine, ...] = ()
    # The employee asserts they received no advance for this scope. A
    # declaration only: the ledger still decides, and a recorded advance in
    # scope raises a type-conflict FACT instead of being ignored.
    no_advance_asserted: bool = False
    no_advance_reason: str | None = None


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
    # Role-aware upload (16/10/2026): submitter intent, kept distinct from the
    # content-determined document_type. None = legacy caller without a role.
    upload_role: Literal["paper", "evidence"] | None = None


class CreateDraft(StrictModel):
    kind: Literal["CREATE_DRAFT"] = "CREATE_DRAFT"
    activity_data: ActivityData


class DigitalExpenseLine(StrictModel):
    """One employee-declared cost row from the web form (S6, 18/10/2026).

    A declaration, not OCR: the server validates every field and resolves
    `source_ids` against sources actually attached to this case. Files are
    mapped by source id, never by bare filename.
    """

    item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    description: str = Field(min_length=1, max_length=500)
    category: str | None = Field(default=None, pattern=r"^[A-Z_]{2,32}$")
    expense_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount: Vnd
    evidence_status: Literal["ORIGINAL", "ALTERNATIVE", "NO_EVIDENCE"] = "ORIGINAL"
    alternative_type: (
        Literal[
            "PAYMENT_PROOF",
            "RECEIPT_OR_COLLECTION_NOTE",
            "CONTRACT_OR_ACCEPTANCE",
            "SUPPLIER_CONFIRMATION",
            "OTHER",
        ]
        | None
    ) = None
    # Reason the original invoice is missing; required for ALTERNATIVE and
    # NO_EVIDENCE, forbidden otherwise (a note is not a reason).
    exception_reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)
    source_ids: tuple[Id, ...] = ()

    @model_validator(mode="after")
    def _reason_matches_status(self) -> DigitalExpenseLine:
        has_reason = bool((self.exception_reason or "").strip())
        if self.evidence_status in ("ALTERNATIVE", "NO_EVIDENCE") and not has_reason:
            raise ValueError("ALTERNATIVE/NO_EVIDENCE lines require exception_reason")
        if self.evidence_status == "ORIGINAL" and has_reason:
            raise ValueError("ORIGINAL lines must not carry exception_reason")
        if self.evidence_status == "ORIGINAL" and not self.source_ids:
            raise ValueError("ORIGINAL lines require at least one attached source")
        return self


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


class RefuseException(StrictModel):
    """An accountant/approver refuses a requested policy exception (S6).

    Records the refusal with reason and refs; the issues stay OPEN so the
    employee can supplement and re-request. No grant is needed to refuse,
    but the actor must be accountant or approver — never the employee
    refusing their own request.
    """

    kind: Literal["REFUSE_EXCEPTION"] = "REFUSE_EXCEPTION"
    root_id: Id
    issue_ids: tuple[Id, ...] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


class RecordActual(StrictModel):
    kind: Literal["RECORD_ACTUAL"] = "RECORD_ACTUAL"
    root_id: Id
    money: RecordMoneyInput


class ConfirmMoneyHistory(StrictModel):
    kind: Literal["CONFIRM_MONEY_HISTORY"] = "CONFIRM_MONEY_HISTORY"
    root_id: Id
    all_prior_money_recorded: bool


class RecheckDossierHistory(StrictModel):
    kind: Literal["RECHECK_DOSSIER_HISTORY"] = "RECHECK_DOSSIER_HISTORY"
    root_id: Id
    reason: str = Field(min_length=12, max_length=2000)


class ConfirmCoverage(StrictModel):
    """Accountant's structured reconciliation of one dossier's money history."""

    kind: Literal["CONFIRM_COVERAGE"] = "CONFIRM_COVERAGE"
    root_id: Id
    start: UtcDatetime
    funds: tuple[Id, ...]
    flow_kinds: tuple[str, ...]
    opening_balance: Vnd
    unallocated_event_ids: tuple[Id, ...] = ()
    witness_refs: tuple[EvidenceRef, ...]
    reason: str = Field(min_length=12)


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
        RefuseException,
        RecordActual,
        ConfirmCoverage,
        ConfirmMoneyHistory,
        RecheckDossierHistory,
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
