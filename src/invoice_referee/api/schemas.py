"""Settlement API request schemas (Pydantic bodies).

Request bodies for the settlement routes in ``api/settlement.py``. They map
HTTP JSON <-> records; all decision logic stays in the Service/Store.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictInt

from invoice_referee.settlement.models import DemoRole, Submission


class CreateCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission: Submission
    actor_id: str
    demo_role: DemoRole
    body: dict[str, Any] = {}


class ReviseSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission: Submission
    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    reason: str = ""


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class RespondRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    content: str
    source_ids: list[str] = []


class DecisionRequest(BaseModel):
    """DECIDE over HTTP: authority-checked approval/refusal (S6)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    kind: Literal["SETTLEMENT"]
    amount_vnd: StrictInt | None = None
    direction: Literal["PAY_EMPLOYEE", "COLLECT_FROM_EMPLOYEE", "REFUSE"]
    reason: str
    basis_report_id: str
    conditions: list[str] = []
    exception_of: str | None = None


class ReviewRequest(BaseModel):
    """Accountant review; amount_vnd is surfaced so the semantic error fires."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    report_id: str
    note: str
    refs: list[str] = []
    amount_vnd: StrictInt | None = None


class MoneyEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    event_ref: str
    kind: Literal["PAYMENT_TO_EMPLOYEE", "PAYMENT_FROM_EMPLOYEE"]
    gross_vnd: StrictInt
    decision_id: str | None = None
    payee_ref: str
    event_at: str
    reported_status: Literal["RECEIVED", "PENDING"]
    refs: list[str] = []


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    action: Literal["STOP", "RESUME"]
    reason: str = ""


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str


class ClosureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    kind: Literal["SETTLEMENT_COMPLETE", "REJECTED_REQUEST_ENDED"]
    basis: str


class VerifyRunRequest(BaseModel):
    """Run the settlement evaluation suite sequentially (same Service path)."""

    model_config = ConfigDict(extra="forbid")

    packets: list[str] | None = None
    mode: Literal["configured", "policy-replay"] | None = None


class CreateB3CaseRequest(BaseModel):
    """B3 v1 intake: chỉ actor + lời khai; context/quyền/clock do backend."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    intake: dict[str, Any]


class CreateB7CaseRequest(BaseModel):
    """Standalone (self-paid) B7 intake: chỉ actor + nội dung; định danh backend."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    intake: dict[str, Any]


class B3PresentRequest(BaseModel):
    """Accountant presentation over HTTP (envelope + payload)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    basis_report_id: str
    review_id: str | None = None
    review: dict[str, Any] | None = None


class B3DecisionRequest(BaseModel):
    """Approver B3 outcome over HTTP (envelope + payload)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    presentation_id: str
    outcome: Literal["APPROVE", "RETURN", "REFUSE"]
    reason: str
    work_allowed: bool | None = None
    budget_vnd: StrictInt | None = None
    advance_vnd: StrictInt | None = None


class B3AdvanceEventRequest(BaseModel):
    """Accountant's actual advance money event over HTTP (envelope + payload)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: Literal["BANK_TRANSFER", "CASH"]
    gross_vnd: StrictInt | None = None
    payer_side: Literal["COMPANY", "EMPLOYEE", "OTHER", "UNKNOWN"]
    payee_ref: str | None = None
    event_at: str | None = None
    reported_status: Literal[
        "RECEIVED", "PENDING", "FAILED", "CANCELLED", "UNCONFIRMED"]
    evidence: list[dict[str, Any]] = []
    allocation_note: str
    supersedes_event_id: str | None = None


class PrepareLinkedB7Request(BaseModel):
    """Open a linked B7 child from a B3 parent (parent version envelope)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class LinkedB7SubmissionRequest(BaseModel):
    """Save/confirm a linked B7 child's declarations (child version envelope)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    intake: dict[str, Any]


class B7CompanyContextRequest(BaseModel):
    """Accountant records the source-backed company packet for a child."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    packet: dict[str, Any]


class LinkedContextRefreshRequest(BaseModel):
    """Refresh the linked context from the latest company packet."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class B7PresentRequest(BaseModel):
    """Accountant presents the linked settlement (envelope + payload)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    basis_report_id: str
    review_id: str | None = None
    review: dict[str, Any] | None = None
    supersedes_decision_id: str | None = None


class B7DecisionRequest(BaseModel):
    """Approver settlement outcome (envelope + payload); no client amount."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    presentation_id: str
    outcome: Literal["APPROVE", "RETURN", "REFUSE"]
    reason: str


class B7MoneyEventRequest(BaseModel):
    """Accountant settlement money event (envelope + typed payload)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str | None = None
    event_namespace: str | None = None
    event_ref: str | None = None
    method: Literal["BANK_TRANSFER", "CASH"]
    gross_vnd: StrictInt | None = None
    payer_ref: str | None = None
    payee_ref: str | None = None
    event_at: str | None = None
    reported_status: Literal["RECEIVED", "PENDING", "FAILED", "CANCELLED",
                             "UNCONFIRMED"]
    purpose: Literal["REIMBURSEMENT_RECEIVED", "ADVANCE_RETURN",
                     "REIMBURSEMENT_RETURN", "UNKNOWN"]
    evidence: list[dict[str, Any]] = []
    allocation_note: str
    supersedes_event_id: str | None = None


class B7MoneyContextRefreshRequest(BaseModel):
    """Advance the money as-of cutoff and rebuild the linked context."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class B7RevalidateRequest(BaseModel):
    """Revalidate a decision against a correct fulfillment."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class B7HandoffRequest(BaseModel):
    """Create a stage-A handoff for the remaining obligation."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str
    reason: str


class B7ClosureRequest(BaseModel):
    """Close a linked settlement; gates are checked before acceptance."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str
    current_report_id: str
    reason: str


class B7AdjustmentRequest(BaseModel):
    """Open a post-closure adjustment child for a closed settlement."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    reason: str

