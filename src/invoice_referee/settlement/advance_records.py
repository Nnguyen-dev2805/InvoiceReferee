"""Advance (B3) lifecycle records: present-and-approve and advance receipts.

Every function takes an already-open ``sqlite3.Connection``. The ``Store``
façade owns the connection/transaction boundary, so each financial check and
write stays atomic inside one ``BEGIN IMMEDIATE``. Nothing here opens its own
connection, commits, or reads financial policy beyond the context passed in.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement import sqlite_records as _rec
from invoice_referee.settlement.advance_workflow import (
    b3_basis_signature,
    b3_context_signature,
    b3_route_for,
)
from invoice_referee.settlement.b3 import B3CompanyContext, is_b3_v1
from invoice_referee.settlement.models import (
    B3AdvanceEventPayload,
    B3AdvanceEventView,
    B3DecisionPayload,
    B3DecisionView,
    B3FundingIncident,
    B3PresentPayload,
    B3PresentationView,
    B3WorkflowView,
    CaseStage,
    Command,
    Report,
    Submission,
    fingerprint,
)

_B3_PRESENT = "B3_PRESENT"
_B3_DECIDE = "B3_DECIDE"
_B3_ADD_ADVANCE_PROOF = "B3_ADD_ADVANCE_PROOF"
_B3_RECORD_ADVANCE = "B3_RECORD_ADVANCE"
_NONTERMINAL_STATUSES = ("QUEUED", "RUNNING")
_OPEN_QUESTION_STATUSES = ("OPEN", "ANSWERED")


def _iso(value: datetime) -> str:
    from datetime import timezone
    return value.astimezone(timezone.utc).isoformat()


def _now_iso() -> str:
    from invoice_referee.settlement.store import utcnow
    return _iso(utcnow())


def b3_case_form(case: sqlite3.Row) -> dict[str, Any]:
    form = _rec.load(case["submission_json"]).get("form")
    if not is_b3_v1(form):
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Trình duyệt/quyết định B3 chỉ áp dụng cho hồ sơ b3-intake-v1.",
        )
    return form


def b3_report_ready(conn: sqlite3.Connection, case_id: str,
                    basis_report_id: str) -> tuple[sqlite3.Row, Report]:
    """Resolve a current, COMPLETE, READY_FOR_ACCOUNTANT_REVIEW basis.

    Raises BASIS_MISMATCH/BASIS_STALE so a presentation/decision can never
    bind to another case's report, a stale revision or a not-ready report.
    """
    run = conn.execute("SELECT * FROM runs WHERE id = ?",
                       (basis_report_id,)).fetchone()
    if run is None or run["case_id"] != case_id:
        raise DomainError(
            "BASIS_MISMATCH",
            f"Report basis {basis_report_id} không thuộc hồ sơ {case_id}.",
        )
    case = _rec.case_row(conn, case_id)
    if run["status"] != "SUCCEEDED" or not run["report_json"]:
        raise DomainError(
            "BASIS_MISMATCH",
            f"Run basis {basis_report_id} chưa SUCCEEDED có report.",
        )
    if (case["current_run_id"] != basis_report_id
            or run["input_revision"] != case["input_revision"]
            or run["control_epoch"] != case["control_epoch"]):
        raise DomainError(
            "BASIS_STALE",
            "Report basis đã cũ (input/epoch đã đổi hoặc run khác là "
            "current); chạy và rà soát lại trước khi trình/quyết định.",
        )
    report = Report.model_validate(_rec.load(run["report_json"]))
    proposal = report.b3
    if report.completion != "COMPLETE" or proposal is None \
            or proposal.readiness != "READY_FOR_ACCOUNTANT_REVIEW":
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Report basis chưa sẵn sàng cho kế toán (cần COMPLETE và "
            "READY_FOR_ACCOUNTANT_REVIEW).",
        )
    return run, report


def b3_has_open_question(conn: sqlite3.Connection, case_id: str) -> bool:
    for row in conn.execute(
            "SELECT payload_json FROM interactions "
            "WHERE case_id = ? AND kind = 'QUESTION'", (case_id,)):
        if _rec.load(row["payload_json"])["status"] in _OPEN_QUESTION_STATUSES:
            return True
    return False


def b3_active_run(conn: sqlite3.Connection, case_id: str) -> bool:
    return conn.execute(
        "SELECT COUNT(*) FROM runs WHERE case_id = ? AND status IN (?, ?)",
        (case_id, *_NONTERMINAL_STATUSES)).fetchone()[0] > 0


def b3_find_review(conn: sqlite3.Connection, case_id: str,
                   review_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM interactions WHERE id = ? AND case_id = ? "
        "AND kind = 'REVIEW'", (review_id, case_id)).fetchone()
    if row is None:
        raise DomainError(
            "BASIS_MISMATCH",
            f"Review {review_id} không thuộc hồ sơ {case_id}.",
        )
    return _rec.load(row["payload_json"])


def b3_other_active_approval(conn: sqlite3.Connection, employee_ref: str,
                             work_ref: str, exclude_case_id: str) -> str | None:
    """A current B3 APPROVE for the same employee/work in another case.

    The match is by explicit employee/work scope, never guessed from a
    duplicated purpose or filename; only records this store manages count.
    """
    for row in conn.execute(
            "SELECT payload_json FROM decisions ORDER BY rowid"):
        payload = _rec.load(row["payload_json"])
        if payload.get("kind") != "B3_ADVANCE" \
                or payload.get("outcome") != "APPROVE":
            continue
        if payload.get("employee_ref") != employee_ref \
                or payload.get("work_ref") != work_ref:
            continue
        if payload.get("case_id") == exclude_case_id:
            continue
        return payload.get("id")
    return None


def advance_events(conn: sqlite3.Connection,
                   case_id: str) -> list[B3AdvanceEventView]:
    """All persisted B3 advance events for a case, oldest first."""
    events: list[B3AdvanceEventView] = []
    for row in conn.execute(
            "SELECT payload_json FROM money_events WHERE case_id = ? "
            "ORDER BY rowid", (case_id,)):
        payload = _rec.load(row["payload_json"])
        if payload.get("kind") != "ADVANCE_TO_EMPLOYEE":
            continue
        events.append(B3AdvanceEventView.model_validate(payload))
    return events


def advance_proof_source_ids(conn: sqlite3.Connection,
                             case_id: str) -> set[str]:
    """Source ids the backend recorded as B5 advance proof (audit-backed).

    Trusted by the audit operation's recorded ``source_id`` — not by a
    client-supplied provenance string or filename.
    """
    ids: set[str] = set()
    for row in conn.execute(
            "SELECT payload_json FROM audit_events WHERE case_id = ? "
            "AND operation = ?", (case_id, _B3_ADD_ADVANCE_PROOF)):
        source_id = _rec.load(row["payload_json"]).get("source_id")
        if source_id:
            ids.add(source_id)
    return ids


def workflow_view(conn: sqlite3.Connection,
                  case_id: str) -> B3WorkflowView | None:
    """Derive the B3 workflow projection from records (not free text)."""
    case = _rec.case_row(conn, case_id)
    if not is_b3_v1(_rec.load(case["submission_json"]).get("form")):
        return None
    pres_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B3_PRESENT)).fetchone()
    dec_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B3_DECIDE)).fetchone()
    presentation = None
    if pres_row is not None:
        presentation = B3PresentationView.model_validate(
            _rec.load(pres_row["payload_json"])["presentation"])
    decision = None
    if dec_row is not None:
        decision = B3DecisionView.model_validate(
            _rec.load(dec_row["payload_json"])["decision"])
    # A decision only governs the presentation it was made on. If a newer
    # presentation exists, the older decision is superseded history (except
    # REFUSE, which stays effective until a separate reopen action).
    decision_for_status = decision
    if decision is not None and decision.outcome != "REFUSE" \
            and (presentation is None
                 or decision.presentation_id != presentation.id):
        decision_for_status = None
    basis_current = False
    blocked: str | None = None
    if presentation is not None:
        run = conn.execute("SELECT * FROM runs WHERE id = ?",
                           (presentation.basis_report_id,)).fetchone()
        basis_current = bool(
            run is not None and run["status"] == "SUCCEEDED"
            and case["current_run_id"] == presentation.basis_report_id
            and run["input_revision"] == case["input_revision"]
            and run["control_epoch"] == case["control_epoch"])
        if not basis_current:
            blocked = ("Căn cứ đã đổi (nguồn/revision/epoch); cần chạy và "
                       "trình lại trước khi quyết định.")
    # A RETURN is addressed once a newer run has become current; the old
    # presentation is no longer pending and the case needs a fresh one.
    if decision_for_status is not None \
            and decision_for_status.outcome == "RETURN" \
            and case["current_run_id"] != decision_for_status.basis_report_id:
        decision_for_status = None
    status = "NOT_PRESENTED"
    if decision_for_status is not None:
        if decision_for_status.outcome == "APPROVE":
            status = "APPROVED" if basis_current else "NEEDS_RECHECK"
        elif decision_for_status.outcome == "RETURN":
            status = "RETURNED"
        else:
            status = "REFUSED"
    elif presentation is not None:
        status = "PENDING" if basis_current else "NEEDS_RECHECK"
    from invoice_referee.settlement.advance_reconciliation import project_b3_funding

    events = advance_events(conn, case_id)
    funding = None
    has_approval = (decision_for_status is not None
                    and decision_for_status.outcome == "APPROVE")
    if has_approval or events:
        funding = project_b3_funding(decision_for_status, events,
                                     bool(case["stop_active"]))
    return B3WorkflowView(
        status=status,
        presentation=presentation,
        decision=decision_for_status,
        basis_current=basis_current,
        blocked_reason=blocked,
        accountant_ref=(presentation.accountant_ref if presentation else None),
        approver_ref=(presentation.approver_ref if presentation else None),
        funding=funding,
        advance_events=events,
    )


def record_presentation(conn: sqlite3.Connection, case_id: str,
                        payload: B3PresentPayload, command: Command,
                        context: B3CompanyContext,
                        policy: dict) -> B3PresentationView:
    """Accountant routes a confirmed B3 basis to the configured approver.

    Saves a new review (note+refs) or reuses a stored one, in ONE
    transaction with the presentation. Stage AWAITING_DECISION; the
    presentation stores a basis signature so a later source/context change
    makes it stale. No money/handoff/closure is created.
    """
    payload_fp = fingerprint(_B3_PRESENT, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B3_PRESENT, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["presentation"]
        return B3PresentationView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    b3_case_form(case)
    if case["stop_active"]:
        raise DomainError("STOP_ACTIVE", "Hồ sơ đang Stop; không trình duyệt mới.")
    _rec.check_version(case, command)
    if not (context.activated):
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            "Company context B3 chưa active; không trình duyệt.")
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    route = b3_route_for(context, submission.employee_ref)
    if (command.demo_role != "ACCOUNTANT" or route is None
            or route.accountant_ref != command.actor_id):
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.demo_role}/{command.actor_id} không phải kế "
            f"toán được phân công cho {submission.employee_ref}; không "
            f"trình duyệt.",
        )
    b3_report_ready(conn, case_id, payload.basis_report_id)
    if b3_has_open_question(conn, case_id):
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Còn câu hỏi/issue chưa được re-check xử lý; chưa trình "
            "duyệt được.",
        )
    if b3_active_run(conn, case_id):
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Hồ sơ đang có run chưa kết thúc; chờ rồi mới trình duyệt.",
        )
    # An active approval for the same employee/work elsewhere blocks a
    # parallel first advance (dedup within managed records only).
    other = b3_other_active_approval(
        conn, submission.employee_ref, submission.work_ref, case_id)
    if other is not None:
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            f"Công việc {submission.work_ref} đã có quyết định ứng "
            f"đang hiệu lực ({other}); không trình thêm đề nghị song song.",
        )
    # An existing decision (APPROVED/REFUSED) must not be bypassed by a
    # new presentation; RETURN/stale already cleared the old pending.
    current = workflow_view(conn, case_id)
    if current is not None and current.decision is not None \
            and current.decision.outcome in ("APPROVE", "REFUSE"):
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Đã có quyết định cho đề nghị này; điều chỉnh/mở lại là "
            "hành động cần quyền riêng chưa hỗ trợ.",
        )
    sources = _rec.source_records(conn, case_id)
    report = b3_report_ready(conn, case_id, payload.basis_report_id)[1]
    basis_sig = b3_basis_signature(submission, sources, report, policy, context)
    ctx_sig = b3_context_signature(context)
    # Idempotent re-present with the same basis while still pending:
    # return the pending record, don't create a second parallel one.
    # After a RETURN/REFUSE decision, a new presentation must follow a
    # fresh run (new basis), never replay the returned one.
    if (current is not None and current.decision is None
            and current.presentation is not None
            and current.presentation.basis_signature == basis_sig):
        return current.presentation.model_copy(
            update={"idempotent_replay": True})
    if (current is not None and current.decision is not None
            and current.decision.outcome == "RETURN"
            and current.presentation is not None
            and current.presentation.basis_signature == basis_sig):
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Đề nghị đã bị yêu cầu bổ sung; nhân viên phải sửa/xác "
            "nhận và chạy lại trước khi trình lại (basis chưa đổi).",
        )
    now = _now_iso()
    if payload.review_id is not None:
        review = b3_find_review(conn, case_id, payload.review_id)
        if review["report_id"] != payload.basis_report_id \
                or review["actor_id"] != command.actor_id:
            raise DomainError(
                "BASIS_MISMATCH",
                "Review đã lưu không thuộc basis report hoặc không do "
                "kế toán này tạo.",
            )
        review_id = payload.review_id
    else:
        review = {
            "id": f"RV-{uuid.uuid4().hex[:12]}", "case_id": case_id,
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
        "id": f"PR-{uuid.uuid4().hex[:12]}", "case_id": case_id,
        "basis_report_id": payload.basis_report_id,
        "review_id": review_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref,
        "accountant_ref": route.accountant_ref,
        "approver_ref": route.approver_ref,
        "basis_input_revision": case["input_revision"],
        "basis_control_epoch": case["control_epoch"],
        "basis_signature": basis_sig,
        "context_signature": ctx_sig,
        "created_at": now,
    }
    conn.execute(
        "UPDATE cases SET stage = 'AWAITING_DECISION', case_version = ?, "
        "updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B3_PRESENTED",
                        _B3_PRESENT, command, payload_fp,
                        {"presentation": presentation, "review": review}, now)
    return B3PresentationView.model_validate(presentation)


def record_decision(conn: sqlite3.Connection, case_id: str,
                    payload: B3DecisionPayload, command: Command,
                    context: B3CompanyContext, policy: dict, grant_ref: str,
                    effective_at: datetime) -> B3DecisionView:
    """Record an approver's B3 outcome on a current pending presentation.

    Authority is resolved by the caller from the trusted context (never a
    client dict) and passed as ``grant_ref``. APPROVE → AWAITING_MONEY;
    RETURN → CHECKING; REFUSE → ADVANCE_REQUEST_REFUSED. No money event.
    """
    payload_fp = fingerprint(_B3_DECIDE, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B3_DECIDE, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["decision"]
        return B3DecisionView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    b3_case_form(case)
    if case["stop_active"]:
        raise DomainError(
            "STOP_ACTIVE", "Hồ sơ đang Stop; không ghi quyết định B3 mới.")
    _rec.check_version(case, command)
    current = workflow_view(conn, case_id)
    if current is None or current.presentation is None:
        raise DomainError(
            "B3_WORKFLOW_BLOCKED",
            "Chưa có presentation để quyết định; kế toán phải trình trước.",
        )
    if current.decision is not None:
        raise DomainError(
            "B3_DECISION_EXISTS",
            "Đề nghị này đã có quyết định; điều chỉnh/thay thế chưa hỗ trợ.",
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
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    route = b3_route_for(context, submission.employee_ref)
    if route is None or route.approver_ref != command.actor_id:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.actor_id} không phải người duyệt được phân "
            f"công cho {submission.employee_ref}.",
        )
    if payload.outcome == "APPROVE":
        proposal = b3_report_ready(
            conn, case_id, presentation.basis_report_id)[1].b3
        forecast_total = proposal.forecast_total_vnd
        forecast_employee = proposal.forecast_employee_vnd
        requested = proposal.intake.request_amount_vnd
        if forecast_total is not None and payload.budget_vnd is not None \
                and payload.budget_vnd < forecast_total:
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Budget duyệt thấp hơn tổng forecast hiện tại; RETURN để "
                "sửa và kiểm lại.",
            )
        if requested is not None and payload.advance_vnd is not None \
                and payload.advance_vnd > requested:
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Số ứng duyệt cao hơn số xin; RETURN để sửa và kiểm lại.",
            )
        if forecast_employee is not None and payload.advance_vnd is not None \
                and payload.advance_vnd > forecast_employee:
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Số ứng duyệt cao hơn phần employee forecast; RETURN để "
                "sửa và kiểm lại.",
            )
    now = _now_iso()
    decision = {
        "id": f"BD-{uuid.uuid4().hex[:12]}", "case_id": case_id,
        "kind": "B3_ADVANCE", "presentation_id": presentation.id,
        "outcome": payload.outcome, "reason": payload.reason,
        "work_allowed": payload.work_allowed,
        "budget_vnd": payload.budget_vnd,
        "advance_vnd": payload.advance_vnd,
        "basis_report_id": presentation.basis_report_id,
        "basis_review_id": presentation.review_id,
        "basis_input_revision": presentation.basis_input_revision,
        "basis_control_epoch": presentation.basis_control_epoch,
        "basis_signature": presentation.basis_signature,
        "context_signature": presentation.context_signature,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref, "actor_id": command.actor_id,
        "grant_ref": grant_ref, "effective_at": _iso(effective_at),
        "created_at": now,
    }
    conn.execute(
        "INSERT INTO decisions (id, case_id, payload_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (decision["id"], case_id, _rec.dump(decision), now),
    )
    if payload.outcome == "APPROVE":
        new_stage: CaseStage = "AWAITING_MONEY"
    elif payload.outcome == "RETURN":
        new_stage = "CHECKING"
    else:
        new_stage = "ADVANCE_REQUEST_REFUSED"
    conn.execute(
        "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
        "WHERE id = ?",
        (new_stage, case["case_version"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B3_DECISION_RECORDED",
                        _B3_DECIDE, command, payload_fp,
                        {"decision": decision}, now)
    return B3DecisionView.model_validate(decision)


def record_receipt(conn: sqlite3.Connection, case_id: str,
                   payload: B3AdvanceEventPayload, command: Command,
                   context: B3CompanyContext) -> B3AdvanceEventView:
    """Record an actual advance money event with human-source evidence.

    Allowed under Stop/stale (the fact already happened) but never opens a
    new payment right or advances the stage past Stop. Records are immutable
    and append-only; a pending/nonfinal record is superseded by a new one,
    never overwritten. The raw gross is kept, never clipped to approval.
    """
    from invoice_referee.settlement.advance_reconciliation import (
        derive_classification, project_b3_funding,
    )

    payload_fp = fingerprint(_B3_RECORD_ADVANCE, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B3_RECORD_ADVANCE, command,
                              scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["event"]
        return B3AdvanceEventView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    b3_case_form(case)
    _rec.check_version(case, command)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    route = b3_route_for(context, submission.employee_ref)
    if (command.demo_role != "ACCOUNTANT" or route is None
            or route.accountant_ref != command.actor_id):
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.demo_role}/{command.actor_id} không phải kế "
            f"toán được phân công cho {submission.employee_ref}; không "
            f"ghi sự kiện ứng.",
        )
    # Evidence sources must resolve to this case's retained sources.
    case_source_ids = {s.id for s in _rec.source_records(conn, case_id)}
    for field in payload.evidence:
        if field.source_id not in case_source_ids:
            raise DomainError(
                "BASIS_MISMATCH",
                f"Nguồn căn cứ {field.source_id} không thuộc hồ sơ {case_id}.",
            )
    # A decision_id, when given, must belong to this case/employee/work.
    decision = None
    if payload.decision_id is not None:
        dec_row = conn.execute(
            "SELECT payload_json FROM decisions WHERE id = ? AND case_id = ?",
            (payload.decision_id, case_id)).fetchone()
        if dec_row is not None:
            candidate = _rec.load(dec_row["payload_json"])
            if candidate.get("kind") == "B3_ADVANCE" \
                    and candidate.get("employee_ref") == submission.employee_ref \
                    and candidate.get("work_ref") == submission.work_ref:
                decision = B3DecisionView.model_validate(candidate)
    incidents: list[B3FundingIncident] = []
    if payload.decision_id is not None and decision is None:
        incidents.append(B3FundingIncident(
            kind="UNAUTHORIZED_OR_UNALLOCATED", event_ids=[], refs=[],
            amount_vnd=payload.gross_vnd,
            reason="decision_id không thuộc hồ sơ/người/công việc này."))
    # Wrong recipient: money reached someone other than the employee.
    if (payload.reported_status == "RECEIVED"
            and payload.payee_ref is not None
            and payload.payee_ref != submission.employee_ref):
        incidents.append(B3FundingIncident(
            kind="WRONG_RECIPIENT", event_ids=[], refs=[],
            amount_vnd=payload.gross_vnd,
            reason=(f"Người nhận {payload.payee_ref} không phải nhân viên "
                    f"{submission.employee_ref}; giữ raw, không tính "
                    f"thực nhận cho nhân viên.")))
    classification = derive_classification(
        payload, submission.employee_ref, incidents)
    existing = advance_events(conn, case_id)
    # Same economic event (namespace+ref) already confirmed RECEIVED:
    # a new RECEIVED for the same identity is a conflicting outcome, not
    # a second payment.
    if (payload.reported_status == "RECEIVED"
            and payload.event_namespace is not None
            and payload.event_ref is not None):
        for prior in existing:
            if (prior.event_namespace == payload.event_namespace
                    and prior.event_ref == payload.event_ref
                    and prior.reported_status == "RECEIVED"
                    and prior.classification == "CONFIRMED_RECEIPT"):
                incidents.append(B3FundingIncident(
                    kind="CONFLICTING_OUTCOME",
                    event_ids=[prior.id], refs=[],
                    amount_vnd=payload.gross_vnd,
                    reason=("Cùng giao dịch đã có kết quả RECEIVED xác "
                            "nhận; giữ cả hai, cần kế toán xử lý.")))
                classification = "CONFLICT"
    now = _now_iso()
    event = {
        "id": f"AE-{uuid.uuid4().hex[:12]}", "case_id": case_id,
        "kind": "ADVANCE_TO_EMPLOYEE",
        "decision_id": payload.decision_id,
        "event_namespace": payload.event_namespace,
        "event_ref": payload.event_ref, "method": payload.method,
        "gross_vnd": payload.gross_vnd, "payer_side": payload.payer_side,
        "payee_ref": payload.payee_ref,
        "event_at": _iso(payload.event_at) if payload.event_at else None,
        "reported_status": payload.reported_status,
        "evidence": [e.model_dump(mode="json") for e in payload.evidence],
        "allocation_note": payload.allocation_note,
        "supersedes_event_id": payload.supersedes_event_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref,
        "classification": classification,
        "actor_id": command.actor_id, "created_at": now,
        "after_money_cutoff": bool(
            payload.event_at is not None
            and payload.event_at > submission.money_as_of),
        "incidents": [i.model_dump(mode="json") for i in incidents],
    }
    conn.execute(
        "INSERT INTO money_events (id, case_id, payload_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (event["id"], case_id, _rec.dump(event), now),
    )
    # Stage projection: only advance when the funding state is clean.
    view_events = existing + [B3AdvanceEventView.model_validate(event)]
    summary = project_b3_funding(decision, view_events,
                                 bool(case["stop_active"]))
    new_stage: CaseStage = case["stage"]
    if decision is not None and not case["stop_active"]:
        if summary.status == "FULFILLED":
            new_stage = "AWAITING_WORK_SETTLEMENT"
        elif summary.status == "NEEDS_RESOLUTION":
            new_stage = "RESOLVING_OBLIGATIONS"
        elif summary.status in ("PARTIAL", "PENDING", "UNCONFIRMED",
                                "NOT_RECORDED"):
            new_stage = "AWAITING_MONEY"
    conn.execute(
        "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
        "WHERE id = ?",
        (new_stage, case["case_version"] + 1, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B3_ADVANCE_EVENT_RECORDED",
                        _B3_RECORD_ADVANCE, command, payload_fp,
                        {"event": event}, now)
    return B3AdvanceEventView.model_validate(event)
