"""TC23: economic identity comes from the document actually bound to a cost.

Invoice 00002301 backs two rows (2.16m + 1.08m = 3.24m); invoice 00002302 backs
one row (mực in 5.4m). The two allocations of 00002301 share its canonical
invoice identity; the 00002302 row must get its OWN identity, never the first
invoice of the report. The identity must not depend on file/row order, and no
valid row may be lost or counted twice.
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

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
INV1 = "00002301"
INV2 = "00002302"


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _paper() -> DocumentAnalysis:
    rows = (
        ("Giấy in A4", "2160000", (INV1,)),
        ("Bút và dụng cụ", "1080000", (INV1,)),
        ("Mực in", "5400000", (INV2,)),
    )
    return DocumentAnalysis(
        source_id="s0", document_id="s0:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Hoàn ứng mua vật tư"),
                _found("printed_total", "8640000"), _found("declared_advance", "9000000")),
        line_items=tuple(
            DocumentLine(id=f"r{i}", fields=(
                _found("description", desc), _found("amount", amount), _found("invoice_refs", refs),
            ))
            for i, (desc, amount, refs) in enumerate(rows, start=1)
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice(number: str, total: str, issuer: str) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id=f"s:{number}", document_id=f"s:{number}:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", number), _found("issuer_name", issuer),
                _found("buyer_name", COMPANY), _found("total_amount", total),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:tc23", "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:employee-a", "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 12_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "ledger": (),
    }))


def _admit(documents: tuple[DocumentAnalysis, ...]):
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=documents)
    return admit_evidence(
        report, scope=CaseScope(tenant="tenant:tc23", employee="employee:employee-a",
                                activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_each_cost_uses_its_own_bound_document_identity() -> None:
    inp = _admit((_paper(), _invoice(INV1, "3240000", "HÒA BÌNH"), _invoice(INV2, "5400000", "MỰC IN VIỆT")))
    assert len(inp.expense_facts) == 3
    keys = [e.economic_key for e in inp.expense_facts]
    assert keys[0] == keys[1], "the two rows of invoice00002301 share its identity"
    assert keys[2] != keys[0], "invoice00002302 must have its own identity"
    assert INV1 in keys[0] and INV2 in keys[2]
    # No row is lost and no full invoice is counted twice.
    total = sum(int(e.incurred.value or 0) for e in inp.expense_facts)
    assert total == 8_640_000


def test_document_order_does_not_change_identity_or_money() -> None:
    paper = _paper()
    a = _admit((paper, _invoice(INV1, "3240000", "HÒA BÌNH"), _invoice(INV2, "5400000", "MỰC IN VIỆT")))
    b = _admit((paper, _invoice(INV2, "5400000", "MỰC IN VIỆT"), _invoice(INV1, "3240000", "HÒA BÌNH")))
    assert sorted(e.economic_key for e in a.expense_facts) == sorted(e.economic_key for e in b.expense_facts)
    assert [int(e.incurred.value or 0) for e in a.expense_facts] == [int(e.incurred.value or 0) for e in b.expense_facts]


def test_valid_allocations_are_not_falsely_blocked() -> None:
    inp = _admit((_paper(), _invoice(INV1, "3240000", "HÒA BÌNH"), _invoice(INV2, "5400000", "MỰC IN VIỆT")))
    assert not inp.admission_issues, "a valid allocation must not raise a FACT"
    assert all(e.eligibility == "ELIGIBLE" for e in inp.expense_facts)
