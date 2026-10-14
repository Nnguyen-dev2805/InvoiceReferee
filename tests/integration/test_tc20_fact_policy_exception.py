"""T5: missing required evidence is FACT → POLICY, resolved by a scoped exception.

A paper row with a stated reason (TC20) is not proof of service/value/payment. The
missing service/value/employee-paid basis is a FACT first; once the facts are
established, the absence of required expense evidence invokes the exact POLICY rule
`expense:missing_required_evidence`, which only a scoped EXCEPT_POLICY grant may
resolve. No initial instruction; no duplicate instruction when answered.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.domain.policy import ExceptionDecision
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.reconciliation.service import Reconciler

SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _found(name: str, value: object, quote: str = "x") -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote=quote),))  # type: ignore[arg-type]


def _paper(*, with_reason: bool, rows: int = 2) -> DocumentAnalysis:
    lines = []
    # Row 1: a covered meal 3.24m; Row 2: an uncovered parking 100k with a reason.
    lines.append(DocumentLine(id="r1", fields=(
        _found("description", "Tiếp khách"), _found("amount", "3240000"), _found("invoice_refs", ("IR1",)),
    )))
    row2 = [_found("description", "Gửi xe"), _found("amount", "100000")]
    if with_reason:
        row2.append(_found("no_evidence_reason", "Mất hóa đơn gửi xe"))
    lines.append(DocumentLine(id="r2", fields=tuple(row2)))
    return DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("purpose", "Công tác"),
                _found("printed_total", "3340000"), _found("declared_advance", "2000000")),
        line_items=tuple(lines), confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _invoice() -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR1"), _found("issuer_name", "Sen"),
                _found("total_amount", "3240000"), _found("buyer_person_name", "Nguyễn An"),
                _found("document_date", "01/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": "tenant:t", "profile": "WORK_EXPENSE",
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-06T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": "employee:a", "name": "Nguyễn An"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000, "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"], "scope": "activity:1",
             "max_amount": 8_000_000, "effective_from": interval[0], "effective_to": interval[1]},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:1",
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED", "scope": "activity:1",
                    "payer": "company:demo", "payee": "employee:a", "amount": 2_000_000,
                    "event_at": "2026-10-05T09:00:00+07:00", "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"activity": "activity:1", "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1", "witness_keys": ["cov:1"]},
        "category_policies": ({"id": "cat:1", "version": "v1", "effective_from": "2026-01-01T00:00:00+07:00",
                               "per_item_caps": {"WORK_CLIENT_MEAL": 5_000_000, "TAXI": 2_000_000},
                               "submission_window_days": 30, "excluded_categories": ["PERSONAL"]},),
    }))


def _admit(*, with_reason: bool, exceptions=()):
    report = ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(with_reason=with_reason), _invoice()))
    inp = admit_evidence(
        report, scope=CaseScope(tenant="tenant:t", employee="employee:a", activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )
    return inp.model_copy(update={"exceptions": tuple(exceptions)})


def test_uncovered_row_with_reason_is_fact_not_policy() -> None:
    inp = _admit(with_reason=True)
    result = Reconciler().assess(inp)
    assert any(i.kind == "FACT" and "missing" in i.field_or_rule for i in result.issues)
    assert result.allowed_effect is None, "no instruction while the FACT is open"


def test_uncovered_row_without_reason_is_fact() -> None:
    inp = _admit(with_reason=False)
    result = Reconciler().assess(inp)
    assert any(i.kind == "FACT" for i in result.issues)


def test_scoped_exception_resolves_the_missing_evidence() -> None:
    inp = _admit(with_reason=True, exceptions=(
        ExceptionDecision(
            rule_id="expense:missing_required_evidence", expense_ids=("expense:2",),
            activity="activity:1", max_effect=100_000, actions=("EXCEPT_POLICY",),
            actor="employee:approver", grant_ref="g:approver",
            decided_at=AS_OF, effect_range=(datetime(2026, 10, 1, tzinfo=UTC), None),
            reason="Chấp nhận khoản gửi xe thiếu hóa đơn",
        ),
    ))
    result = Reconciler().assess(inp)
    # The scoped exception clears the POLICY/FACT for that expense.
    assert not any("missing" in i.field_or_rule and i.kind in ("FACT", "POLICY") for i in result.issues)
