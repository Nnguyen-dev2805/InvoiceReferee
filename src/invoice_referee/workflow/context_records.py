"""Immutable organization-context snapshots and their typed projection (plan A1).

The importer persists the full validated `OrganizationContext` payload verbatim
(one row per digest, versioned, never overwritten) AND projects the relational
activity/people/grants/witnesses rows the existing authorization commands read.
A restart loads the exact context an assessment rested on, so policies, budgets,
the ledger and coverage are not silently dropped.

The typed readers here turn the stored payload into domain objects with refs
bound to the context digest + record key — never a fake PDF page.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import CoverageRecord, MoneyEvent
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.domain.policy import BudgetDecision, Grant, PolicyVersion


def _parse_dt(value: object) -> datetime:
    text = str(value)
    return datetime.fromisoformat(text)


def _context_ref(digest: str, record_key: str, quote: str) -> EvidenceRef:
    """A ref into the stored context payload (record_key, not a PDF page)."""
    return EvidenceRef(
        source_id="source:company-context",
        source_sha256=digest,
        page=None,
        record_key=record_key,
        exact_quote=quote or record_key,
    )


def store_snapshot(
    cx: sqlite3.Connection,
    context: OrganizationContext,
    origin: str,
    *,
    imported_at: str | None = None,
) -> str:
    """Store one immutable snapshot row (no relational projection). Returns digest.

    A repeated import of the same payload is a no-op (the digest is the primary
    key); a changed payload adds a new version and leaves the older intact.
    """
    tenant = context.organization_id or context.tenant
    raw = json.dumps(context.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = imported_at or datetime.now(UTC).isoformat()

    existing = cx.execute(
        "SELECT version FROM context_snapshots WHERE tenant = ? AND digest = ?",
        (tenant, digest),
    ).fetchone()
    if existing is None:
        row = cx.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM context_snapshots WHERE tenant = ?",
            (tenant,),
        ).fetchone()
        version = int(row["v"]) + 1
        cx.execute(
            "INSERT INTO context_snapshots (tenant, digest, version, payload_json, "
            "origin, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant, digest, version, raw, origin, now),
        )
    return digest


def persist_context(
    cx: sqlite3.Connection,
    context: OrganizationContext,
    origin: str,
    *,
    imported_at: str | None = None,
) -> str:
    """Persist one immutable context snapshot and project its relational rows.

    Returns the payload digest.
    """
    tenant = context.organization_id or context.tenant
    digest = store_snapshot(cx, context, origin, imported_at=imported_at)
    _project_relational(cx, context, tenant=tenant, digest=digest)
    return digest


def _project_relational(
    cx: sqlite3.Connection, context: OrganizationContext, *, tenant: str, digest: str
) -> None:
    """Project activity/people/grants/witnesses for the existing commands."""
    activity = context.activity or {}
    activity_id = str(activity.get("activity_id") or "")
    if activity_id:
        authorization = activity.get("authorization")
        budget = _budget_for(context.budgets, activity_id)
        cx.execute(
            "INSERT INTO context_activities (activity_id, tenant, name, occurred_at, "
            "purpose, budget_amount, budget_effect_from, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(tenant, activity_id) DO UPDATE SET name=excluded.name, "
            "occurred_at=excluded.occurred_at, purpose=excluded.purpose, "
            "budget_amount=excluded.budget_amount, "
            "budget_effect_from=excluded.budget_effect_from, status=excluded.status",
            (
                activity_id,
                tenant,
                str(activity.get("name") or activity_id),
                activity.get("occurred_at"),
                str(activity.get("purpose") or ""),
                int(budget["amount"]) if budget else None,
                (budget["effect_range"][0] if budget else None),
                "AUTHORIZED" if authorization is not None else "PROPOSED",
            ),
        )
    for person in context.people:
        cx.execute(
            "INSERT OR REPLACE INTO context_people (id, tenant, name) VALUES (?, ?, ?)",
            (str(person["id"]), tenant, str(person["name"])),
        )
    for grant in context.grants:
        cx.execute(
            "INSERT OR REPLACE INTO context_grants (grant_id, tenant, version, actor, "
            "actions_json, scope, allowed_profiles_json, max_amount, effective_from, "
            "effective_to) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(grant["id"]),
                tenant,
                str(grant.get("version", "v1")),
                str(grant["actor"]),
                json.dumps(list(grant.get("actions", [])), ensure_ascii=False),
                str(grant["scope"]),
                json.dumps(list(grant.get("allowed_profiles", [])), ensure_ascii=False),
                int(grant["max_amount"]),
                str(grant["effective_from"]),
                grant.get("effective_to"),
            ),
        )
    for witness in context.witnesses:
        cx.execute(
            "INSERT OR REPLACE INTO context_witnesses (tenant, kind, record_key, quote, "
            "source_id, source_sha256) VALUES (?, ?, ?, ?, ?, ?)",
            (
                tenant,
                "LEDGER_COVERAGE",
                str(witness["record_key"]),
                str(witness["quote"]),
                "source:company-context",
                digest,
            ),
        )


def _budget_for(
    budgets: tuple[dict[str, object], ...], activity_id: str
) -> dict[str, object] | None:
    for budget in budgets:
        if str(budget.get("activity")) == activity_id:
            return budget
    return None


def _snapshot_contains_activity(context: OrganizationContext, activity: str) -> bool:
    primary = context.activity or {}
    if str(primary.get("activity_id") or "") == activity:
        return True
    for entry in context.activities:
        if str(entry.get("id") or entry.get("activity_id") or "") == activity:
            return True
    return False


def load_context(
    cx: sqlite3.Connection, tenant: str, activity: str, as_of: datetime
) -> OrganizationContext | None:
    """Load the newest stored context snapshot for a tenant, scoped to `activity`.

    The snapshot is loaded whole (policies/budgets/ledger/coverage survive a
    restart), but only the newest snapshot that actually CONTAINS `activity` is
    returned: a snapshot for another activity must not be used as this
    activity's context (plan A5/D). Returns None when no snapshot names it.
    """
    rows = cx.execute(
        "SELECT payload_json FROM context_snapshots WHERE tenant = ? "
        "ORDER BY version DESC",
        (tenant,),
    ).fetchall()
    for row in rows:
        context = OrganizationContext.model_validate_json(row["payload_json"])
        if _snapshot_contains_activity(context, activity):
            return context
    return None


def context_policies(
    context: OrganizationContext, *, digest: str, profile: str
) -> tuple[PolicyVersion, ...]:
    out: list[PolicyVersion] = []
    for policy in context.policies:
        out.append(
            PolicyVersion(
                id=str(policy["id"]),
                version=str(policy.get("version", "v1")),
                effective_from=_parse_dt(policy["effective_from"]),
                effective_to=_parse_dt(policy["effective_to"]) if policy.get("effective_to") else None,
                profile=str(policy.get("profile") or profile),
                rules=tuple(str(r) for r in policy.get("rules", [])),
            )
        )
    return tuple(out)


def context_budgets(
    context: OrganizationContext, *, activity: str, digest: str
) -> tuple[BudgetDecision, ...]:
    out: list[BudgetDecision] = []
    for budget in context.budgets:
        if str(budget.get("activity")) != activity:
            continue
        effect = budget.get("effect_range") or []
        start = _parse_dt(effect[0]) if effect else datetime(2026, 1, 1, tzinfo=UTC)
        end = _parse_dt(effect[1]) if len(effect) > 1 and effect[1] else None
        out.append(
            BudgetDecision(
                id=str(budget["id"]),
                activity=activity,
                amount=int(budget["amount"]),
                effect_range=(start, end),
                actor=str(budget.get("actor") or ""),
                grant_ref=str(budget["grant_ref"]) if budget.get("grant_ref") else None,
                refs=(_context_ref(digest, str(budget["id"]), "budget"),),
            )
        )
    return tuple(out)


def context_grants(
    context: OrganizationContext, *, digest: str
) -> tuple[Grant, ...]:
    out: list[Grant] = []
    for grant in context.grants:
        out.append(
            Grant(
                id=str(grant["id"]),
                version=str(grant.get("version", "v1")),
                actor=str(grant["actor"]),
                actions=tuple(str(a) for a in grant.get("actions", [])),
                scope=str(grant["scope"]),
                max_amount=int(grant["max_amount"]),
                effective_from=_parse_dt(grant["effective_from"]),
                effective_to=_parse_dt(grant["effective_to"]) if grant.get("effective_to") else None,
                allowed_profiles=tuple(str(p) for p in grant.get("allowed_profiles", [])),
            )
        )
    return tuple(out)


def context_ledger(
    context: OrganizationContext, *, digest: str
) -> tuple[MoneyEvent, ...]:
    out: list[MoneyEvent] = []
    for event in context.ledger:
        out.append(
            MoneyEvent(
                id=str(event["id"]),
                external_key=str(event["external_key"]),
                kind=str(event["kind"]),  # type: ignore[arg-type]
                scope=str(event["scope"]),
                payer=str(event["payer"]),
                payee=str(event["payee"]),
                amount=int(event["amount"]),
                event_at=_parse_dt(event["event_at"]),
                recorded_at=_parse_dt(event["recorded_at"]),
                verification_state=str(event.get("verification_state") or "OBSERVED"),  # type: ignore[arg-type]
                allocation_state=str(event.get("allocation_state") or "UNKNOWN"),  # type: ignore[arg-type]
                reverses_event_id=(
                    str(event["reverses_event_id"]) if event.get("reverses_event_id") else None
                ),
                refs=(_context_ref(digest, str(event["id"]), "ledger"),),
            )
        )
    return tuple(out)


def merge_ledger(
    context_events: tuple[MoneyEvent, ...],
    actual_events: tuple[MoneyEvent, ...],
) -> tuple[tuple[MoneyEvent, ...], tuple[str, ...]]:
    """Merge context-fixture ledger events with recorded actual-money events.

    Deduplicates by ``external_key``: the same external transaction is one event,
    never a doubled A/P/R. When two copies of the same external key disagree on
    amount/kind, the FIRST (context fixture) is kept and the key is reported as a
    conflict so the caller keeps the money a FACT issue rather than silently
    summing both. Recorded actual events are never edited by a context import.

    Returns (merged_events, conflicting_external_keys).
    """
    by_key: dict[str, MoneyEvent] = {}
    conflicts: list[str] = []
    for event in (*context_events, *actual_events):
        existing = by_key.get(event.external_key)
        if existing is None:
            by_key[event.external_key] = event
            continue
        if (
            existing.amount != event.amount
            or existing.kind != event.kind
            or existing.payer != event.payer
            or existing.payee != event.payee
        ) and event.external_key not in conflicts:
            conflicts.append(event.external_key)
    return tuple(by_key.values()), tuple(conflicts)


def context_coverage(
    context: OrganizationContext, *, digest: str
) -> CoverageRecord | None:
    """The stored coverage record, or None when the context declares none.

    A context WITHOUT coverage must not imply A/P/R = 0: absence stays None, and
    the caller keeps those flows UNKNOWN (plan A1/A3).
    """
    coverage = context.coverage
    if not coverage:
        return None
    opening = coverage.get("opening_by_fund") or {}
    opening_total = sum(int(v) for v in opening.values()) if opening else None
    return CoverageRecord(
        scope=str(coverage.get("activity") or ""),
        start=_parse_dt(coverage["start"]),
        as_of=_parse_dt(coverage["as_of"]),
        funds=tuple(str(f) for f in coverage.get("fund_ids", [])),
        flow_kinds=tuple(str(k) for k in coverage.get("flow_kinds", [])),  # type: ignore[arg-type]
        opening_balance=(
            Fact[int](key="coverage:opening", value=opening_total, state="KNOWN",
                      refs=(_context_ref(digest, "coverage:opening", "opening"),))
            if opening_total is not None
            else None
        ),
        ledger_version=str(coverage["ledger_version"]) if coverage.get("ledger_version") else None,
        witness_refs=tuple(
            _context_ref(digest, str(k), "coverage witness")
            for k in coverage.get("witness_keys", [])
        ),
    )
