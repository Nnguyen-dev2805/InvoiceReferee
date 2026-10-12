"""Settlement (B7) lifecycle records: presentation/decision, B9 money
fulfillment, revalidation, handoff, closure and post-closure adjustment.

Functions take an already-open ``sqlite3.Connection`` (plus ``artifact_root``
where a file is needed). The ``Store`` façade owns the transaction boundary, so
every financial check and write stays atomic inside one ``BEGIN IMMEDIATE``.
Shared parent/B3 reads call ``advance_records``; context calls
``linked_context_records``. There is no reverse dependency.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement import sqlite_records as _rec
from invoice_referee.settlement import advance_records as _adv
from invoice_referee.settlement import linked_context_records as _lc
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

_B7_CONTEXT_REFRESH = "B7_CONTEXT_REFRESH"
_B7_MONEY_CONTEXT_REFRESH = "B7_MONEY_CONTEXT_REFRESH"
_B7_PRESENT = "B7_PRESENT"
_B7_DECIDE = "B7_DECIDE"
_B7_ADD_SETTLEMENT_PROOF = "B7_ADD_SETTLEMENT_PROOF"
_B7_RECORD_MONEY = "B7_RECORD_MONEY"
_B7_REVALIDATE = "B7_REVALIDATE"
_B7_HANDOFF = "B7_HANDOFF"
_B7_CLOSE = "B7_CLOSE"
_B7_ADJUSTMENT = "B7_ADJUSTMENT"
_B7_SETTLEMENT_PROOF_USE = "B7_SETTLEMENT_PROOF"
_CLOSED_STAGES: tuple[str, ...] = ("SETTLEMENT_CLOSED", "REJECTED_REQUEST_ENDED")
_OPEN_QUESTION_STATUSES = ("OPEN", "ANSWERED")


def _iso(value) -> str:
    from datetime import timezone
    return value.astimezone(timezone.utc).isoformat()


def _now_dt():
    from invoice_referee.settlement.store import utcnow
    return utcnow()


def _now() -> str:
    return _iso(_now_dt())


# --- reads -------------------------------------------------------------------

def workflow_view(conn: sqlite3.Connection,
                  case_id: str) -> B7WorkflowView | None:
    """Derive the settlement workflow projection from records."""
    case = _rec.case_row(conn, case_id)
    if _lc.origin_link(case) is None:
        return None
    pres_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B7_PRESENT)).fetchone()
    dec_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B7_DECIDE)).fetchone()
    presentation = None
    if pres_row is not None:
        presentation = B7PresentationView.model_validate(
            _rec.load(pres_row["payload_json"])["presentation"])
    decision = None
    if dec_row is not None:
        decision = B7DecisionView.model_validate(
            _rec.load(dec_row["payload_json"])["decision"])
    # A decision governs the presentation it was made on; a newer
    # presentation supersedes an older non-REFUSE decision.
    decision_for_status = decision
    if decision is not None and decision.outcome != "REFUSE" \
            and (presentation is None
                 or decision.presentation_id != presentation.id):
        decision_for_status = None
    basis_current = False
    blocked: list[str] = []
    if presentation is not None:
        run = conn.execute("SELECT * FROM runs WHERE id = ?",
                           (presentation.basis_report_id,)).fetchone()
        basis_current = bool(
            run is not None and run["status"] == "SUCCEEDED"
            and case["current_run_id"] == presentation.basis_report_id
            and run["input_revision"] == case["input_revision"]
            and run["control_epoch"] == case["control_epoch"])
        if not basis_current:
            blocked.append(
                "Căn cứ đã đổi (nguồn/revision/epoch); cần chạy và trình lại.")
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
    return B7WorkflowView(
        status=status, presentation=presentation,
        decision=decision_for_status, basis_current=basis_current,
        blocked_reasons=blocked,
        accountant_ref=(presentation.accountant_ref if presentation else None),
        approver_ref=(presentation.approver_ref if presentation else None),
        fulfillment=fulfillment(conn, case_id),
        revalidation=current_revalidation(conn, case_id),
        current_handoff=latest_handoff(conn, case_id),
        closure=closure(conn, case_id),
    )


def settlement_proof_source_ids(conn: sqlite3.Connection,
                                case_id: str) -> set[str]:
    """Source ids the backend recorded as B9 proof (audit-backed)."""
    ids: set[str] = set()
    for row in conn.execute(
            "SELECT payload_json FROM audit_events WHERE case_id = ? "
            "AND operation = ?", (case_id, _B7_ADD_SETTLEMENT_PROOF)):
        source_id = _rec.load(row["payload_json"]).get("source_id")
        if source_id:
            ids.add(source_id)
    return ids


def money_events(conn: sqlite3.Connection,
                 case_id: str) -> list[B7MoneyEventView]:
    """All persisted B9 settlement money events for a case, oldest first."""
    events: list[B7MoneyEventView] = []
    for row in conn.execute(
            "SELECT payload_json FROM money_events WHERE case_id = ? "
            "ORDER BY rowid", (case_id,)):
        payload = _rec.load(row["payload_json"])
        if payload.get("kind") != "B7_SETTLEMENT_EVENT":
            continue
        events.append(B7MoneyEventView.model_validate(payload))
    return events


def current_decision(conn: sqlite3.Connection,
                     case_id: str) -> B7DecisionView | None:
    """The decision governing the current presentation, if any.

    Mirrors ``workflow_view``'s rule (a newer presentation supersedes an
    older non-REFUSE decision) without calling it, so fulfillment can derive
    the governing decision without a recursion cycle.
    """
    pres_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B7_PRESENT)).fetchone()
    dec_row = conn.execute(
        "SELECT * FROM audit_events WHERE case_id = ? AND operation = ? "
        "ORDER BY rowid DESC LIMIT 1", (case_id, _B7_DECIDE)).fetchone()
    if dec_row is None:
        return None
    decision = B7DecisionView.model_validate(
        _rec.load(dec_row["payload_json"])["decision"])
    presentation = None
    if pres_row is not None:
        presentation = B7PresentationView.model_validate(
            _rec.load(pres_row["payload_json"])["presentation"])
    if decision.outcome != "REFUSE" \
            and (presentation is None
                 or decision.presentation_id != presentation.id):
        return None
    return decision


def fulfillment(conn: sqlite3.Connection,
                case_id: str) -> B7FulfillmentSummary | None:
    """Decision-scoped fulfillment projection from the store's own events."""
    from invoice_referee.settlement.settlement_reconciliation import (
        canonical_event_id, project_b7_fulfillment, receipt_state,
    )

    decision = current_decision(conn, case_id)
    if decision is None or decision.outcome != "APPROVE" \
            or decision.target is None:
        return None
    events = money_events(conn, case_id)
    scoped = [e for e in events if e.decision_id == decision.id]
    receipts = [B7FulfillmentReceipt(
        event_id=e.id,
        canonical_id=canonical_event_id(e.event_namespace, e.event_ref, e.id),
        decision_id=e.decision_id or decision.id, amount_vnd=e.gross_vnd,
        state=receipt_state(e.classification),
        qualifying=e.classification == "CONFIRMED_RECEIPT",
        after_cutoff=e.after_cutoff, incidents=list(e.incidents))
        for e in scoped]
    case = _rec.case_row(conn, case_id)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    return project_b7_fulfillment(
        decision.id, decision.target.amount_vnd, decision.target.direction,
        receipts, as_of=submission.money_as_of,
        knowledge_cutoff=submission.knowledge_cutoff)


