from datetime import date
from decimal import Decimal

import pytest

from invoice_referee.domain import (
    DocumentFieldState,
    DocumentLineFact,
    DocumentValidityStatus,
    ExpenseDocumentFacts,
    ExpenseDocumentRole,
    PaperSettlementFacts,
    PaperSettlementLine,
)
from invoice_referee.policy import (
    validate_expense_document,
    validate_paper_settlement_document,
)
from invoice_referee.application.process_settlement import _validity_findings
from invoice_referee.application.decision_guard import build_settlement_decision


def _electronic_invoice(**changes) -> ExpenseDocumentFacts:
    payload = {
        "document_id": "DOC-INVOICE",
        "document_type": "E_INVOICE",
        "classification_confidence": 0.98,
        "classification_signals": ["Có mẫu số, ký hiệu và số hóa đơn"],
        "issuer_name": "Công ty Nhà cung cấp",
        "issuer_tax_code": "0101234567",
        "buyer_name": "Công ty Demo",
        "buyer_tax_code": "0319999999",
        "document_number": "00001234",
        "template_number": "1C26TAA",
        "serial_number": "C26TAA",
        "document_date": date(2026, 10, 10),
        "total_amount": Decimal("1200000"),
        "line_items": [DocumentLineFact(description="Dịch vụ bảo trì")],
        "source_refs": ["DOC:DOC-INVOICE"],
    }
    payload.update(changes)
    return ExpenseDocumentFacts(**payload)


def test_clear_electronic_invoice_is_eligible_for_matching() -> None:
    result = validate_expense_document(
        _electronic_invoice(),
        company_tax_codes=frozenset({"0319999999"}),
    )

    assert result.status == DocumentValidityStatus.CLEAR
    assert result.eligible_for_matching is True
    assert result.document_role == ExpenseDocumentRole.ORIGINAL_EVIDENCE
    assert result.issues == []


def test_electronic_invoice_missing_buyer_tax_code_stops_before_matching() -> None:
    result = validate_expense_document(_electronic_invoice(buyer_tax_code=None))

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert result.eligible_for_matching is False
    assert any(issue.field == "buyer_tax_code" for issue in result.issues)


def test_unreadable_required_field_is_not_treated_as_present() -> None:
    result = validate_expense_document(
        _electronic_invoice(
            buyer_tax_code="0319999999",
            field_states={"buyer_tax_code": DocumentFieldState.UNREADABLE},
        )
    )

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert any(issue.field == "buyer_tax_code" for issue in result.issues)


def test_invalid_tax_code_format_needs_human_confirmation() -> None:
    result = validate_expense_document(
        _electronic_invoice(buyer_tax_code="0317L_688"),
        company_tax_codes=frozenset({"0319999999"}),
    )

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert any(issue.code == "INVALID_TAX_CODE_FORMAT" for issue in result.issues)
    assert not any(issue.code == "BUYER_TAX_CODE_MISMATCH" for issue in result.issues)


def test_buyer_tax_code_from_another_company_is_outside_policy() -> None:
    result = validate_expense_document(
        _electronic_invoice(buyer_tax_code="0401234567"),
        company_tax_codes=frozenset({"0319999999"}),
    )

    assert result.status == DocumentValidityStatus.OUTSIDE_POLICY
    assert result.eligible_for_matching is False
    assert any(issue.code == "BUYER_TAX_CODE_MISMATCH" for issue in result.issues)


def test_paper_receipt_does_not_require_tax_codes() -> None:
    result = validate_expense_document(
        ExpenseDocumentFacts(
            document_id="DOC-RECEIPT",
            document_type="PAPER_RECEIPT",
            issuer_name="Nhà hàng Demo",
            document_date=date(2026, 10, 10),
            total_amount=Decimal("450000"),
        )
    )

    assert result.status == DocumentValidityStatus.CLEAR
    assert "buyer_tax_code" not in result.required_fields


def test_transport_ticket_does_not_block_on_missing_tax_code_warning() -> None:
    result = validate_expense_document(
        ExpenseDocumentFacts(
            document_id="DOC-TICKET",
            document_type="TRANSPORT_TICKET",
            issuer_name="Bãi đỗ xe Thành Công",
            document_number="VDT-171026-0385",
            document_date=date(2026, 10, 17),
            total_amount=Decimal("200000"),
            extraction_warnings=[
                "Chứng từ không có mã số thuế bên bán và bên mua, "
                "không phải hóa đơn GTGT."
            ],
        )
    )

    assert result.status == DocumentValidityStatus.CLEAR
    assert result.eligible_for_matching is True
    assert "issuer_tax_code" not in result.required_fields
    assert "buyer_tax_code" not in result.required_fields
    assert result.issues[0].blocking is False


def test_payment_proof_requires_reference_payee_and_success_status() -> None:
    result = validate_expense_document(
        ExpenseDocumentFacts(
            document_id="DOC-PAYMENT",
            document_type="PAYMENT_PROOF",
            document_date=date(2026, 10, 10),
            total_amount=Decimal("450000"),
        )
    )

    assert result.document_role == ExpenseDocumentRole.SUPPORTING_DOCUMENT
    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    missing_fields = {issue.field for issue in result.issues}
    assert {"payee_name", "transaction_reference", "transaction_status"} <= missing_fields


def test_unknown_document_type_is_not_eligible_for_matching() -> None:
    result = validate_expense_document(
        ExpenseDocumentFacts(
            document_id="DOC-UNKNOWN",
            document_type="UNKNOWN",
        )
    )

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert result.document_role == ExpenseDocumentRole.UNKNOWN
    assert any(issue.code == "DOCUMENT_TYPE_UNCLEAR" for issue in result.issues)


