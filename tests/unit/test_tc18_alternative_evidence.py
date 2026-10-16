"""TC18: one row supported by two alternative documents (acceptance + transfer)."""

from __future__ import annotations

from tests.tc18_shapes import (
    AS_OF,
    _acceptance,
    _admit,
    _invoice,
    _org,
    _paper,
    _transfer,
)


def _rules(inp):
    return sorted({i.field_or_rule for i in inp.admission_issues})


def test_tc18_labor_keeps_association_with_two_alternative_documents() -> None:
    inp = _admit(_paper(), (_invoice(), _acceptance(), _transfer()))
    rules = _rules(inp)
    # The labor row keeps its two-document association: no generic
    # missing-evidence FACT pretending the documents are unrelated.
    assert "expense:2:missing_evidence" not in rules
    labor = next(e for e in inp.expense_facts if e.id == "expense:2")
    # Exactly one 1.5m cost: the two files never double into 3m.
    assert labor.incurred.state == "KNOWN" and labor.incurred.value == 1_500_000
    assert labor.refs, "admitted cost keeps two-sided refs"


def test_tc18_payee_supplier_mismatch_is_a_blocking_fact() -> None:
    inp = _admit(_paper(), (_invoice(), _acceptance(), _transfer()))
    mismatch = [
        i for i in inp.admission_issues if i.field_or_rule == "expense:2:party_mismatch"
    ]
    assert len(mismatch) == 1
    issue = mismatch[0]
    assert issue.kind == "FACT"
    quotes = " ".join(r.exact_quote for r in issue.refs).upper()
    assert "AN THỊNH" in quotes and "PHÚC AN" in quotes
    assert "gian lận" not in issue.basis and "gian lận" not in issue.question


def test_tc18_missing_original_reason_is_a_per_row_supplement_task() -> None:
    inp = _admit(_paper(), (_invoice(), _acceptance(), _transfer()))
    supplement = [
        i
        for i in inp.admission_issues
        if i.field_or_rule == "expense:2:exception_reason"
    ]
    assert len(supplement) == 1
    assert supplement[0].owner == "employee"


def test_tc18_note_is_never_an_exception_reason() -> None:
    # The paper note describes the attached set; it must not become a reason.
    inp = _admit(_paper(), (_invoice(), _acceptance(), _transfer()))
    labor = next(e for e in inp.expense_facts if e.id == "expense:2")
    assert labor.eligibility != "ELIGIBLE"
    assert not any(
        "Biên bản nghiệm thu và chuyển khoản" in (i.basis or "") and i.kind == "POLICY"
        for i in inp.admission_issues
    )


def test_tc18_wrong_note_about_invoice_raises_a_note_fact() -> None:
    inp = _admit(
        _paper(labor_note="Đính kèm hóa đơn nhân công"),
        (_invoice(), _acceptance(), _transfer()),
    )
    assert any(
        i.field_or_rule == "expense:2:note_contradiction" for i in inp.admission_issues
    )


def test_tc18_consistent_parties_with_reason_reaches_policy_exception() -> None:
    inp = _admit(
        _paper(labor_reason="Nhà cung cấp không xuất hóa đơn"),
        (
            _invoice(),
            _acceptance(issuer="Công ty An Thịnh"),
            _transfer(payee="Công ty An Thịnh", status="Thành công"),
        ),
    )
    rules = _rules(inp)
    assert "expense:2:party_mismatch" not in rules
    assert "expense:2:exception_reason" not in rules
    policy = [
        i
        for i in inp.admission_issues
        if i.field_or_rule == "expense:2:missing_evidence"
    ]
    assert len(policy) == 1 and policy[0].kind == "POLICY"
    assert policy[0].owner == "accountant"


