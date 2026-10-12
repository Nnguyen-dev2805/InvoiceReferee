from __future__ import annotations

import sqlite3
from pathlib import Path

from invoice_referee.shared.errors import DomainError
from invoice_referee.shared import clock
from invoice_referee.settlement.persistence import sqlite_records as _rec
from invoice_referee.settlement.persistence import queries as _q
from invoice_referee.settlement.persistence import advance_records as _adv
from invoice_referee.settlement.persistence import linked_context_records as _lc
from invoice_referee.settlement.advance_workflow import b3_route_for
from invoice_referee.settlement.models import (
    B7ClosureView,
    B7DecisionPayload,
    B7DecisionView,
    B7FulfillmentReceipt,
    B7FulfillmentSummary,
    B7HandoffPayload,
    B7HandoffView,
    B7MoneyEventPayload,
    B7MoneyEventView,
    B7MoneyIncident,
    B7PresentPayload,
    B7PresentationView,
    B7RevalidationView,
    B7WorkflowView,
    CaseStage,
    Command,
    MoneyComponents,
    Report,
    SourceRecord,
    Submission,
    Upload,
    fingerprint,
)

from invoice_referee.settlement.persistence.operations import (
    B7_ADD_SETTLEMENT_PROOF as _B7_ADD_SETTLEMENT_PROOF,
    B7_ADJUSTMENT as _B7_ADJUSTMENT,
    B7_CLOSE as _B7_CLOSE,
    B7_CONTEXT_REFRESH as _B7_CONTEXT_REFRESH,
    B7_DECIDE as _B7_DECIDE,
    B7_HANDOFF as _B7_HANDOFF,
    B7_MONEY_CONTEXT_REFRESH as _B7_MONEY_CONTEXT_REFRESH,
    B7_PRESENT as _B7_PRESENT,
    B7_RECORD_MONEY as _B7_RECORD_MONEY,
    B7_REVALIDATE as _B7_REVALIDATE,
    B7_SETTLEMENT_PROOF_USE as _B7_SETTLEMENT_PROOF_USE,
)
_CLOSED_STAGES: tuple[str, ...] = ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED")
_OPEN_QUESTION_STATUSES = ("OPEN", "ANSWERED")