def current_revalidation(conn: sqlite3.Connection,
                         case_id: str) -> B7RevalidationView | None:
    row = conn.execute(
        "SELECT payload_json FROM audit_events WHERE case_id = ? AND "
        "operation = ? ORDER BY rowid DESC LIMIT 1",
        (case_id, _B7_REVALIDATE)).fetchone()
    if row is None:
        return None
    return B7RevalidationView.model_validate(
        _rec.load(row["payload_json"])["revalidation"])


def open_question_count(conn: sqlite3.Connection, case_id: str) -> int:
    count = 0
    for row in conn.execute(
            "SELECT payload_json FROM interactions WHERE case_id = ? AND "
            "kind = 'QUESTION'", (case_id,)):
        if _rec.load(row["payload_json"])["status"] in _OPEN_QUESTION_STATUSES:
            count += 1
    return count


def latest_handoff(conn: sqlite3.Connection,
                   case_id: str) -> B7HandoffView | None:
    row = conn.execute(
        "SELECT payload_json FROM audit_events WHERE case_id = ? AND "
        "operation = ? ORDER BY rowid DESC LIMIT 1",
        (case_id, _B7_HANDOFF)).fetchone()
    if row is None:
        return None
    return B7HandoffView.model_validate(_rec.load(row["payload_json"])["handoff"])


