"""A3 pure evidence admission tests (plan A3, contracts §12/§3; ADR0007).

`admit_evidence` maps a typed ReadResult + organization context + scoped
confirmations into an AssessmentInput. It is PURE (no I/O, no model call, no
mutation of the report). Its job is the seam the evidence pipeline never had:
turn a verified evidence report into typed Expense/ledger/coverage records
WITHOUT letting a model output become verified money.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentAnalysis,
    DocumentLine,
    EvidenceLink,
    EvidenceMatchingResult,
    FieldCandidate,
)
from invoice_referee.domain.evidence import Confirmation, ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref(quote: str = "x", page: int = 1) -> EvidenceRef:
    return EvidenceRef(
        source_id="source:1", source_sha256=SHA, page=page, exact_quote=quote
    )


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _paper(rows=((("Bữa ăn", "3240000", ("IR1",)),))) -> DocumentAnalysis:
    line_items = []
    for index, (description, amount, refs) in enumerate(rows, start=1):
        line_items.append(
            DocumentLine(
                id=f"row:{index}",
                fields=(
                    _found("description", description),
                    _found("amount", amount),
                    _found("invoice_refs", refs),
                ),
            )
        )
    return DocumentAnalysis(
        source_id="source:1",
        document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(
            _found("declared_name", "Nguyễn An"),
            _found("printed_total", "3240000"),
        ),
        line_items=tuple(line_items),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _invoice(number: str = "IR1", total: str = "3240000") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:2",
        document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=(
            _found("document_number", number),
            _found("issuer_name", "Công ty An Bình"),
            _found("total_amount", total),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _scope() -> CaseScope:
    return CaseScope(
        tenant="tenant:demo",
        employee="employee:a",
        activity="activity:1",
        profile="TRAVEL",
    )


def _read_set() -> ReadSet:
    return ReadSet(
        input_revision=1,
        control_epoch=0,
        context_version=1,
        ledger_version=1,
        usage_version=0,
    )


def _report(documents: tuple[DocumentAnalysis, ...], links=()) -> ReadResult:
    return ReadResult(
        provider_mode="LIVE",
        data_origin="LIVE_READ",
        documents=documents,
        links=links,
    )


def _org(*, advance: int = 4_000_000, coverage: bool = True) -> OrganizationContext:
    ledger = []
    if advance:
        ledger.append(
            {
                "id": "advance:1",
                "external_key": "company:bank:ADV-1",
                "kind": "ADVANCE_RECEIVED",
                "scope": "activity:1",
                "payer": "company:demo",
                "payee": "employee:a",
                "amount": advance,
                "event_at": "2026-10-05T09:00:00+07:00",
                "recorded_at": "2026-10-05T10:00:00+07:00",
                "verification_state": "CONFIRMED",
                "allocation_state": "ALLOCATED",
            }
        )
    cov = None
    if coverage:
        cov = {
            "activity": "activity:1",
            "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-10-10T18:00:00+07:00",
            "fund_ids": ["company:bank"],
            "flow_kinds": [
                "ADVANCE_RECEIVED",
                "REIMBURSEMENT_RECEIVED",
                "EMPLOYEE_RETURN",
                "REVERSAL",
                "OBSERVED_UNALLOCATED",
            ],
            "opening_by_fund": {"company:bank": 0},
            "ledger_version": "ledger:v1",
            "witness_keys": ["coverage:1"],
        }
    return OrganizationContext.model_validate(
        {
            "organization_id": "tenant:demo",
            "profile": "TRAVEL",
            "activity": {
                "activity_id": "activity:1",
                "name": "a",
                "occurred_at": "2026-10-06T09:00:00+07:00",
                "purpose": "p",
                "authorization": {"id": "auth:1"},
            },
            "budgets": (
                {
                    "id": "budget:1",
                    "activity": "activity:1",
                    "amount": 8_000_000,
                    "effect_range": [
                        "2026-10-01T00:00:00+07:00",
                        "2026-12-31T23:59:59+07:00",
                    ],
                    "actor": "employee:approver",
                    "grant_ref": "grant:1",
                },
            ),
            "grants": (
                {
                    "id": "grant:recognize",
                    "version": "v1",
                    "actor": "system:referee",
                    "actions": ["RECOGNIZE_COST"],
                    "scope": "activity:1",
                    "max_amount": 8_000_000,
                    "effective_from": "2026-10-01T00:00:00+07:00",
                    "effective_to": "2026-12-31T23:59:59+07:00",
                    "allowed_profiles": ["TRAVEL"],
                },
                {
                    "id": "grant:issue",
                    "version": "v1",
                    "actor": "system:referee",
                    "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
                    "scope": "activity:1",
                    "max_amount": 4_000_000,
                    "effective_from": "2026-10-01T00:00:00+07:00",
                    "effective_to": "2026-12-31T23:59:59+07:00",
                    "allowed_profiles": ["TRAVEL"],
                },
            ),
            "ledger": tuple(ledger),
            "coverage": cov,
        }
    )


def _claim(amount: int = 3_240_000, invoice: str = "IR1") -> Confirmation:
    return Confirmation(
        fact_key=f"expense:{invoice}:employee_paid",
        value=amount,
        actor="employee:a",
        scope="activity:1",
        refs=(_ref("3.240.000 đ"),),
        reason="đã trả",
        observed_at=AS_OF,
    )


def _admit(report, *, org=None, claims=(), coverage=None):
    return admit_evidence(
        report,
        scope=_scope(),
        organization=org or _org(),
        confirmations=claims,
        ledger=(),
        coverage=coverage,
        read_set=_read_set(),
        as_of=AS_OF,
    )


# --- happy path: pilot-shaped report + claim -> typed expenses --------------


def test_clear_report_and_claim_yields_one_expense_with_refs() -> None:
    inp = _admit(_report((_paper(), _invoice())), claims=(_claim(),))
    assert len(inp.expense_facts) == 1
    expense = inp.expense_facts[0]
    assert expense.incurred.state == "KNOWN"
    assert expense.incurred.value == 3_240_000
    assert expense.eligibility == "ELIGIBLE"
    assert expense.refs, "the expense must carry source refs"
    assert inp.expense_set_complete is True


def test_admission_uses_confirmed_mapping_without_inventing_payer():
    from invoice_referee.reconciliation.admission import _match_expense_documents

    paper = _paper(rows=(("Bữa ăn", "3240000", ()),))
    invoice = _invoice()
    invoice = invoice.model_copy(
        update={
            "fields": tuple(
                field.model_copy(
                    update={
                        "refs": tuple(
                            ref.model_copy(update={"source_id": invoice.source_id})
                            for ref in field.refs
                        )
                    }
                )
                for field in invoice.fields
            )
        }
    )
    link = EvidenceLink(
        item_id="ITEM-001",
        source_id=invoice.source_id,
        document_id=invoice.document_id,
        status="AUTO_LINK",
        method="LLM_RESOLVED",
        score=Decimal("0.95"),
        allocated_amount=Decimal("3240000"),
        explanation="Source-backed service match",
        refs=(_ref().model_copy(update={"source_id": invoice.source_id}),),
    )
    report = _report((paper, invoice), links=(link,))
    matched, extra = _match_expense_documents(report, paper)
    assert matched[0].document is invoice
    assert extra == ()
    assert _admit(report).expense_facts[0].payments == ()


def test_suggested_mapping_does_not_fall_back_to_printed_ref():
    from invoice_referee.reconciliation.admission import _match_expense_documents

    paper, invoice = _paper(), _invoice()
    link = EvidenceLink(
        item_id="ITEM-001",
        source_id=invoice.source_id,
        document_id=invoice.document_id,
        status="SUGGEST_LINK",
        method="AMOUNT_AND_CONTENT",
        score=Decimal("0.65"),
        explanation="Unresolved allocation",
    )
    matched, _ = _match_expense_documents(
        _report((paper, invoice), links=(link,)), paper
    )
    assert matched[0].document is None


def test_employee_paid_portion_carries_q32_basis_not_bank_fact() -> None:
    inp = _admit(_report((_paper(), _invoice())), claims=(_claim(),))
    payment = inp.expense_facts[0].payments[0]
    assert payment.payer == "employee:a"
    assert payment.basis_kind == "EMPLOYEE_DECLARATION_Q32"
    assert payment.responsible_actor == "employee:a"


# --- money stays UNKNOWN without a basis ------------------------------------


def test_invoice_without_a_bound_buyer_person_is_not_employee_paid() -> None:
    # Demo policy (chốt 14/10/2026): a valid invoice IS the employee-paid basis
    # only when it binds to the right employee. This invoice has no buyer person
    # (the binding key), so it is NOT auto-admitted as employee-paid, and no
    # A/P/R is fabricated from it.
    inp = _admit(_report((_paper(), _invoice())), claims=())
    expense = inp.expense_facts[0]
    assert expense.payments == ()
    assert expense.eligibility == "UNKNOWN"


def test_missing_coverage_leaves_a_p_r_unknown() -> None:
    # The context has a ledger event but no coverage record: admission must not
    # fabricate coverage, so the projection (A4) keeps A/P/R UNKNOWN.
    inp = _admit(
        _report((_paper(), _invoice())), claims=(_claim(),), org=_org(coverage=False)
    )
    assert inp.coverage is None


def test_empty_report_never_implies_zero() -> None:
    inp = _admit(_report(()), claims=())
    assert inp.expense_set_complete is False
    assert inp.expense_facts == ()


def test_unreadable_money_stays_unknown() -> None:
    # No readable amount anywhere: admission must not fabricate a zero expense.
    paper = _paper(rows=())
    invoice = _invoice().model_copy(
        update={
            "fields": (
                _found("document_number", "IR1"),
                FieldCandidate(field="total_amount", state="UNREADABLE"),
            )
        }
    )
    inp = _admit(_report((paper, invoice)), claims=(_claim(),))
    assert inp.expense_facts == ()
    assert inp.expense_set_complete is False


# --- Q32 bounds -------------------------------------------------------------


def test_q32_outside_issue_bound_is_not_accepted() -> None:
    # E=9m > 8m recognition limit: the declaration must not silently become E.
    inp = _admit(
        _report(
            (
                _paper(
                    rows=((("x", "9000000", ("IR1",)),)),
                ),
                _invoice(total="9000000"),
            )
        ),
        claims=(_claim(amount=9_000_000),),
    )
    expense = inp.expense_facts[0]
    assert expense.payments == (), (
        "out-of-bound claim must not create an employee-paid portion"
    )


def test_q32_unknown_s_cannot_be_treated_as_within_bound() -> None:
    # With no advance/coverage the S is UNKNOWN, so the bounded path must not
    # accept the claim as within abs(S)<=4m.
    inp = _admit(
        _report((_paper(), _invoice())),
        claims=(_claim(),),
        org=_org(advance=0, coverage=False),
    )
    expense = inp.expense_facts[0]
    assert expense.payments == ()


def test_vn_formatted_money_is_parsed() -> None:
    # A real model returns VN-formatted money ("3.240.000 đ"); admission must
    # parse it, or a correctly-read form yields zero expenses.
    from invoice_referee.reconciliation.admission import _as_decimal as admit_decimal
    from invoice_referee.evidence.matching import _as_decimal as match_decimal

    for parser in (admit_decimal, match_decimal):
        assert parser("3.240.000 đ") == 3_240_000
        assert parser("4.000.000") == 4_000_000
        assert parser("3240000") == 3_240_000
        assert parser(3_240_000) == 3_240_000


def test_q32_total_bound_is_enforced_across_rows() -> None:
    # Two rows, each individually <= 8m, but the TOTAL claimed E (2 x 5m = 10m)
    # exceeds the 8m recognition limit: the bounded Q32 path must not accept the
    # whole set (the bound is on total E, not per-row).
    paper = _paper(
        rows=(
            ("A", "5000000", ("IR1",)),
            ("B", "5000000", ("IR2",)),
        )
    )
    inv1 = _invoice(number="IR1", total="5000000")
    inv2 = _invoice(number="IR2", total="5000000").model_copy(
        update={"source_id": "source:3"}
    )
    claims = (
        _claim(amount=5_000_000, invoice="IR1"),
        _claim(amount=5_000_000, invoice="IR2"),
    )
    inp = _admit(_report((paper, inv1, inv2)), claims=claims)
    # No employee-paid portion may be accepted once the total exceeds the bound.
    assert all(e.payments == () for e in inp.expense_facts)
    assert inp.admission_issues, "an out-of-bound total is a FACT to resolve"


# --- TC25 association-vs-allocation (17/10/2026) ----------------------------


def _receipt(number: str = "PT-1", total: str = "700000") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:3",
        document_id="source:3:1-1:COLLECTION_RECEIPT",
        document_type="COLLECTION_RECEIPT",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",),
        page_range=(1, 1),
        fields=(
            _found("document_number", number, quote="Số phiếu: PT-1"),
            _found("issuer_name", "HTX Thành Đạt", quote="Đơn vị: HTX Thành Đạt"),
            _found("total_amount", total, quote="Số tiền: 700000"),
            _found("document_date", "2026-10-10", quote="Ngày: 10/10/2026"),
            _found("payer_name", "NGUYEN VAN A", quote="Người nộp: NGUYEN VAN A"),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _tc25_paper() -> DocumentAnalysis:
    row = DocumentLine(
        id="row:1",
        fields=(
            _found("description", "Di chuyển nội thành"),
            _found("amount", "900000"),
            _found("invoice_refs", ("PT-1",)),
        ),
        refs=(_ref("Di chuyển nội thành 900000 ref PT-251026-016"),),
    )
    return DocumentAnalysis(
        source_id="source:1",
        document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(
            _found("declared_name", "Nguyễn An"),
            _found("printed_total", "900000"),
        ),
        line_items=(row,),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
        refs=(_ref("Tổng cộng: 900000"),),
    )


def _suggest_link(document: DocumentAnalysis) -> EvidenceLink:
    return EvidenceLink(
        item_id="ITEM-001",
        source_id=document.source_id,
        document_id=document.document_id,
        status="SUGGEST_LINK",
        method="INVOICE_NUMBER_EXACT",
        score=Decimal("1.0"),
        allocated_amount=None,
        explanation="Phân bổ vượt giá trị chứng từ; cần xác nhận.",
        refs=document.refs,
    )


def test_disputed_exact_number_keeps_association_without_relevance_fact() -> None:
    paper, receipt = _tc25_paper(), _receipt()
    report = _report((paper, receipt), links=(_suggest_link(receipt),))
    admitted = _admit(report)
    rules = [issue.field_or_rule for issue in admitted.admission_issues]
    assert not any(rule.startswith("expense:relevance") for rule in rules), (
        "an exactly-referenced document is associated, never 'unreferenced'"
    )
    assert any(rule == f"expense:allocation:{receipt.document_id}" for rule in rules)


def test_disputed_row_has_no_generic_missing_evidence_fact() -> None:
    paper, receipt = _tc25_paper(), _receipt()
    report = _report((paper, receipt), links=(_suggest_link(receipt),))
    admitted = _admit(report)
    rules = [issue.field_or_rule for issue in admitted.admission_issues]
    assert "expense:1:missing_evidence" not in rules


def test_allocation_fact_carries_both_sides_provenance() -> None:
    paper, receipt = _tc25_paper(), _receipt()
    report = _report((paper, receipt), links=(_suggest_link(receipt),))
    admitted = _admit(report)
    fact = next(
        issue
        for issue in admitted.admission_issues
        if issue.field_or_rule == f"expense:allocation:{receipt.document_id}"
    )
    quotes = [ref.exact_quote for ref in fact.refs]
    assert any("900000" in quote for quote in quotes), "paper row side missing"
    assert any("700000" in quote for quote in quotes), "receipt side missing"
    assert "200000" in (fact.basis or "")


def test_duplicate_serials_stay_unresolved_without_relevance_fact() -> None:
    paper = _tc25_paper()
    first = _receipt()
    second = _receipt()
    second = second.model_copy(
        update={
            "source_id": "source:4",
            "document_id": "source:4:1-1:COLLECTION_RECEIPT",
        }
    )
    report = _report(
        (paper, first, second),
        links=(_suggest_link(first), _suggest_link(second)),
    )
    admitted = _admit(report)
    rules = [issue.field_or_rule for issue in admitted.admission_issues]
    assert not any(rule.startswith("expense:relevance") for rule in rules)
    assert "expense:1:missing_evidence" in rules, "no accepted evidence exists"


def test_truly_unreferenced_document_keeps_relevance_fact() -> None:
    paper = _tc25_paper()
    other = _invoice(number="OTHER-9", total="100000")
    report = _report((paper, other))
    admitted = _admit(report)
    assert any(
        issue.field_or_rule == f"expense:relevance:{other.document_id}"
        for issue in admitted.admission_issues
    )


def test_disputed_row_keeps_evidence_date_for_deadline() -> None:
    paper, receipt = _tc25_paper(), _receipt()
    report = _report((paper, receipt), links=(_suggest_link(receipt),))
    admitted = _admit(report)
    disputed = next(
        e for e in admitted.expense_facts if e.id in admitted.disputed_expense_ids
    )
    assert disputed.source_date is not None


def test_admission_emits_issue_for_unverified_blurry_critical_field() -> None:
    from invoice_referee.domain.documents import DocumentProfileIssue

    paper = _paper()
    blurry_invoice = _invoice().model_copy(
        update={
            "profile_status": "NEEDS_HUMAN",
            "profile_findings": (
                DocumentProfileIssue(
                    code="CRITICAL_FIELD_UNVERIFIED",
                    field="total_amount",
                    status="UNRESOLVED",
                    message="critical field lacks verified confidence",
                    blocking=True,
                ),
            ),
        }
    )
    report = _report((paper, blurry_invoice))
    admitted = _admit(report)
    quality_issues = [
        issue
        for issue in admitted.admission_issues
        if issue.field_or_rule == f"evidence:quality:{blurry_invoice.document_id}:total_amount"
    ]
    assert len(quality_issues) == 1
    issue = quality_issues[0]
    assert issue.kind == "FACT"
    assert issue.owner == "accountant"
    assert "chưa đọc chắc chắn" in issue.basis
    assert "tổng số tiền" in issue.basis or "total_amount" in issue.basis

