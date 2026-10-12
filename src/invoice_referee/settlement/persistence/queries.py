from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from invoice_referee.domain.models import DomainError
from invoice_referee.shared import clock
from invoice_referee.settlement.persistence import sqlite_records as _rec
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
    return clock.utcnow()


def _now() -> str:
    return _iso(_now_dt())


def _iso(value) -> str:
    from datetime import timezone
    return value.astimezone(timezone.utc).isoformat()


def _now_dt():
    from invoice_referee.shared import clock
    return clock.utcnow()


def _now() -> str:
    return _iso(_now_dt())


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
    # A decision governs the presentation it was made on; a newer presentation
    # supersedes an older non-REFUSE decision. Shared with the fulfillment
    # selector so both agree on which decision is current.
    from invoice_referee.settlement.settlement_workflow import governing_decision
    decision_for_status = governing_decision(
        presentation, decision, case["current_run_id"])
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

    Uses the shared ``governing_decision`` selector (a newer presentation
    supersedes an older non-REFUSE decision; a RETURN stops governing once a
    newer run is current) so the workflow projection and fulfillment agree,
    without a recursion cycle into fulfillment.
    """
    from invoice_referee.settlement.settlement_workflow import governing_decision

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
    case = _rec.case_row(conn, case_id)
    return governing_decision(presentation, decision, case["current_run_id"])


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


def decision_cost_signature(conn: sqlite3.Connection, case_id: str,
                            decision_id: str) -> str | None:
    """The server-derived cost signature recorded when a decision was made.

    Read from the immutable B7_DECIDE audit metadata; None when absent (an
    older decision), so revalidation refuses to guess VALID.
    """
    for row in conn.execute(
            "SELECT payload_json FROM audit_events WHERE case_id = ? "
            "AND operation = ? ORDER BY rowid DESC", (case_id, _B7_DECIDE)):
        payload = _rec.load(row["payload_json"])
        stored = payload.get("decision") or {}
        if stored.get("id") == decision_id:
            return payload.get("cost_signature")
    return None


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
    """The decision-time grant snapshot (historical; used for handoff validity).

    Not a new-action authorization: it re-checks the grant at the decision's own
    effective_at, so it can only confirm the authority that was already used.
    """
    from invoice_referee.settlement.rules import covering_grant
    if b7 is None or not b7.activated or decision.target is None:
        return None
    scoped = [g for g in b7.grants if g.actor_ref == decision.actor_id]
    return covering_grant(
        scoped, decision.employee_ref, decision.work_ref,
        decision.effective_at, decision.target.employee_cost_vnd,
        decision.target.signed_net_vnd, decision.target.total_work_cost_vnd)


def grant_for_action(b7, decision, effective_at):
    """One scoped grant covering E and abs(S) for a NEW action at ``effective_at``.

    Uses the current server/demo time, not the decision time, so a grant that
    has since expired does not authorize a new handoff/action. Closure keeps its
    own evidence that authority held at decision/action times.
    """
    from invoice_referee.settlement.rules import covering_grant
    if b7 is None or not b7.activated or decision.target is None:
        return None
    scoped = [g for g in b7.grants if g.actor_ref == decision.actor_id]
    return covering_grant(
        scoped, decision.employee_ref, decision.work_ref, effective_at,
        decision.target.employee_cost_vnd, decision.target.signed_net_vnd,
        decision.target.total_work_cost_vnd)


def require_handoff_basis(conn: sqlite3.Connection, artifact_root: Path,
                          case_id: str, decision: B7DecisionView, b7, b3,
                          policy: dict):
    """Resolve the current basis for a handoff or raise BASIS_STALE.

    A handoff may only use the ORIGINAL current basis (the decision's report
    still current under the case's input_revision/epoch and still the case's
    current run) or a current VALID revalidation of the SAME decision. It never
    falls back to the old ``decision.basis_report_id`` when the input has since
    changed. Returns ``(report, snapshot, cost_signature)``.
    """
    from invoice_referee.settlement.settlement_workflow import (
        b7_business_signature, b7_cost_signature,
    )

    case = _rec.case_row(conn, case_id)
    run = conn.execute("SELECT * FROM runs WHERE id = ?",
                       (decision.basis_report_id,)).fetchone()
    basis_current = bool(
        run is not None and run["status"] == "SUCCEEDED" and run["report_json"]
        and case["current_run_id"] == decision.basis_report_id
        and run["input_revision"] == case["input_revision"]
        and run["control_epoch"] == case["control_epoch"])
    submission = Submission.model_validate(_rec.load(case["submission_json"]))
    context_ids = _lc.context_source_ids(conn, case_id)
    if not context_ids:
        raise DomainError(
            "BASIS_STALE", "Chưa có company context hiện hành để bàn giao.")
    snapshot = _lc.load_context(conn, artifact_root, context_ids[-1])
    if basis_current:
        report = Report.model_validate(_rec.load(run["report_json"]))
    else:
        # The original report is no longer current: only a current VALID
        # revalidation of the SAME decision, whose cost signature still matches
        # the current cost basis, may authorize the handoff. A stale VALID badge
        # (a material source changed after it) does not authorize a new action.
        reval = current_revalidation(conn, case_id)
        current_run = (conn.execute("SELECT * FROM runs WHERE id = ?",
                                    (case["current_run_id"],)).fetchone()
                       if case["current_run_id"] else None)
        if (reval is None or reval.status != "VALID"
                or reval.original_decision_id != decision.id
                or current_run is None
                or current_run["status"] != "SUCCEEDED"
                or not current_run["report_json"]):
            raise DomainError(
                "BASIS_STALE",
                "Căn cứ đã đổi kể từ khi duyệt và chưa có revalidation VALID "
                "cho đúng quyết định; cần chạy và trình lại trước khi bàn giao.")
        report = Report.model_validate(_rec.load(current_run["report_json"]))
        current_cost = b7_cost_signature(
            submission, _rec.source_records(conn, case_id), report, policy,
            snapshot)
        if current_cost != reval.cost_signature:
            raise DomainError(
                "BASIS_STALE",
                "Basis chi phí đã đổi sau revalidation; revalidation cũ không "
                "còn hiệu lực, cần chạy và trình lại trước khi bàn giao.")
    sources = _rec.source_records(conn, case_id)
    cost_sig = b7_cost_signature(submission, sources, report, policy, snapshot)
    return report, snapshot, cost_sig


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


def dossier_reference(conn: sqlite3.Connection, case: sqlite3.Row) -> str:
    """Shared root dossier id for a case (read-only projection).

    - Linked B7 child / adjustment: the B3 parent's id (``origin_case_id``).
    - B3 or standalone B7: the case's own id.

    The parent must exist and match the child's employee/work scope; a broken
    link raises ``LINKED_B7_INVALID`` rather than silently using the child id as
    the root (which would hide a data error). Never derives the root from
    ``work_ref``.
    """
    link = _lc.origin_link(case)
    if link is None:
        return case["id"]
    parent_id = link.get("origin_case_id")
    if not isinstance(parent_id, str) or not parent_id:
        raise DomainError(
            "LINKED_B7_INVALID",
            f"Hồ sơ {case['id']} thiếu origin_case_id hợp lệ trong link.",
        )
    parent = conn.execute("SELECT * FROM cases WHERE id = ?",
                          (parent_id,)).fetchone()
    if parent is None:
        raise DomainError(
            "LINKED_B7_INVALID",
            f"Hồ sơ gốc {parent_id} của {case['id']} không tồn tại.",
        )
    submission = _rec.load(case["submission_json"])
    parent_submission = _rec.load(parent["submission_json"])
    if (link.get("employee_ref") != parent_submission.get("employee_ref")
            or submission.get("employee_ref")
            != parent_submission.get("employee_ref")):
        raise DomainError(
            "LINKED_B7_INVALID",
            f"Hồ sơ {case['id']} và gốc {parent_id} khác nhân viên.",
        )
    return parent_id


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
