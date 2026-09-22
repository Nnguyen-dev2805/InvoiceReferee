from invoice_referee.domain import (
    ConflictAnalysis,
    InventoryAnalysis,
    InventoryDocumentFacts,
    InventoryItemMatch,
    InventoryLineItemFact,
    InventoryTextReport,
    PotentialConflict,
)
from invoice_referee.policy import evaluate_inventory_consistency


ROLES = {
    "EV-INVOICE": "PRIMARY_DOCUMENT",
    "EV-REPORT": "SUPPORTING_DOCUMENT",
}
NAMES = {
    "EV-INVOICE": "mua_san.pdf",
    "EV-REPORT": "Phieu_nhap_kho.pdf",
}


def _item(
    source_id: str,
    *,
    quantity: str,
    line_amount: str,
) -> InventoryLineItemFact:
    return InventoryLineItemFact(
        item_id=f"{source_id}:ITEM-001",
        raw_name="Củ sắn tươi",
        quantity=quantity,
        unit="kg",
        unit_price="3300",
        line_amount=line_amount,
        source_refs=[f"{source_id}:page-0-block-5"],
    )


def _analysis(
    *,
    report_quantity: str = "25992",
    report_amount: str = "85773600",
) -> InventoryAnalysis:
    return InventoryAnalysis(
        applicability="APPLICABLE",
        applicability_reason="Hóa đơn mua hàng có phiếu nhập kho.",
        document_facts=[
            InventoryDocumentFacts(
                evidence_id="EV-INVOICE",
                document_type="E_INVOICE",
                supplier_name="Công ty TNHH Nông Sản và Vận Tải Trí Nguyên",
                supplier_tax_code="4400995188",
                document_date="2026-09-19",
                receipt_status="NOT_APPLICABLE",
                items=[
                    _item(
                        "EV-INVOICE",
                        quantity="25992",
                        line_amount="85773600",
                    )
                ],
            ),
            InventoryDocumentFacts(
                evidence_id="EV-REPORT",
                document_type="GOODS_RECEIPT",
                supplier_name="Công ty TNHH Nông Sản và Vận Tải Trí Nguyên",
                supplier_tax_code="4400995188",
                document_date="2026-09-19",
                receipt_status="RECEIVED_FULL",
                items=[
                    _item(
                        "EV-REPORT",
                        quantity=report_quantity,
                        line_amount=report_amount,
                    )
                ],
            ),
        ],
        text_report=InventoryTextReport(
            is_inventory_report=True,
            supplier_name="Công ty TNHH Nông Sản và Vận Tải Trí Nguyên",
            report_date="2026-09-19",
            receipt_status="RECEIVED_FULL",
            source_refs=["EMPLOYEE_CLAIM"],
        ),
        suggested_item_matches=[
            InventoryItemMatch(
                primary_item_id="EV-INVOICE:ITEM-001",
                supporting_item_id="EV-REPORT:ITEM-001",
                semantic_match=True,
                reason="Hai nguồn cùng ghi củ sắn tươi.",
            )
        ],
    )


def test_happy_bill_and_inventory_report_pass() -> None:
    findings = evaluate_inventory_consistency(_analysis(), ROLES, NAMES)

    assert not any(item.status in {"FAIL", "ERROR"} for item in findings)
    assert any(item.rule_id == "INVENTORY_CONSISTENCY" for item in findings)


def test_unhappy_report_exposes_quantity_and_amount_conflicts() -> None:
    findings = evaluate_inventory_consistency(
        _analysis(report_quantity="2", report_amount="92828283"),
        ROLES,
        NAMES,
    )

    by_rule = {item.rule_id: item for item in findings}
    assert "INVENTORY_QUANTITY_MISMATCH" in by_rule
    assert "INVENTORY_LINE_AMOUNT_MISMATCH" in by_rule
    assert "25992" in by_rule["INVENTORY_QUANTITY_MISMATCH"].message
    assert "2" in by_rule["INVENTORY_QUANTITY_MISMATCH"].message
    assert "92828283" in by_rule["INVENTORY_LINE_AMOUNT_MISMATCH"].message