def record_presentation(conn: sqlite3.Connection, artifact_root: Path,
                        case_id: str, payload: B7PresentPayload,
                        command: Command, b7, b3,
                        policy: dict) -> B7PresentationView:
    """Accountant presents the current linked settlement basis to approver.

    Saves a new review (note+refs) or reuses a stored one, in ONE
    transaction with the presentation. Target/signatures are server-derived;
    route uses the inherited B3 company route. No financial action.
    """
    from invoice_referee.settlement.settlement_workflow import (
        b7_business_signature, b7_configuration_signature,
        b7_cost_signature, settlement_target,
    )

    payload_fp = fingerprint(_B7_PRESENT, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_PRESENT, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["presentation"]
        return B7PresentationView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Trình quyết toán chỉ áp dụng cho hồ sơ liên kết.",
        )
    if case["stop_active"]:
        raise DomainError("STOP_ACTIVE",
                          "Hồ sơ đang Stop; không trình quyết toán.")
    _rec.check_version(case, command)
    if b7 is None or not b7.activated:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            "Chưa cấu hình B7 company config; không trình quyết toán.")
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    link = _lc.origin_link(case)
    parent_id = link["origin_case_id"]
    _lc.check_origin_not_stopped(conn, parent_id)
    route = b3_route_for(b3, submission.employee_ref) if b3 else None
    if (command.demo_role != "ACCOUNTANT" or route is None
            or route.accountant_ref != command.actor_id):
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.demo_role}/{command.actor_id} không phải kế "
            f"toán được phân công cho {submission.employee_ref}.",
        )
    case, run, report, context_source_id = _lc.linked_ready(
        conn, case_id, payload.basis_report_id)
    target = settlement_target(report)
    snapshot = _lc.load_context(conn, artifact_root, context_source_id)
    sources = _rec.source_records(conn, case_id)
    business_sig = b7_business_signature(submission, sources, report,
                                         policy, snapshot)
    cost_sig = b7_cost_signature(submission, sources, report, policy, snapshot)
    config_sig = b7_configuration_signature(b7, b3, policy)
    parent_fp = _lc.parent_fingerprint(conn, parent_id, _q._b3_workflow_of,
                                       _adv.advance_events)
    current = _q.workflow_view(conn, case_id)
    # Idempotent re-present while still pending and same basis. Register the
    # command (fingerprint/result) so a later reuse of the same key with a
    # different body is an IDEMPOTENCY_CONFLICT, not a silent reuse.
    if (current is not None and current.decision is None
            and current.presentation is not None
            and current.presentation.business_signature == business_sig):
        _rec.record_command(conn, case_id, case_id, "B7_PRESENTED",
                            _B7_PRESENT, command, payload_fp,
                            {"presentation": current.presentation.model_dump(
                                mode="json"),
                             "cost_signature": cost_sig, "no_op": True}, clock.now_iso())
        return current.presentation.model_copy(update={"idempotent_replay": True})
    now = clock.now_iso()
    if payload.review_id is not None:
        review = _adv.b3_find_review(conn, case_id, payload.review_id)
        if review["report_id"] != payload.basis_report_id \
                or review["actor_id"] != command.actor_id:
            raise DomainError(
                "BASIS_MISMATCH",
                "Review đã lưu không thuộc basis report/kế toán này.")
        review_id = payload.review_id
    else:
        review = {
            "id": _rec.new_id("RV-"), "case_id": case_id,
            "report_id": payload.review.report_id,
            "note": payload.review.note, "refs": payload.review.refs,
            "actor_id": command.actor_id, "created_at": now,
        }
        review_id = review["id"]
        conn.execute(
            "INSERT INTO interactions (id, case_id, kind, payload_json, "
            "created_at) VALUES (?, ?, 'REVIEW', ?, ?)",
            (review_id, case_id, _rec.dump(review), now),
        )
    presentation = {
        "id": _rec.new_id("PR-"), "case_id": case_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref,
        "basis_report_id": payload.basis_report_id,
        "basis_review_id": review_id,
        "accountant_ref": route.accountant_ref,
        "approver_ref": route.approver_ref,
        "basis_input_revision": case["input_revision"],
        "control_epoch": case["control_epoch"],
        "business_signature": business_sig,
        "parent_fingerprint": parent_fp,
        "config_signature": config_sig,
        "target": target.model_dump(mode="json"),
        "created_at": now,
    }
    conn.execute(
        "UPDATE cases SET stage = 'AWAITING_DECISION', case_version = ?, "
        "updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_PRESENTED",
                        _B7_PRESENT, command, payload_fp,
                        {"presentation": presentation, "review": review,
                         "cost_signature": cost_sig}, now)
    return B7PresentationView.model_validate(presentation)


