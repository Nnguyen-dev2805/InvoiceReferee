"""B8 settlement-decision helpers (b7-linked-intake-v1).

Deterministic Python derives the financial decision target from a current
report, and the authority is a single scoped B7 grant that covers both the
accepted employee cost (E) and the absolute signed net (abs(S)). No LLM, no
client-supplied amount/rights.

Report-only before B8: presentation records the accountant's routing; a decision
records the approver's APPROVE/RETURN/REFUSE. Approval is NOT receipt.
"""
from __future__ import annotations

from datetime import datetime, timezone

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    B7DecisionTarget,
    MoneyComponents,
    Report,
    SourceRecord,
    Submission,
    fingerprint,
)

# Routine B7 checks a COMPLETE report must carry; a missing/FAIL/UNRESOLVED
# routine check blocks a routine APPROVE. (Rulebook R7–R10.)
REQUIRED_ROUTINE_CHECKS = (
    "relation_status", "duplicate_events", "eligibility", "payer_parts",
    "history_coverage", "budget", "authority",
)


def _known_int(slot, name: str) -> int:
    if slot.state != "KNOWN" or not isinstance(slot.value, int) \
            or isinstance(slot.value, bool):
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            f"Component {name} chưa KNOWN/integer có nguồn; không duyệt được.",
        )
    return slot.value


def governing_decision(presentation, decision, current_run_id: str | None):
    """The decision that currently governs a linked settlement, or None.

    A decision only governs the presentation it was made on. A newer
    presentation supersedes an older non-REFUSE decision; REFUSE stays effective
    until a separate reopen. A RETURN stops governing once a newer run has become
    current (the case needs a fresh presentation).

    Shared by the workflow projection and the fulfillment/revalidation selector;
    it is a freshness *selector*, not a validator and not a recursion with
    fulfillment.
    """
    if decision is None:
        return None
    if decision.outcome != "REFUSE" \
            and (presentation is None
                 or decision.presentation_id != presentation.id):
        return None
    if decision.outcome == "RETURN" \
            and current_run_id != decision.basis_report_id:
        return None
    return decision


def settlement_target(report: Report) -> B7DecisionTarget:
    """Derive the decision target from a current report, or raise.

    Rejects a non-B7 report, a non-COMPLETE report, unresolved material issues,
    claim CONFLICT/UNRESOLVED, missing/FAIL/UNRESOLVED routine checks, unknown
    components, and a proposed net that is absent or inconsistent with the
    calculated net. ``amount_vnd`` is ``abs(net)``; the direction comes from the
    sign (BALANCED at 0).
    """
    if report.job != "B7":
        raise DomainError("B7_WORKFLOW_BLOCKED", "Chỉ B7 mới có quyết toán.")
    if report.completion != "COMPLETE":
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Report chưa COMPLETE (còn issue/unresolved); không duyệt được.",
        )
    if any(issue.unresolved for issue in report.issues):
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "Còn material issue chưa xử lý; không duyệt được.",
        )
    for comparison in report.claim_comparisons:
        if comparison.status in ("CONFLICT", "UNRESOLVED"):
            raise DomainError(
                "B7_WORKFLOW_BLOCKED",
                f"Khoản khai {comparison.claim_id} chưa MATCHED "
                f"({comparison.status}); không duyệt được.",
            )
    statuses = {check.rule: check.status for check in report.checks}
    for rule in REQUIRED_ROUTINE_CHECKS:
        status = statuses.get(rule)
        if status is None:
            raise DomainError(
                "B7_WORKFLOW_BLOCKED",
                f"Thiếu check bắt buộc {rule}; không duyệt được.",
            )
        if status not in ("PASS", "NOT_APPLICABLE"):
            raise DomainError(
                "B7_WORKFLOW_BLOCKED",
                f"Check {rule} chưa PASS ({status}); không duyệt được.",
            )

    components = report.components
    e = _known_int(components.e, "e")
    a = _known_int(components.a, "a")
    ra = _known_int(components.ra, "ra")
    p = _known_int(components.p, "p")
    rp = _known_int(components.rp, "rp")
    t = _known_int(components.t, "t")
    b = _known_int(components.b, "b")

    net = e - (a - ra) - (p - rp)
    if report.calculated_net_vnd != net:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "calculated_net không khớp công thức E-(A-RA)-(P-RP); không duyệt.",
        )
    if report.proposed_net_vnd != net:
        raise DomainError(
            "B7_WORKFLOW_BLOCKED",
            "proposed_net trống hoặc không khớp calculated_net; không duyệt.",
        )
    if net > 0:
        direction, amount = "PAY_EMPLOYEE", net
    elif net < 0:
        direction, amount = "COLLECT_FROM_EMPLOYEE", -net
    else:
        direction, amount = "BALANCED", 0
    return B7DecisionTarget(
        employee_cost_vnd=e, total_work_cost_vnd=t, budget_vnd=b,
        signed_net_vnd=net, direction=direction, amount_vnd=amount)


