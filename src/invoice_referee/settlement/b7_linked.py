"""B6→B7 linked settlement helpers (b7-linked-intake-v1).

A linked child is a NEW B7 case sharing the parent B3's employee/work; the
parent is never mutated. Deterministic Python imports persisted financial facts
from the parent (decision/managed advance events) and a source-backed company
packet; the Reader/matcher still handles the employee's actual expense
originals. Nothing here decides money via an LLM, and no forecast/approved
advance/PERSONAL declaration ever becomes a fact.

This slice is report-only: no B8 decision, payment, handoff or closure.
"""
from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    B7ClaimComparison,
    B7CompanyConfig,
    B7CompanyPacket,
    B7LinkedIntake,
    Issue,
    LinkedB7ContextSnapshot,
    Observation,
    Relation,
)

B7_LINKED_SCHEMA = "b7-linked-intake-v1"

# Canonical whole-work history keys; a group is KNOWN only when coverage lists
# it (absence with incomplete coverage is unknown, never 0).
_HISTORY_GROUPS = {
    "ADVANCE": "history.advance.received",
    "ADVANCE_RETURN": "history.advance.returned",
    "REIMBURSEMENT_RECEIVED": "history.reimbursement.received",
    "REIMBURSEMENT_RETURN": "history.reimbursement.returned",
}
# kind -> (history key, sign)
_EVENT_HISTORY = {
    "ADVANCE_RECEIVED": ("history.advance.received", 1),
    "ADVANCE_RETURN": ("history.advance.returned", 1),
    "REIMBURSEMENT_RECEIVED": ("history.reimbursement.received", 1),
    "REIMBURSEMENT_RETURN": ("history.reimbursement.returned", 1),
}


def is_linked_b7(form: dict | None) -> bool:
    """True when a form follows the b7-linked-intake-v1 contract."""
    return isinstance(form, dict) and \
        form.get("schema_version") == B7_LINKED_SCHEMA


def load_b7_linked_intake(form: dict) -> B7LinkedIntake:
    """Validate a linked intake form; shape errors are technical, not silent.

    The server appends ``origin_link`` to the persisted form; it is stripped
    here so validation covers only the client-editable intake.
    """
    cleaned = {k: v for k, v in form.items() if k != "origin_link"}
    try:
        return B7LinkedIntake.model_validate(cleaned)
    except Exception as error:  # pydantic ValidationError
        raise DomainError(
            "INVALID_PAYLOAD",
            f"Form quyết toán liên kết không hợp lệ: {error}",
        ) from error


def load_b7_company_config(path: Path) -> B7CompanyConfig:
    """Load an explicitly configured B7 company config; malformed is fatal."""
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"Không đọc được SETTLEMENT_B7_CONTEXT_PATH ({file}): {error}",
        ) from error
    except json.JSONDecodeError as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File B7 company config không phải JSON hợp lệ ({file}): {error}",
        ) from error
    try:
        return B7CompanyConfig.model_validate(data)
    except Exception as error:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"File B7 company config không hợp lệ ({file}): {error}",
        ) from error


def load_b7_company_packet(payload: dict) -> B7CompanyPacket:
    try:
        return B7CompanyPacket.model_validate(payload)
    except Exception as error:
        raise DomainError(
            "INVALID_PAYLOAD",
            f"Company packet không hợp lệ: {error}",
        ) from error


