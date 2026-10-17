"""S6 digital intake: server validation + declaration->paper adapter (RED)."""

from __future__ import annotations

import pytest

from invoice_referee.domain.commands import Declaration, DigitalExpenseLine


def _line(**over) -> DigitalExpenseLine:
    base = {
        "item_id": "L01",
        "description": "Nhân công sửa chữa",
        "expense_date": "2026-10-09",
        "amount": 1_500_000,
        "evidence_status": "ALTERNATIVE",
        "exception_reason": "Nhà cung cấp không xuất hóa đơn",
        "source_ids": ("source:acc", "source:trf"),
    }
    base.update(over)
    return DigitalExpenseLine(**base)


def test_alternative_line_without_reason_is_rejected() -> None:
    with pytest.raises(Exception):
        _line(exception_reason=None)


def test_original_line_with_reason_is_rejected() -> None:
    with pytest.raises(Exception):
        _line(evidence_status="ORIGINAL", exception_reason="x")


def test_original_line_without_source_is_rejected() -> None:
    with pytest.raises(Exception):
        _line(evidence_status="ORIGINAL", exception_reason=None, source_ids=())


def test_adapter_builds_synthetic_paper_with_declared_refs() -> None:
    from invoice_referee.reconciliation.digital_intake import digital_to_paper

    declaration = Declaration(
        declared_purpose="Sửa chữa máy in",
        settlement_type="EMPLOYEE_REIMBURSEMENT",
        submission_source="DIGITAL_FORM",
        digital_lines=(_line(),),
        no_advance_asserted=True,
        no_advance_reason="Tự chi, không nhận ứng",
    )
    paper = digital_to_paper(
        declaration,
        root_id="root:1",
        evidence_numbers={
            "source:acc": "BBNT-181026-02",
            "source:trf": "FT262918104578",
        },
    )
    assert paper.document_type == "SETTLEMENT_FORM"
    assert len(paper.line_items) == 1
    row = paper.line_items[0]
    fields = {f.field: f for f in row.fields}
    assert fields["amount"].value == 1_500_000
    assert set(fields["invoice_refs"].value) == {"BBNT-181026-02", "FT262918104578"}
    assert fields["no_evidence_reason"].value == "Nhà cung cấp không xuất hóa đơn"
    # Declaration provenance, never fake OCR: real digest + record locator.
    assert all(r.source_id == "declaration:root:1" for r in fields["amount"].refs)
    assert all(len(r.source_sha256) == 64 for r in fields["amount"].refs)


def test_adapter_rejects_unknown_source_mapping() -> None:
    from invoice_referee.reconciliation.digital_intake import digital_to_paper

    declaration = Declaration(
        declared_purpose="x",
        submission_source="DIGITAL_FORM",
        digital_lines=(_line(),),
    )
    with pytest.raises(Exception):
        digital_to_paper(declaration, root_id="root:1", evidence_numbers={})


def test_validate_rejects_advance_fields_on_self_expense() -> None:
    from invoice_referee.reconciliation.digital_intake import (
        validate_digital_declaration,
    )

    declaration = Declaration(
        declared_purpose="x",
        settlement_type="EMPLOYEE_REIMBURSEMENT",
        submission_source="DIGITAL_FORM",
        digital_lines=(_line(),),
        declared_advance=5_000_000,
    )
    with pytest.raises(Exception):
        validate_digital_declaration(
            declaration, attached_source_ids={"source:acc", "source:trf"}
        )


def test_paper_self_expense_declaration_retains_intake_choice_and_assertion():
    import json
    from invoice_referee.domain.commands import Declaration
    from invoice_referee.workflow.service import CaseWorkflow
    declaration=Declaration(declared_purpose="Sửa máy in",settlement_type="EMPLOYEE_REIMBURSEMENT",submission_source="PAPER_SCAN",no_advance_asserted=True,no_advance_reason="Tự thanh toán trước")
    saved=json.loads(CaseWorkflow._declaration_draft_json(declaration,actor="employee:a",now="2026-10-16T00:00:00Z"))
    assert saved["confirmed"]["settlement_type"]=="EMPLOYEE_REIMBURSEMENT"
    assert saved["confirmed"]["submission_source"]=="PAPER_SCAN"
    assert saved["confirmed"]["no_advance_reason"]=="Tự thanh toán trước"


def test_adapter_allows_attached_sources_without_read_document_number() -> None:
    from invoice_referee.reconciliation.digital_intake import digital_to_paper

    declaration = Declaration(
        declared_purpose="Thuê cloud server",
        settlement_type="EMPLOYEE_REIMBURSEMENT",
        submission_source="DIGITAL_FORM",
        digital_lines=(_line(source_ids=("source:unreadable",)),),
        no_advance_asserted=True,
        no_advance_reason="Tự chi",
    )
    paper = digital_to_paper(
        declaration,
        root_id="root:1",
        attached_source_ids={"source:unreadable"},
        evidence_numbers={},
    )
    assert paper.document_type == "SETTLEMENT_FORM"
    assert len(paper.line_items) == 1
    row = paper.line_items[0]
    fields = {f.field: f for f in row.fields}
    assert fields["amount"].value == 1_500_000
    assert "invoice_refs" not in fields

