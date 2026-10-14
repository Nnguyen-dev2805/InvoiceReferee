"""A3 pure evidence admission tests (plan A3, contracts §12/§3; ADR0007).

`admit_evidence` maps a typed ReadResult + organization context + scoped
confirmations into an AssessmentInput. It is PURE (no I/O, no model call, no
mutation of the report). Its job is the seam the evidence pipeline never had:
turn a verified evidence report into typed Expense/ledger/coverage records
WITHOUT letting a model output become verified money.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=page, exact_quote=quote)


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
        fields=(_found("declared_name", "Nguyễn An"), _found("printed_total", "3240000")),
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
    return CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL")


def _read_set() -> ReadSet:
    return ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0)


def _report(documents: tuple[DocumentAnalysis, ...], links=()) -> ReadResult:
    return ReadResult(
        provider_mode="LIVE", data_origin="LIVE_READ",
        documents=documents, links=links,
    )


def _org(*, advance: int = 4_000_000, coverage: bool = True) -> OrganizationContext:
    ledger = []
    if advance:
        ledger.append({
            "id": "advance:1", "external_key": "company:bank:ADV-1", "kind": "ADVANCE_RECEIVED",
            "scope": "activity:1", "payer": "company:demo", "payee": "employee:a",
            "amount": advance, "event_at": "2026-10-05T09:00:00+07:00",
            "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED",
        })
    cov = None
    if coverage:
        cov = {
            "activity": "activity:1", "start": "2026-09-01T00:00:00+07:00",
            "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"],
            "flow_kinds": ["ADVANCE_RECEIVED", "REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN", "REVERSAL", "OBSERVED_UNALLOCATED"],
            "opening_by_fund": {"company:bank": 0}, "ledger_version": "ledger:v1",
            "witness_keys": [],
        }
    return OrganizationContext.model_validate({
        "organization_id": "tenant:demo", "profile": "TRAVEL",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "authorization": {"id": "auth:1"}},
        "budgets": ({"id": "budget:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver", "grant_ref": "grant:1"},),
        "grants": (
            {"id": "grant:recognize", "version": "v1", "actor": "system:referee",
             "actions": ["RECOGNIZE_COST"], "scope": "activity:1", "max_amount": 8_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00",
             "allowed_profiles": ["TRAVEL"]},
            {"id": "grant:issue", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:1", "max_amount": 4_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00",
             "allowed_profiles": ["TRAVEL"]},
        ),
        "ledger": tuple(ledger), "coverage": cov,
    })


def _claim(amount: int = 3_240_000, invoice: str = "IR1") -> Confirmation:
    return Confirmation(
        fact_key=f"expense:{invoice}:employee_paid", value=amount, actor="employee:a",
        scope="activity:1", refs=(_ref("3.240.000 đ"),),
        reason="đã trả", observed_at=AS_OF,
    )


def _admit(report, *, org=None, claims=(), coverage=None):
    return admit_evidence(
        report, scope=_scope(), organization=org or _org(), confirmations=claims,
        ledger=(), coverage=coverage, read_set=_read_set(), as_of=AS_OF,
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


def test_employee_paid_portion_carries_q32_basis_not_bank_fact() -> None:
    inp = _admit(_report((_paper(), _invoice())), claims=(_claim(),))
    payment = inp.expense_facts[0].payments[0]
    assert payment.payer == "employee:a"
    assert payment.basis_kind == "EMPLOYEE_DECLARATION_Q32"
    assert payment.responsible_actor == "employee:a"


# --- money stays UNKNOWN without a basis ------------------------------------


def test_invoice_alone_does_not_create_employee_paid_or_ap_r() -> None:
    # An invoice (and its printed "Chuyển khoản") never proves who paid.
    inp = _admit(_report((_paper(), _invoice())), claims=())
    expense = inp.expense_facts[0]
    assert expense.payments == ()
    assert expense.eligibility == "UNKNOWN"


def test_missing_coverage_leaves_a_p_r_unknown() -> None:
    # The context has a ledger event but no coverage record: admission must not
    # fabricate coverage, so the projection (A4) keeps A/P/R UNKNOWN.
    inp = _admit(_report((_paper(), _invoice())), claims=(_claim(),), org=_org(coverage=False))
    assert inp.coverage is None


def test_empty_report_never_implies_zero() -> None:
    inp = _admit(_report(()), claims=())
    assert inp.expense_set_complete is False
    assert inp.expense_facts == ()


def test_unreadable_money_stays_unknown() -> None:
    # No readable amount anywhere: admission must not fabricate a zero expense.
    paper = _paper(rows=())
    invoice = _invoice().model_copy(
        update={"fields": (
            _found("document_number", "IR1"),
            FieldCandidate(field="total_amount", state="UNREADABLE"),
        )}
    )
    inp = _admit(_report((paper, invoice)), claims=(_claim(),))
    assert inp.expense_facts == ()
    assert inp.expense_set_complete is False


# --- Q32 bounds -------------------------------------------------------------


def test_q32_outside_issue_bound_is_not_accepted() -> None:
    # E=9m > 8m recognition limit: the declaration must not silently become E.
    inp = _admit(_report((_paper(rows=((("x", "9000000", ("IR1",)),)),), _invoice(total="9000000"))),
                 claims=(_claim(amount=9_000_000),))
    expense = inp.expense_facts[0]
    assert expense.payments == (), "out-of-bound claim must not create an employee-paid portion"


def test_q32_unknown_s_cannot_be_treated_as_within_bound() -> None:
    # With no advance/coverage the S is UNKNOWN, so the bounded path must not
    # accept the claim as within abs(S)<=4m.
    inp = _admit(_report((_paper(), _invoice())), claims=(_claim(),), org=_org(advance=0, coverage=False))
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
    paper = _paper(rows=(
        ("A", "5000000", ("IR1",)),
        ("B", "5000000", ("IR2",)),
    ))
    inv1 = _invoice(number="IR1", total="5000000")
    inv2 = _invoice(number="IR2", total="5000000").model_copy(update={"source_id": "source:3"})
    claims = (_claim(amount=5_000_000, invoice="IR1"), _claim(amount=5_000_000, invoice="IR2"))
    inp = _admit(_report((paper, inv1, inv2)), claims=claims)
    # No employee-paid portion may be accepted once the total exceeds the bound.
    assert all(e.payments == () for e in inp.expense_facts)
    assert inp.admission_issues, "an out-of-bound total is a FACT to resolve"