def b7_business_signature(submission: Submission, sources: list[SourceRecord],
                          report: Report, policy: dict,
                          linked_context) -> str:
    """Semantic business basis: excludes run ID/usage/note, keeps history.

    Includes employee/work/scope, source hashes, policy, budget, component
    baseline (including history a/ra/p/rp) and cost facts. B9 revalidation uses
    this to distinguish a fulfillment delta from a basis change.
    """
    components = report.components
    payload = {
        "scope": {"employee_ref": submission.employee_ref,
                  "work_ref": submission.work_ref},
        "form": submission.form,
        "sources": sorted(source.sha256 for source in sources),
        "policy": policy,
        "completion": report.completion,
        "components": {key: getattr(components, key).value
                       for key in ("t", "b", "e", "a", "ra", "p", "rp")},
        "calculated_net": report.calculated_net_vnd,
        "expense_rows": [(row.expense_id, row.state, row.claimed_amount_vnd,
                          row.eligible_employee_vnd, row.company_direct_vnd)
                         for row in report.expense_rows],
        "links": [(link.kind, link.from_id, link.to_id, link.portion_vnd,
                   link.status) for link in report.links],
        "claims": [(c.claim_id, c.expense_id, c.status)
                   for c in report.claim_comparisons],
        "context_history": (linked_context.history
                            if linked_context is not None else None),
        "context_ref": (linked_context.company_packet_ref
                        if linked_context is not None else None),
    }
    return fingerprint("B7_BUSINESS", payload)


# Backend-owned source uses that carry fulfillment/context snapshots, not
# employee cost evidence. They change as receipts are folded in, so they must
# not invalidate the accepted cost basis (a correct receipt keeps it VALID).
_FULFILLMENT_SOURCE_USES = ("LINKED_B7_CONTEXT", "B7_SETTLEMENT_PROOF")


def _cost_evidence_sources(sources: list[SourceRecord]) -> list[SourceRecord]:
    return [source for source in sources
            if source.provenance.get("source_use")
            not in _FULFILLMENT_SOURCE_USES]


def b7_cost_signature(submission: Submission, sources: list[SourceRecord],
                      report: Report, policy: dict, linked_context) -> str:
    """Cost-only basis: excludes A/RA/P/RP and backend fulfillment sources.

    So a new receipt (history delta) does not invalidate the accepted cost
    basis. Resolves cost facts by owning-document hash, not the whole context
    JSON (which changes when a receipt arrives). Backend-owned context/proof
    sources are excluded so only employee cost evidence can change the basis.
    """
    evidence = _cost_evidence_sources(sources)
    payload = {
        "scope": {"employee_ref": submission.employee_ref,
                  "work_ref": submission.work_ref},
        "form": submission.form,
        "sources": sorted(source.sha256 for source in evidence),
        "policy": policy,
        "cost_components": {"e": report.components.e.value,
                            "t": report.components.t.value,
                            "b": report.components.b.value},
        "expense_rows": [(row.expense_id, row.state, row.claimed_amount_vnd,
                          row.eligible_employee_vnd, row.company_direct_vnd)
                         for row in report.expense_rows],
        "claims": [(c.claim_id, c.expense_id, c.status)
                   for c in report.claim_comparisons],
    }
    return fingerprint("B7_COST", payload)


def b7_configuration_signature(b7, b3, policy: dict) -> str:
    """Activation/version/grants/routes/policy identity (not the demo clock).

    Changing the settlement clock to re-check a receipt is not itself a reason
    to revoke authority; the config/authority change is still considered by B9
    revalidation.
    """
    payload = {
        "b7": {"schema_version": b7.schema_version, "version": b7.version,
               "activated": b7.activated, "synthetic": b7.synthetic,
               "ref": b7.ref,
               "grants": [g.model_dump(mode="json") for g in b7.grants]},
        "b3": ({"version": b3.version, "activated": b3.activated,
                "routes": [r.model_dump(mode="json") for r in b3.routes]}
               if b3 is not None else None),
        "policy": policy,
    }
    return fingerprint("B7_CONFIG", payload)


def effective_b7_time(config) -> datetime:
    """Business time for a B7 authority check (server UTC unless demo clock)."""
    if config is not None and config.activated and config.synthetic \
            and config.demo_clock is not None:
        return config.demo_clock
    return datetime.now(timezone.utc)


def authorize_b7_decision(config, employee_ref: str, work_ref: str,
                          actor_ref: str, effective_at: datetime,
                          target: B7DecisionTarget | None):
    """Pick the single scoped B7 grant covering E and abs(S), or raise.

    Requires the B7 config activated and the actor present in the B3 route for
    the employee. A grant must be effective at ``effective_at`` and cover both
    the employee cost (E) and the absolute settlement (abs(S)); a missing limit
    does not cover. Two grants are never summed, and the B3 advance grant or a
    generic demo grant is never a substitute.
    """
    from invoice_referee.settlement.rules import covering_grant

    if config is None or not config.activated:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            "Chưa cấu hình B7 company config; không có quyền quyết toán B7.",
        )
    scoped = [grant for grant in config.grants if grant.actor_ref == actor_ref]
    if not scoped:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {actor_ref} không có B7 grant trong config; không quyết định.",
        )
    if target is None:
        # RETURN/REFUSE: still need a scoped, effective grant (route/scope),
        # without asserting a monetary acceptance.
        grant = covering_grant(scoped, employee_ref, work_ref, effective_at,
                               employee_cost_vnd=None, settlement_vnd=None,
                               total_work_cost_vnd=None)
        if grant is None:
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"B7 grant của {actor_ref} không còn hiệu lực/đúng scope; "
                f"không quyết định.",
            )
        return grant
    grant = covering_grant(
        scoped, employee_ref, work_ref, effective_at,
        employee_cost_vnd=target.employee_cost_vnd,
        settlement_vnd=target.signed_net_vnd,
        total_work_cost_vnd=target.total_work_cost_vnd)
    if grant is None:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Không có một B7 grant cover cả E={target.employee_cost_vnd} và "
            f"abs(S)={abs(target.signed_net_vnd)} cho {employee_ref}/{work_ref} "
            f"tại thời điểm quyết định; không duyệt.",
        )
    return grant
