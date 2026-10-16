"""One accountable intake checkpoint, then only source-bound workflow updates."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from invoice_referee.domain.case import CaseScope
from invoice_referee.domain.common import Fact
from invoice_referee.domain.finance import COVERAGE_REQUIRED_FLOW_KINDS, CoverageRecord, MoneyEvent
from invoice_referee.reconciliation.admission import coverage_is_valid, history_fingerprint
from invoice_referee.workflow.context_records import context_ledger, load_context, merge_ledger


INITIAL_STATEMENT = (
    "Kế toán xác nhận đã ghi nhận đầy đủ các khoản ứng, chi bổ sung và hoàn trả "
    "trước khi tiếp nhận công việc này; không còn số dư hoặc giao dịch chưa khai báo. "
    "Các phát sinh tiếp theo phải được ghi nhận qua hệ thống."
)


def history_snapshot(cx, row, as_of: datetime):
    organization = load_context(cx, str(row["tenant"]), str(row["activity"]), as_of)
    imported = context_ledger(
        organization, digest=hashlib.sha256(organization.model_dump_json().encode()).hexdigest()
    ) if organization is not None else ()
    local = tuple(MoneyEvent.model_validate_json(item["payload_json"]) for item in cx.execute(
        "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? ORDER BY id",
        (str(row["tenant"]), str(row["id"])),
    ))
    merged, conflicts = merge_ledger(imported, local)
    # Check both copies: dedup must not hide an observed local movement.
    unresolved = bool(conflicts) or any(
        event.verification_state != "CONFIRMED" or event.allocation_state != "ALLOCATED"
        or event.scope not in (str(row["activity"]), str(row["tenant"]))
        or event.event_at > as_of
        for event in (*imported, *local)
    )
    return merged, history_fingerprint(imported), len(local), unresolved


def initial_history(cx, row, *, actor: str, now: datetime) -> CoverageRecord:
    events, fingerprint, version, unresolved = history_snapshot(cx, row, now)
    if unresolved:
        raise ValueError("Còn giao dịch chưa xác minh, chưa phân bổ hoặc mâu thuẫn; xử lý trước khi xác nhận lịch sử ban đầu.")
    return CoverageRecord(
        scope=str(row["activity"]), employee=str(row["employee"]),
        start=min((event.event_at for event in events), default=now), as_of=now,
        flow_kinds=COVERAGE_REQUIRED_FLOW_KINDS,
        # This zero asserts no omitted carry-in, not a fabricated bank balance.
        opening_balance=Fact[int](key="history:unrecorded-carry-in", value=0, state="KNOWN"),
        ledger_version=str(version), source="MANAGED_HISTORY", actor=actor,
        recorded_at=now, reason=INITIAL_STATEMENT, context_ledger_fingerprint=fingerprint,
        witness_refs=tuple(dict.fromkeys(ref for event in events for ref in event.refs)),
    )


def record_dossier_history(cx, row, *, actor: str, now: datetime, only_if_untracked: bool = False, reason: str | None = None) -> bool:
    """Scope is recorded dossier money, never an assertion of complete bank history.

    Called after a source-bound advance or an instruction-bound P/R succeeded.
    No second human action, fabricated opening balance or absence quote.
    """
    events, fingerprint, version, unresolved = history_snapshot(cx, row, now)
    if unresolved or not events:
        return False
    saved = cx.execute(
        "SELECT coverage_json FROM case_coverage_records WHERE tenant = ? AND root_id = ? "
        "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
        (str(row["tenant"]), str(row["id"])),
    ).fetchone()
    if saved is not None:
        current = CoverageRecord.model_validate_json(saved["coverage_json"])
        if only_if_untracked and current.source in ("MANAGED_HISTORY", "DOSSIER_RECORDS"):
            return False
        if (current.source == "DOSSIER_RECORDS" and current.ledger_version == str(version)
                and current.context_ledger_fingerprint == fingerprint):
            return False
    coverage = CoverageRecord(
        scope=str(row["activity"]), employee=str(row["employee"]), actor=actor,
        source="DOSSIER_RECORDS", start=min(event.event_at for event in events),
        as_of=now, recorded_at=now, ledger_version=str(version),
        flow_kinds=COVERAGE_REQUIRED_FLOW_KINDS,
        context_ledger_fingerprint=fingerprint,
        reason=reason or "Đối soát các khoản tiền đã ghi nhận cho hồ sơ theo chứng từ được xác nhận; không xác nhận toàn bộ lịch sử ngân hàng.",
        witness_refs=tuple(dict.fromkeys(ref for event in events for ref in event.refs)),
    )
    cx.execute(
        "INSERT INTO case_coverage_records (coverage_id, tenant, root_id, ledger_version, "
        "coverage_json, actor, recorded_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (f"coverage:{uuid.uuid4().hex}", str(row["tenant"]), str(row["id"]), str(version),
         coverage.model_dump_json(), actor, now.isoformat(), coverage.reason),
    )
    return True


def maintain_history(cx, row, event: MoneyEvent, *, controlled: bool, now: datetime) -> str | None:
    """Advance a valid checkpoint atomically; never repair an already stale one."""
    saved = cx.execute(
        "SELECT coverage_id, coverage_json FROM case_coverage_records WHERE tenant = ? AND root_id = ? "
        "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
        (str(row["tenant"]), str(row["id"])),
    ).fetchone()
    if saved is None or not controlled:
        return None
    coverage = CoverageRecord.model_validate_json(saved["coverage_json"])
    if coverage.source not in ("MANAGED_HISTORY", "DOSSIER_RECORDS"):
        return None
    _events, fingerprint, version, unresolved = history_snapshot(cx, row, now)
    if unresolved or event.kind == "REVERSAL":
        return None
    scope = CaseScope(tenant=str(row["tenant"]), employee=str(row["employee"]),
                      activity=str(row["activity"]), profile=str(row["profile"]))
    if not coverage_is_valid(coverage, scope=scope, as_of=now,
                             current_ledger_version=version - 1,
                             current_context_ledger_fingerprint=fingerprint):
        return None
    # Receipts may state a day only: compare calendar days, never invent hours.
    zone = ZoneInfo("Asia/Ho_Chi_Minh")
    if event.event_at.astimezone(zone).date() < coverage.as_of.astimezone(zone).date():
        return None
    updated = coverage.model_copy(update={"ledger_version": str(version), "as_of": now})
    cx.execute(
        "UPDATE case_coverage_records SET coverage_json = ?, ledger_version = ? WHERE coverage_id = ?",
        (updated.model_dump_json(), str(version), saved["coverage_id"]),
    )
    return str(saved["coverage_id"])
