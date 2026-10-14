"""A declared advance with no matching record must not let coverage assert A=0.

Flow "chưa có bản ghi ứng" (plan E): the employee's settlement form declares a
4.000.000 đ advance, but no company record exists yet. Coverage over the scope
establishes zero FLOWS, but the printed declared advance is a material signal
that A is not zero — the advance must be verified/recorded by the accountant
before S is settled. This is the seam that hands advance verification to the
accountant rather than issuing a wrong PAY for the full cost.
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


def _paper(declared_advance: str | None = "4000000") -> DocumentAnalysis:
    fields = [_found("declared_name", "Nguyễn An"), _found("printed_total", "3240000")]
    if declared_advance is not None:
        fields.append(_found("declared_advance", declared_advance))
    return DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=tuple(fields),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Bữa ăn"), _found("amount", "3240000"), _found("invoice_refs", ("IR1",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR1"), _found("issuer_name", "An Bình"),
                _found("total_amount", "3240000"), _found("buyer_person_name", "Nguyễn An")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org(*, advance: int | None) -> OrganizationContext:
    ledger = []
    if advance:
        ledger.append({
            "id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
            "scope": "activity:1", "payer": "company:demo", "payee": "employee:a",
            "amount": advance, "event_at": "2026-10-05T09:00:00+07:00",
            "recorded_at": "2026-10-05T10:00:00+07:00",
            "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED",
        })
    return OrganizationContext.model_validate({
        "organization_id": "tenant:demo", "profile": "TRAVEL",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": "Nguyễn An"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver"},),
        "ledger": tuple(ledger),
        "coverage": {"activity": "activity:1", "start": "2026-09-01T00:00:00+07:00",
                     "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"],
                     "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    })


def _admit(org: OrganizationContext, *, paper: DocumentAnalysis | None = None):
    return admit_evidence(
        ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper or _paper(), _invoice())),
        scope=CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL"),
        organization=org, confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_declared_advance_without_record_drops_coverage() -> None:
    inp = _admit(_org(advance=None))
    assert inp.coverage is None, "a declared advance with no record must not assert A=0"
    assert any("advance" in i.field_or_rule for i in inp.admission_issues)


def test_declared_advance_with_matching_record_keeps_coverage() -> None:
    inp = _admit(_org(advance=4_000_000))
    assert inp.coverage is not None
    assert not any("advance" in i.field_or_rule for i in inp.admission_issues)


def test_no_declared_advance_keeps_coverage() -> None:
    inp = _admit(_org(advance=None), paper=_paper(declared_advance=None))
    assert inp.coverage is not None
