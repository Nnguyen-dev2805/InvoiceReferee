"""Tests for domain data contracts (DATA_MODEL.md)."""

import dataclasses

import pytest

from invoice_referee.domain import models as m


# --- Enums: exact allowed values ---------------------------------------------


def test_decision_action_values():
    assert {a.value for a in m.DecisionAction} == {
        "AUTO_PROCESS",
        "REQUEST_INFO",
        "ESCALATE",
    }


def test_check_status_values():
    assert {s.value for s in m.CheckStatus} == {
        "PASS",
        "FAIL",
        "UNKNOWN",
        "NOT_APPLICABLE",
    }


def test_uncertainty_type_values():
    assert {u.value for u in m.UncertaintyType} == {
        "FACTUAL_UNKNOWN",
        "OUTSIDE_POLICY",
        "BEYOND_AUTHORITY",
    }


def test_payment_status_values():
    assert {p.value for p in m.PaymentStatus} == {
        "UNPAID",
        "PARTIALLY_PAID",
        "PAID",
        "UNKNOWN",
    }


def test_scope_status_is_tristate():
    assert {s.value for s in m.ScopeStatus} == {
        "IN_SCOPE",
        "OUTSIDE_POLICY",
        "UNKNOWN",
    }


def test_transaction_type_sprint1_only_po_goods():
    assert {t.value for t in m.TransactionType} == {"PO_GOODS_PURCHASE"}


def test_workflow_status_values():
    assert {w.value for w in m.WorkflowStatus} == {"ACTIVE", "STOPPED"}


def test_invoice_type_values():
    assert {i.value for i in m.InvoiceType} == {
        "ORIGINAL",
        "ADJUSTMENT",
        "REPLACEMENT",
    }


# --- Integer-money validation ------------------------------------------------


def test_money_rejects_float():
    with pytest.raises((TypeError, ValueError)):
        m.PurchaseOrder(
            po_id="PO-001",
            vendor_id="V-ABC",
            items=[],
            approved_total=30_000_000.0,  # float money not allowed
            status="APPROVED",
        )


def test_money_rejects_bool():
    with pytest.raises((TypeError, ValueError)):
        m.PaymentRecord(invoice_id="INV-001", status=m.PaymentStatus.UNPAID, paid_amount=True)


def test_money_rejects_negative():
    with pytest.raises(ValueError):
        m.PaymentRecord(invoice_id="INV-001", status=m.PaymentStatus.PAID, paid_amount=-1)


def test_money_accepts_int_zero():
    rec = m.PaymentRecord(invoice_id="INV-001", status=m.PaymentStatus.UNPAID, paid_amount=0)
    assert rec.paid_amount == 0


def test_invoice_line_total_must_be_int():
    with pytest.raises((TypeError, ValueError)):
        m.InvoiceLineItem(
            item_id="ITEM-001",
            invoiced_quantity=10,
            unit_price=3_000_000,
            line_total=30_000_000.5,
        )


def test_quantity_rejects_float():
    with pytest.raises((TypeError, ValueError)):
        m.InvoiceLineItem(
            item_id="ITEM-001",
            invoiced_quantity=10.5,
            unit_price=3_000_000,
            line_total=30_000_000,
        )


# --- Construction of core evidence objects -----------------------------------


def test_purchase_order_construction():
    po = m.PurchaseOrder(
        po_id="PO-001",
        vendor_id="V-ABC",
        items=[
            m.POLineItem(
                item_id="ITEM-001",
                description="Dell Monitor",
                ordered_quantity=10,
                unit_price=3_000_000,
                line_total=30_000_000,
            )
        ],
        approved_total=30_000_000,
        status="APPROVED",
    )
    assert po.po_id == "PO-001"
    assert po.items[0].ordered_quantity == 10
    assert po.currency == "VND"


