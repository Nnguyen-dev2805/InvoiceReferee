"""Snapshot builder: persisted sources -> immutable AssessmentInput (contracts §9, §10.2).

The Reconciler is pure over an AssessmentInput, so the workflow assembles that
input from the root's stored sources, the org context (budget/grants/policy) and
the tenant usage registry. Eligibility basis and money basis stay separate.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from invoice_referee.domain.case import (
    AssessmentInput,
    CaseScope,
    ReadSet,
)
from invoice_referee.domain.evidence import Observation, Relation, SourceRef
from invoice_referee.domain.finance import CoverageRecord, Expense, ExpensePayment, MoneyEvent
from invoice_referee.domain.policy import BudgetDecision, Grant, PolicyVersion
from invoice_referee.evaluation.models import Transcription


def _int_fact(fact) -> int | None:
    """Coerce a transcribed fact's value to int, or None if it is not numeric."""
    if fact is None:
        return None
    try:
        return int(fact.value)
    except (TypeError, ValueError):
        return None


def _ref(source_id: str, digest: str, page: int, quote: str):
    from invoice_referee.domain.common import EvidenceRef

    return EvidenceRef(
        source_id=source_id,
        source_sha256=digest,
        page=page,
        exact_quote=quote or "transcription",
    )


def _load_confirmations(cx: sqlite3.Connection, tenant: str, root_id: str):
    """Responsible confirmations from owner answers (contracts §3, §5)."""
    from datetime import datetime as _dt

    from invoice_referee.domain.common import EvidenceRef
    from invoice_referee.domain.evidence import Confirmation

    out: list[Confirmation] = []
    for row in cx.execute(
        "SELECT * FROM case_confirmations WHERE tenant = ? AND root_id = ? "
        "ORDER BY observed_at, id",
        (tenant, root_id),
    ).fetchall():
        refs = tuple(
            EvidenceRef.model_validate(ref)
            for ref in json.loads(row["refs_json"] or "[]")
        )
        out.append(
            Confirmation(
                fact_key=str(row["fact_key"]),
                value=row["value"],
                actor=str(row["actor"]),
                scope=str(row["scope"]),
                refs=refs,
                reason=str(row["reason"]),
                observed_at=_dt.fromisoformat(row["observed_at"]),
            )
        )
    return tuple(out)