def closure(conn: sqlite3.Connection, case_id: str) -> B7ClosureView | None:
    row = conn.execute(
        "SELECT payload_json FROM audit_events WHERE case_id = ? AND "
        "operation = ? ORDER BY rowid DESC LIMIT 1",
        (case_id, _B7_CLOSE)).fetchone()
    if row is None:
        return None
    return B7ClosureView.model_validate(_rec.load(row["payload_json"])["closure"])


def receipt_signature(conn: sqlite3.Connection, case_id: str) -> str:
    from invoice_referee.settlement.settlement_reconciliation import canonical_event_id
    events = [e for e in money_events(conn, case_id)
              if e.classification == "CONFIRMED_RECEIPT"]
    ids = sorted(canonical_event_id(e.event_namespace, e.event_ref, e.id)
                 for e in events)
    return fingerprint("B7_RECEIPTS", {"ids": ids})


def grant_for(b7, decision):
    from invoice_referee.settlement.rules import covering_grant
    if b7 is None or not b7.activated or decision.target is None:
        return None
    scoped = [g for g in b7.grants if g.actor_ref == decision.actor_id]
    return covering_grant(
        scoped, decision.employee_ref, decision.work_ref,
        decision.effective_at, decision.target.employee_cost_vnd,
        decision.target.signed_net_vnd, decision.target.total_work_cost_vnd)


def require_accountant_route(conn: sqlite3.Connection, case: sqlite3.Row,
                             command: Command, b3) -> None:
    """Direct-Store guard: only the assigned accountant may act."""
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    route = b3_route_for(b3, submission.employee_ref) if b3 else None
    if (command.demo_role != "ACCOUNTANT" or route is None
            or route.accountant_ref != command.actor_id):
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {command.demo_role}/{command.actor_id} không phải kế toán "
            f"được phân công; không thao tác fulfillment/closure.",
        )


# --- writes ------------------------------------------------------------------

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
    parent_fp = _lc.parent_fingerprint(conn, parent_id, _b3_workflow_of,
                                       _adv.advance_events)
    current = workflow_view(conn, case_id)
    # Idempotent re-present while still pending and same basis.
    if (current is not None and current.decision is None
            and current.presentation is not None
            and current.presentation.business_signature == business_sig):
        return current.presentation.model_copy(update={"idempotent_replay": True})
    now = _now()
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
        authorize_b7_decision, b7_business_signature,
        b7_configuration_signature, effective_b7_time, settlement_target,
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
    current = workflow_view(conn, case_id)
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
    config_sig = b7_configuration_signature(b7, b3, policy)
    authority_sig = fingerprint("B7_AUTHORITY", {
        "grant_ref": getattr(grant, "actor_ref", None),
        "grant": grant.model_dump(mode="json"),
        "effective_at": _iso(effective_at)})
    history_baseline = None
    if target is not None:
        history_baseline = MoneyComponents(
            e=report.components.e.value, a=report.components.a.value,
            ra=report.components.ra.value, p=report.components.p.value,
            rp=report.components.rp.value)
    now = _now()
    decision = {
        "id": f"B7D-{uuid.uuid4().hex[:12]}", "case_id": case_id,
        "kind": "B7_SETTLEMENT", "outcome": payload.outcome,
        "reason": payload.reason,
        "presentation_id": presentation.id,
        "basis_report_id": presentation.basis_report_id,
        "basis_review_id": presentation.basis_review_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref, "actor_id": command.actor_id,
        "effective_at": _iso(effective_at), "created_at": now,
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
                        {"decision": decision}, now)
    return B7DecisionView.model_validate(decision)