def build_linked_context(*, origin_case_id: str, parent_fingerprint: str,
                         decision, managed_events, packet: B7CompanyPacket | None,
                         policy: dict, authority_version: str | None,
                         money_as_of, knowledge_cutoff) -> LinkedB7ContextSnapshot:
    """Build the linked context from typed records + a validated company packet.

    Whole-work history is KNOWN only for groups the coverage lists and only from
    canonical company events; unknown groups stay ``None`` (never fabricated 0).
    Managed B5 advance subtotal is never used as whole-work A.
    """
    issues = []
    history: dict[str, int | None] = {key: None for key in _HISTORY_GROUPS.values()}
    company_events = list(packet.events) if packet is not None else []
    company_expenses = list(packet.expenses) if packet is not None else []
    coverage_groups = set(packet.coverage.groups) if packet is not None else set()
    coverage_ok = bool(packet is not None
                       and packet.coverage.complete_prior_history
                       and not packet.coverage.missing_ranges)

    if coverage_ok:
        for group, key in _HISTORY_GROUPS.items():
            if group not in coverage_groups:
                continue
            total = 0
            for event in company_events:
                if event.outcome != "RECEIVED" or event.amount_vnd is None:
                    continue
                mapping = _EVENT_HISTORY.get(event.kind)
                if mapping is None or mapping[0] != key:
                    continue
                total += mapping[1] * event.amount_vnd
            history[key] = total

    budget = None
    if decision is not None and decision.outcome == "APPROVE":
        budget = decision.budget_vnd

    return LinkedB7ContextSnapshot(
        origin_case_id=origin_case_id,
        parent_fingerprint=parent_fingerprint,
        decision_ref=decision.id if decision is not None else None,
        managed_advance_refs=[e.id for e in managed_events],
        company_packet_ref=packet.coverage.ref if packet is not None else None,
        context_version=packet.coverage.ref if packet is not None else None,
        policy=policy,
        b7_authority_version=authority_version,
        history=history,
        budget_vnd=budget,
        company_packet=packet,
        company_events=company_events,
        company_expenses=company_expenses,
        issues=issues,
        money_as_of=money_as_of,
        knowledge_cutoff=knowledge_cutoff,
    )


def linked_context_observations(snapshot: LinkedB7ContextSnapshot,
                                source_id: str
                                ) -> tuple[list[Observation], list[Relation],
                                           list[Issue]]:
    """Turn typed persisted context into sourced observations (no LLM re-read).

    History/budget become KNOWN financial facts only when coverage-backed
    (``None`` stays out of the aggregate). Company actual expenses/payments are
    emitted as sourced observations for the matcher. Employee declarations never
    appear here — they are not facts.
    """
    observations: list[Observation] = []
    relations: list[Relation] = []
    issues: list[Issue] = list(snapshot.issues)
    for key, value in (snapshot.history or {}).items():
        if value is None:
            continue
        observations.append(Observation(
            fact_id=f"ctx:{key}", key=key, read_state="READ", value=value,
            source_id=source_id, locator=f"context:{key}",
            basis="LINKED_B7_CONTEXT (coverage-backed)", usability="USABLE"))
    if snapshot.budget_vnd is not None:
        observations.append(Observation(
            fact_id="ctx:budget.approved", key="budget.approved",
            read_state="READ", value=snapshot.budget_vnd, source_id=source_id,
            locator="context:budget.approved",
            basis="LINKED_B7_CONTEXT (B3 decision budget)", usability="USABLE"))
    for expense in snapshot.company_expenses:
        if expense.amount_vnd is None:
            continue
        eid = expense.expense_ref
        observations.append(Observation(
            fact_id=f"ctx:expense.{eid}.amount", key=f"expense.{eid}.amount",
            read_state="READ", value=expense.amount_vnd, source_id=source_id,
            locator=f"context:expense.{eid}",
            basis="LINKED_B7_CONTEXT (company actual expense)",
            usability="USABLE"))
        observations.append(Observation(
            fact_id=f"ctx:expense.{eid}.purpose", key=f"expense.{eid}.purpose",
            read_state="READ", value=expense.purpose, source_id=source_id,
            locator=f"context:expense.{eid}",
            basis="LINKED_B7_CONTEXT (company actual expense)",
            usability="USABLE"))
    for event in snapshot.company_events:
        if event.outcome != "RECEIVED" or event.amount_vnd is None:
            continue
        pay_id = f"{event.event_namespace}:{event.event_ref}"
        observations.append(Observation(
            fact_id=f"ctx:payment.{pay_id}.amount",
            key=f"payment.{pay_id}.amount", read_state="READ",
            value=event.amount_vnd, source_id=source_id,
            locator=f"context:payment.{pay_id}",
            basis="LINKED_B7_CONTEXT (company actual event)",
            usability="USABLE"))
        observations.append(Observation(
            fact_id=f"ctx:payment.{pay_id}.payer",
            key=f"payment.{pay_id}.payer", read_state="READ",
            value=event.payer_ref or "COMPANY", source_id=source_id,
            locator=f"context:payment.{pay_id}",
            basis="LINKED_B7_CONTEXT (company actual event)",
            usability="USABLE"))
        observations.append(Observation(
            fact_id=f"ctx:payment.{pay_id}.status",
            key=f"payment.{pay_id}.status", read_state="READ",
            value="RECEIVED", source_id=source_id,
            locator=f"context:payment.{pay_id}",
            basis="LINKED_B7_CONTEXT (company actual event)",
            usability="USABLE"))
    for expense in snapshot.company_expenses:
        for event_ref in expense.payment_event_refs:
            relations.append(Relation(
                relation_id=f"ctx-link:{expense.expense_ref}:{event_ref}",
                kind="EXPENSE_PAYMENT", from_id=expense.expense_ref,
                to_id=event_ref, supporting_refs=[source_id],
                status="ESTABLISHED",
                reason="company packet links expense to payment event"))
    return observations, relations, issues


