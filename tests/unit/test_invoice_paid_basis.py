"""C: a valid invoice bound to the right employee/dossier is the employee-paid basis.

Demo policy (user chốt 14/10/2026): in this demo the invoice is accepted as the
basis for an employee-paid cost when it is a valid invoice, bound to the right
employee and dossier, with no material conflict. This REPLACES the earlier
requirement for a separate responsible payer confirmation on the routine,
in-policy dossier. The basis is still labelled as a demo-policy invoice basis —
never a bank-verified fact — and a mismatch of person/dossier/amount, an
unreadable document, or a missing history still asks the right question.

RED first: the current admission only creates an employee-paid portion from a Q32
confirmation, so a clear, bound invoice with no confirmation yields E UNKNOWN.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _paper(declared_name: str = "Nguyễn An") -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            _found("declared_name", declared_name, "Người đề nghị: " + declared_name),
            _found("printed_total", "3240000"),
        ),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Bữa ăn"), _found("amount", "3240000"), _found("invoice_refs", ("IR26101001",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice(*, buyer_person: str | None = "Nguyễn An", status: str = "CLEAR") -> DocumentAnalysis:
    fields = [
        _found("document_number", "IR26101001"),
        _found("issuer_name", "Công ty TNHH Dịch vụ An Bình"),
        _found("total_amount", "3240000"),
    ]
    if buyer_person is not None:
        fields.append(_found("buyer_person_name", buyer_person))
    return DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=tuple(fields), confidence_status="ASSESSED", profile_status=status,  # type: ignore[arg-type]
    )


def _scope() -> CaseScope:
    return CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL")


def _org(*, employee_name: str = "Nguyễn An", advance: int = 4_000_000, coverage: bool = True) -> OrganizationContext:
    ledger = []
    if advance:
        ledger.append({
            "id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
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
            "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
            "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
            "witness_keys": ["cov:1"],
        }
    return OrganizationContext.model_validate({
        "organization_id": "tenant:demo", "profile": "TRAVEL",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": employee_name},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
             "scope": "activity:1", "max_amount": 4_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
        ),
        "ledger": tuple(ledger), "coverage": cov,
    })


def _admit(report: ReadResult, *, org: OrganizationContext | None = None):
    return admit_evidence(
        report, scope=_scope(), organization=org or _org(), confirmations=(), ledger=(),
        coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_clear_bound_invoice_is_the_employee_paid_basis_without_confirmation() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    inp = _admit(report)
    assert len(inp.expense_facts) == 1
    expense = inp.expense_facts[0]
    assert expense.eligibility == "ELIGIBLE"
    assert expense.payment_state == "PAID"
    payment = expense.payments[0]
    assert payment.payer == "employee:a"
    assert payment.basis_kind == "EMPLOYEE_PAID_INVOICE"
    assert payment.responsible_actor == "employee:a"


def test_invoice_basis_is_never_labelled_bank_verified() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    inp = _admit(report)
    assert inp.expense_facts[0].payments[0].basis_kind != "INDEPENDENT_PAYMENT"


def test_buyer_company_is_not_treated_as_company_direct_payer() -> None:
    # The invoice buyer is the company; that must never create a company-direct C
    # portion. Only the employee-paid basis is created.
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    inp = _admit(report)
    assert all(p.payer == "employee:a" for p in inp.expense_facts[0].payments)


def test_invoice_buyer_person_mismatch_is_blocked() -> None:
    # The invoice names a different buyer person than the dossier claimant.
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper("Nguyễn An"), _invoice(buyer_person="Trần Văn B")))
    inp = _admit(report)
    assert inp.expense_facts[0].payments == (), "a person mismatch must not create an employee-paid portion"
    assert any("claimant" in i.field_or_rule for i in inp.admission_issues)


def test_unclear_invoice_does_not_establish_employee_paid() -> None:
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                        documents=(_paper(), _invoice(status="NEEDS_HUMAN")))
    inp = _admit(report)
    assert inp.expense_facts[0].payments == ()


def test_invoice_basis_is_established_without_coverage_even_when_s_unknown() -> None:
    # E (the employee-paid cost) rests on the invoice alone; the advance history
    # (A) is a separate axis. Without coverage A is UNKNOWN -> S UNKNOWN and the
    # policy engine blocks the effect. E must NOT be fabricated as zero.
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(), _invoice()))
    inp = _admit(report, org=_org(coverage=False))
    assert inp.coverage is None
    assert inp.expense_facts[0].payments != (), "the invoice establishes E; A/S are the separate axis"


def test_invoice_basis_over_recognize_bound_still_establishes_e() -> None:
    # The 8m/4m bound is the Q32 declaration autonomy bound, NOT an invoice-basis
    # condition. A valid 9m invoice establishes E; the system's RECOGNIZE/ISSUE
    # authority gate is applied later by policy, never by fabricating E=0.
    paper = _paper()
    invoice = _invoice()
    big_paper = paper.model_copy(update={"line_items": (DocumentLine(id="row:1", fields=(
        _found("description", "x"), _found("amount", "9000000"), _found("invoice_refs", ("IR26101001",)),
    )),)})
    big_invoice = invoice.model_copy(update={"fields": (
        _found("document_number", "IR26101001"), _found("issuer_name", "An Bình"),
        _found("total_amount", "9000000"), _found("buyer_person_name", "Nguyễn An"),
    )})
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(big_paper, big_invoice))
    inp = _admit(report)
    assert inp.expense_facts[0].payments != (), "a valid bound invoice establishes E even above 8m"


def test_wrong_dossier_claimant_is_blocked() -> None:
    # The paper's declared claimant does not match the dossier's employee.
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper("Nguyễn An"), _invoice()))
    inp = _admit(report, org=_org(employee_name="Nguyễn Văn A"))
    assert inp.expense_facts[0].payments == ()
    assert any("claimant" in i.field_or_rule for i in inp.admission_issues)