def record_money(conn: sqlite3.Connection, case_id: str,
                 payload: B7MoneyEventPayload, command: Command, b7, b3,
                 policy: dict) -> B7MoneyEventView:
    """Record an actual settlement money event with human-source evidence.

    Allowed under Stop/stale (the fact already happened) but never opens a
    new payment right or advances past Stop. Records are immutable and
    append-only; a pending record is superseded by a later final one, never
    overwritten. The raw gross is kept, never clipped to the approval.
    """
    from invoice_referee.settlement.settlement_reconciliation import (
        canonical_event_id, classify_b7_money,
    )

    payload_fp = fingerprint(_B7_RECORD_MONEY, {
        "case_id": case_id, "payload": payload.model_dump(mode="json")})
    row = _rec.lookup_command(conn, _B7_RECORD_MONEY, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        stored = _rec.load(row["payload_json"])["event"]
        return B7MoneyEventView.model_validate(stored).model_copy(
            update={"idempotent_replay": True})
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Sự kiện tiền quyết toán chỉ áp dụng cho hồ sơ liên kết.",
        )
    _rec.check_version(case, command)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    sources = _rec.source_records(conn, case_id)
    company_ref = getattr(b7, "company_ref", None) if b7 is not None else None
    from invoice_referee.settlement.settlement_workflow import effective_b7_time
    effective_at = effective_b7_time(b7)
    classification, incidents = classify_b7_money(
        payload, employee_ref=submission.employee_ref,
        work_ref=submission.work_ref, company_ref=company_ref,
        sources=sources, effective_at=effective_at)
    # A decision_id, when given, must belong to this case/scope.
    if payload.decision_id is not None:
        dec_row = conn.execute(
            "SELECT payload_json FROM decisions WHERE id = ? AND case_id = ?",
            (payload.decision_id, case_id)).fetchone()
        candidate = _rec.load(dec_row["payload_json"]) if dec_row else None
        if (candidate is None or candidate.get("kind") != "B7_SETTLEMENT"
                or candidate.get("employee_ref") != submission.employee_ref
                or candidate.get("work_ref") != submission.work_ref):
            incidents.append(B7MoneyIncident(
                code="UNALLOCATED", event_ids=[], refs=[],
                reason="decision_id không thuộc hồ sơ/người/công việc này."))
            if classification == "CONFIRMED_RECEIPT":
                classification = "INCIDENT"
    # Same economic identity (namespace+ref) already confirmed: a new
    # RECEIVED for the same identity is a conflict, not a second payment.
    if (classification == "CONFIRMED_RECEIPT"
            and payload.event_namespace and payload.event_ref):
        for prior in money_events(conn, case_id):
            if (prior.event_namespace == payload.event_namespace
                    and prior.event_ref == payload.event_ref
                    and prior.classification == "CONFIRMED_RECEIPT"):
                incidents.append(B7MoneyIncident(
                    code="CONFLICTING_EVENT", event_ids=[prior.id],
                    refs=[], reason=("Cùng giao dịch đã có kết quả RECEIVED "
                                     "xác nhận; giữ cả hai, cần xử lý.")))
                classification = "INCIDENT"
                break
    after_cutoff = bool(payload.event_at is not None
                        and payload.event_at > submission.money_as_of)
    now = _now()
    event = {
        "id": f"BM-{uuid.uuid4().hex[:12]}", "case_id": case_id,
        "kind": "B7_SETTLEMENT_EVENT",
        "decision_id": payload.decision_id,
        "event_namespace": payload.event_namespace,
        "event_ref": payload.event_ref, "method": payload.method,
        "gross_vnd": payload.gross_vnd, "payer_ref": payload.payer_ref,
        "payee_ref": payload.payee_ref,
        "event_at": _iso(payload.event_at) if payload.event_at else None,
        "reported_status": payload.reported_status,
        "purpose": payload.purpose,
        "evidence": [e.model_dump(mode="json") for e in payload.evidence],
        "allocation_note": payload.allocation_note,
        "supersedes_event_id": payload.supersedes_event_id,
        "employee_ref": submission.employee_ref,
        "work_ref": submission.work_ref, "actor_id": command.actor_id,
        "created_at": now, "known_at": now,
        "classification": classification,
        "after_cutoff": after_cutoff,
        "incidents": [i.model_dump(mode="json") for i in incidents],
    }
    conn.execute(
        "INSERT INTO money_events (id, case_id, payload_json, created_at) "
        "VALUES (?, ?, ?, ?)",
        (event["id"], case_id, _rec.dump(event), now),
    )
    new_version = case["case_version"] + 1
    new_stage: CaseStage = case["stage"]
    if not case["stop_active"]:
        decision = current_decision(conn, case_id)
        if decision is not None and decision.target is not None:
            summary = fulfillment(conn, case_id)
            if summary is not None:
                if summary.status == "FULFILLED":
                    new_stage = "READY_TO_CLOSE"
                elif summary.status == "BLOCKED":
                    new_stage = "RESOLVING_OBLIGATIONS"
                else:
                    new_stage = "AWAITING_MONEY"
    conn.execute(
        "UPDATE cases SET stage = ?, case_version = ?, updated_at = ? "
        "WHERE id = ?",
        (new_stage, new_version, now, case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_SETTLEMENT_EVENT_RECORDED",
                        _B7_RECORD_MONEY, command, payload_fp,
                        {"event": event}, now)
    return B7MoneyEventView.model_validate(event)


def revalidate(conn: sqlite3.Connection, artifact_root: Path, case_id: str,
               command: Command, policy: dict) -> B7RevalidationView:
    """Revalidate that a correct fulfillment keeps the original decision.

    Compares the current report's cost basis and history delta against the
    original decision's baseline + canonical qualifying receipts. Persists
    an audit record; never rewrites the decision.
    """
    from invoice_referee.settlement.settlement_reconciliation import (
        revalidate_b7_decision,
    )

    payload_fp = fingerprint(_B7_REVALIDATE, {"case_id": case_id})
    row = _rec.lookup_command(conn, _B7_REVALIDATE, command, scope_key=case_id)
    if row is not None:
        _rec.check_replay(row, payload_fp)
        return B7RevalidationView.model_validate(
            _rec.load(row["payload_json"])["revalidation"])
    case = _rec.case_row(conn, case_id)
    _rec.check_open(case)
    _rec.check_version(case, command)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            "Revalidate chỉ áp dụng cho hồ sơ quyết toán liên kết.",
        )
    decision = current_decision(conn, case_id)
    report = None
    if case["current_run_id"]:
        run = conn.execute("SELECT * FROM runs WHERE id = ?",
                           (case["current_run_id"],)).fetchone()
        if run is not None and run["status"] == "SUCCEEDED" \
                and run["report_json"]:
            report = Report.model_validate(_rec.load(run["report_json"]))
    if report is None or decision is None:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Cần report hiện hành và quyết định APPROVE để revalidate.")
    snapshot = _lc.load_context(
        conn, artifact_root, _lc.context_source_ids(conn, case_id)[-1])
    from invoice_referee.settlement.settlement_workflow import b7_cost_signature
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    current_cost = b7_cost_signature(
        submission, _rec.source_records(conn, case_id), report, policy, snapshot)
    qualifying = [e for e in money_events(conn, case_id)
                  if e.classification == "CONFIRMED_RECEIPT"]
    reval = revalidate_b7_decision(
        decision, report, snapshot.history or {}, qualifying, current_cost)
    now = _now()
    _rec.record_command(conn, case_id, case_id, "B7_REVALIDATED",
                        _B7_REVALIDATE, command, payload_fp,
                        {"revalidation": reval.model_dump(mode="json")}, now)
    return reval


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
    require_accountant_route(conn, case, command, b3)
    _lc.check_origin_not_stopped(conn, _lc.origin_link(case)["origin_case_id"])
    decision = current_decision(conn, case_id)
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
    summary = fulfillment(conn, case_id)
    if summary is None or summary.status == "BLOCKED":
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Còn pending/unknown/incident; không bàn giao phần còn lại.")
    remaining = summary.remaining_vnd
    if remaining is None or remaining <= 0:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Không còn phần nghĩa vụ để bàn giao.")
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    snapshot = _lc.load_context(
        conn, artifact_root, _lc.context_source_ids(conn, case_id)[-1])
    business_sig = b7_business_signature(
        submission, _rec.source_records(conn, case_id),
        Report.model_validate(_rec.load(conn.execute(
            "SELECT * FROM runs WHERE id = ?",
            (decision.basis_report_id,)).fetchone()["report_json"])),
        policy, snapshot)
    obligation_sig = fingerprint("B7_OBLIGATION", {
        "decision_id": decision.id, "remaining_vnd": remaining})
    receipt_sig = receipt_signature(conn, case_id)
    # One current handoff per obligation signature: reuse, else conflict.
    prior = latest_handoff(conn, case_id)
    if prior is not None and prior.obligation_signature == obligation_sig:
        return prior.model_copy(update={"idempotent_replay": True})
    now_dt = _now_dt()
    valid_until = None
    grant = grant_for(b7, decision)
    if grant is not None:
        valid_until = getattr(grant, "effective_until", None)
    handoff_view = B7HandoffView(
        id=f"BH-{uuid.uuid4().hex[:12]}", case_id=case_id,
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
                        _iso(now_dt))
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
                return stored.model_copy(update={"idempotent_replay": True})
        raise DomainError(
            "CASE_CLOSED",
            "Hồ sơ đã đóng; nguồn mới cần hồ sơ điều chỉnh liên kết.")
    _rec.check_version(case, command)
    if _lc.origin_link(case) is None:
        raise DomainError(
            "LINKED_B7_INVALID", "Đóng chỉ áp dụng cho hồ sơ liên kết.")
    require_accountant_route(conn, case, command, b3)
    decision = current_decision(conn, case_id)
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
    summary = fulfillment(conn, case_id)
    reval = current_revalidation(conn, case_id)
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
        open_question_count=open_question_count(conn, case_id))
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
    now_dt = _now_dt()
    closure_view = B7ClosureView(
        id=f"BC-{uuid.uuid4().hex[:12]}", case_id=case_id,
        decision_id=decision.id, current_report_id=payload.current_report_id,
        actor_id=command.actor_id, kind="SETTLEMENT_COMPLETE",
        employee_ref=submission.employee_ref, work_ref=submission.work_ref,
        close_as_of=submission.money_as_of,
        knowledge_cutoff=submission.knowledge_cutoff, created_at=now_dt,
        input_revision=case["input_revision"],
        control_epoch=case["control_epoch"], business_signature=business_sig,
        receipt_history_signature=receipt_signature(conn, case_id),
        parent_fingerprint=_lc.parent_fingerprint(
            conn, _lc.origin_link(case)["origin_case_id"], _b3_workflow_of,
            _adv.advance_events),
        source_refs=list(report.source_refs) if report else [],
        event_ids=[e.id for e in money_events(conn, case_id)
                   if e.classification == "CONFIRMED_RECEIPT"],
        original_decision_id=decision.id,
        revalidation_ref=(reval.current_report_id if reval else None),
        reason=payload.reason)
    conn.execute(
        "UPDATE cases SET stage = 'SETTLEMENT_CLOSED', case_version = ?, "
        "updated_at = ? WHERE id = ?",
        (case["case_version"] + 1, _iso(now_dt), case_id),
    )
    _rec.record_command(conn, case_id, case_id, "B7_SETTLEMENT_CLOSED",
                        _B7_CLOSE, command, payload_fp,
                        {"closure": closure_view.model_dump(mode="json")},
                        _iso(now_dt))
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
    require_accountant_route(conn, closed, command, b3)
    parent_id = link["origin_case_id"]
    # One active settlement per employee/work: reuse if one is open.
    active = _lc.find_linked_child(conn, parent_id)
    if active is not None:
        return active["id"], False
    now_dt = _now_dt()
    now = _iso(now_dt)
    child_id = f"C-{uuid.uuid4().hex[:12]}"
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
        (f"R-{uuid.uuid4().hex[:12]}", child_id,
         _rec.dump(submission.model_dump(mode="json")), payload.reason,
         command.actor_id, command.key, now),
    )
    _rec.record_command(conn, child_id, closed_case_id, "B7_ADJUSTMENT_PREPARED",
                        _B7_ADJUSTMENT, command, payload_fp,
                        {"child_id": child_id,
                         "adjustment_of_case_id": closed_case_id}, now)
    return child_id, False


