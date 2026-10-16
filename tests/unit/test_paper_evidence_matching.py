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
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


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


def test_two_invoices_cannot_multiply_one_paper_row():
    paper = _paper(rows=(("Chi phí", "100000", ("A", "B"), None),))
    docs = (_invoice("D1", number="A", total="100000"), _invoice("D2", number="B", total="100000"))
    result = match_paper_evidence(paper, docs)
    assert not any(link.status == "AUTO_LINK" for link in result.links)
    assert any(f.code == "SET_PAPER_AMOUNT_001" and f.status == "UNRESOLVED" for f in result.findings)


def test_stored_link_needs_actual_provenance_and_its_method_basis():
    from invoice_referee.evidence.matching import project_evidence_matches
    from invoice_referee.domain.documents import EvidenceLink
    paper = _paper(rows=(("Chi phí", "100000", (), None),))
    doc = _invoice("D1", number="A", total="100000")
    forged = _ref().model_copy(update={"source_sha256": "b"*64, "page": 99, "exact_quote": "Invented"})
    for method, refs in [("LLM_RESOLVED", (forged,)), ("INVOICE_NUMBER_EXACT", ())]:
        link = EvidenceLink(item_id="ITEM-001", document_id="D1", source_id=doc.source_id,
            status="AUTO_LINK", method=method, score=Decimal("1"), explanation="forged", refs=refs)
        projected = project_evidence_matches(paper, (doc,), (link,))
        assert projected.rows[0].evidence_status == "NO_EVIDENCE"


async def test_explicit_number_conflict_cannot_be_overridden_by_issuer():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Đi lại", "100000", ("IR-A",), None),))
    docs = (_invoice("D1", number="IR-B", issuer="Nhà cung cấp dịch vụ", total="100000"),)
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "D1", "confidence": 0.99,
                "rationale": "Same issuer", "basis": [
                  {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                  {"kind": "ISSUER", "left_field": "row.description", "right_field": "document.issuer_name"}]}]}
    result = match_paper_evidence(paper, docs)
    resolved = await resolve_evidence_suggestions(result, docs, paper=paper, llm=Llm(), budget=RunBudget())
    assert not any(link.status == "AUTO_LINK" for link in resolved.links)


def test_numeric_invoice_reference_matches_unique_series_prefixed_number() -> None:
    paper = _paper(rows=(("Chi phí tiếp khách", "3240000", ("00000101",), None),))
    docs = (_invoice("DOC-1", number="IR26E00000101", issuer="Nhà hàng", total="3240000"),)

    result = match_paper_evidence(paper, docs)

    assert len(result.links) == 1
    assert result.links[0].status == "AUTO_LINK"
    assert result.links[0].method == "INVOICE_NUMBER_EXACT"
    assert result.links[0].allocated_amount == Decimal("3240000")


def test_numeric_invoice_reference_does_not_choose_between_duplicate_serials() -> None:
    paper = _paper(rows=(("Chi phí tiếp khách", "3240000", ("00000101",), None),))
    docs = (
        _invoice("DOC-1", number="IR26E00000101", issuer="Nhà hàng", total="3240000"),
        _invoice("DOC-2", number="AB00000101", issuer="Nhà hàng", total="3240000"),
    )

    result = match_paper_evidence(paper, docs)

    assert len(result.links) == 2
    assert all(link.status == "SUGGEST_LINK" for link in result.links)
    assert all(link.method != "INVOICE_NUMBER_EXACT" for link in result.links)


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


def test_summary_total_row_is_not_matched_as_a_third_cost() -> None:
    paper = _paper(rows=(
        ("Chi phí tiếp khách", "1500000", ("HQ1",), None),
        ("Chi phí phòng họp", "1500000", ("HQ1",), None),
        ("Tổng cộng", "3000000", ("HQ1",), None),
    ))
    docs = (_invoice("DOC-1", number="HQ1", total="3000000"),)

    result = match_paper_evidence(paper, docs)

    assert [row.item_id for row in result.rows] == ["ITEM-001", "ITEM-002"]
    assert len(result.links) == 2
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

    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",))
    document = document.model_copy(update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    assert result.links and all(link.status == "SUGGEST_LINK" for link in result.links)

    class Llm:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            self.calls += 1
            return {"promotions": [{"document_id": "DOC-1", "item_id": "ITEM-001",
                "confidence": 0.95, "rationale": "Source line matches claim", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "SERVICE", "left_field": "row.description", "right_field": "document.line_items[*].description"}]}]}

    llm = Llm()
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=llm, budget=RunBudget())
    assert llm.calls == 1
    assert resolved.links[0].status == "AUTO_LINK"
    assert resolved.links[0].method == "LLM_RESOLVED"
    assert resolved.links[0].allocated_amount == Decimal("100000")
    assert resolved.rows[0].evidence_status == "ORIGINAL_EVIDENCE"
    assert resolved.rows[0].original_total == Decimal("100000")
    assert not any(f.code == "SET_PAPER_EVIDENCE_REQUIRED" for f in resolved.findings)


