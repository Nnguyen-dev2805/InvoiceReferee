"""T4: one source backing several rows is allocated, never double-counted.

TC23: one invoice (3.24m) may back two allocations (2.16m + 1.08m = 3.24m); the
allocations must not exceed the source total. TC22: a 5.4m invoice cannot back
7.56m of rows. A payment proof is not a second invoice. An extra unreferenced
source is a relevance FACT, not silently dropped or added.
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


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _paper(rows) -> DocumentAnalysis:
    lines = []
    for i, (desc, amount, refs) in enumerate(rows, start=1):
        lines.append(DocumentLine(id=f"r{i}", fields=(
            _found("description", desc), _found("amount", amount), _found("invoice_refs", refs),
        )))
    total = sum(int(a) for _, a, _ in rows)
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("purpose", "p"), _found("printed_total", str(total))),
        line_items=tuple(lines), confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice(number: str, total: str) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id=f"s:{number}", document_id=f"s:{number}:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", number), _found("issuer_name", "X"),
                _found("total_amount", total), _found("buyer_person_name", "Nguyễn An"),
                _found("document_date", "01/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:t", "profile": "WORK_EXPENSE",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": "Nguyễn An"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 20_000_000, "effect_range": interval, "actor": "employee:approver"},),
        "ledger": (),
    }))


def _admit(documents):
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=tuple(documents))
    return admit_evidence(
        report, scope=CaseScope(tenant="tenant:t", employee="employee:a", activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_two_rows_may_share_one_invoice_within_its_total() -> None:
    paper = _paper((("Tiếp khách A", "2160000", ("IR9",)), ("Tiếp khách B", "1080000", ("IR9",))))
    inp = _admit((paper, _invoice("IR9", "3240000")))
    assert len(inp.expense_facts) == 2
    # Both rows admit; the source total bounds the sum.
    total = sum(int(e.incurred.value or 0) for e in inp.expense_facts)
    assert total == 3_240_000
    assert not any("allocation" in i.field_or_rule for i in inp.admission_issues)


def test_rows_exceeding_the_source_total_is_fact() -> None:
    # TC22: invoice 5.4m cannot back 7.56m of rows.
    paper = _paper((("Máy in", "5400000", ("IR8",)), ("Phụ kiện", "2160000", ("IR8",))))
    inp = _admit((paper, _invoice("IR8", "5400000")))
    assert any("allocation" in i.field_or_rule for i in inp.admission_issues)


def test_extra_unreferenced_source_is_a_relevance_fact() -> None:
    # TC24: an invoice the paper does not reference is not silently added; it is a
    # relevance FACT for the reviewer.
    paper = _paper((("Tiếp khách", "3240000", ("IR9",)),))
    inp = _admit((paper, _invoice("IR9", "3240000"), _invoice("IR7", "1000000")))
    assert any("relevance" in i.field_or_rule for i in inp.admission_issues)