# --- money context (B9 refresh) ----------------------------------------------

def _b3_workflow_of(conn: sqlite3.Connection, case_id: str):
    return _adv.workflow_view(conn, case_id)


def augment_packet_with_money(conn: sqlite3.Connection, packet, case_id: str):
    """Append canonical B9 receipts to the packet as company events.

    Deduped by economic identity (namespace:ref) so a receipt already in the
    company ledger is not double-counted. Only CONFIRMED receipts whose
    identity is not already present are added.
    """
    from invoice_referee.settlement.models import B7CompanyEvent

    kind_by_purpose = {
        "ADVANCE_RETURN": "ADVANCE_RETURN",
        "REIMBURSEMENT_RECEIVED": "REIMBURSEMENT_RECEIVED",
        "REIMBURSEMENT_RETURN": "REIMBURSEMENT_RETURN",
    }
    existing = {(e.event_namespace, e.event_ref) for e in packet.events}
    added = list(packet.events)
    for event in money_events(conn, case_id):
        if event.classification != "CONFIRMED_RECEIPT" or event.gross_vnd is None:
            continue
        kind = kind_by_purpose.get(event.purpose)
        if kind is None:
            continue
        namespace = event.event_namespace or f"b7money:{event.id}"
        ref = event.event_ref or event.id
        if (namespace, ref) in existing:
            continue
        existing.add((namespace, ref))
        added.append(B7CompanyEvent(
            event_namespace=namespace, event_ref=ref, kind=kind,
            amount_vnd=event.gross_vnd, payer_ref=event.payer_ref,
            payee_ref=event.payee_ref, employee_ref=event.employee_ref,
            work_ref=event.work_ref, outcome="RECEIVED",
            event_at=event.event_at or event.created_at,
            known_at=event.known_at or event.created_at,
            refs=[f"b7money:{event.id}"]))
    return packet.model_copy(update={"events": added})