def test_supplier_invoice_optional_related_invoice_defaults_none():
    inv = m.SupplierInvoice(
        invoice_id="INV-001",
        invoice_number="0000123",
        invoice_series="2C23TTU",
        invoice_type=m.InvoiceType.ORIGINAL,
        vendor_id="V-ABC",
        vendor_tax_code="0101234567",
        po_id="PO-001",
        invoice_date="2026-09-13",
        items=[],
        total_amount=30_000_000,
    )
    assert inv.related_invoice_number is None
    assert inv.flagged is False
    assert inv.source_type == m.SourceType.JSON


def test_supplier_invoice_unreadable_amount_stays_none():
    # TC15: an unreadable/uncertain amount must remain unknown, not guessed.
    inv = m.SupplierInvoice(
        invoice_id="INV-015",
        invoice_number="0000999",
        invoice_series="2C23TTU",
        invoice_type=m.InvoiceType.ORIGINAL,
        vendor_id="V-ABC",
        vendor_tax_code="0101234567",
        po_id="PO-015",
        invoice_date="2026-09-13",
        items=[],
        total_amount=None,
        flagged=True,
    )
    assert inv.total_amount is None
    assert inv.flagged is True


def test_supplier_invoice_amount_still_rejects_float_when_present():
    with pytest.raises((TypeError, ValueError)):
        m.SupplierInvoice(
            invoice_id="INV-001",
            invoice_number="0000123",
            invoice_series="2C23TTU",
            invoice_type=m.InvoiceType.ORIGINAL,
            vendor_id="V-ABC",
            vendor_tax_code="0101234567",
            po_id="PO-001",
            invoice_date="2026-09-13",
            items=[],
            total_amount=30_000_000.0,
        )


def test_transaction_preserves_raw_declared_type():
    tx = m.Transaction(
        transaction_id="TX-014",
        transaction_type=None,
        declared_transaction_type="SERVICE_INVOICE",
    )
    # Known-but-unsupported type is preserved for tri-state scope classification.
    assert tx.transaction_type is None
    assert tx.declared_transaction_type == "SERVICE_INVOICE"


