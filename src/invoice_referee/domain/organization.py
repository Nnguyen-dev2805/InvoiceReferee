"""Typed organization context (contracts §2, §3, §5; plan A1).

The organization context is the simulated-but-observable ledger/context an
assessment rests on: the activity + authorization, people, policies, budgets,
grants, the ledger (A/P/R so far), the coverage record and its witnesses. It
never carries an expected E/S or a route.

This DTO lives in the domain layer so both the workflow importer and the
evaluation loader share ONE schema; `evaluation.models` re-exports it for
compatibility.
"""

from __future__ import annotations

from invoice_referee.domain.common import Id, StrictModel


class OrganizationContext(StrictModel):
    """Genuine simulated observable ledger/context — never the expected E/S.

    The typed records the importer turns into domain PolicyVersion / Grant /
    BudgetDecision / MoneyEvent / CoverageRecord (plan A.1/A1). The legacy
    ``tenant``/``profile``/``records``/``budget_amount`` fields are retained so
    older generators keep loading.
    """

    tenant: Id = "tenant:demo"
    profile: str = "TRAVEL"
    # Simulated observable records only; no `expected`/`forced` routing fields.
    records: tuple[str, ...] = ()
    # The activity's verified budget B, if one exists (observable org data).
    budget_amount: int | None = None
    # Typed records (plan A.1).
    organization_id: str | None = None
    activity: dict[str, object] | None = None
    people: tuple[dict[str, object], ...] = ()
    policies: tuple[dict[str, object], ...] = ()
    budgets: tuple[dict[str, object], ...] = ()
    grants: tuple[dict[str, object], ...] = ()
    ledger: tuple[dict[str, object], ...] = ()
    coverage: dict[str, object] | None = None
    witnesses: tuple[dict[str, object], ...] = ()
    financial_as_of: str | None = None
    data_origin: str | None = None