def build_money_context(conn: sqlite3.Connection, artifact_root: Path,
                        case_id: str, policy: dict,
                        authority_version: str | None):
    """Rebuild the linked context from the stored packet + canonical money.

    The packet's coverage is kept unchanged (the accountant owns the
    external book); the canonical B9 events are appended to the packet's
    company events (deduped by economic identity) so a re-run sees a correct
    fulfillment in its history without re-importing it.
    """
    from invoice_referee.settlement.linked_context import build_linked_context

    snapshot = _lc.load_context(
        conn, artifact_root, _lc.context_source_ids(conn, case_id)[-1])
    packet = snapshot.company_packet
    if packet is None:
        raise DomainError(
            "BASIS_MISMATCH", "Chưa có company packet để làm mới context.")
    case = _rec.case_row(conn, case_id)
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    link = _lc.origin_link(case)
    parent_id = link["origin_case_id"]
    decision = None
    parent_wf = _adv.workflow_view(conn, parent_id)
    if parent_wf is not None and parent_wf.decision is not None:
        decision = parent_wf.decision
    managed = _adv.advance_events(conn, parent_id)
    augmented = augment_packet_with_money(conn, packet, case_id)
    merged = build_linked_context(
        origin_case_id=parent_id,
        parent_fingerprint=_lc.parent_fingerprint(
            conn, parent_id, _adv.workflow_view, _adv.advance_events),
        decision=decision, managed_events=managed, packet=augmented,
        policy=policy, authority_version=authority_version,
        money_as_of=submission.money_as_of,
        knowledge_cutoff=submission.knowledge_cutoff,
        submission=submission, source_records=_rec.source_records(conn, case_id))
    return case_id, merged
