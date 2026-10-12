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

def handoff(conn: sqlite3.Connection, artifact_root: Path, case_id: str,
            payload: B7HandoffPayload, command: Command, b7, b3,
            policy: dict) -> B7HandoffView:
    """Create a stage-A handoff for the remaining obligation (audit only)."""
    from invoice_referee.settlement.settlement_workflow import (
        b7_business_signature, effective_b7_time,
    )

    payload_fp = fingerprint(_B7_HANDOFF, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_HANDOFF, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return B7HandoffView.model_validate(
            _rec.load(row["payload_json"])["handoff"]).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID", "Handoff chỉ áp dụng cho hồ sơ liên kết.")
    if case["stop_active"]:
        raise DomainError("STOP_ACTIVE", "Hồ sơ đang Stop; không handoff.")
    _rec.check_version(case, command)
    _q.require_accountant_route(conn, case, command, b3)
    _lc.check_origin_not_stopped(conn, _lc.origin_link(case)["origin_case_id"])
    decision = _q.current_decision(conn, case_id)
    if decision is None or decision.outcome != "APPROVE" \
            or decision.target is None:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Cần quyết định APPROVE hiện hành để bàn giao.")
    if payload.decision_id != decision.id:
        raise DomainError(
            "BASIS_MISMATCH", "decision_id không khớp quyết định hiện hành.")
    if decision.target.direction == "BALANCED":
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Quyết toán cân bằng không có phần tiền để bàn giao.")
    summary = _q.fulfillment(conn, case_id)
    if summary is None or summary.status == "BLOCKED":
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Còn pending/unknown/incident; không bàn giao phần còn lại.")
    remaining = summary.remaining_vnd
    if remaining is None or remaining <= 0:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Không còn phần nghĩa vụ để bàn giao.")
    # A new handoff needs a CURRENT basis: the original report while it is still
    # current, else a current VALID revalidation of the same decision. A material
    # source added after approval makes this raise BASIS_STALE.
    report, snapshot, cost_sig = _q.require_handoff_basis(
        conn, artifact_root, case_id, decision, b7, b3, policy)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    business_sig = b7_business_signature(
        submission, _rec.source_records(conn, case_id), report, policy, snapshot)
    # The obligation signature binds the decision, remaining amount, cost basis
    # and receipt history: same remaining with a different basis/receipt is a
    # NEW obligation, never a silent reuse of an old handoff.
    receipt_sig = _q.receipt_signature(conn, case_id)
    obligation_sig = fingerprint("B7_OBLIGATION", {
        "decision_id": decision.id, "remaining_vnd": remaining,
        "cost_signature": cost_sig, "receipt_history": receipt_sig})
    # One current handoff per obligation signature: reuse, else new. The reuse
    # still registers the command so a later same-key/different-body request is
    # an IDEMPOTENCY_CONFLICT rather than a silent no-op.
    prior = _q.latest_handoff(conn, case_id)
    if prior is not None and prior.obligation_signature == obligation_sig:
        _rec.record_command(conn, case_id, case_id, "B7_HANDOFF_RECORDED",
                            _B7_HANDOFF, command, payload_fp,
                            {"handoff": prior.model_dump(mode="json"),
                             "no_op": True}, clock.now_iso())
        return prior.model_copy(update={"idempotent_replay": True})
    now_dt = clock.utcnow()
    valid_until = None
    grant = _q.grant_for_action(b7, decision, effective_b7_time(b7))
    if grant is not None:
        valid_until = getattr(grant, "effective_until", None)
    handoff_view = B7HandoffView(
        id=_rec.new_id("BH-"), case_id=case_id,
        decision_id=decision.id, report_id=case["current_run_id"] or "",
        employee_ref=submission.employee_ref,
        work_ref=submission.work_ref, actor_id=command.actor_id,
        direction=decision.target.direction, remaining_vnd=remaining,
        obligation_signature=obligation_sig,
        business_signature=business_sig,
        receipt_history_signature=receipt_sig,
        refs=[decision.id, decision.basis_report_id],
        created_at=now_dt, valid_until=valid_until)
    _rec.record_command(conn, case_id, case_id, "B7_HANDOFF_RECORDED",
                        _B7_HANDOFF, command, payload_fp,
                        {"handoff": handoff_view.model_dump(mode="json")},
                        clock.iso(now_dt))
    return handoff_view


def close(conn: sqlite3.Connection, artifact_root: Path, case_id: str,
          payload, command: Command, b3, policy: dict) -> B7ClosureView:
    """Close a linked settlement only when every gate holds, in the txn."""
    from invoice_referee.settlement.settlement_reconciliation import (
        b7_closure_blockers, closure_matches,
    )

    payload_fp = fingerprint(_B7_CLOSE, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_CLOSE, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return B7ClosureView.model_validate(
            _rec.load(row["payload_json"])["closure"]).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    if case["stage"] in _CLOSED_STAGES:
        existing = conn.execute(
            "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
            "ORDER BY rowid DESC LIMIT 1", (case_id, _B7_CLOSE)).fetchone()
        if existing is not None:
            stored = B7ClosureView.model_validate(
                _rec.load(existing["payload_json"])["closure"])
            if closure_matches(stored, payload):
                _rec.record_command(conn, case_id, case_id, "B7_SETTLEMENT_CLOSED",
                                    _B7_CLOSE, command, payload_fp,
                                    {"closure": stored.model_dump(mode="json"),
                                     "no_op": True}, clock.now_iso())
                return stored.model_copy(update={"idempotent_replay": True})
        raise DomainError(
            "CASE_CLOSED",
            "Hồ sơ đã đóng; nguồn mới cần hồ sơ điều chỉnh liên kết.")
    _rec.check_version(case, command)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID", "Đóng chỉ áp dụng cho hồ sơ liên kết.")
    _q.require_accountant_route(conn, case, command, b3)
    decision = _q.current_decision(conn, case_id)
    # Closure relies on the decision's stored authority snapshot; an
    # expired grant after a valid completed action does not erase the
    # actuals or force a ritual re-approval to close (spec §6.2). New
    # obligations still require a current grant at handoff time.
    report = None
    run = None
    if payload.current_report_id:
        run = conn.execute("SELECT * FROM runs WHERE id = ? AND case_id = ?",
                           (payload.current_report_id, case_id)).fetchone()
        if run is not None and run["status"] == "SUCCEEDED" \
                and run["report_json"]:
            report = Report.model_validate(_rec.load(run["report_json"]))
    summary = _q.fulfillment(conn, case_id)
    reval = _q.current_revalidation(conn, case_id)
    snapshot = _lc.load_context(
        conn, artifact_root, _lc.context_source_ids(conn, case_id)[-1])
    scope_current = bool(
        report is not None and case["current_run_id"] == payload.current_report_id
        and run["input_revision"] == case["input_revision"]
        and run["control_epoch"] == case["control_epoch"])
    coverage_current = bool(snapshot.company_packet is not None
                            and snapshot.company_packet.coverage.complete_prior_history
                            and not snapshot.company_packet.coverage.missing_ranges)
    parent_stop = bool(_rec.case_row(
        conn, _lc.origin_link(case)["origin_case_id"])["stop_active"])
    blockers = b7_closure_blockers(
        report=report, decision=decision, fulfillment=summary,
        revalidation=reval, scope_current=scope_current,
        coverage_current=coverage_current,
        stop_active=bool(case["stop_active"]) or parent_stop,
        open_question_count=_q.open_question_count(conn, case_id))
    if decision is None or payload.decision_id != decision.id:
        blockers.append("decision_id không khớp quyết định hiện hành.")
    if blockers:
        raise DomainError(
            "B7_CLOSURE_BLOCKED",
            "Không đóng được hồ sơ quyết toán: " + "; ".join(blockers))
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    from invoice_referee.settlement.settlement_workflow import b7_business_signature
    business_sig = b7_business_signature(
        submission, _rec.source_records(conn, case_id), report, policy, snapshot)
    now_dt = clock.utcnow()
    closure_view = B7ClosureView(
        id=_rec.new_id("BC-"), case_id=case_id,
        decision_id=decision.id, current_report_id=payload.current_report_id,
        actor_id=command.actor_id, kind="SETTLEMENT_COMPLETE",
        employee_ref=submission.employee_ref, work_ref=submission.work_ref,
        close_as_of=submission.money_as_of,
        knowledge_cutoff=submission.knowledge_cutoff, created_at=now_dt,
        input_revision=case["input_revision"],
        control_epoch=case["control_epoch"], business_signature=business_sig,
        receipt_history_signature=_q.receipt_signature(conn, case_id),
        parent_fingerprint=_lc.parent_fingerprint(
            conn, _lc.origin_link(case)["origin_case_id"], _q._b3_workflow_of,
            _adv.advance_events),
        source_refs=list(report.source_refs) if report else [],
        event_ids=[e.id for e in _q.money_events(conn, case_id)
                   if e.classification == "CONFIRMED_RECEIPT"],
        original_decision_id=decision.id,
        revalidation_ref=(reval.current_report_id if reval else None),
        reason=payload.reason)
    conn.execute(
        "UPDATE cases SET stage = 'SETTLEMENT_CLOSED', case_version = ?, "
        "updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, clock.iso(now_dt), case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_SETTLEMENT_CLOSED",
                        _B7_CLOSE, command, payload_fp,
                        {"closure": closure_view.model_dump(mode="json")},
                        clock.iso(now_dt))
    return closure_view


def prepare_adjustment(conn: sqlite3.Connection, closed_case_id: str, payload,
                       command: Command, b3) -> tuple[str, bool]:
    """Open a post-closure adjustment child for a closed settlement.

    The closed case is never mutated; a NEW linked B7 child is created with
    the same employee/work/B3 and an ``adjustment_of_case_id`` origin link.
    Only one active settlement exists per employee/work: an existing active
    child is reused rather than duplicated. Returns ``(child_id, replay)``.
    """
    payload_fp = fingerprint(_B7_ADJUSTMENT, {
        "closed_case_id": closed_case_id,
        "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_ADJUSTMENT, command,
                              scope_key=closed_case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return _rec.load(row["payload_json"])["child_id"], True
    closed = _rec.case_row(conn, closed_case_id)
    if closed["stage"] not in _CLOSED_STAGES:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Chỉ hồ sơ đã đóng mới mở hồ sơ điều chỉnh.")
    link = _lc.origin_link(closed)
    if link is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Điều chỉnh chỉ áp dụng cho hồ sơ quyết toán liên kết.")
    _rec.check_version(closed, command)
    _q.require_accountant_route(conn, closed, command, b3)
    parent_id = link["origin_case_id"]
    # One active settlement per employee/work: reuse if one is open.
    active = _lc.find_linked_child(conn, parent_id)
    if active is not None:
        return active["id"], False
    now_dt = clock.utcnow()
    now = clock.iso(now_dt)
    prefix = f"QT-{now_dt.strftime('%y%m')}-"
    child_id = _rec.new_case_id(conn, prefix)
    new_link = {
        "origin_case_id": parent_id,
        "employee_ref": link["employee_ref"], "work_ref": link["work_ref"],
        "created_at": now, "adjustment_of_case_id": closed_case_id,
    }
    form = {"schema_version": "b7-linked-intake-v1", "confirmed": False,
            "expense_rows": [], "note": payload.reason, "origin_link": new_link}
    submission = Submission(
        employee_ref=link["employee_ref"], work_ref=link["work_ref"],
        job="B7", money_as_of=now_dt, knowledge_cutoff=now_dt, form=form)
    conn.execute(
        "INSERT INTO cases (id, case_version, input_revision, control_epoch, "
        "stop_active, stage, current_run_id, submission_json, origin, "
        "created_at, updated_at) "
        "VALUES (?, 1, 1, 1, 0, 'CHECKING', NULL, ?, 'USER', ?, ?)",
        (child_id, _rec.dump(submission.model_dump(mode="json")), now, now),
    )
    conn.execute(
        "INSERT INTO case_revisions (id, case_id, revision, submission_json, "
        "reason, actor_id, command_key, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
        (_rec.new_id("R-"), child_id,
         _rec.dump(submission.model_dump(mode="json")), payload.reason,
         command.actor_id, command.key, now),
    )
    _rec.record_command(conn, child_id, closed_case_id, "B7_ADJUSTMENT_PREPARED",
                        _B7_ADJUSTMENT, command, payload_fp,
                        {"child_id": child_id,
                         "adjustment_of_case_id": closed_case_id}, now)
    return child_id, False
