"""Core arithmetic gate: a readable number is not a consistent number.

TC06: the paper prints ứng 4.000.000 − chi 3.240.000 = 760.000, but the refund
line says 700.000 (off by 60.000). TC11: the invoice prints 5.000.000 + thuế
400.000 = 5.400.000, but the total says 5.500.000 (off by 100.000). Neither is
an OCR failure — the numbers are read correctly; the document's own arithmetic
does not close. The gate is pure and returns typed findings the admission layer
turns into blocking FACTs. A material component (tax/fee/discount) that is
UNREADABLE makes the check impossible -> a finding, never a silent zero.
"""

from __future__ import annotations

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.reconciliation.document_arithmetic import (
    ArithmeticFinding,
    check_document_arithmetic,
)

SHA = "a" * 64


def _ref(quote: str) -> EvidenceRef:
    return EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _state(name: str, state: str) -> FieldCandidate:
    return FieldCandidate(field=name, state=state)  # type: ignore[arg-type]


def _paper(**fields: object) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s", document_id="s:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=tuple(_found(name, value, str(value)) for name, value in fields.items()),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _paper_with_lines(lines: tuple[DocumentLine, ...], **fields: object) -> DocumentAnalysis:
    return _paper(**fields).model_copy(update={"line_items": lines})


def _cost_line(identifier: str, description: str, amount: object) -> DocumentLine:
    return DocumentLine(id=identifier, fields=(
        _found("description", description, f"{description} dòng {identifier}"),
        amount if isinstance(amount, FieldCandidate) else _found(
            "amount", amount, f"{description} {amount} đ"
        ),
    ))


