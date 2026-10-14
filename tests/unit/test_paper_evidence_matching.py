"""E6 evidence-matching tests (plan E6, contracts §12.4).

Golden tests ported from Hoangha's pinned matcher (revision 1ee33487…) plus the
final evidence-only projection differences: original-only totals, missing amount
stays None, a stated reason is metadata not a policy exception, and a second-row
reuse needs an explicit amount-bounded allocation.
"""

from __future__ import annotations

from decimal import Decimal

from invoice_referee.domain.documents import (
    DocumentAnalysis,
    DocumentLine,
    FieldCandidate,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.evidence.matching import match_paper_evidence

SHA = "a" * 64


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote)


def _field(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _invoice(
    document_id: str,
    *,
    number: str | None = None,
    issuer: str | None = None,
    total: str | None = None,
    document_type: str = "E_INVOICE",
    lines: tuple[str, ...] = (),
) -> DocumentAnalysis:
    fields = []
    if issuer is not None:
        fields.append(_field("issuer_name", issuer))
    if number is not None:
        fields.append(_field("document_number", number))
    if total is not None:
        fields.append(_field("total_amount", Decimal(total)))
    return DocumentAnalysis(
        source_id="source:1",
        document_id=document_id,
        document_type=document_type,  # type: ignore[arg-type]
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=tuple(fields),
        line_items=tuple(
            DocumentLine(id=f"{document_id}:line:{i}", fields=(_field("description", d),))
            for i, d in enumerate(lines, start=1)
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _paper(*, rows: tuple[tuple[str, str | None, tuple[str, ...], str | None], ...]) -> DocumentAnalysis:
    """rows = (description, amount, invoice_refs, no_evidence_reason)."""
    line_items = []
    for index, (description, amount, refs, reason) in enumerate(rows, start=1):
        line_fields = [_field("description", description)]
        if amount is not None:
            line_fields.append(_field("amount", Decimal(amount)))
        if refs:
            line_fields.append(_field("invoice_refs", refs))
        if reason is not None:
            line_fields.append(_field("no_evidence_reason", reason))
        line_items.append(DocumentLine(id=f"row:{index}", fields=tuple(line_fields)))
    return DocumentAnalysis(
        source_id="source:1",
        document_id="DOC-FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(),
        line_items=tuple(line_items),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def test_exact_number_preserves_hoangha_method() -> None:
    paper = _paper(rows=(("Chi phí ăn trưa", "3314780", ("HQ54201",), None),))
    docs = (_invoice("DOC-1", number="HQ54201", issuer="Kiều Hoa Quán", total="3314780"),)
    result = match_paper_evidence(paper, docs)
    assert result.links[0].score == Decimal("1")
    assert result.links[0].method == "INVOICE_NUMBER_EXACT"
    assert result.links[0].status == "AUTO_LINK"


def test_amount_and_content_auto_match_clear_invoice() -> None:
    paper = _paper(
        rows=(("Mua vật phẩm từ công ty Thiên Ưng", "83600000", (), None),)
    )
    docs = (
        _invoice(
            "DOC-INVOICE",
            issuer="CÔNG TY CÔNG NGHỆ THIÊN ƯNG",
            total="83600000",
            lines=("Máy tính để bàn", "Chuột máy tính", "Màn hình máy tính"),
        ),
    )
    result = match_paper_evidence(paper, docs)
    assert result.links[0].status == "AUTO_LINK"
    assert result.links[0].score >= Decimal("0.80")
    assert result.links[0].method == "AMOUNT_AND_CONTENT"


def test_support_only_row_is_alternative_not_original() -> None:
    paper = _paper(rows=(("Chi phí ăn trưa Kiều Hoa Quán", "3314780", (), None),))
    docs = (
        _invoice(
            "DOC-PAYMENT",
            issuer="Kiều Hoa Quán",
            total="3314780",
            document_type="PAYMENT_PROOF",
            lines=("Chi phí ăn trưa Kiều Hoa Quán",),
        ),
    )
    result = match_paper_evidence(paper, docs)
    assert result.rows[0].evidence_status == "ALTERNATIVE_EVIDENCE"


def test_missing_amount_stays_none() -> None:
    paper = _paper(rows=(("Khoản chưa rõ tiền", None, (), None),))
    result = match_paper_evidence(paper, ())
    assert result.rows[0].paper_amount is None
    assert result.rows[0].original_total is None


def test_stated_reason_is_metadata_not_policy_exception() -> None:
    paper = _paper(rows=(("Khoản có lý do", "100000", (), "Nhà cung cấp không xuất hóa đơn"),))
    result = match_paper_evidence(paper, ())
    assert result.rows[0].no_evidence_reason == "Nhà cung cấp không xuất hóa đơn"
    assert result.rows[0].evidence_status == "NO_EVIDENCE"
    # No policy_exception_code / financial disposition field exists.
    assert not hasattr(result.rows[0], "policy_exception_code")


def test_one_evidence_is_not_auto_linked_to_two_rows() -> None:
    paper = _paper(
        rows=(
            ("Chi phí ăn trưa Kiều Hoa Quán", "3314780", (), None),
            ("Chi phí ăn trưa Kiều Hoa Quán", "3314780", (), None),
        )
    )
    docs = (
        _invoice(
            "DOC-PAYMENT",
            issuer="Kiều Hoa Quán",
            total="3314780",
            document_type="PAYMENT_PROOF",
            lines=("Chi phí ăn trưa Kiều Hoa Quán",),
        ),
    )
    result = match_paper_evidence(paper, docs)
    statuses = [link.status for link in result.links]
    assert statuses == ["AUTO_LINK", "SUGGEST_LINK"]


def test_explicit_allocation_allows_second_row_when_bounded() -> None:
    # Both rows repeat the same invoice ref and state an allocated amount whose
    # sum is <= the source total: the reuse is allowed.
    paper = _paper(
        rows=(
            ("Dòng 1", "200000", ("HQ1",), None),
            ("Dòng 2", "200000", ("HQ1",), None),
        )
    )
    docs = (_invoice("DOC-1", number="HQ1", total="500000"),)
    result = match_paper_evidence(paper, docs)
    assert all(link.status == "AUTO_LINK" for link in result.links)


def test_overallocation_keeps_reuse_unresolved() -> None:
    paper = _paper(
        rows=(
            ("Dòng 1", "400000", ("HQ1",), None),
            ("Dòng 2", "400000", ("HQ1",), None),
        )
    )
    docs = (_invoice("DOC-1", number="HQ1", total="500000"),)
    result = match_paper_evidence(paper, docs)
    assert not all(link.status == "AUTO_LINK" for link in result.links)
    assert result.findings


def test_unknown_candidate_not_promoted() -> None:
    # An UNKNOWN document is not matchable; the row has no evidence.
    paper = _paper(rows=(("Dòng 1", "100000", (), None),))
    docs = (_invoice("DOC-X", total="100000", document_type="UNKNOWN"),)
    result = match_paper_evidence(paper, docs)
    assert result.rows[0].evidence_status == "NO_EVIDENCE"
    assert result.links == ()


async def test_suggestion_resolution_promotes_existing_pair_at_threshold() -> None:
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget

    # A weak-but-present suggestion pair; the LLM promotes only an existing pair.
    paper = _paper(rows=(("Đi lại", "100000", (), None),))
    docs = (_invoice("DOC-1", issuer="Nhà cung cấp dịch vụ", total="100000"),)
    result = match_paper_evidence(paper, docs)
    assert any(link.status == "SUGGEST_LINK" for link in result.links)

    class Llm:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            self.calls += 1
            return {"promotions": [{"document_id": "DOC-1", "item_id": "ITEM-001",
                                    "confidence": 0.95}]}

    llm = Llm()
    resolved = await resolve_evidence_suggestions(result, docs, llm=llm, budget=RunBudget())
    assert llm.calls == 1
    promoted = [link for link in resolved.links if link.status == "AUTO_LINK"]
    assert promoted and promoted[0].method == "LLM_RESOLVED"


async def test_suggestion_resolution_cannot_create_a_new_pair() -> None:
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget

    paper = _paper(rows=(("Đi lại", "100000", (), None),))
    docs = (_invoice("DOC-1", issuer="Nhà cung cấp dịch vụ", total="100000"),)
    result = match_paper_evidence(paper, docs)

    class Llm:
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            # Names a pair that was never suggested.
            return {"promotions": [{"document_id": "DOC-NOPE", "item_id": "ITEM-001",
                                    "confidence": 0.99}]}

    resolved = await resolve_evidence_suggestions(result, docs, llm=Llm(), budget=RunBudget())
    assert resolved.links == result.links


def test_first_explicit_allocation_cannot_exceed_source_total() -> None:
    # A row claiming 600 against a 500 invoice must not auto-link.
    paper = _paper(rows=(("Dòng 1", "600000", ("HQ1",), None),))
    docs = (_invoice("DOC-1", number="HQ1", total="500000"),)
    result = match_paper_evidence(paper, docs)
    assert not any(link.status == "AUTO_LINK" for link in result.links)
    assert result.findings


def test_unmatched_ids_are_source_ids_not_document_ids() -> None:
    # An unrelated amount/description -> score < 0.50 -> genuinely unmatched.
    paper = _paper(rows=(("Dòng 1", "100000", (), None),))
    docs = (_invoice("DOC-1", issuer="Nhà cung cấp khác", total="999999"),)
    result = match_paper_evidence(paper, docs)
    # The DTO field is unmatched_source_ids; the values must be source ids.
    assert result.unmatched_source_ids == ("source:1",)
