"""Assemble the typed admission input from stored state (plan A5).

The evidence worker publishes a typed `ReadResult`; this module turns that report
plus the stored organization context, scoped confirmations, recorded money and
coverage into the immutable `AssessmentInput` the Reconciler assesses. It reads
the CURRENT stored state, so a change between the read and the commit is caught
by the workflow's read-set re-check (it never uses STUB constant counters).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import Confirmation, ReadResult
from invoice_referee.domain.finance import (
    ActivityAcceptance,
    ActivityLinkSignal,
    CoverageRecord,
    MoneyEvent,
)
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.workflow.context_records import load_context


def _load_confirmations(cx: sqlite3.Connection, tenant: str, root_id: str) -> tuple[Confirmation, ...]:
    from invoice_referee.domain.common import EvidenceRef

    out: list[Confirmation] = []
    for row in cx.execute(
        "SELECT * FROM case_confirmations WHERE tenant = ? AND root_id = ? ORDER BY observed_at, id",
        (tenant, root_id),
    ).fetchall():
        refs = tuple(
            EvidenceRef.model_validate(ref) for ref in json.loads(row["refs_json"] or "[]")
        )
        out.append(
            Confirmation(
                fact_key=str(row["fact_key"]),
                value=row["value"],
                actor=str(row["actor"]),
                scope=str(row["scope"]),
                refs=refs,
                reason=str(row["reason"]),
                observed_at=datetime.fromisoformat(row["observed_at"]),
            )
        )
    return tuple(out)


def _load_recorded_money(cx: sqlite3.Connection, tenant: str, root_id: str) -> tuple[MoneyEvent, ...]:
    return tuple(
        MoneyEvent.model_validate_json(row["payload_json"])
        for row in cx.execute(
            "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? "
            "AND verification_state = 'CONFIRMED' ORDER BY recorded_at, id",
            (tenant, root_id),
        ).fetchall()
    )


def _load_activity_acceptances(
    cx: sqlite3.Connection, tenant: str, root_id: str
) -> tuple[ActivityAcceptance, ...]:
    import json

    return tuple(
        ActivityAcceptance(
            root_id=str(row["root_id"]),
            employee=str(row["employee"]),
            activity=str(row["activity"]),
            advance_external_key=str(row["advance_external_key"]),
            advance_draft_id=str(row["advance_draft_id"]),
            actor=str(row["actor"]),
            accepted_at=datetime.fromisoformat(str(row["accepted_at"])),
            link_basis=str(row["link_basis"]),
            reason=str(row["reason"]),
            refs=tuple(json.loads(row["refs_json"] or "[]")),
            link_signals=tuple(
                ActivityLinkSignal.model_validate({
                    **signal,
                    "refs": tuple(
                        EvidenceRef.model_validate(ref)
                        for ref in signal.get("refs", [])
                    ),
                })
                for signal in json.loads(row["link_signals_json"] or "[]")
            ),
        )
        for row in cx.execute(
            "SELECT * FROM case_activity_acceptances WHERE tenant = ? AND root_id = ? "
            "ORDER BY accepted_at, acceptance_id",
            (tenant, root_id),
        ).fetchall()
    )


def _load_coverage_record(
    cx: sqlite3.Connection, tenant: str, root_id: str
) -> CoverageRecord | None:
    row = cx.execute(
        "SELECT coverage_json FROM case_coverage_records WHERE tenant = ? AND root_id = ? "
        "ORDER BY recorded_at DESC, rowid DESC LIMIT 1",
        (tenant, root_id),
    ).fetchone()
    if row is None:
        return None
    return CoverageRecord.model_validate_json(row["coverage_json"])


def _context_version(cx: sqlite3.Connection, tenant: str) -> int:
    from invoice_referee.workflow.controls import context_version

    return context_version(cx, tenant)


def _ledger_version(cx: sqlite3.Connection, tenant: str, root_id: str) -> int:
    row = cx.execute(
        "SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?",
        (tenant, root_id),
    ).fetchone()
    return int(row["n"]) if row is not None else 0


def _usage_version(cx: sqlite3.Connection, tenant: str) -> int:
    row = cx.execute(
        "SELECT COALESCE(SUM(version), 0) AS v FROM usage_registry WHERE tenant = ?",
        (tenant,),
    ).fetchone()
    return int(row["v"]) if row is not None else 0


def build_evidence_assessment_input(
    cx: sqlite3.Connection,
    *,
    tenant: str,
    root_id: str,
    report: ReadResult,
    as_of: datetime,
) -> AssessmentInput:
    """Assemble the typed admission input from the stored report + current state.

    `as_of` is the assessment instant, taken from the server/harness clock by
    the caller (never the client): it drives coverage freshness and every
    time-scoped gate consistently through admission and policy.
    """
    row = cx.execute(
        "SELECT * FROM cases WHERE id = ? AND tenant = ?", (root_id, tenant)
    ).fetchone()
    if row is None:
        raise ValueError(f"case {root_id} not found in tenant {tenant}")

    organization = load_context(cx, tenant, str(row["activity"]), as_of)
    if organization is None:
        organization = OrganizationContext.model_validate({"organization_id": tenant})

    scope = CaseScope(
        tenant=tenant,
        employee=str(row["employee"]),
        activity=str(row["activity"]),
        profile=str(row["profile"]),
    )
    read_set = ReadSet(
        input_revision=int(row["input_revision"]),
        control_epoch=int(row["control_epoch"]),
        context_version=_context_version(cx, tenant),
        ledger_version=_ledger_version(cx, tenant, root_id),
        usage_version=_usage_version(cx, tenant),
    )
    return admit_evidence(
        report,
        scope=scope,
        organization=organization,
        confirmations=_load_confirmations(cx, tenant, root_id),
        ledger=_load_recorded_money(cx, tenant, root_id),
        coverage=_load_coverage_record(cx, tenant, root_id),
        read_set=read_set,
        as_of=as_of,
        activity_acceptances=_load_activity_acceptances(cx, tenant, root_id),
    )