def claim_comparisons(claim_rows, relations: list[Relation],
                      expenses: dict[str, dict]) -> list[B7ClaimComparison]:
    """Compare each declared claim against its matched actual expense.

    One claim → one expense for the MVP. A matched amount yields MATCHED; a
    material amount difference yields CONFLICT (never the forecast); no link
    yields UNRESOLVED. Declared values are shown as declarations only.
    """
    by_claim: dict[str, str] = {}
    for relation in relations:
        if relation.kind == "CLAIM_EXPENSE" and relation.status == "ESTABLISHED":
            by_claim.setdefault(relation.from_id, relation.to_id)
    out: list[B7ClaimComparison] = []
    for row in claim_rows:
        expense_id = by_claim.get(row.claim_id)
        if expense_id is None:
            out.append(B7ClaimComparison(
                claim_id=row.claim_id, expense_id=None,
                declared_amount_vnd=row.declared_amount_vnd,
                payer_declaration=row.declared_payer, status="UNRESOLVED",
                reason="Chưa ghép được khoản khai với chi phí thực tế."))
            continue
        expense = expenses.get(expense_id, {})
        verified = expense.get("amount")
        if verified is None or row.declared_amount_vnd is None:
            out.append(B7ClaimComparison(
                claim_id=row.claim_id, expense_id=expense_id,
                declared_amount_vnd=row.declared_amount_vnd,
                verified_amount_vnd=verified,
                payer_declaration=row.declared_payer, status="UNRESOLVED",
                refs=expense.get("refs", []),
                reason="Số khai hoặc số thực tế chưa xác định."))
            continue
        if verified == row.declared_amount_vnd:
            out.append(B7ClaimComparison(
                claim_id=row.claim_id, expense_id=expense_id,
                declared_amount_vnd=row.declared_amount_vnd,
                verified_amount_vnd=verified,
                payer_declaration=row.declared_payer, status="MATCHED",
                refs=expense.get("refs", []), reason="Số khai khớp chi phí."))
        else:
            out.append(B7ClaimComparison(
                claim_id=row.claim_id, expense_id=expense_id,
                declared_amount_vnd=row.declared_amount_vnd,
                verified_amount_vnd=verified,
                payer_declaration=row.declared_payer, status="CONFLICT",
                refs=expense.get("refs", []),
                reason=(f"Số khai {row.declared_amount_vnd} khác chi phí thực tế "
                        f"{verified}; cần làm rõ.")))
    return out
