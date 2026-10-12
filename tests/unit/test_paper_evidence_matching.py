from decimal import Decimal

from invoice_referee.application.paper_evidence_matching import match_paper_evidence
from invoice_referee.domain import (
    DocumentLineFact,
    ExpenseDocumentFacts,
    PaperSettlementFacts,
    PaperSettlementLine,
)


def _paper(*, reason: str | None = None) -> PaperSettlementFacts:
    return PaperSettlementFacts(
        document_id="DOC-FORM",
        purpose="Hoàn ứng công tác",
        total_amount=Decimal("3314780"),
        lines=[
            PaperSettlementLine(
                line_id="LINE-001",
                description="Chi phí ăn trưa Kiều Hoa Quán",
                invoice_refs=["HQ54201", "KHQ54202"],
                amount=Decimal("3314780"),
                note="Đính kèm bảng kê",
                requires_evidence=True,
                no_evidence_reason=reason,
                source_refs=["DOC:DOC-FORM"],
            )
        ],
    )


def _document(document_id: str, name: str) -> dict[str, str]:
    return {"document_id": document_id, "original_name": name}


def test_invoice_references_match_multiple_evidence_and_reconcile_sum() -> None:
    facts = [
        ExpenseDocumentFacts(
            document_id="DOC-1",
            document_type="E_INVOICE",
            issuer_name="Kiều Hoa Quán",
            document_number="HQ54201",
            total_amount=Decimal("1800000"),
        ),
        ExpenseDocumentFacts(
            document_id="DOC-2",
            document_type="E_INVOICE",
            issuer_name="Kiều Hoa Quán",
            document_number="KHQ54202",
            total_amount=Decimal("1514780"),
        ),
    ]

    items, links, findings = match_paper_evidence(
        _paper(),
        facts,
        [_document("DOC-1", "hq54201.pdf"), _document("DOC-2", "khq54202.jpg")],
    )

    assert len(items) == 1
    assert [link["link_status"] for link in links] == ["AUTO_LINK", "AUTO_LINK"]
    assert not any(finding.rule_id == "SET_PAPER_AMOUNT_001" for finding in findings)
    assert any(
        finding.rule_id == "SET_PAPER_MATCH_001" and finding.status == "PASS"
        for finding in findings
    )


def test_required_evidence_without_match_or_reason_requests_employee() -> None:
    _, _, findings = match_paper_evidence(_paper(), [], [])

    finding = next(
        item for item in findings if item.rule_id == "SET_PAPER_EVIDENCE_REQUIRED"
    )
    assert finding.status == "FAIL"
    assert finding.target.value == "EMPLOYEE"


def test_unstated_evidence_requirement_without_document_or_reason_requests_employee() -> None:
    """Regression for UC-03 TC19: blank note must not imply an exemption."""
    paper = _paper()
    line = paper.lines[0]
    line.requires_evidence = False
    line.invoice_refs = []
    line.note = None
    line.no_evidence_reason = None

    _, _, findings = match_paper_evidence(paper, [], [])

    finding = next(
        item for item in findings if item.rule_id == "SET_PAPER_EVIDENCE_REQUIRED"
    )
    assert finding.status == "FAIL"
    assert finding.uncertainty_type.value == "FACTUAL_UNKNOWN"
    assert finding.target.value == "EMPLOYEE"


def test_required_evidence_with_reason_routes_exception_to_accountant() -> None:
    _, _, findings = match_paper_evidence(
        _paper(reason="Nhà cung cấp không xuất hóa đơn"),
        [],
        [],
    )

    finding = next(
        item for item in findings if item.rule_id == "SET_PAPER_EVIDENCE_EXCEPTION"
    )
    assert finding.uncertainty_type.value == "OUTSIDE_POLICY"
    assert finding.target.value == "ACCOUNTANT"


def test_alternative_payment_proof_can_match_by_amount_and_content() -> None:
    fact = ExpenseDocumentFacts(
        document_id="DOC-PAYMENT",
        document_type="PAYMENT_PROOF",
        issuer_name="Kiều Hoa Quán",
        total_amount=Decimal("3314780"),
        line_items=[
            DocumentLineFact(description="Chi phí ăn trưa Kiều Hoa Quán")
        ],
    )

    _, links, findings = match_paper_evidence(
        _paper(),
        [fact],
        [_document("DOC-PAYMENT", "chuyen-khoan.png")],
    )

    assert links[0]["link_status"] == "AUTO_LINK"
    assert links[0]["link_method"] == "AMOUNT_AND_CONTENT"
    assert any(finding.status == "PASS" for finding in findings)


def test_general_reason_is_not_reused_for_multiple_missing_lines() -> None:
    paper = _paper()
    paper.lines.append(
        PaperSettlementLine(
            line_id="LINE-002",
            description="Chi phí taxi",
            amount=Decimal("250000"),
            note="Kèm chứng từ",
            requires_evidence=True,
            source_refs=["DOC:DOC-FORM"],
        )
    )

    _, _, findings = match_paper_evidence(
        paper,
        [],
        [],
        fallback_no_evidence_reason="Nhà cung cấp không xuất hóa đơn",
    )

    missing = [
        finding
        for finding in findings
        if finding.rule_id == "SET_PAPER_EVIDENCE_REQUIRED"
    ]
    assert len(missing) == 2
    assert all("chưa chỉ rõ" in finding.message for finding in missing)
    assert not any(
        finding.rule_id == "SET_PAPER_EVIDENCE_EXCEPTION"
        for finding in findings
    )