def _invoice(**fields: object) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s", document_id="s:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=tuple(
            (field if isinstance(field, FieldCandidate) else _found(name, field, str(field)))
            for name, field in fields.items()
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _codes(findings: tuple[ArithmeticFinding, ...]) -> list[str]:
    return [f.code for f in findings]


def test_tc06_printed_refund_contradicts_advance_minus_total() -> None:
    findings = check_document_arithmetic(
        _paper(declared_advance="4000000", printed_total="3240000", printed_return="700000")
    )
    assert _codes(findings) == ["settlement-return"]
    basis = findings[0].basis
    assert "760000" in basis and "700000" in basis and "60000" in basis
    assert findings[0].refs, "the finding must carry the source refs"


def test_tc05_itemized_cost_rows_must_match_the_printed_total() -> None:
    paper = _paper_with_lines(
        (
            _cost_line("1", "Chi phí tiếp khách", "2000000"),
            _cost_line("2", "Chi phí phòng họp", "1000000"),
        ),
        declared_advance="4000000",
        printed_total="3500000",
        printed_return="500000",
    )

    findings = check_document_arithmetic(paper)

    assert _codes(findings) == ["settlement-line-total"]
    finding = findings[0]
    assert "2.000.000" in finding.basis and "1.000.000" in finding.basis
    assert "3.000.000" in finding.basis and "3.500.000" in finding.basis and "500.000" in finding.basis
    assert "3.000.000" in finding.question and "3.500.000" in finding.question
    assert {ref.exact_quote for ref in finding.refs} >= {
        "3500000", "Chi phí tiếp khách dòng 1", "Chi phí tiếp khách 2000000 đ",
        "Chi phí phòng họp dòng 2", "Chi phí phòng họp 1000000 đ",
    }


def test_unreadable_cost_row_is_unresolved_not_a_zero() -> None:
    paper = _paper_with_lines(
        (
            _cost_line("1", "Chi phí tiếp khách", "2000000"),
            _cost_line("2", "Chi phí phòng họp", _state("amount", "UNREADABLE")),
        ),
        printed_total="3500000",
    )

    findings = check_document_arithmetic(paper)

    assert _codes(findings) == ["settlement-line-items-unresolved"]
    assert "Chi phí phòng họp" in findings[0].basis
    assert "coi là 0" in findings[0].basis
    assert findings[0].refs


def test_ambiguous_line_amount_is_unresolved_not_partially_summed() -> None:
    ambiguous = FieldCandidate(
        field="amount", state="AMBIGUOUS", alternatives=(
            {"value": "1000000", "refs": (_ref("1.000.000"),)},
            {"value": "1500000", "refs": (_ref("1.500.000"),)},
        ),
    )
    paper = _paper_with_lines(
        (_cost_line("1", "Chi phí tiếp khách", "2000000"), _cost_line("2", "Chi phí khác", ambiguous)),
        printed_total="3500000",
    )

    assert _codes(check_document_arithmetic(paper)) == ["settlement-line-items-unresolved"]


def test_unreadable_printed_total_keeps_row_sum_unresolved() -> None:
    paper = _paper_with_lines(
        (_cost_line("1", "Chi phí tiếp khách", "3000000"),),
        declared_advance="4000000",
    ).model_copy(update={
        "fields": _paper(declared_advance="4000000").fields + (_state("printed_total", "UNREADABLE"),),
    })

    findings = check_document_arithmetic(paper)

    assert _codes(findings) == ["settlement-line-items-unresolved"]
    assert "UNREADABLE" in findings[0].basis


def test_absent_printed_total_does_not_invent_an_aggregate_relation() -> None:
    paper = _paper_with_lines(
        (_cost_line("1", "Chi phí tiếp khách", "3000000"),),
    )

    assert check_document_arithmetic(paper) == ()


def test_total_and_subtotal_rows_are_not_counted_again() -> None:
    paper = _paper_with_lines(
        (
            _cost_line("1", "Chi phí tiếp khách", "2000000"),
            _cost_line("2", "Chi phí phòng họp", "1000000"),
            _cost_line("sum", "Tổng cộng", "3000000"),
            _cost_line("subtotal", "Cộng tiền", "3000000"),
        ),
        printed_total="3000000",
    )

    assert check_document_arithmetic(paper) == ()


def test_unrelated_tax_field_does_not_reconcile_a_settlement_row_mismatch() -> None:
    paper = _paper_with_lines(
        (_cost_line("1", "Chi phí tiếp khách", "3000000"),),
        printed_total="3240000",
        tax="240000",
    )

    findings = check_document_arithmetic(paper)

    assert _codes(findings) == ["settlement-line-total"]


def test_settlement_line_sum_uses_the_shared_vnd_parser() -> None:
    paper = _paper_with_lines(
        (
            _cost_line("1", "Chi phí tiếp khách", "2.000.000 đ"),
            _cost_line("2", "Chi phí phòng họp", "1.000.000đ"),
        ),
        printed_total="3.000.000 đ",
    )

    assert check_document_arithmetic(paper) == ()


def test_tc06_correct_refund_has_no_finding() -> None:
    findings = check_document_arithmetic(
        _paper(declared_advance="4000000", printed_total="3240000", printed_return="760000")
    )
    assert findings == ()


def test_f02_company_pays_extra_is_not_a_false_refund_finding() -> None:
    # F02: advance 5m < cost 5.4m, so the refund is a verified zero and the
    # company pays 400k extra. The inapplicable side is 0, not a negative.
    assert check_document_arithmetic(
        _paper(declared_advance="5000000", printed_total="5400000",
               printed_return="0", printed_reimbursement="400000")
    ) == ()


def test_f03_balanced_paper_has_no_finding() -> None:
    assert check_document_arithmetic(
        _paper(declared_advance="4320000", printed_total="4320000",
               printed_return="0", printed_reimbursement="0")
    ) == ()


def test_wrong_reimbursement_amount_is_a_finding() -> None:
    findings = check_document_arithmetic(
        _paper(declared_advance="5000000", printed_total="5400000",
               printed_return="0", printed_reimbursement="100000")
    )
    assert _codes(findings) == ["settlement-reimburse"]
    assert "400000" in findings[0].basis and "300000" in findings[0].basis


def test_tc11_invoice_total_does_not_equal_subtotal_plus_tax() -> None:
    findings = check_document_arithmetic(
        _invoice(subtotal="5000000", tax="400000", total_amount="5500000")
    )
    assert _codes(findings) == ["invoice-total"]
    basis = findings[0].basis
    assert "5400000" in basis and "5500000" in basis and "100000" in basis


def test_tc11_correct_invoice_total_has_no_finding() -> None:
    findings = check_document_arithmetic(
        _invoice(subtotal="5000000", tax="400000", total_amount="5400000")
    )
    assert findings == ()


def test_valid_invoice_with_consistent_tax_has_no_finding() -> None:
    # TC01: 3.000.000 + 240.000 = 3.240.000.
    assert check_document_arithmetic(
        _invoice(subtotal="3000000", tax="240000", total_amount="3240000")
    ) == ()


def test_unreadable_material_component_blocks_instead_of_zero() -> None:
    # A tax that could not be read must not be treated as 0; the total cannot be
    # verified, so the document is not silently eligible.
    invoice = _invoice(subtotal="5000000", total_amount="5500000")
    invoice = invoice.model_copy(update={"fields": (
        _found("subtotal", "5000000"), _found("total_amount", "5500000"),
        _state("tax", "UNREADABLE"),
    )})
    findings = check_document_arithmetic(invoice)
    assert _codes(findings) == ["invoice-components-unread"]
    assert "tax" in findings[0].basis


def test_founded_zero_tax_with_matching_total_is_clear() -> None:
    assert check_document_arithmetic(
        _invoice(subtotal="3000000", tax="0", total_amount="3000000")
    ) == ()


def test_receipt_without_vat_fields_is_not_forced_to_reconcile() -> None:
    receipt = DocumentAnalysis(
        source_id="s", document_id="s:1-1:PAPER_RECEIPT", document_type="PAPER_RECEIPT",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("issuer_name", "X"), _found("total_amount", "120000")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    assert check_document_arithmetic(receipt) == ()


def test_paper_without_both_advance_and_total_is_not_checked() -> None:
    assert check_document_arithmetic(_paper(printed_total="3240000", printed_return="700000")) == ()
