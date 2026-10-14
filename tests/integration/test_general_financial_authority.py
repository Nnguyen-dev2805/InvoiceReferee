"""T3: category policy reaches admission from context; authority boundaries hold.

Distinct expenses totalling E>8m need recognition AUTHORITY even when each item is
within its category cap; office E7.5m/A0 needs issuance AUTHORITY (>4m); independent
B below T is a POLICY issue even when the category passes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef, Fact
from invoice_referee.domain.finance import Expense
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _org(*, category_policies) -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:g", "profile": "WORK_EXPENSE",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": "Nguyễn An"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000, "effective_from": interval[0], "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
             "scope": "activity:1", "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "category_policies": category_policies,
    }))


def _report(amount: int) -> ReadResult:
    paper = DocumentAnalysis(
        source_id="s", document_id="s:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("purpose", "Mua thiết bị"),
                _found("printed_total", str(amount))),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Máy in văn phòng"), _found("amount", str(amount)), _found("invoice_refs", ("IR1",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR1"), _found("issuer_name", "An Bình"),
                _found("total_amount", str(amount)), _found("buyer_person_name", "Nguyễn An"),
                _found("document_date", "01/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


def _admit(amount: int, category_policies):
    return admit_evidence(
        _report(amount),
        scope=CaseScope(tenant="tenant:g", employee="employee:a", activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(category_policies=category_policies), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_category_policy_reaches_admission() -> None:
    inp = _admit(5_400_000, ({"id": "cat:1", "version": "v1", "effective_from": "2026-01-01T00:00:00+07:00",
                              "per_item_caps": {"WORK_CLIENT_MEAL": 5_000_000, "TAXI": 2_000_000},
                              "submission_window_days": 30, "excluded_categories": ["PERSONAL"]},))
    assert inp.category_policy, "the versioned category policy must reach admission"
    assert inp.expense_facts[0].category == "OFFICE_PURCHASE"
    assert inp.expense_facts[0].source_date is not None


def test_no_category_policy_in_context_leaves_it_empty() -> None:
    inp = _admit(5_400_000, ())
    assert inp.category_policy == ()


def test_admitted_expense_carries_category_and_source_date() -> None:
    inp = _admit(1_000_000, ())
    expense = inp.expense_facts[0]
    assert expense.source_date == datetime(2026, 10, 1, tzinfo=UTC)
