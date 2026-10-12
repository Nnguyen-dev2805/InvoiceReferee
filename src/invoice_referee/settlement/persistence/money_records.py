from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from invoice_referee.domain.models import DomainError
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
        for prior in _q.money_events(conn, case_id):
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
        decision = _q.current_decision(conn, case_id)
        if decision is not None and decision.target is not None:
            summary = _q.fulfillment(conn, case_id)
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
    decision = _q.current_decision(conn, case_id)
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
    qualifying = [e for e in _q.money_events(conn, case_id)
                  if e.classification == "CONFIRMED_RECEIPT"]
    original_cost = _q.decision_cost_signature(conn, case_id, decision.id)
    reval = revalidate_b7_decision(
        decision, report, snapshot.history or {}, qualifying, current_cost,
        original_cost)
    now = _now()
    _rec.record_command(conn, case_id, case_id, "B7_REVALIDATED",
                        _B7_REVALIDATE, command, payload_fp,
                        {"revalidation": reval.model_dump(mode="json")}, now)
    return reval
