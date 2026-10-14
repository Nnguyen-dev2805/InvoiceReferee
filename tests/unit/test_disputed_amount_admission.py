"""TC08: a disputed amount is not verified eligible employee-paid money.

The paper declares 3.500.000 but the linked invoice only proves 3.240.000
(difference 260.000). The row over-allocates its source, so the cost is in
dispute: it must stay unresolved (T/E/S UNKNOWN) with a FACT that keeps BOTH
source numbers and the 260.000 difference, owned by the employee. The verified
advance history (A) is retained; nothing is silently cut to 3.24m or taken as the
declared 3.5m. A disputed amount is never elevated to ELIGIBLE/verified money.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.reconciliation.service import Reconciler

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _paper() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Chi phí tiếp khách"),
                _found("declared_advance", "4000000"), _found("printed_total", "3500000"),
                _found("printed_return", "500000")),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Chi phí tiếp khách"), _found("amount", "3500000"),
            _found("invoice_refs", ("00000801",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00000801"), _found("issuer_name", "MINH PHÁT"),
                _found("buyer_name", COMPANY), _found("subtotal", "3000000"),
                _found("tax", "240000"), _found("total_amount", "3240000"),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:tc08", "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000, "effective_from": interval[0],
             "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:1",
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": "activity:1", "payer": "company:demo", "payee": "employee:employee-a",
                    "amount": 4_000_000, "event_at": "2026-10-05T09:00:00+07:00",
                    "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"employee": "employee:employee-a", "activity": "activity:1",
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _admit():
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    return admit_evidence(
        report, scope=CaseScope(tenant="tenant:tc08", employee="employee:employee-a",
                                activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_disputed_cost_stays_unresolved_not_eligible_money() -> None:
    inp = _admit()
    expense = inp.expense_facts[0]
    assert expense.incurred.state == "UNKNOWN", "a disputed amount is not a verified cost"
    assert expense.eligibility == "UNKNOWN"
    assert expense.payments == (), "the disputed amount must not become an employee-paid portion"


def test_dispute_fact_keeps_both_numbers_and_the_difference() -> None:
    inp = _admit()
    fact = next(i for i in inp.admission_issues if "allocation" in i.field_or_rule)
    assert fact.kind == "FACT" and fact.owner == "employee"
    assert "3500000" in fact.basis and "3240000" in fact.basis and "260000" in fact.basis
    assert fact.refs, "the FACT must carry the source refs"


def test_projection_keeps_a_known_but_e_and_s_unknown() -> None:
    result = Reconciler().assess(_admit())
    assert result.projection.T.state == "UNKNOWN"
    assert result.projection.E.state == "UNKNOWN"
    assert result.projection.S.state == "UNKNOWN"
    # The verified advance history is retained, not blanket-UNKNOWN.
    assert result.projection.A.state == "KNOWN"
    assert result.projection.A.value == 4_000_000
    assert result.allowed_effect is None, "no money while the amount is disputed"


def test_dispute_does_not_raise_a_false_payer_or_budget_fact() -> None:
    # The payer basis IS known (a bound invoice); only the amount is disputed.
    # The specific dispute FACT owns the question, so the generic payer/T facts
    # are not duplicated.
    result = Reconciler().assess(_admit())
    rules = {i.field_or_rule for i in result.issues}
    assert "expense:payer" not in rules
    assert "expense:allocation:s2:1-1:E_INVOICE" in rules
