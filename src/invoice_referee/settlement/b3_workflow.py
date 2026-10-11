"""B3 present-and-approve workflow helpers (b3-intake-v1).

Lifecycle logic for the verbal-assignment branch lives here — NOT in the
Reader (which only returns sourced facts/proposals) and NOT via any LLM. These
functions are deterministic and backend-owned: they resolve the effective
business time and the basis signature that a presentation/decision is bound to.

No decision/approval/authority arithmetic is done by a provider; grants come
from the backend company context (``B3CompanyContext``), never from a client
dict.
"""
from __future__ import annotations

from datetime import datetime, timezone

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3CompanyContext, B3Route
from invoice_referee.settlement.models import (
    Report,
    SourceRecord,
    Submission,
    fingerprint,
)


def effective_b3_time(context: B3CompanyContext) -> datetime:
    """Business time an authority check is evaluated at.

    Uses the fixture ``demo_clock`` only when the context is both activated and
    synthetic; real data uses the server clock (never a stale ``money_as_of``
    supplied by a client). The real ``created_at`` is kept separately by the
    caller.
    """
    if context.demo_clock is not None and context.activated and context.synthetic:
        return context.demo_clock
    return datetime.now(timezone.utc)


def b3_context_signature(context: B3CompanyContext) -> str:
    """Deterministic identity of the applied company context.

    Includes version/activation/grants/route/coverage/history so a context or
    authority change invalidates a pending basis.
    """
    return fingerprint("B3_CONTEXT", context.model_dump(mode="json"))


def b3_route_for(context: B3CompanyContext, employee_ref: str) -> B3Route | None:
    """The backend-selected accountant/approver route for an employee."""
    for route in context.routes:
        if route.employee_ref == employee_ref:
            return route
    return None


def b3_basis_signature(submission: Submission, sources: list[SourceRecord],
                       report: Report, policy: dict,
                       context: B3CompanyContext) -> str:
    """Deterministic fingerprint of the business basis a presentation binds.

    Deliberately excludes run ID, timestamps, token counts and pure message
    copies: those are not business facts. Includes the scope/form/revision
    content, active source hashes, policy/context identity and the
    proposal-critical values/check states that affect a decision.
    """
    proposal = report.b3
    checks = sorted((check.rule, check.status) for check in report.checks)
    issues = sorted((issue.issue_id, issue.type, issue.owner, issue.unresolved)
                    for issue in report.issues)
    payload = {
        "scope": {"employee_ref": submission.employee_ref,
                  "work_ref": submission.work_ref},
        "form": submission.form,
        "sources": sorted(source.sha256 for source in sources),
        "policy": policy,
        "context": b3_context_signature(context),
        "completion": report.completion,
        "readiness": proposal.readiness if proposal is not None else None,
        "forecast": ([proposal.forecast_company_vnd,
                      proposal.forecast_employee_vnd,
                      proposal.forecast_total_vnd]
                     if proposal is not None else None),
        "checks": checks,
        "issues": issues,
    }
    return fingerprint("B3_BASIS", payload)


def b3_grant_for(context: B3CompanyContext, actor_ref: str,
                 employee_ref: str, work_ref: str) -> list:
    """Grants that belong to this actor for this employee/work (no client dict).

    A grant with ``work_ref is None`` covers every work for the employee; a
    concrete ``work_ref`` must match. Returned in context order so the caller
    can pick the single covering grant.
    """
    return [grant for grant in context.grants
            if grant.actor_ref == actor_ref
            and grant.employee_ref == employee_ref
            and (grant.work_ref is None or grant.work_ref == work_ref)]


def authorize_b3_decision(context: B3CompanyContext, employee_ref: str,
                          work_ref: str, payload, actor_id: str,
                          effective_at: datetime, requested_vnd: int | None):
    """Pick the single covering B3 grant for a decision, or raise.

    One grant must cover every required content — work permission, budget and
    advance — inside its effective window. Limits missing on the grant are not
    unlimited: the grant simply does not cover that content. Two grants are
    never summed to reach authority. RETURN/REFUSE still need a grant whose
    advance limit covers the requested amount, so refusal cannot dodge scope.
    """
    route = b3_route_for(context, employee_ref)
    if route is None or route.approver_ref != actor_id:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Vai {actor_id} không phải người duyệt được cấu hình cho "
            f"nhân viên {employee_ref}; quyết định không được ghi.",
        )
    covering = [grant for grant in
                b3_grant_for(context, actor_id, employee_ref, work_ref)
                if grant.effective_from <= effective_at <= grant.effective_to]
    if not covering:
        raise DomainError(
            "BEYOND_AUTHORITY",
            f"Không có B3 grant còn hiệu lực cho {actor_id}/{employee_ref}/"
            f"{work_ref}; quyết định không được ghi.",
        )
    outcome = payload.outcome
    for grant in covering:
        if grant.max_advance_vnd is None:
            continue
        if requested_vnd is not None and grant.max_advance_vnd < requested_vnd:
            continue  # grant does not cover the amount being decided
        if outcome == "APPROVE":
            if not grant.allow_work:
                continue
            if grant.max_budget_vnd is None or payload.budget_vnd is None \
                    or payload.budget_vnd > grant.max_budget_vnd:
                continue
            if payload.advance_vnd is None \
                    or payload.advance_vnd > grant.max_advance_vnd:
                continue
        return grant
    raise DomainError(
        "BEYOND_AUTHORITY",
        f"Grant hiện có không cover nội dung {outcome} cho {actor_id} "
        f"(thiếu hạn mức/allow_work hoặc ngoài hiệu lực); quyết định không "
        f"được ghi.",
    )