def test_missing_paper_line_amount_requests_accountant_confirmation() -> None:
    paper = _paper()
    paper.lines[0].amount = None

    _, _, findings = match_paper_evidence(paper, [], [])

    amount_finding = next(
        finding
        for finding in findings
        if finding.rule_id == "SET_PAPER_LINE_AMOUNT_001"
    )
    assert amount_finding.status == "FAIL"
    assert amount_finding.target.value == "ACCOUNTANT"


def test_payment_proof_supports_invoice_without_double_counting_amount() -> None:
    facts = [
        ExpenseDocumentFacts(
            document_id="DOC-INVOICE",
            document_type="E_INVOICE",
            issuer_name="Kiều Hoa Quán",
            document_number="HQ54201",
            total_amount=Decimal("3314780"),
        ),
        ExpenseDocumentFacts(
            document_id="DOC-PAYMENT",
            document_type="PAYMENT_PROOF",
            issuer_name="Kiều Hoa Quán",
            total_amount=Decimal("3314780"),
            line_items=[
                DocumentLineFact(description="Chi phí ăn trưa Kiều Hoa Quán")
            ],
        ),
    ]

    _, links, findings = match_paper_evidence(
        _paper(),
        facts,
        [
            _document("DOC-INVOICE", "hoa-don.pdf"),
            _document("DOC-PAYMENT", "chuyen-khoan.png"),
        ],
    )

    assert len(links) == 2
    assert all(link["link_status"] == "AUTO_LINK" for link in links)
    assert not any(
        finding.rule_id == "SET_PAPER_AMOUNT_001"
        for finding in findings
    )


def test_one_evidence_is_not_auto_linked_to_two_paper_lines() -> None:
    paper = _paper()
    paper.lines.append(
        PaperSettlementLine(
            line_id="LINE-002",
            description="Chi phí ăn trưa Kiều Hoa Quán",
            amount=Decimal("3314780"),
            requires_evidence=True,
        )
    )
    fact = ExpenseDocumentFacts(
        document_id="DOC-PAYMENT",
        document_type="PAYMENT_PROOF",
        issuer_name="Kiều Hoa Quán",
        total_amount=Decimal("3314780"),
        line_items=[DocumentLineFact(description="Chi phí ăn trưa Kiều Hoa Quán")],
    )

    _, links, findings = match_paper_evidence(
        paper,
        [fact],
        [_document("DOC-PAYMENT", "chuyen-khoan.png")],
    )

    assert [link["link_status"] for link in links] == [
        "AUTO_LINK",
        "SUGGEST_LINK",
    ]
    assert any(
        finding.rule_id == "SET_PAPER_MATCH_001"
        and finding.status == "FAIL"
        for finding in findings
    )


def test_no_evidence_note_on_paper_routes_exception_to_accountant() -> None:
    paper = _paper()
    paper.lines[0].requires_evidence = False
    paper.lines[0].note = "Không có chứng từ"
    paper.lines[0].no_evidence_reason = "Không có chứng từ"

    items, _, findings = match_paper_evidence(paper, [], [])

    assert items[0]["evidence_status"] == "NO_EVIDENCE"
    finding = next(
        item
        for item in findings
        if item.rule_id == "SET_PAPER_EVIDENCE_EXCEPTION"
    )
    assert finding.uncertainty_type.value == "OUTSIDE_POLICY"
    assert finding.target.value == "ACCOUNTANT"


def test_amount_and_normalized_vendor_name_auto_match_clear_invoice() -> None:
    paper = PaperSettlementFacts(
        document_id="DOC-FORM",
        purpose="Hoàn ứng chi phí mua thiết bị máy tính",
        total_amount=Decimal("83600000"),
        lines=[
            PaperSettlementLine(
                line_id="LINE-001",
                description="Mua vật phẩm công nghệ từ công ty Thiên Ưng",
                amount=Decimal("83600000"),
                note="Đính kèm bảng kê",
                requires_evidence=True,
            )
        ],
    )
    invoice = ExpenseDocumentFacts(
        document_id="DOC-INVOICE",
        document_type="E_INVOICE",
        issuer_name="CÔNG TY CÔNG NGHỆ THIÊN ƯNG",
        total_amount=Decimal("83600000"),
        line_items=[
            DocumentLineFact(description="Máy tính để bàn"),
            DocumentLineFact(description="Chuột máy tính"),
            DocumentLineFact(description="Màn hình máy tính"),
        ],
    )

    _, links, findings = match_paper_evidence(
        paper,
        [invoice],
        [_document("DOC-INVOICE", "hoa_don_thien_ung.pdf")],
    )

    assert links[0]["link_status"] == "AUTO_LINK"
    assert links[0]["score"] >= 0.80
    assert "đơn vị phát hành" in links[0]["explanation"]
    assert any(
        finding.rule_id == "SET_PAPER_MATCH_001"
        and finding.status == "PASS"
        for finding in findings
    )