def test_text_report_cannot_replace_an_attached_supporting_document() -> None:
    analysis = _analysis()
    analysis.document_facts = analysis.document_facts[:1]
    analysis.text_report = InventoryTextReport(
        is_inventory_report=True,
        receipt_status="RECEIVED_FULL",
        items=[],
        source_refs=["EMPLOYEE_CLAIM"],
    )

    findings = evaluate_inventory_consistency(
        analysis,
        {"EV-INVOICE": "PRIMARY_DOCUMENT"},
        {"EV-INVOICE": "mua_san.pdf"},
    )

    assert findings[0].rule_id == "INVENTORY_SOURCE_REQUIRED"
    assert findings[0].status == "FAIL"


def test_missing_supporting_report_requires_human_review() -> None:
    analysis = _analysis()
    analysis.document_facts = analysis.document_facts[:1]
    analysis.text_report = None

    findings = evaluate_inventory_consistency(
        analysis,
        {"EV-INVOICE": "PRIMARY_DOCUMENT"},
        {"EV-INVOICE": "mua_san.pdf"},
    )

    assert findings[0].rule_id == "INVENTORY_SOURCE_REQUIRED"
    assert findings[0].status == "FAIL"


def test_policy_does_not_apply_to_non_inventory_case() -> None:
    analysis = InventoryAnalysis(
        applicability="NOT_APPLICABLE",
        applicability_reason="Bill dịch vụ không phát sinh nhận hàng.",
        document_facts=[
            InventoryDocumentFacts(
                evidence_id="EV-INVOICE",
                document_type="PAPER_RECEIPT",
                receipt_status="NOT_APPLICABLE",
            )
        ],
    )

    findings = evaluate_inventory_consistency(
        analysis,
        {"EV-INVOICE": "PRIMARY_DOCUMENT"},
        {"EV-INVOICE": "bill.jpg"},
    )

    assert findings[0].rule_id == "INVENTORY_NOT_APPLICABLE"
    assert findings[0].status == "PASS"


def test_missing_document_facts_names_file_and_missing_fields() -> None:
    analysis = _analysis()
    analysis.document_facts = analysis.document_facts[:1]

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert findings[0].rule_id == "INVENTORY_EXTRACTION_COVERAGE_INVALID"
    assert "Phieu_nhap_kho.pdf" in findings[0].message
    assert "nhà cung cấp và MST" in findings[0].message
    assert "số lượng" in findings[0].message


def test_text_report_mapping_is_ignored_when_attached_report_is_valid() -> None:
    analysis = _analysis()
    assert analysis.text_report is not None
    analysis.text_report.items = [
        InventoryLineItemFact(
            item_id="TEXT_REPORT:ITEM-001",
            raw_name="Củ sắn",
            quantity="25992",
            unit="kg",
            source_refs=["EMPLOYEE_CLAIM"],
        )
    ]
    analysis.suggested_item_matches.append(
        InventoryItemMatch(
            primary_item_id="EV-INVOICE:ITEM-001",
            supporting_item_id="TEXT_REPORT:ITEM-001",
            semantic_match=True,
            reason="Text nhân viên xác nhận cùng mặt hàng.",
        )
    )

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert not any(item.status in {"FAIL", "ERROR"} for item in findings)
    assert not any(
        item.rule_id == "INVENTORY_SUPPORTING_ITEM_UNMATCHED"
        for item in findings
    )


def test_unmapped_text_item_is_not_treated_as_extra_inventory_line() -> None:
    analysis = _analysis()
    assert analysis.text_report is not None
    analysis.text_report.items = [
        InventoryLineItemFact(
            item_id="TEXT_REPORT:ITEM-001",
            raw_name="Củ sắn",
            quantity="25992",
            unit="kg",
            source_refs=["EMPLOYEE_CLAIM"],
        )
    ]

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert not any(
        item.rule_id == "INVENTORY_SUPPORTING_ITEM_UNMATCHED"
        for item in findings
    )


def test_text_report_quantity_conflict_is_ignored() -> None:
    analysis = _analysis()
    assert analysis.text_report is not None
    analysis.text_report.items = [
        InventoryLineItemFact(
            item_id="TEXT_REPORT:ITEM-001",
            raw_name="Củ sắn",
            quantity="2",
            unit="kg",
            source_refs=["EMPLOYEE_CLAIM"],
        )
    ]
    analysis.suggested_item_matches.append(
        InventoryItemMatch(
            primary_item_id="EV-INVOICE:ITEM-001",
            supporting_item_id="TEXT_REPORT:ITEM-001",
            semantic_match=True,
            reason="Text nói về cùng lô củ sắn.",
        )
    )

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert not any(
        item.rule_id == "INVENTORY_QUANTITY_MISMATCH" for item in findings
    )


