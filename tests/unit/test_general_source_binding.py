"""T2: composite claimant/company binding for a company-buyer-only invoice.

Hoangha original invoices often name only the company buyer (no natural person).
Under the accepted demo employee-paid policy, a company-buyer-only invoice can
still bind to the employee when: the paper claimant matches the server employee,
the paper row links the invoice (invoice ref), the company buyer matches the
scoped organization identity, and there is no contradictory natural-person/payer
evidence. A mismatching natural person or an explicit other payer stays a FACT.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _paper(*, declared_name: str = "Nguyễn An", invoice_ref: str = "00000101") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            _found("declared_name", declared_name, "Người đề nghị: " + declared_name),
            _found("purpose", "Chi phí tiếp khách"),
            _found("printed_total", "3240000"),
        ),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Tiếp khách"), _found("amount", "3240000"),
            _found("invoice_refs", (invoice_ref,)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice(*, number: str = "00000101", buyer_name: str | None = "Công ty InvoiceReferee",
             buyer_person: str | None = None, issuer: str = "Nhà hàng Sen") -> DocumentAnalysis:
    fields = [
        _found("document_number", number),
        _found("issuer_name", issuer),
        _found("total_amount", "3240000"),
        _found("document_date", "01/10/2026"),
    ]
    if buyer_name is not None:
        fields.append(_found("buyer_name", buyer_name))
    if buyer_person is not None:
        fields.append(_found("buyer_person_name", buyer_person))
    return DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=tuple(fields), confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org(*, company: str = "Công ty InvoiceReferee", employee_name: str = "Nguyễn An",
         advance: int = 4_000_000, coverage: bool = True) -> OrganizationContext:
    ledger = []
    if advance:
        ledger.append({
            "id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
            "scope": "activity:1", "payer": "company:demo", "payee": "employee:a",
            "amount": advance, "event_at": "2026-10-05T09:00:00+07:00",
            "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED",
        })
    cov = None
    if coverage:
        cov = {"activity": "activity:1", "start": "2026-09-01T00:00:00+07:00",
               "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"],
               "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
               "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
               "witness_keys": ["cov:1"]}
    return OrganizationContext.model_validate_json(__import__("json").dumps({
        "organization_id": "tenant:demo", "profile": "WORK_EXPENSE",
        "company_name": company,
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": employee_name},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000, "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
             "scope": "activity:1", "max_amount": 4_000_000, "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
        ),
        "ledger": tuple(ledger), "coverage": cov,
    }))


def _admit(report, org):
    return admit_evidence(
        report, scope=CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="WORK_EXPENSE"),
        organization=org, confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_company_buyer_only_invoice_binds_via_composite() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    inp = _admit(report, _org())
    expense = inp.expense_facts[0]
    assert expense.eligibility == "ELIGIBLE"
    assert expense.payments and expense.payments[0].basis_kind == "EMPLOYEE_PAID_INVOICE"


def test_company_buyer_mismatch_is_not_bound() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper(), _invoice(buyer_name="Công ty Khác")))
    inp = _admit(report, _org())
    assert inp.expense_facts[0].payments == ()
    assert any("buyer" in i.field_or_rule or "claimant" in i.field_or_rule for i in inp.admission_issues)


def test_natural_person_buyer_mismatch_blocks() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper(declared_name="Nguyễn An"), _invoice(buyer_person="Trần Văn B")))
    inp = _admit(report, _org())
    assert inp.expense_facts[0].payments == ()


def test_paper_claimant_mismatch_blocks_composite() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper(declared_name="Nguyễn An"), _invoice()))
    inp = _admit(report, _org(employee_name="Nguyễn Văn A"))
    assert inp.expense_facts[0].payments == ()


def test_unlinked_invoice_is_not_bound_to_the_row() -> None:
    # The paper row references a different invoice number -> no composite bind.
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper(invoice_ref="99999999"), _invoice(number="00000101")))
    inp = _admit(report, _org())
    assert inp.expense_facts[0].payments == ()
