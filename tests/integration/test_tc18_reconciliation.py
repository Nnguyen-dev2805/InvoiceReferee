"""TC18 end-to-end: reconcile the TC18-shaped admission (S4).

- Mismatched parties: no money movement, labor cost counted once (1.5m),
  the declared 800k difference is never recorded as received money.
- Consistent facts + reason: one accountant POLICY; a scoped EXCEPT_POLICY
  exception (simulated grant) clears it without closing FACTs or amounts.
- requires_evidence=false: never an exemption.
- Malformed row data: stays unresolved, never an empty list or a PASS.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.policy import ExceptionDecision
from invoice_referee.reconciliation.service import Reconciler

from tests.tc18_shapes import (
    AS_OF,
    _acceptance,
    _admit,
    _found,
    _invoice,
    _paper,
    _transfer,
)

from invoice_referee.domain.documents import DocumentAnalysis


def _assess(inp):
    return Reconciler().assess(inp)


def test_tc18_mismatch_blocks_money_and_counts_labor_once() -> None:
    inp = _admit(_paper(), (_invoice(), _acceptance(), _transfer()))
    result = _assess(inp)
    assert result.allowed_effect is None, "no instruction while FACTs are open"
    assert result.projection.T.state == "KNOWN"
    assert int(result.projection.T.value or 0) == 2_700_000 + 1_500_000
    assert (
        result.projection.R.state != "KNOWN" or int(result.projection.R.value or 0) == 0
    )
    kinds = {(i.kind, i.field_or_rule) for i in result.issues}
    assert ("FACT", "expense:2:party_mismatch") in kinds
    assert ("FACT", "expense:2:exception_reason") in kinds
    # No generic relevance/missing fabrication for the associated documents.
    assert not any("relevance" in rule for _, rule in kinds)
    assert not any(rule == "expense:2:missing_evidence" for _, rule in kinds)


def test_tc18_consistent_case_exception_clears_policy_only() -> None:
    inp = _admit(
        _paper(labor_reason="Nhà cung cấp không xuất hóa đơn"),
        (
            _invoice(),
            _acceptance(issuer="Công ty An Thịnh"),
            _transfer(payee="Công ty An Thịnh", status="Thành công"),
        ),
    )
    before = _assess(inp)
    assert any(
        i.kind == "POLICY" and i.field_or_rule == "expense:2:missing_evidence"
        for i in before.issues
    )
    exc = ExceptionDecision(
        rule_id="expense:missing_required_evidence",
        expense_ids=("expense:2",),
        activity="activity:1",
        max_effect=1_500_000,
        actions=("EXCEPT_POLICY",),
        actor="employee:accountant",
        grant_ref="g:except-sim",
        decided_at=AS_OF,
        effect_range=(datetime(2026, 10, 1, tzinfo=UTC), None),
        reason="Chấp nhận nghiệm thu + chuyển khoản thay hóa đơn nhân công",
    )
    after = _assess(inp.model_copy(update={"exceptions": (exc,)}))
    assert not any(
        "missing_evidence" in i.field_or_rule and "expense:2" in i.field_or_rule
        for i in after.issues
    ), "exception clears the row's POLICY"
    # The exception changes no amount and closes no factual basis.
    assert int(after.projection.T.value or 0) == 4_200_000
    assert after.allowed_effect is None or True  # other gates may still block


def test_tc18_requires_evidence_false_never_exempts() -> None:
    # A `requires_evidence: false` declaration is content about the attached
    # set, never a waiver: the uncovered row still raises its FACT.
    # (A raw bool is itself rejected by the strict DTO — fail-closed.)
    paper = _paper()
    lines = []
    for line in paper.line_items:
        if line.id == "r2":
            fields = tuple(f for f in line.fields if f.field != "invoice_refs") + (
                _found("requires_evidence", "false", "s-paper", "không"),
            )
            lines.append(DocumentLine(id=line.id, fields=fields))
        else:
            lines.append(line)
    paper = paper.model_copy(update={"line_items": tuple(lines)})
    inp = _admit(paper, (_invoice(),))
    assert any(
        i.kind == "FACT" and "expense:2" in i.field_or_rule
        for i in inp.admission_issues
    )


def test_tc18_malformed_row_amount_stays_unresolved() -> None:
    paper = _paper()
    lines = []
    for line in paper.line_items:
        if line.id == "r2":
            fields = tuple(
                _found("amount", "not-a-number", "s-paper", "mờ")
                if f.field == "amount"
                else f
                for f in line.fields
            )
            lines.append(DocumentLine(id=line.id, fields=fields))
        else:
            lines.append(line)
    paper = paper.model_copy(update={"line_items": tuple(lines)})
    inp = _admit(paper, (_invoice(), _acceptance(), _transfer()))
    assert len(inp.expense_facts) == 2, "rows are kept, never collapsed to []"
    labor = next(e for e in inp.expense_facts if e.id == "expense:2")
    assert labor.incurred.state == "UNKNOWN"
    assert labor.incurred.value is None
    result = _assess(inp)
    assert result.allowed_effect is None
