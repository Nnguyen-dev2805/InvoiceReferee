"""Policy Engine — build immutable PolicyContext and resolve the policy-correct action.

``build_policy_context`` produces the structured constraints (tri-state scope,
authority threshold, applicable rules). ``resolve_action`` is the single
deterministic mapping from verified facts to a user-facing action; both the
Decision Guard and the agent fallback rely on it, so the answer is identical
whether or not the LLM is available.

This module never mutates facts and never calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from invoice_referee.domain import models as m
from invoice_referee.policy import config

# Business-check evaluation order (mirrors the check engine / DECISION_FLOW step 5).
_CHECK_ORDER = [
    "CHECK_VENDOR",
    "CHECK_ITEM",
    "CHECK_QUANTITY",
    "CHECK_PRICE",
    "CHECK_AMOUNT",
    "CHECK_DUPLICATE",
    "CHECK_PAYMENT",
    "CHECK_PO_LIMIT",
]

# Which role can supply the missing fact for a REQUEST_INFO, by check id.
_REQUEST_INFO_TARGET = {
    "CHECK_VENDOR": "Purchasing",
    "CHECK_ITEM": "Purchasing",
    "CHECK_QUANTITY": "Warehouse",
    "CHECK_PRICE": "Purchasing",
    "CHECK_AMOUNT": "Purchasing",
    "CHECK_DUPLICATE": "Accounting",
    "CHECK_PAYMENT": "Accounting",
    "CHECK_PO_LIMIT": "Purchasing",
}


@dataclass
class PolicyOutcome:
    """Deterministic policy resolution over verified facts."""

    action: m.DecisionAction
    uncertainty_type: Optional[m.UncertaintyType] = None
    primary_check_id: Optional[str] = None
    policy_rule_ids: list[str] = field(default_factory=list)
    target: Optional[str] = None
    reason: str = ""


def classify_scope(tx: m.Transaction) -> m.ScopeStatus:
    if tx.transaction_type is m.TransactionType.PO_GOODS_PURCHASE:
        return m.ScopeStatus.IN_SCOPE
    if tx.declared_transaction_type:
        return m.ScopeStatus.OUTSIDE_POLICY
    return m.ScopeStatus.UNKNOWN


def _unresolved_checks(checks: list[m.CheckResult]) -> list[m.CheckResult]:
    unresolved = [c for c in checks if c.status in (m.CheckStatus.FAIL, m.CheckStatus.UNKNOWN)]
    order = {cid: i for i, cid in enumerate(_CHECK_ORDER)}
    unresolved.sort(key=lambda c: order.get(c.check_id, len(order)))
    return unresolved


def _transaction_amount(tx: m.Transaction) -> Optional[int]:
    if tx.invoice and tx.invoice.total_amount is not None:
        return tx.invoice.total_amount
    if tx.po is not None:
        return tx.po.approved_total
    return None


def resolve_action(
    tx: m.Transaction, checks: list[m.CheckResult], ctx: m.PolicyContext
) -> PolicyOutcome:
    scope = ctx.scope_status

    # 1. Transaction type not determinable -> ask.
    if scope is m.ScopeStatus.UNKNOWN:
        return PolicyOutcome(
            action=m.DecisionAction.REQUEST_INFO,
            uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
            policy_rule_ids=["P01"],
            target="Accounting",
            reason="Transaction type cannot be determined from the provided evidence.",
        )

    # 2. Known type outside policy -> escalate.
    if scope is m.ScopeStatus.OUTSIDE_POLICY:
        return PolicyOutcome(
            action=m.DecisionAction.ESCALATE,
            uncertainty_type=m.UncertaintyType.OUTSIDE_POLICY,
            policy_rule_ids=["P13"],
            target=config.TARGET_ACCOUNTING_OWNER,
            reason="Transaction type is outside the PO-goods-purchase workflow covered by Policy v0.",
        )

    # 3a. Required evidence presence (specific rules before generic checks).
    if tx.po is None:
        return PolicyOutcome(
            action=m.DecisionAction.REQUEST_INFO,
            uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
            primary_check_id="CHECK_VENDOR",
            policy_rule_ids=["P01"],
            target="Purchasing",
            reason="No Purchase Order could be linked to this invoice.",
        )
    if not tx.goods_receipts:
        return PolicyOutcome(
            action=m.DecisionAction.REQUEST_INFO,
            uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
            primary_check_id="CHECK_QUANTITY",
            policy_rule_ids=["P04"],
            target="Warehouse",
            reason="No Goods Receipt confirms delivery for this PO.",
        )
    if tx.invoice is not None and tx.invoice.flagged:
        return PolicyOutcome(
            action=m.DecisionAction.REQUEST_INFO,
            uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
            primary_check_id="CHECK_AMOUNT",
            policy_rule_ids=["P15"],
            target="Supplier",
            reason="A critical invoice field is flagged/unreadable and cannot be trusted.",
        )

    # 3b. Any unresolved (FAIL/UNKNOWN) required check -> ask.
    unresolved = _unresolved_checks(checks)
    if unresolved:
        primary = unresolved[0]
        rule = primary.policy_rule_id or "P14"
        return PolicyOutcome(
            action=m.DecisionAction.REQUEST_INFO,
            uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
            primary_check_id=primary.check_id,
            policy_rule_ids=[rule],
            target=_REQUEST_INFO_TARGET.get(primary.check_id, "Purchasing"),
            reason=primary.reason or "A required fact is missing or inconsistent.",
        )

    # 4. Facts clear but beyond authority -> escalate.
    amount = _transaction_amount(tx)
    if amount is not None and amount > ctx.authority_threshold_vnd:
        return PolicyOutcome(
            action=m.DecisionAction.ESCALATE,
            uncertainty_type=m.UncertaintyType.BEYOND_AUTHORITY,
            policy_rule_ids=["P12"],
            target=config.TARGET_FINANCE_MANAGER,
            reason=(
                f"Transaction amount {amount} exceeds the {ctx.authority_threshold_vnd} "
                "agent authority threshold."
            ),
        )

    # 5. All clear and within authority -> auto-process.
    return PolicyOutcome(
        action=m.DecisionAction.AUTO_PROCESS,
        uncertainty_type=None,
        policy_rule_ids=[],
        target=None,
        reason="All required evidence is consistent and the transaction is within agent authority.",
    )


def build_policy_context(
    tx: m.Transaction, checks: list[m.CheckResult]
) -> m.PolicyContext:
    scope = classify_scope(tx)

    applicable: list[str] = []
    for c in checks:
        if c.status in (m.CheckStatus.FAIL, m.CheckStatus.UNKNOWN) and c.policy_rule_id:
            if c.policy_rule_id not in applicable:
                applicable.append(c.policy_rule_id)
    if "P12" not in applicable:
        applicable.append("P12")
    if scope is m.ScopeStatus.OUTSIDE_POLICY and "P13" not in applicable:
        applicable.append("P13")

    ctx = m.PolicyContext(
        scope_status=scope,
        authority_threshold_vnd=config.AUTHORITY_THRESHOLD_VND,
        applicable_rule_ids=applicable,
        deterministic_uncertainties=[],
    )

    # Deterministic uncertainty implied by the facts (single, priority-ordered).
    outcome = resolve_action(tx, checks, ctx)
    if outcome.uncertainty_type is not None:
        ctx.deterministic_uncertainties = [outcome.uncertainty_type]
    return ctx