def test_validity_result_does_not_cite_another_document() -> None:
    result = validate_expense_document(
        _electronic_invoice(source_refs=["DOC:OTHER-DOCUMENT"])
    )

    assert result.source_refs == ["DOC:DOC-INVOICE"]


def test_item_description_typo_is_non_blocking_warning() -> None:
    result = validate_expense_document(
        _electronic_invoice(
            extraction_warnings=[
                "Mô tả hàng hóa có lỗi chính tả: 'Vẻ máy bay'."
            ]
        )
    )

    assert result.status == DocumentValidityStatus.CLEAR
    assert result.eligible_for_matching is True
    assert len(result.issues) == 1
    assert result.issues[0].blocking is False

    findings = _validity_findings(result, filename="hoa_don_ve_may_bay.pdf")
    assert [finding.status for finding in findings] == ["WARN", "PASS"]
    assert findings[0].question is None
    assert build_settlement_decision(findings).automation_decision == (
        "READY_FOR_APPROVAL"
    )


def test_unclear_total_warning_still_blocks_matching() -> None:
    result = validate_expense_document(
        _electronic_invoice(
            extraction_warnings=[
                "Tổng thanh toán không đọc chắc một chữ số."
            ]
        )
    )

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert result.eligible_for_matching is False
    assert result.issues[0].blocking is True


def test_paper_request_must_be_clear_before_evidence_matching() -> None:
    result = validate_paper_settlement_document(
        PaperSettlementFacts(
            document_id="DOC-FORM",
            purpose="Quyết toán công tác phí",
            total_amount=Decimal("1000000"),
            advance_amount=Decimal("1500000"),
            lines=[
                PaperSettlementLine(
                    line_id="LINE-001",
                    description="Taxi",
                    amount=None,
                )
            ],
        ),
        advance_amount_required=True,
    )

    assert result.status == DocumentValidityStatus.NEEDS_HUMAN
    assert result.eligible_for_matching is False
    assert any(issue.code == "PAPER_LINE_AMOUNT_UNCLEAR" for issue in result.issues)


@pytest.mark.parametrize(
    ("document_type", "fields", "expected_role"),
    [
        (
            "HOTEL_RECEIPT",
            {"issuer_name": "Khách sạn Demo", "document_date": date(2026, 10, 10), "total_amount": 900000},
            ExpenseDocumentRole.ORIGINAL_EVIDENCE,
        ),
        (
            "TRANSPORT_TICKET",
            {"issuer_name": "Hãng xe Demo", "document_number": "VE-01", "document_date": date(2026, 10, 10), "total_amount": 250000},
            ExpenseDocumentRole.ORIGINAL_EVIDENCE,
        ),
        (
            "COLLECTION_RECEIPT",
            {"issuer_name": "Đơn vị thu", "buyer_name": "Nguyễn Minh An", "document_number": "PT-01", "document_date": date(2026, 10, 10), "total_amount": 300000},
            ExpenseDocumentRole.ORIGINAL_EVIDENCE,
        ),
        (
            "CARD_SLIP",
            {"issuer_name": "Nhà hàng Demo", "document_date": date(2026, 10, 10), "total_amount": 450000, "transaction_reference": "TRACE-01"},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "PAYMENT_PROOF",
            {"payee_name": "Nhà cung cấp Demo", "document_date": date(2026, 10, 10), "total_amount": 450000, "transaction_reference": "TXN-01", "transaction_status": "Thành công"},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "CONTRACT",
            {"issuer_name": "Nhà cung cấp Demo", "buyer_name": "Công ty Demo", "document_number": "HD-01", "document_date": date(2026, 10, 10), "total_amount": 5000000},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "QUOTATION",
            {"issuer_name": "Nhà cung cấp Demo", "document_date": date(2026, 10, 10), "total_amount": 5000000, "line_items": [DocumentLineFact(description="Thiết bị")]},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "PURCHASE_ORDER",
            {"issuer_name": "Nhà cung cấp Demo", "buyer_name": "Công ty Demo", "document_number": "PO-01", "document_date": date(2026, 10, 10), "total_amount": 5000000, "line_items": [DocumentLineFact(description="Thiết bị")]},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "ACCEPTANCE_RECORD",
            {"issuer_name": "Nhà cung cấp Demo", "buyer_name": "Công ty Demo", "document_date": date(2026, 10, 10), "line_items": [DocumentLineFact(description="Dịch vụ bảo trì")], "confirmation_present": True},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "DELIVERY_NOTE",
            {"issuer_name": "Nhà cung cấp Demo", "buyer_name": "Công ty Demo", "document_number": "GH-01", "document_date": date(2026, 10, 10), "line_items": [DocumentLineFact(description="Thiết bị")], "confirmation_present": True},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "GOODS_RECEIPT",
            {"issuer_name": "Nhà cung cấp Demo", "buyer_name": "Công ty Demo", "document_number": "NK-01", "document_date": date(2026, 10, 10), "line_items": [DocumentLineFact(description="Thiết bị")], "confirmation_present": True},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
        (
            "SUPPLIER_CONFIRMATION",
            {"issuer_name": "Nhà cung cấp Demo", "document_date": date(2026, 10, 10), "line_items": [DocumentLineFact(description="Dịch vụ")], "confirmation_present": True},
            ExpenseDocumentRole.SUPPORTING_DOCUMENT,
        ),
    ],
)
def test_supported_document_profiles_can_become_clear(
    document_type: str,
    fields: dict,
    expected_role: ExpenseDocumentRole,
) -> None:
    result = validate_expense_document(
        ExpenseDocumentFacts(
            document_id=f"DOC-{document_type}",
            document_type=document_type,
            **fields,
        )
    )

    assert result.status == DocumentValidityStatus.CLEAR
    assert result.document_role == expected_role
    assert result.eligible_for_matching is True
