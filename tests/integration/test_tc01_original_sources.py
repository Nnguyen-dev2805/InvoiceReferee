"""T2: TC01 original sources admit under composite claimant/company binding.

The original TC01 invoice names only the company buyer; the paper names the
employee claimant. With a scoped organization identity + the paper row linking the
invoice + no contradiction, the invoice binds as the employee-paid basis. A buyer
mismatch stays blocking. Sources are the raw original PDFs (their bytes unchanged);
a fake reader supplies OCR text so this is a source-shape test, not LIVE.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence

CORPUS = Path(__file__).resolve().parents[2] / "data" / "tham-khao" / "uc-03" / "tc01-hop-le-nhan-vien-hoan-tra-tien-thua"
SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _paper() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Chi phí tiếp khách"),
                _found("printed_total", "3240000"), _found("declared_advance", "4000000")),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Chi phí tiếp khách"), _found("amount", "3240000"),
            _found("invoice_refs", ("00000101",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice(*, buyer: str = COMPANY) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00000101"), _found("issuer_name", "MINH PHÁT"),
                _found("buyer_name", buyer), _found("total_amount", "3240000"),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    import json

    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:tc01", "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:1", "name": "Tiếp khách", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "Tiếp khách", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver"},),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": "activity:1", "payer": "company:demo", "payee": "employee:employee-a",
                    "amount": 4_000_000, "event_at": "2026-10-05T09:00:00+07:00",
                    "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"activity": "activity:1", "start": "2026-09-01T00:00:00+07:00",
                     "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"],
                     "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _admit(invoice: DocumentAnalysis):
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), invoice))
    return admit_evidence(
        report, scope=CaseScope(tenant="tenant:tc01", employee="employee:employee-a",
                                activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_original_tc01_pdfs_are_present_and_unchanged_shape() -> None:
    assert (CORPUS / "report_hoan_ung.pdf").is_file()
    assert (CORPUS / "hoa_don_dien_tu.pdf").is_file()


def test_tc01_company_buyer_invoice_binds_composite() -> None:
    inp = _admit(_invoice())
    expense = inp.expense_facts[0]
    assert expense.eligibility == "ELIGIBLE"
    assert expense.payments and expense.payments[0].basis_kind == "EMPLOYEE_PAID_INVOICE"


def test_tc01_buyer_mismatch_stays_blocking() -> None:
    inp = _admit(_invoice(buyer="CÔNG TY KHÁC"))
    assert inp.expense_facts[0].payments == ()
    assert inp.admission_issues


def test_serial_prefixed_invoice_number_still_links_to_the_row() -> None:
    # LIVE discovery: the model reads the invoice number with its serial prefix
    # ("IR26E00000101") while the paper references "00000101". The row link must
    # still match so the composite binding admits the cost.
    invoice = _invoice().model_copy(update={"fields": (
        _found("document_number", "IR26E00000101"), _found("issuer_name", "MINH PHÁT"),
        _found("buyer_name", COMPANY), _found("total_amount", "3240000"),
        _found("document_date", "10/10/2026"),
    )})
    inp = _admit(invoice)
    assert inp.expense_facts[0].payments, "a serial-prefixed number must still link"