def build_assessment_input(
    cx: sqlite3.Connection,
    *,
    tenant: str,
    root_id: str,
    employee: str,
    activity: str,
    profile: str,
    transcription: Transcription | None,
    as_of: datetime | None = None,
) -> AssessmentInput:
    """Assemble the immutable snapshot the Reconciler assesses.

    A STUB transcription is turned into verified expenses/payments/observations
    with real locators. No expected/oracle value enters here.
    """
    sources = {
        row["source_id"]: row
        for row in cx.execute(
            "SELECT * FROM case_sources WHERE root_id = ?", (root_id,)
        ).fetchall()
    }
    primary = next(iter(sources.values()), None)
    src_id = str(primary["source_id"]) if primary is not None else "source:stub"
    src_digest = str(primary["digest"]) if primary is not None else "0" * 64

    observations: list[Observation] = []
    relations: list[Relation] = []
    expenses: list[Expense] = []
    ledger: list[MoneyEvent] = []
    coverage: CoverageRecord | None = None

    # Responsible confirmations from owner answers (contracts §3, §5): an
    # answered FACT changes the basis on the next assessment.
    confirmations = _load_confirmations(cx, tenant, root_id)
    confirmed_payer = next(
        (c.value for c in confirmations if c.fact_key == "expense:payer"), None
    )

    if transcription is not None:
        facts = {f.field: f for f in transcription.facts}
        for fact in transcription.facts:
            observations.append(
                Observation(
                    field=fact.field,
                    raw=fact.quote,
                    normalized=fact.value,
                    read_state="CLEAR",
                    ref=_ref(src_id, src_digest, fact.page, fact.quote),
                )
            )
        for kind, from_id, to_id, state in transcription.relations:
            relations.append(
                Relation(
                    kind=kind,
                    from_id=from_id,
                    to_id=to_id,
                    state=state,  # type: ignore[arg-type]
                    refs=(_ref(src_id, src_digest, 1, "transcription relation"),),
                )
            )

        # Incurred cost (T) and payment portions (E/C) from the transcription.
        incurred = facts.get("incurred")
        if incurred is not None:
            payments: list[ExpensePayment] = []
            paid_employee = _int_fact(facts.get("paid_employee"))
            paid_company = _int_fact(facts.get("paid_company"))
            if paid_employee and paid_employee > 0:
                payments.append(
                    ExpensePayment(
                        external_key="payment:employee",
                        payer=employee,
                        payee="vendor:demo",
                        amount=paid_employee,
                        expense_id="expense:1",
                        received_state="CLEAR",
                        refs=(_ref(src_id, src_digest, 1, "employee paid"),),
                    )
                )
            if paid_company and paid_company > 0:
                payments.append(
                    ExpensePayment(
                        external_key="payment:company",
                        payer="company:demo",
                        payee="vendor:demo",
                        amount=paid_company,
                        expense_id="expense:1",
                        received_state="CLEAR",
                        refs=(_ref(src_id, src_digest, 1, "company paid"),),
                    )
                )
            # A responsible confirmation that the employee paid establishes the
            # E candidate for the full incurred cost (contracts §3), when no
            # explicit employee-paid portion was read.
            if confirmed_payer == employee and not paid_employee:
                payments.append(
                    ExpensePayment(
                        external_key="payment:employee-confirmed",
                        payer=employee,
                        payee="vendor:demo",
                        amount=_int_fact(incurred) or 0,
                        expense_id="expense:1",
                        received_state="CLEAR",
                        refs=(_ref(src_id, src_digest, 1, "confirmed payer"),),
                    )
                )
            eligibility = facts.get("eligibility")
            from invoice_referee.domain.common import Fact

            # No verified payer means E is not established: an incurred cost
            # with no payment proof is a FACT, not a silent E=0 (§3).
            if eligibility is not None:
                eligibility_state = str(eligibility.value)
            elif payments:
                eligibility_state = "ELIGIBLE"
            else:
                eligibility_state = "UNKNOWN"

            expenses.append(
                Expense(
                    id="expense:1",
                    economic_key=str(facts["economic_key"].value)
                    if facts.get("economic_key")
                    else f"invoice:{root_id}",
                    activity=activity,
                    incurred=Fact[int](
                        key="expense:1:incurred",
                        value=_int_fact(incurred) or 0,
                        state="KNOWN",
                        refs=(_ref(src_id, src_digest, 1, incurred.quote),),
                    ),
                    incurred_at=as_of or datetime.now(UTC),
                    payments=tuple(payments),
                    eligibility=eligibility_state,  # type: ignore[arg-type]
                    refs=(_ref(src_id, src_digest, 1, "expense"),),
                )
            )

        # Ledger events (A/P/R) from the transcription.
        for field, kind, payer, payee in (
            ("advance", "ADVANCE_RECEIVED", "company:demo", employee),
            ("reimbursed", "REIMBURSEMENT_RECEIVED", "company:demo", employee),
            ("returned", "EMPLOYEE_RETURN", employee, "company:demo"),
        ):
            fact = facts.get(field)
            amount = _int_fact(fact)
            if amount and amount > 0:
                ledger.append(
                    MoneyEvent(
                        id=f"event:{field}",
                        external_key=f"external:{field}",
                        kind=kind,  # type: ignore[arg-type]
                        scope=activity,
                        payer=payer,
                        payee=payee,
                        amount=amount,
                        event_at=as_of or datetime.now(UTC),
                        recorded_at=as_of or datetime.now(UTC),
                        verification_state="CONFIRMED",
                        allocation_state="ALLOCATED",
                        refs=(_ref(src_id, src_digest, 1, fact.quote),),
                    )
                )

        if facts.get("coverage") is not None or "coverage" in facts:
            coverage = CoverageRecord(
                scope=activity,
                start=datetime(2026, 9, 1, tzinfo=UTC),
                as_of=as_of or datetime.now(UTC),
                funds=("company:demo",),
                flow_kinds=(
                    "ADVANCE_RECEIVED",
                    "REIMBURSEMENT_RECEIVED",
                    "EMPLOYEE_RETURN",
                    "REVERSAL",
                    "OBSERVED_UNALLOCATED",
                ),
                ledger_version="ledger:v1",
                witness_refs=(_ref(src_id, src_digest, 1, "coverage witness"),),
            )

    # Recorded money events (actual P/R/A) join the ledger so the projection
    # reflects what really moved (§4). Only CONFIRMED events are projected; an
    # OBSERVED-only claim is preserved for audit but is not verified money, so
    # it must not move A/P/R/S or fulfill an instruction.
    for row in cx.execute(
        "SELECT payload_json FROM money_events WHERE tenant = ? AND root_id = ? "
        "AND verification_state = 'CONFIRMED' ORDER BY recorded_at, id",
        (tenant, root_id),
    ).fetchall():
        ledger.append(MoneyEvent.model_validate_json(row["payload_json"]))
    if coverage is None and cx.execute(
        "SELECT 1 FROM money_events WHERE tenant = ? AND root_id = ? "
        "AND verification_state = 'CONFIRMED' LIMIT 1",
        (tenant, root_id),
    ).fetchone() is not None:
        coverage = CoverageRecord(
            scope=activity,
            start=datetime(2026, 9, 1, tzinfo=UTC),
            as_of=as_of or datetime.now(UTC),
            funds=("company:demo",),
            flow_kinds=(
                "ADVANCE_RECEIVED",
                "REIMBURSEMENT_RECEIVED",
                "EMPLOYEE_RETURN",
                "REVERSAL",
                "OBSERVED_UNALLOCATED",
            ),
            ledger_version="ledger:v1",
            witness_refs=(_ref(src_id, src_digest, 1, "ledger coverage"),),
        )

    # Org context: budget, grants, policy for this activity/tenant.
    budget_rows = cx.execute(
        "SELECT * FROM context_activities WHERE activity_id = ? AND tenant = ?",
        (activity, tenant),
    ).fetchall()
    budgets: list[BudgetDecision] = []
    for row in budget_rows:
        if row["budget_amount"] is not None:
            from datetime import datetime as _dt

            effect_from = (
                _dt.fromisoformat(row["budget_effect_from"])
                if row["budget_effect_from"]
                else datetime(2026, 1, 1, tzinfo=UTC)
            )
            budgets.append(
                BudgetDecision(
                    id=f"budget:{activity}",
                    activity=activity,
                    amount=int(row["budget_amount"]),
                    effect_range=(effect_from, None),
                    actor="employee:approver",
                )
            )

    grants: list[Grant] = []
    for row in cx.execute(
        "SELECT * FROM context_grants WHERE tenant = ?", (tenant,)
    ).fetchall():
        from datetime import datetime as _dt

        grants.append(
            Grant(
                id=str(row["grant_id"]),
                version=str(row["version"]),
                actor=str(row["actor"]),
                actions=tuple(json.loads(row["actions_json"])),
                scope=str(row["scope"]),
                max_amount=int(row["max_amount"]),
                effective_from=_dt.fromisoformat(row["effective_from"]),
                effective_to=_dt.fromisoformat(row["effective_to"])
                if row["effective_to"]
                else None,
            )
        )

    policy = (
        PolicyVersion(
            id=f"policy:{profile}",
            version="v1",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            profile=profile,
            rules=("TRAVEL_CORE", "INVOICE_REQUIRED"),
        ),
    )

    scope = CaseScope(tenant=tenant, employee=employee, activity=activity, profile=profile)
    return AssessmentInput(
        scope=scope,
        expense_facts=tuple(expenses),
        observations=tuple(observations),
        relations=tuple(relations),
        confirmations=confirmations,
        ledger=tuple(ledger),
        coverage=coverage,
        policy=policy,
        grants=tuple(grants),
        budget=tuple(budgets),
        exceptions=(),
        previous_eligibility=None,
        read_set=ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=1,
        ),
        as_of=as_of or datetime.now(UTC),
    )


def cost_basis_digest(input: AssessmentInput) -> str:
    """A stable digest of the cost-relevant fields only (contracts §10.2)."""
    payload = {
        "expenses": [
            (e.id, e.economic_key, e.incurred.value, e.eligibility) for e in input.expense_facts
        ],
        "activity": input.scope.activity,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