def test_transaction_declared_type_defaults_none():
    tx = m.Transaction(transaction_id="TX-1", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    assert tx.declared_transaction_type is None


def test_transaction_prior_invoices_default_empty_and_independent():
    a = m.Transaction(transaction_id="TX-A", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    b = m.Transaction(transaction_id="TX-B", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    assert a.prior_invoices == []
    a.prior_invoices.append("x")
    assert b.prior_invoices == []


def test_payment_record_optional_payment_date():
    rec = m.PaymentRecord(
        invoice_id="INV-001",
        status=m.PaymentStatus.UNPAID,
        paid_amount=0,
    )
    assert rec.payment_date is None


# --- Transaction container ---------------------------------------------------


def test_transaction_defaults():
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    assert tx.workflow_status == m.WorkflowStatus.ACTIVE
    assert tx.goods_receipts == []
    assert tx.payment_history == []
    assert tx.approvals == []
    assert tx.checks == []
    assert tx.audit_log == []
    assert tx.human_stops == []
    assert tx.human_overrides == []
    assert tx.decision is None


def test_transaction_lists_are_independent_between_instances():
    a = m.Transaction(transaction_id="TX-A", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    b = m.Transaction(transaction_id="TX-B", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    a.checks.append("x")
    assert b.checks == []


# --- CheckResult -------------------------------------------------------------


def test_check_result_construction():
    cr = m.CheckResult(
        check_id="CHECK_QUANTITY",
        status=m.CheckStatus.FAIL,
        policy_rule_id="P05",
        expected=10,
        actual=12,
        reason="Invoice quantity exceeds received quantity",
        evidence_refs=["PO-001", "GR-001", "INV-001"],
    )
    assert cr.status is m.CheckStatus.FAIL
    assert cr.evidence_refs == ["PO-001", "GR-001", "INV-001"]


def test_check_result_rejects_float_money_in_expected_or_actual():
    """Money is integer VND everywhere, including what a check reports."""
    with pytest.raises((TypeError, ValueError)):
        m.CheckResult(check_id="CHECK_AMOUNT", status=m.CheckStatus.FAIL, actual=30_000_000.5)
    with pytest.raises((TypeError, ValueError)):
        m.CheckResult(check_id="CHECK_AMOUNT", status=m.CheckStatus.FAIL, expected=1.5)
    # int, str, list and None remain valid (payment/item checks use them).
    m.CheckResult(check_id="CHECK_PAYMENT", status=m.CheckStatus.FAIL, actual="PAID")
    m.CheckResult(check_id="CHECK_ITEM", status=m.CheckStatus.FAIL, actual=["ITEM-1"])
    m.CheckResult(check_id="CHECK_AMOUNT", status=m.CheckStatus.UNKNOWN)


def test_check_result_optional_fields_default():
    cr = m.CheckResult(check_id="CHECK_VENDOR", status=m.CheckStatus.PASS)
    assert cr.policy_rule_id is None
    assert cr.expected is None
    assert cr.actual is None
    assert cr.evidence_refs == []


# --- PolicyContext -----------------------------------------------------------


def test_policy_context_construction():
    ctx = m.PolicyContext(
        scope_status=m.ScopeStatus.IN_SCOPE,
        authority_threshold_vnd=50_000_000,
        applicable_rule_ids=["P05", "P12"],
        deterministic_uncertainties=[m.UncertaintyType.FACTUAL_UNKNOWN],
    )
    assert ctx.scope_status is m.ScopeStatus.IN_SCOPE
    assert ctx.authority_threshold_vnd == 50_000_000


def test_policy_context_threshold_must_be_int():
    with pytest.raises((TypeError, ValueError)):
        m.PolicyContext(
            scope_status=m.ScopeStatus.IN_SCOPE,
            authority_threshold_vnd=50_000_000.0,
        )


# --- AgentAssessment ---------------------------------------------------------


def test_agent_assessment_construction():
    a = m.AgentAssessment(
        proposed_uncertainty_type=m.UncertaintyType.FACTUAL_UNKNOWN,
        proposed_action=m.DecisionAction.REQUEST_INFO,
        explanation="Invoice amount exceeds approved PO amount.",
        primary_check_id="CHECK_AMOUNT",
        question="Có phê duyệt điều chỉnh thêm 5M không?",
        target="Purchasing",
        policy_rule_ids=["P07"],
        evidence_refs=["PO-001", "INV-001"],
    )
    assert a.fallback_used is False
    assert a.proposed_action is m.DecisionAction.REQUEST_INFO


# --- Decision ----------------------------------------------------------------


def test_decision_auto_process_has_no_question_or_target():
    d = m.Decision(
        action=m.DecisionAction.AUTO_PROCESS,
        reason="All checks pass and within authority",
    )
    assert d.question is None
    assert d.target is None
    assert d.policy_rule_ids == []


def test_decision_request_info_carries_question():
    d = m.Decision(
        action=m.DecisionAction.REQUEST_INFO,
        reason="Invoice exceeds PO amount",
        uncertainty=m.Uncertainty(type=m.UncertaintyType.FACTUAL_UNKNOWN, field="invoice.total_amount"),
        question="Có phê duyệt điều chỉnh thêm 5M không?",
        target="Purchasing",
        policy_rule_ids=["P07"],
    )
    assert d.action is m.DecisionAction.REQUEST_INFO
    assert d.question


# --- Human controls preserve original decision -------------------------------


def test_human_override_rejects_stopped_as_action():
    # overridden_action must be one of the three user-facing actions
    with pytest.raises((TypeError, ValueError)):
        m.HumanOverride(
            actor="a@example.com",
            original_action=m.DecisionAction.AUTO_PROCESS,
            overridden_action="STOPPED",
            reason="bad",
            timestamp="2026-09-20T10:12:00+07:00",
        )


def test_human_stop_construction():
    s = m.HumanStop(
        actor="a@example.com",
        previous_workflow_status=m.WorkflowStatus.ACTIVE,
        new_workflow_status=m.WorkflowStatus.STOPPED,
        reason="Supplier bank account changed",
        timestamp="2026-09-20T10:10:00+07:00",
    )
    assert s.new_workflow_status is m.WorkflowStatus.STOPPED


# --- ReviewResult ------------------------------------------------------------


def test_review_result_bundles_outputs():
    tx = m.Transaction(transaction_id="TX-001", transaction_type=m.TransactionType.PO_GOODS_PURCHASE)
    ctx = m.PolicyContext(scope_status=m.ScopeStatus.IN_SCOPE, authority_threshold_vnd=50_000_000)
    decision = m.Decision(action=m.DecisionAction.AUTO_PROCESS, reason="ok")
    rr = m.ReviewResult(
        transaction=tx,
        checks=[],
        policy_context=ctx,
        agent_assessment=None,
        decision=decision,
        audit_events=[],
    )
    assert rr.decision.action is m.DecisionAction.AUTO_PROCESS
    assert dataclasses.is_dataclass(rr)


# --- ExtractedDocument -------------------------------------------------------


def test_extracted_document_contract():
    doc = m.ExtractedDocument(
        document_type="SUPPLIER_INVOICE",
        source_type=m.SourceType.JSON,
        source_ref="fixture://TC01/invoice.json",
        extractor="json_adapter",
        fields={"invoice_number": "0000123"},
    )
    assert doc.parse_warnings == []
    assert doc.fields["invoice_number"] == "0000123"


# --- OCR / extraction contracts (Task 4) -------------------------------------


def test_field_status_values():
    assert {s.value for s in m.FieldStatus} == {
        "EXTRACTED",
        "NEEDS_CONFIRMATION",
        "CONFIRMED",
        "CORRECTED",
        "MISSING",
        "INVALID",
        "CONFLICTING",
    }


def test_extraction_status_values():
    assert {s.value for s in m.ExtractionStatus} == {
        "PROCESSING",
        "NEEDS_REVIEW",
        "REVIEWED",
        "FAILED",
    }


def test_bounding_box_requires_normalized_coordinates():
    with pytest.raises(ValueError):
        m.BoundingBox(-0.1, 0.0, 1.0, 1.0)


def test_bounding_box_requires_ordered_coordinates():
    with pytest.raises(ValueError):
        m.BoundingBox(0.9, 0.0, 0.1, 1.0)  # x1 > x2


def test_bounding_box_accepts_valid_normalized_box():
    box = m.BoundingBox(0.1, 0.7, 0.8, 0.8)
    assert box.x1 == 0.1
    assert box.y2 == 0.8


def test_field_candidate_preserves_provenance():
    candidate = m.FieldCandidate(
        field_name="total_amount",
        raw_text="30.000.000 VND",
        normalized_value=30_000_000,
        confidence=0.94,
        status=m.FieldStatus.EXTRACTED,
        page_number=1,
        bounding_box=m.BoundingBox(0.1, 0.7, 0.8, 0.8),
        evidence_block_ids=["BLK-001"],
        extraction_method="OCR_RULE",
        warnings=[],
    )
    assert candidate.evidence_block_ids == ["BLK-001"]
    assert candidate.original_normalized_value is None


def test_field_candidate_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        m.FieldCandidate(
            field_name="total_amount",
            raw_text="x",
            normalized_value=None,
            confidence=1.5,
            status=m.FieldStatus.EXTRACTED,
            page_number=1,
            bounding_box=None,
        )


def test_field_candidate_allows_none_confidence():
    candidate = m.FieldCandidate(
        field_name="po_id",
        raw_text="PO-001",
        normalized_value="PO-001",
        confidence=None,
        status=m.FieldStatus.NEEDS_CONFIRMATION,
        page_number=1,
        bounding_box=None,
        extraction_method="HUMAN",
    )
    assert candidate.confidence is None


def test_extraction_result_lists_are_instance_local():
    first = m.InvoiceExtractionResult("DOC-A", m.ExtractionStatus.NEEDS_REVIEW)
    second = m.InvoiceExtractionResult("DOC-B", m.ExtractionStatus.NEEDS_REVIEW)
    first.warnings.append("x")
    first.line_items.append({})
    assert second.warnings == []
    assert second.line_items == []


def test_document_page_carries_native_text_and_warnings():
    page = m.DocumentPage(
        document_id="DOC-1",
        page_number=1,
        image_bytes=b"\x89PNG",
        width=1240,
        height=1754,
        dpi=300,
        native_text="Invoice No: 123",
    )
    assert page.native_text == "Invoice No: 123"
    assert page.warnings == []


def test_ocr_document_holds_blocks_and_engine_metadata():
    block = m.OCRBlock(
        block_id="BLK-001",
        page_number=1,
        text="30.000.000 VND",
        confidence=0.97,
        bounding_box=m.BoundingBox(0.1, 0.7, 0.8, 0.8),
        block_type="TABLE_CELL",
        row_index=0,
        column_index=3,
    )
    doc = m.OCRDocument(
        document_id="DOC-1",
        pages=[],
        blocks=[block],
        full_text="30.000.000 VND",
        engine="paddleocr-pp-structure-v3",
        engine_version="fixture-v1",
        processing_ms=0,
    )
    assert doc.blocks[0].block_id == "BLK-001"
    assert doc.warnings == []


# --- document-path extraction contracts ---------------------------------------


def _candidate(
    *,
    field_name="total_amount",
    normalized_value=9_000_000,
    confidence=None,
    provider_confidence=None,
    mapping_score=None,
):
    return m.FieldCandidate(
        field_name=field_name,
        raw_text="9.000.000",
        normalized_value=normalized_value,
        confidence=confidence,
        status=m.FieldStatus.EXTRACTED,
        page_number=1,
        bounding_box=None,
        provider_confidence=provider_confidence,
        mapping_score=mapping_score,
    )


def test_ocr_block_preserves_table_identity():
    block = m.OCRBlock(
        block_id="P1-T2-R9-C5",
        page_number=1,
        text="9.000.000",
        confidence=0.99,
        bounding_box=m.BoundingBox(0.1, 0.1, 0.9, 0.2),
        block_type="TABLE_CELL",
        table_index=2,
        row_index=9,
        column_index=5,
    )
    assert (block.table_index, block.row_index, block.column_index) == (2, 9, 5)


def test_field_candidate_separates_provider_and_mapping_scores():
    candidate = _candidate(
        provider_confidence=0.99,
        mapping_score=0.91,
    )
    assert candidate.provider_confidence == 0.99
    assert candidate.mapping_score == 0.91
    # Compatibility alias during migration: confidence mirrors provider_confidence.
    assert candidate.confidence == 0.99


def test_field_candidate_confidence_defaults_to_provider_confidence():
    # Legacy callers pass confidence only; provider_confidence mirrors it.
    legacy = _candidate(confidence=0.87)
    assert legacy.provider_confidence == 0.87
    assert legacy.confidence == 0.87


def test_field_candidate_rejects_out_of_range_mapping_score():
    with pytest.raises(ValueError):
        _candidate(mapping_score=1.5)


def test_extraction_result_candidate_sets_are_instance_local():
    first = m.InvoiceExtractionResult("DOC-A", m.ExtractionStatus.NEEDS_REVIEW)
    second = m.InvoiceExtractionResult("DOC-B", m.ExtractionStatus.NEEDS_REVIEW)
    first.field_candidates["total_amount"] = [_candidate()]
    assert second.field_candidates == {}
    assert second.line_item_candidate_sets == []


