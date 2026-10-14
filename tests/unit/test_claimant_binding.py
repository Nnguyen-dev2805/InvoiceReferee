"""Claimant/activity binding on a document (contracts §3; plan A3/B).

A settlement form names a claimant and a trip; the report's declared name and
activity must bind to the dossier's responsible claimant/context. A different
name is not automatically fraud, but it must not be ignored: it becomes a
specific FACT to confirm/correct/alias. Only format-normalized differences are
treated as equal; no fuzzy match or LLM confidence decides two people are one.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.domain.case import ReadSet

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _ref(quote="x"):
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


def _found(name, value, quote="x"):
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(quote),))


def _paper(declared_name="Nguyễn An", purpose="Làm việc với khách hàng tại Hà Nội"):
    return DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(
            _found("declared_name", declared_name, "Người đề nghị: " + declared_name),
            _found("purpose", purpose),
            _found("printed_total", "3240000"),
        ),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Bữa ăn"), _found("amount", "3240000"), _found("invoice_refs", ("IR1",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice():
    return DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR1"), _found("issuer_name", "An Bình"), _found("total_amount", "3240000")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _report(paper):
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, _invoice()))


def _org(*, people_names=("Nguyễn An",), activity="activity:1"):
    return OrganizationContext.model_validate({
        "organization_id": "tenant:demo", "profile": "TRAVEL",
        "activity": {"activity_id": activity, "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "authorization": {"id": "auth:1"}},
        "people": tuple({"id": "employee:a", "name": n} for n in people_names),
        "budgets": ({"id": "b:1", "activity": activity, "amount": 8_000_000,
                     "effect_range": ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"],
                     "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": activity, "max_amount": 8_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
             "scope": activity, "max_amount": 4_000_000,
             "effective_from": "2026-10-01T00:00:00+07:00", "effective_to": "2026-12-31T23:59:59+07:00"},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": activity, "payer": "company:demo", "payee": "employee:a", "amount": 4_000_000,
                    "event_at": "2026-10-05T09:00:00+07:00", "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"activity": activity, "start": "2026-09-01T00:00:00+07:00",
                     "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"],
                     "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    })


def _admit(report, org):
    scope = CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL")
    return admit_evidence(
        report, scope=scope, organization=org, confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_matching_name_binds_without_extra_question() -> None:
    inp = _admit(_report(_paper("Nguyễn An")), _org(people_names=("Nguyễn An",)))
    assert not any("claimant" in i.field_or_rule or "binding" in i.field_or_rule for i in inp.admission_issues)


def test_format_only_name_difference_binds() -> None:
    # Whitespace/case/diacritic-of-case differences are format, not identity.
    inp = _admit(_report(_paper("  nguyễn  an ")), _org(people_names=("Nguyễn An",)))
    assert not any("claimant" in i.field_or_rule for i in inp.admission_issues)


def test_different_name_creates_a_binding_fact() -> None:
    # Account is Nguyễn Văn A, the paper says Nguyễn An -> a FACT to resolve.
    inp = _admit(_report(_paper("Nguyễn An")), _org(people_names=("Nguyễn Văn A",)))
    assert any("claimant" in i.field_or_rule for i in inp.admission_issues)


def test_binding_issue_preserves_the_literal_name_and_source() -> None:
    inp = _admit(_report(_paper("Nguyễn An")), _org(people_names=("Nguyễn Văn A",)))
    issue = next(i for i in inp.admission_issues if "claimant" in i.field_or_rule)
    assert issue.refs, "the issue must carry the source ref of the declared name"
    assert "Nguyễn An" in issue.basis or "Nguyễn An" in issue.question