def test_diesel_invoice_and_receipt_pass_while_employee_text_is_ignored() -> None:
    analysis = InventoryAnalysis(
        applicability="APPLICABLE",
        applicability_reason="Hóa đơn nhiên liệu có phiếu nhập kho.",
        document_facts=[
            InventoryDocumentFacts(
                evidence_id="EV-INVOICE",
                document_type="E_INVOICE",
                supplier_tax_code="6000235027-018",
                document_date="2026-04-13",
                receipt_status="NOT_APPLICABLE",
                items=[
                    InventoryLineItemFact(
                        item_id="EV-INVOICE:ITEM-001",
                        raw_name="Dầu Điêzen 0,001S Mức 5",
                        quantity="110.467",
                        unit="Lit",
                        unit_price="34400",
                        line_amount="3800065",
                    )
                ],
            ),
            InventoryDocumentFacts(
                evidence_id="EV-REPORT",
                document_type="GOODS_RECEIPT",
                supplier_tax_code="6000235027-018",
                document_date="2026-04-13",
                receipt_status="RECEIVED_FULL",
                items=[
                    InventoryLineItemFact(
                        item_id="EV-REPORT:ITEM-001",
                        raw_name="Dầu Điêzen 0,001S Mức 5",
                        quantity="110.467",
                        unit="Lít",
                        unit_price="34400",
                        line_amount="3800065",
                    )
                ],
            ),
        ],
        text_report=InventoryTextReport(
            is_inventory_report=True,
            report_date="2026-04-13",
            receipt_status="RECEIVED_FULL",
            items=[
                InventoryLineItemFact(
                    item_id="TEXT_REPORT:ITEM-001",
                    raw_name="Dầu Diesel",
                    quantity="110.467",
                    unit="lít",
                    source_refs=["EMPLOYEE_CLAIM"],
                )
            ],
        ),
        suggested_item_matches=[
            InventoryItemMatch(
                primary_item_id="EV-INVOICE:ITEM-001",
                supporting_item_id="EV-REPORT:ITEM-001",
                semantic_match=True,
                reason="Cùng mặt hàng nhiên liệu.",
            ),
            InventoryItemMatch(
                primary_item_id="EV-INVOICE:ITEM-001",
                supporting_item_id="TEXT_REPORT:ITEM-001",
                semantic_match=True,
                reason="Text nhân viên mô tả cùng mặt hàng nhiên liệu.",
            ),
        ],
    )

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert not any(item.status in {"FAIL", "ERROR"} for item in findings)
    assert any(item.rule_id == "INVENTORY_CONSISTENCY" for item in findings)


def test_semantic_conflict_proposed_by_agent_becomes_a_specific_human_question() -> None:
    base = _analysis()
    analysis = ConflictAnalysis(
        **base.model_dump(),
        potential_conflicts=[
            PotentialConflict(
                code="RECEIPT_STATUS",
                field="receipt_status",
                description="Hóa đơn và phiếu nhập kho có trạng thái không thống nhất.",
                source_refs=["EV-INVOICE", "EV-REPORT"],
                human_question=(
                    "Vui lòng xác nhận lô củ sắn đã được kho nhận đủ hay chưa."
                ),
            )
        ],
    )

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    conflict = next(
        item
        for item in findings
        if item.rule_id == "INVENTORY_SEMANTIC_CONFLICT_RECEIPT_STATUS"
    )
    assert conflict.status == "FAIL"
    assert conflict.message == (
        "Vui lòng xác nhận lô củ sắn đã được kho nhận đủ hay chưa."
    )


def test_semantic_conflict_from_employee_text_is_ignored() -> None:
    base = _analysis()
    analysis = ConflictAnalysis(
        **base.model_dump(),
        potential_conflicts=[
            PotentialConflict(
                code="EMPLOYEE_TEXT_CONFLICT",
                field="receipt_status",
                description="Text nhân viên khác phiếu nhập kho.",
                source_refs=["EV-REPORT", "EMPLOYEE_CLAIM"],
                human_question="Vui lòng xác nhận nội dung nhân viên khai báo.",
            )
        ],
    )

    findings = evaluate_inventory_consistency(analysis, ROLES, NAMES)

    assert not any(
        item.rule_id == "INVENTORY_SEMANTIC_CONFLICT_EMPLOYEE_TEXT_CONFLICT"
        for item in findings
    )