def record_decision(conn: sqlite3.Connection, artifact_root: Path,
                    case_id: str, payload: B7DecisionPayload, command: Command,
                    b7, b3, policy: dict) -> B7DecisionView:
    """Record the approver's settlement outcome on a current presentation.

    APPROVE uses a single scoped B7 grant covering E and abs(S); the target
    is server-derived from the current report, never client-supplied.
    RETURN/REFUSE keep the obligation and need only a scoped effective grant.
    No money event is created.
    """
    from invoice_referee.settlement.settlement_workflow import (
        authorize_b7_decision, b7_business_signature, b7_configuration_signature,
        b7_cost_signature, effective_b7_time, settlement_target,
    )

    payload_fp = fingerprint(_B7_DECIDE, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_DECIDE, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["decision"]
        return B7DecisionView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Quyết định quyết toán chỉ áp dụng cho hồ sơ liên kết.",
        )
    if case["stop_active"]:
        raise DomainError("STOP_ACTIVE",
                          "Hồ sơ đang Stop; không ghi quyết định.")
    _rec.check_version(case, command)
    if b7 is None or not b7.activated:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            "Chưa cấu hình B7 company config; không quyết định.")
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    link = _lc.origin_link(case)
    parent_id = link["origin_case_id"]
    _lc.check_origin_not_stopped(conn, parent_id)
    current = _q.workflow_view(conn, case_id)
    if current is None or current.presentation is None:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Chưa có presentation để quyết định; kế toán phải trình trước.",
        )
    if current.decision is not None:
        raise DomainError(
            "B7_ALREADY_DECIDED",
            "Đã có quyết định cho presentation này; không ghi lần hai.",
        )
    presentation = current.presentation
    if presentation.id != payload.presentation_id:
        raise DomainError(
            "BASIS_MISMATCH",
            "presentation_id không khớp presentation đang chờ.",
        )
    if not current.basis_current:
        raise DomainError(
            "BASIS_STALE",
            "Căn cứ đã đổi kể từ khi trình; cần chạy và trình lại.",
        )
    route = b3_route_for(b3, submission.employee_ref) if b3 else None
    if route is None or route.approver_ref != command.actor_id:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.actor_id} không phải người duyệt được phân "
            f"công cho {submission.employee_ref}.",
        )
    report = Report.model_validate(
        _rec.load(conn.execute("SELECT * FROM runs WHERE id = ?",
                               (presentation.basis_report_id,)).fetchone()
                  ["report_json"]))
    target = None
    if payload.outcome == "APPROVE":
        target = settlement_target(report)
    effective_at = effective_b7_time(b7)
    grant = authorize_b7_decision(
        b7, submission.employee_ref, submission.work_ref,
        command.actor_id, effective_at, target)
    sources = _rec.source_records(conn, case_id)
    snapshot = _lc.load_context(
        conn, artifact_root, _lc.context_source_ids(conn, case_id)[-1])
    business_sig = b7_business_signature(submission, sources, report,
                                         policy, snapshot)
    # Server-derived cost signature at decision time: revalidation compares it
    # against the current one so an equal total never waives a changed cost
    # basis. Recorded in the B7_DECIDE audit metadata (never a client field).
    cost_sig = b7_cost_signature(submission, sources, report, policy, snapshot)
    config_sig = b7_configuration_signature(b7, b3, policy)
    authority_sig = fingerprint("B7_AUTHORITY", {
        "grant_ref": getattr(grant, "actor_ref", None),
        "grant": grant.model_dump(mode="json"),
        "effective_at": clock.iso(effective_at)})
    history_baseline = None
    if target is not None:
        history_baseline = MoneyComponents(
            e=report.components.e.value, a=report.components.a.value,
            ra=report.components.ra.value, p=report.components.p.value,
            rp=report.components.rp.value)
    now = clock.now_iso()
    decision = {
        "id": _rec.new_id("B7D-"), "case_id": case_id,
        "kind": "B7_SETTLEMENT", "outcome": payload.outcome,
        "reason": payload.reason,
        "presentation_id": presentation.id,
        "basis_report_id": presentation.basis_report_id,
        "basis_review_id": presentation.basis_review_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref, "actor_id": command.actor_id,
        "effective_at": clock.iso(effective_at), "created_at": now,
        "basis_input_revision": presentation.basis_input_revision,
        "control_epoch": presentation.control_epoch,
        "business_signature": business_sig,
        "parent_fingerprint": presentation.parent_fingerprint,
        "config_signature": config_sig,
        "authority_signature": authority_sig,
        "target": (target.model_dump(mode="json")
                   if target is not None else None),
        "history_baseline": (history_baseline.model_dump(mode="json")
                             if history_baseline is not None else None),
        "supersedes_decision_id": presentation.model_dump(
            mode="json").get("supersedes_decision_id"),
    }
    conn.execute(
        "INSERT INTO decisions (id, case_id, payload_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (decision["id"], case_id, _rec.dump(decision), now),
    )
    if payload.outcome == "APPROVE":
        if target is not None and target.amount_vnd == 0:
            new_stage: CaseStage = "READY_TO_CLOSE"
        else:
            new_stage = "AWAITING_MONEY"
    elif payload.outcome == "RETURN":
        new_stage = "CHECKING"
    else:
        new_stage = "SETTLEMENT_REQUEST_REFUSED"
    conn.execute(
        "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
        "WHERE id = ?",
        (new_stage, case["case_version"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_DECISION_RECORDED",
                        _B7_DECIDE, command, payload_fp,
                        {"decision": decision,
                         "cost_signature": cost_sig}, now)
    return B7DecisionView.model_validate(decision)