def test_tc18_draft_marks_alternative_row_without_green_tick() -> None:
    from decimal import Decimal

    from invoice_referee.domain.evidence import ReadResult, SourceRef
    from invoice_referee.domain.documents import EvidenceLink
    from invoice_referee.reconciliation.settlement_draft import build_settlement_draft

    paper = _paper()
    acceptance, transfer = _acceptance(), _transfer()
    links = tuple(
        EvidenceLink(
            item_id="ITEM-002",
            source_id=doc.source_id,
            document_id=doc.document_id,
            status="AUTO_LINK",
            method="INVOICE_NUMBER_EXACT",
            score=Decimal("1"),
            allocated_amount=Decimal("1500000"),
            explanation="ALTERNATIVE association",
            refs=doc.refs,
        )
        for doc in (acceptance, transfer)
    )
    sources = tuple(
        SourceRef(
            id=sid,
            digest="a" * 64,
            tenant="t",
            media="PDF",
            storage_key="k",
            filename=name,
        )
        for sid, name in (
            ("s-paper", "report.pdf"),
            ("s-inv", "hoa_don.pdf"),
            ("s-acc", "nghiem_thu.pdf"),
            ("s-trf", "chuyen_khoan.pdf"),
        )
    )
    draft = build_settlement_draft(
        ReadResult(documents=(paper, _invoice(), acceptance, transfer), links=links),
        sources=sources,
    )
    labor = next(
        e for e in draft["expenses"] if e["description"] == "Nhân công sửa chữa"
    )
    assert labor["status"] == "ALTERNATIVE"
    assert labor["matched_invoice"] is not None
    parts = next(
        e for e in draft["expenses"] if e["description"] == "Mua linh kiện máy in"
    )
    assert parts["status"] in ("CLEAR", "SUGGESTED", "UNMATCHED", "ALTERNATIVE")


def _exception(amount: int = 1_500_000):
    from datetime import UTC, datetime

    from invoice_referee.domain.policy import ExceptionDecision

    return ExceptionDecision(
        rule_id="expense:missing_required_evidence",
        expense_ids=("expense:2",),
        activity="activity:1",
        max_effect=amount,
        actions=("EXCEPT_POLICY",),
        actor="employee:accountant",
        grant_ref="g:sim",
        decided_at=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
        effect_range=(datetime(2026, 10, 1, tzinfo=UTC), None),
        reason="Chấp nhận thay thế",
    )


def _admit_with(paper, docs, exceptions=()):
    from invoice_referee.domain.case import CaseScope, ReadSet
    from invoice_referee.domain.evidence import ReadResult
    from invoice_referee.reconciliation.admission import admit_evidence

    report = ReadResult(
        provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, *docs)
    )
    return admit_evidence(
        report,
        scope=CaseScope(
            tenant="tenant:t",
            employee="employee:a",
            activity="activity:1",
            profile="WORK_EXPENSE",
        ),
        organization=_org(),
        confirmations=(),
        ledger=(),
        coverage=None,
        read_set=ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=0,
        ),
        as_of=AS_OF,
        exceptions=exceptions,
    )


def test_accepted_exception_makes_consistent_alternative_eligible() -> None:
    inp = _admit_with(
        _paper(labor_reason="Nhà cung cấp không xuất hóa đơn"),
        (
            _invoice(),
            _acceptance(issuer="Công ty An Thịnh"),
            _transfer(payee="Công ty An Thịnh", status="Thành công"),
        ),
        exceptions=(_exception(),),
    )
    labor = next(e for e in inp.expense_facts if e.id == "expense:2")
    assert labor.eligibility == "ELIGIBLE"
    assert labor.payment_state == "PAID"
    assert [p.basis_kind for p in labor.payments] == ["ALTERNATIVE_ACCEPTED"]
    from invoice_referee.reconciliation.service import Reconciler

    result = Reconciler().assess(inp)
    assert not any(
        i.field_or_rule == "expense:2:missing_evidence" for i in result.issues
    )


def test_accepted_exception_does_not_close_open_party_mismatch() -> None:
    inp = _admit_with(
        _paper(labor_reason="Nhà cung cấp không xuất hóa đơn"),
        (_invoice(), _acceptance(), _transfer()),
        exceptions=(_exception(),),
    )
    labor = next(e for e in inp.expense_facts if e.id == "expense:2")
    assert labor.eligibility == "UNKNOWN"
    assert any(
        i.field_or_rule == "expense:2:party_mismatch" for i in inp.admission_issues
    )
