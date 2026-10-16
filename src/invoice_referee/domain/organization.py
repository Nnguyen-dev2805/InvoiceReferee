"""Typed organization context (contracts §2, §3, §5; plan A1).

The organization context is the simulated-but-observable ledger/context an
assessment rests on: activity identity/authorization, people, policies, grants,
the ledger (A/P/R so far), the coverage record and its witnesses. It
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
    MoneyEvent / CoverageRecord (plan A.1/A1). Legacy budget fields remain
    loadable for older contexts but do not affect current settlement decisions.
    The legacy ``tenant``/``profile``/``records`` fields also remain compatible.
    """

    tenant: Id = "tenant:demo"
    profile: str = "TRAVEL"
    # Simulated observable records only; no `expected`/`forced` routing fields.
    records: tuple[str, ...] = ()
    # Legacy field: retained for older context files; ignored by current decisions.
    budget_amount: int | None = None
    # Typed records (plan A.1).
    organization_id: str | None = None
    # The scoped organization's legal name (T2): used to bind a company-buyer-only
    # invoice to the dossier via composite claimant/company/activity identity.
    company_name: str | None = None
    company_tax_id: str | None = None
    activity: dict[str, object] | None = None
    people: tuple[dict[str, object], ...] = ()
    policies: tuple[dict[str, object], ...] = ()
    # Versioned per-item category caps + submission window (T3). Each entry:
    # {id, version, effective_from, effective_to?, profile?, per_item_caps?,
    #  submission_window_days?, excluded_categories?}.
    category_policies: tuple[dict[str, object], ...] = ()
    budgets: tuple[dict[str, object], ...] = ()
    grants: tuple[dict[str, object], ...] = ()
    ledger: tuple[dict[str, object], ...] = ()
    coverage: dict[str, object] | None = None
    # A shared demo may carry one history snapshot per activity; the loader
    # exposes only the selected activity's snapshot as ``coverage``.
    coverages: tuple[dict[str, object], ...] = ()
    witnesses: tuple[dict[str, object], ...] = ()
    # The other activities the demo context declares (id + name + purpose), so a
    # snapshot built from the demo importer can be scoped per activity without
    # inventing per-activity money it never had (plan A5/D).
    activities: tuple[dict[str, object], ...] = ()
    financial_as_of: str | None = None
    data_origin: str | None = None