async def test_resolver_does_not_promote_when_issuer_basis_contradicts_row():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Nhà cung cấp khác", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000").model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1",
                "confidence": 0.99, "rationale": "issuer matches", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "ISSUER", "left_field": "row.description", "right_field": "document.issuer_name"}]}]}
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert resolved.links[0].status == "SUGGEST_LINK"


async def test_resolver_does_not_promote_when_service_basis_contradicts_row():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Dịch vụ A", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1",
                "confidence": 0.99, "rationale": "service matches", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "SERVICE", "left_field": "row.description", "right_field": "document.line_items[*].description"}]}]}
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert resolved.links[0].status == "SUGGEST_LINK"


async def test_resolver_does_not_promote_amount_only_confidence():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1",
                "confidence": 0.99, "rationale": "amount matches", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"}]}]}
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert resolved.links[0].status == "SUGGEST_LINK"


async def test_resolver_handles_existing_single_candidate_gray_suggestion():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1",
                "confidence": 0.99, "rationale": "source service matches", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "SERVICE", "left_field": "row.description", "right_field": "document.line_items[*].description"}]}]}
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert resolved.links[0].status == "AUTO_LINK"
    assert resolved.links[0].method == "LLM_RESOLVED"
    assert resolved.links[0].allocated_amount == Decimal("100000")
    assert resolved.rows[0].evidence_status == "ORIGINAL_EVIDENCE"
    assert resolved.rows[0].original_total == Decimal("100000")
    assert not any(f.code == "SET_PAPER_EVIDENCE_REQUIRED" for f in resolved.findings)


async def test_resolver_retains_competing_candidates_as_suggestions():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    first = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    second = _invoice("DOC-2", issuer="Nhà cung cấp C", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (first, second))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1",
                "confidence": 0.99, "rationale": "same service", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "SERVICE", "left_field": "row.description", "right_field": "document.line_items[*].description"}]}]}
    resolved = await resolve_evidence_suggestions(result, (first, second), paper=paper, llm=Llm(), budget=RunBudget())
    assert all(link.status == "SUGGEST_LINK" for link in resolved.links)


async def test_high_confidence_without_facts_cannot_promote():
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget
    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
        for link in result.links
    )})
    class Llm:
        async def complete_json(self, **kwargs):
            return {"promotions": [{"item_id": "ITEM-001", "document_id": "DOC-1", "confidence": 0.99}]}
    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert not any(link.status == "AUTO_LINK" for link in resolved.links)


async def test_promoted_link_rebuilds_row_and_allocation():
    await test_resolver_handles_existing_single_candidate_gray_suggestion()


async def test_suggestion_resolution_cannot_create_a_new_pair() -> None:
    from invoice_referee.evidence.matching import resolve_evidence_suggestions
    from invoice_referee.evidence.trace import RunBudget

    paper = _paper(rows=(("Dịch vụ B", "100000", (), None),))
    document = _invoice("DOC-1", issuer="Nhà cung cấp A", total="100000", lines=("Dịch vụ B",)).model_copy(
        update={"profile_status": "CLEAR"})
    result = match_paper_evidence(paper, (document,))
    result = result.model_copy(update={"links": tuple(
        link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None}) for link in result.links
    )})

    class Llm:
        async def complete_json(self, *, system: str, user: str, budget: RunBudget) -> dict:
            return {"promotions": [{"document_id": "DOC-NOPE", "item_id": "ITEM-001",
                "confidence": 0.99, "rationale": "not an allowed pair", "basis": [
                    {"kind": "AMOUNT", "left_field": "row.amount", "right_field": "document.total_amount"},
                    {"kind": "SERVICE", "left_field": "row.description", "right_field": "document.line_items[*].description"}]}]}

    resolved = await resolve_evidence_suggestions(result, (document,), paper=paper, llm=Llm(), budget=RunBudget())
    assert resolved.links == result.links


def test_first_explicit_allocation_cannot_exceed_source_total() -> None:
    paper = _paper(rows=(("Dòng 1", "600000", ("HQ1",), None),))
    docs = (_invoice("DOC-1", number="HQ1", total="500000"),)
    result = match_paper_evidence(paper, docs)
    assert not any(link.status == "AUTO_LINK" for link in result.links)
    assert result.findings


def test_party_identity_similarity_does_not_treat_generic_supplier_terms_as_identity():
    from invoice_referee.evidence.matching import _party_identity_similarity
    assert _party_identity_similarity("Nhà cung cấp khác", "Nhà cung cấp A") == 0
    assert _party_identity_similarity("Công ty Minh Phát", "Minh Phát") == 1


def test_unmatched_ids_are_source_ids_not_document_ids() -> None:
    paper = _paper(rows=(("Dòng 1", "100000", (), None),))
    docs = (_invoice("DOC-1", issuer="Nhà cung cấp khác", total="999999"),)
    result = match_paper_evidence(paper, docs)
    assert result.unmatched_source_ids == ("source:1",)
