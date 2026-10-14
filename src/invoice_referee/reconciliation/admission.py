"""Pure evidence admission: ReadResult -> AssessmentInput (plan A3; ADR0007).

This is the seam the §12 evidence pipeline never had. It is PURE: no I/O, no
model call, and it never mutates the report. Its one job is to turn a typed,
provenance-checked evidence report into typed Expense/ledger/coverage records
WITHOUT letting a model output become verified money:

- a service occurrence/expense needs a FOUND, quoted value from an original
  expense document; the settlement row supplies the paper amount + refs;
- an employee-paid portion needs a responsible Q32 confirmation, and only when
  the amount is within E<=8m and abs(S)<=4m with no material conflict; an
  invoice's signature/"Chuyển khoản" wording never proves the payer;
- A/P/R come only from the scoped ledger + coverage, never from printed or
  declared totals; missing coverage keeps them UNKNOWN;
- an empty/unknown report never implies T=E=0: `expense_set_complete` stays
  False so the projection keeps the affected totals UNKNOWN.

The reconciler and policy engine remain the decision-makers; this module only
builds the typed input they consume.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef, Fact, parse_vnd
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine
from invoice_referee.domain.evidence import Confirmation, ReadResult
from invoice_referee.domain.finance import (
    CoverageRecord,
    Expense,
    ExpensePayment,
    MoneyEvent,
)
from invoice_referee.domain.issues import BusinessIssue, ProcessingProblem
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.context_records import (
    context_budgets,
    context_coverage,
    context_grants,
    context_ledger,
    context_policies,
    merge_ledger,
)

# The system's autonomy limits (contracts §5). A Q32 declaration may only
# establish E inside these bounds; outside them the factual paid basis must be
# resolved first (plan A3, Q32).
RECOGNIZE_LIMIT = 8_000_000
ISSUE_LIMIT = 4_000_000

_ORIGINAL_EXPENSE_TYPES = frozenset(
    {"E_INVOICE", "PAPER_RECEIPT", "TRANSPORT_TICKET", "HOTEL_RECEIPT", "COLLECTION_RECEIPT"}
)


def _as_decimal(value: object) -> Decimal | None:
    """Parse a model/source money value to Decimal, VN formatting included.

    A real provider returns "3.240.000 đ"; the shared parser handles it (and a
    bare int/Decimal). None when no amount is recoverable — never a fake zero.
    """
    from invoice_referee.domain.common import parse_vnd

    parsed = parse_vnd(value)
    return None if parsed is None else Decimal(parsed)


def _field(document: DocumentAnalysis, name: str) -> object | None:
    for candidate in document.fields:
        if candidate.field == name and candidate.state == "FOUND":
            return candidate.value
    return None


def _line_field(line: DocumentLine, name: str) -> object | None:
    for candidate in line.fields:
        if candidate.field == name and candidate.state == "FOUND":
            return candidate.value
    return None


def _document_refs(document: DocumentAnalysis) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    for candidate in document.fields:
        if candidate.state == "FOUND":
            refs.extend(candidate.refs)
    for line in document.line_items:
        for candidate in line.fields:
            if candidate.state == "FOUND":
                refs.extend(candidate.refs)
    return tuple(refs)


def _settlement_rows(
    paper: DocumentAnalysis | None,
) -> tuple[tuple[str, Decimal | None, tuple[str, ...]], ...]:
    """(description, amount, invoice_refs) for each paper cost row."""
    if paper is None:
        return ()
    rows = []
    for line in paper.line_items:
        description = str(_line_field(line, "description") or "")
        amount = _as_decimal(_line_field(line, "amount"))
        refs_value = _line_field(line, "invoice_refs") or ()
        if isinstance(refs_value, str):
            refs = (refs_value,)
        else:
            refs = tuple(str(r) for r in refs_value)
        rows.append((description, amount, refs))
    return tuple(rows)


class _MatchedExpense(NamedTuple):
    """One admitted cost: its amount, refs and the matched original document."""

    amount: Decimal
    refs: tuple[EvidenceRef, ...]
    document: DocumentAnalysis | None


def _match_expense_documents(
    report: ReadResult, paper: DocumentAnalysis | None
) -> list[_MatchedExpense]:
    """One matched original-expense document (with its amount + refs) per cost."""
    rows = _settlement_rows(paper)
    out: list[_MatchedExpense] = []
    original = [
        d for d in report.documents if d.document_type in _ORIGINAL_EXPENSE_TYPES
    ]
    for document in original:
        total = _as_decimal(_field(document, "total_amount"))
        if total is None:
            continue
        out.append(_MatchedExpense(total, _document_refs(document), document))
    # When the paper states rows but no document matched, fall back to the row's
    # own stated amount so an unresolved-but-present row is not silently zero.
    if not out:
        for description, amount, refs in rows:
            if amount is not None:
                out.append(_MatchedExpense(amount, (), None))
    return out


def coverage_is_valid(
    coverage: CoverageRecord | None, *, scope: CaseScope, as_of: datetime
) -> bool:
    """Whether a coverage record is a VALID basis for a zero A/P/R (contracts §3).

    A coverage OBJECT is not a valid coverage. It must name the scope
    (employee/activity), cover the assessment time (`start <= as_of <=
    coverage.as_of`), list a non-empty fund set and flow-kind set, state an
    opening balance, and carry witness refs. A stale (as_of before the decision)
    or incomplete coverage cannot establish a zero, so it must not produce an
    instruction.
    """
    if coverage is None:
        return False
    if coverage.scope not in (scope.activity, scope.tenant):
        return False
    if not (coverage.start <= as_of <= coverage.as_of):
        return False
    if not coverage.funds or not coverage.flow_kinds:
        return False
    if coverage.opening_balance is None:
        return False
    if not coverage.witness_refs:
        return False
    return True


def _normalize_name(value: object) -> str:
    """Format-only name normalization (whitespace + case). No fuzzy matching."""
    import unicodedata

    text = unicodedata.normalize("NFC", str(value or "")).strip().casefold()
    return " ".join(text.split())


def _claimant_name(organization: OrganizationContext, employee: str) -> str | None:
    for person in organization.people:
        if str(person.get("id")) == employee:
            return str(person.get("name") or "")
    return None


def _declared_name(paper: DocumentAnalysis | None) -> tuple[str, tuple[EvidenceRef, ...]] | None:
    if paper is None:
        return None
    for candidate in paper.fields:
        if candidate.field == "declared_name" and candidate.state == "FOUND":
            return str(candidate.value), candidate.refs
    return None


def _buyer_person_name(
    document: DocumentAnalysis,
) -> tuple[str, tuple[EvidenceRef, ...]] | None:
    for candidate in document.fields:
        if candidate.field == "buyer_person_name" and candidate.state == "FOUND":
            return str(candidate.value), candidate.refs
    return None


def _claimant_binding_issue(
    paper: DocumentAnalysis | None,
    organization: OrganizationContext,
    employee: str,
    *,
    original_documents: tuple[DocumentAnalysis, ...] = (),
) -> BusinessIssue | None:
    """A FACT when a document's declared person does not bind to the dossier.

    Two names can bind a document to the responsible employee: the settlement
    form's `declared_name` and an invoice's `buyer_person_name` (the natural
    person who bought). Any present name that does not bind to the dossier's
    employee is a specific FACT to confirm/correct/alias. A different name is not
    automatically fraud, but it must not be ignored. Only format-normalized
    differences count as equal (no fuzzy match).
    """
    context_name = _claimant_name(organization, employee)
    if context_name is None:
        return None
    declared = _declared_name(paper)
    if declared is not None:
        literal_name, refs = declared
        if _normalize_name(literal_name) != _normalize_name(context_name):
            return BusinessIssue(
                id="issue:fact:claimant-binding",
                kind="FACT",
                field_or_rule="expense:claimant_binding",
                owner="employee",
                basis=(
                    f"Hồ sơ gắn với '{context_name}', nhưng giấy quyết toán khai '{literal_name}'."
                ),
                refs=refs,
                question=(
                    f"Xác nhận/correct người đề nghị: hồ sơ đang gắn '{context_name}', "
                    f"tài liệu khai '{literal_name}'. Xác nhận đây là cùng một người "
                    f"(ghi nhận alias) hoặc sửa lại cho đúng."
                ),
            )
    for document in original_documents:
        buyer = _buyer_person_name(document)
        if buyer is None:
            continue
        literal_name, refs = buyer
        if _normalize_name(literal_name) != _normalize_name(context_name):
            return BusinessIssue(
                id="issue:fact:claimant-binding",
                kind="FACT",
                field_or_rule="expense:claimant_binding",
                owner="employee",
                basis=(
                    f"Hồ sơ gắn với '{context_name}', nhưng người mua trên chứng từ là '{literal_name}'."
                ),
                refs=refs,
                question=(
                    f"Xác nhận/correct người mua trên chứng từ: hồ sơ đang gắn '{context_name}', "
                    f"chứng từ ghi người mua '{literal_name}'. Xác nhận đây là cùng một người "
                    f"(ghi nhận alias) hoặc sửa lại cho đúng."
                ),
            )
    return None


def _invoice_is_employee_paid_basis(
    document: DocumentAnalysis | None,
    organization: OrganizationContext,
    employee: str,
) -> bool:
    """Whether a valid, bound, clear original invoice establishes the employee-paid cost.

    Demo policy (user chốt 14/10/2026): a valid invoice bound to the right
    employee and dossier is accepted as the basis for an employee-paid cost, with
    no separate payer confirmation. It requires a CLEAR profile, a FOUND total,
    and — when the invoice names a buyer person — that the buyer binds to the
    dossier's employee. The company buyer is never a payer.
    """
    if document is None or document.profile_status != "CLEAR":
        return False
    if document.document_type not in _ORIGINAL_EXPENSE_TYPES:
        return False
    if _field(document, "total_amount") is None:
        return False
    buyer = _buyer_person_name(document)
    if buyer is None:
        return False
    context_name = _claimant_name(organization, employee)
    if context_name is None:
        return False
    return _normalize_name(buyer[0]) == _normalize_name(context_name)


def _declared_advance(
    paper: DocumentAnalysis | None,
) -> tuple[int, tuple[EvidenceRef, ...]] | None:
    if paper is None:
        return None
    for candidate in paper.fields:
        if candidate.field == "declared_advance" and candidate.state == "FOUND":
            parsed = parse_vnd(candidate.value)
            if parsed is None:
                return None
            return parsed, candidate.refs
    return None


def _claim_index(confirmations: tuple[Confirmation, ...]) -> dict[str, Confirmation]:
    index: dict[str, Confirmation] = {}
    for confirmation in confirmations:
        # fact_key = expense:<invoice_reference>:employee_paid
        parts = confirmation.fact_key.split(":")
        if len(parts) >= 3 and parts[0] == "expense" and parts[-1] == "employee_paid":
            index[parts[1]] = confirmation
    return index


def admit_evidence(
    report: ReadResult,
    *,
    scope: CaseScope,
    organization: OrganizationContext,
    confirmations: tuple[Confirmation, ...],
    ledger: tuple[MoneyEvent, ...],
    coverage: CoverageRecord | None,
    read_set: ReadSet,
    as_of,
) -> AssessmentInput:
    """Map a typed evidence report into an immutable AssessmentInput (pure)."""
    import hashlib

    org_raw = organization.model_dump_json()
    org_digest = hashlib.sha256(org_raw.encode("utf-8")).hexdigest()

    problems: list[ProcessingProblem] = list(report.problems)
    issues: list[BusinessIssue] = []

    paper = next(
        (d for d in report.documents if d.document_type == "SETTLEMENT_FORM"), None
    )
    if paper is None and any(d.document_type != "UNKNOWN" for d in report.documents):
        problems.append(
            ProcessingProblem(
                kind="TECHNICAL",
                affected_fields=("SETTLEMENT_FORM",),
                message="không có giấy quyết toán (SETTLEMENT_FORM) trong hồ sơ",
                relevance="MATERIAL",
                blocking=False,
                next_action="report_missing_settlement_form",
            )
        )

    # Context ledger/coverage/policy/budget come from the stored snapshot. The
    # recorded actual-money events are MERGED with the context ledger (deduped by
    # external key), not substituted for it: dropping the context advance once a
    # receipt is recorded would miscompute S and the Q32 bound (plan A1/A3).
    ctx_ledger = context_ledger(organization, digest=org_digest)
    merged_ledger, _conflicts = merge_ledger(ctx_ledger, tuple(ledger))
    candidate_coverage = coverage if coverage is not None else context_coverage(
        organization, digest=org_digest
    )
    # A coverage OBJECT is not a valid coverage: it must cover the assessment
    # time and name scope/funds/kinds/opening/witnesses (contracts §3). An
    # invalid (stale/incomplete/wrong-scope) coverage is not a zero basis, so it
    # is dropped here (A/P/R stay UNKNOWN) and raised as a scoped FACT issue.
    if candidate_coverage is not None and not coverage_is_valid(
        candidate_coverage, scope=scope, as_of=as_of
    ):
        issues.append(
            BusinessIssue(
                id="issue:fact:coverage-invalid",
                kind="FACT",
                field_or_rule="ledger:coverage",
                owner="accountant",
                basis="Coverage hiện có không bao phủ thời điểm đánh giá hoặc thiếu scope/quỹ/loại dòng tiền/số dư đầu kỳ/căn cứ.",
                refs=candidate_coverage.witness_refs,
                question="Xác minh coverage lịch sử đủ scope/thời gian/quỹ/loại dòng tiền/số dư đầu kỳ cho thời điểm quyết định.",
            )
        )
        effective_coverage: CoverageRecord | None = None
    else:
        effective_coverage = candidate_coverage

    # A declared advance with no matching company record must NOT be read as A=0.
    # Coverage establishes zero FLOWS in the scope, but the printed declared
    # advance is a material signal that the advance exists: the accountant must
    # verify/record it before S is settled. Dropping coverage keeps A/S UNKNOWN
    # and hands advance verification to the accountant (flow "chưa có bản ghi").
    declared = _declared_advance(paper)
    if declared is not None and effective_coverage is not None:
        declared_amount, declared_refs = declared
        recorded_advance = sum(
            int(e.amount) for e in merged_ledger if e.kind == "ADVANCE_RECEIVED"
        )
        if recorded_advance < declared_amount:
            issues.append(
                BusinessIssue(
                    id="issue:fact:advance-unrecorded",
                    kind="FACT",
                    field_or_rule="ledger:advance",
                    owner="accountant",
                    basis=(
                        f"Giấy quyết toán khai ứng {declared_amount} đ nhưng bản ghi ứng thực nhận "
                        f"mới là {recorded_advance} đ."
                    ),
                    refs=declared_refs,
                    question=(
                        "Xác minh và ghi nhận khoản ứng thực nhận đúng scope trước khi đối soát "
                        "(đã duyệt ứng không tự thành đã nhận)."
                    ),
                )
            )
            effective_coverage = None

    budgets = context_budgets(organization, activity=scope.activity, digest=org_digest)
    policies = context_policies(organization, digest=org_digest, profile=scope.profile)
    grants = context_grants(organization, digest=org_digest)

    # Classify each material source as resolved or unresolved.
    material_unresolved = any(
        d.profile_status != "CLEAR" for d in report.documents
    ) or any(
        d.document_type == "UNKNOWN" for d in report.documents
    )

    matched = _match_expense_documents(report, paper)
    claims = _claim_index(confirmations)

    # Claimant binding: any declared person on the paper or on an original
    # document (invoice buyer) must bind to the dossier's responsible employee.
    # A mismatch is a FACT to resolve (never silently ignored, never
    # auto-interpreted as fraud).
    original_documents = tuple(
        d for d in report.documents if d.document_type in _ORIGINAL_EXPENSE_TYPES
    )
    binding_issue = _claimant_binding_issue(
        paper, organization, scope.employee, original_documents=original_documents
    )
    if binding_issue is not None:
        issues.append(binding_issue)

    # A/P/R known only when coverage exists; used to bound the Q32 path.
    a_known = effective_coverage is not None
    advance_total = sum(
        int(e.amount) for e in merged_ledger if e.kind == "ADVANCE_RECEIVED"
    ) if a_known else None

    # The Q32 bound is on the TOTAL declared E (<=8m) and abs(TOTAL S) (<=4m),
    # not per-row: two 5m claims must not both be accepted just because each row
    # is individually under the limit (ADR0007/Q32). The bound is checked once
    # against the sum of the matched claims before any portion is admitted. It
    # bounds the Q32 DECLARATION path only; the invoice basis (demo policy) does
    # not fabricate E=0 when the total is large — authority is gated by policy.
    matched_claims = [
        _claim_for(claims, entry.refs, report, index)
        for index, entry in enumerate(matched, start=1)
    ]
    total_claimed = sum(
        int(_as_decimal(c.value) or 0) for c in matched_claims if c is not None
    )
    total_s = (
        total_claimed - advance_total
        if advance_total is not None and any(c is not None for c in matched_claims)
        else None
    )
    bound_ok = (
        total_claimed <= RECOGNIZE_LIMIT
        and total_s is not None
        and abs(total_s) <= ISSUE_LIMIT
    )

    expenses: list[Expense] = []
    for index, entry in enumerate(matched, start=1):
        amount, refs = entry.amount, entry.refs
        expense_id = f"expense:{index}"
        # The service evidence must name the cost; the settlement row is the
        # canonical cost identity. Ref-less rows still carry the document refs.
        payments: list[ExpensePayment] = []
        eligibility = "UNKNOWN"
        # Payment status is its own axis: with no admitted payment the basis does
        # not establish the payment status, so it stays UNKNOWN (never a proven
        # debt). An accepted invoice/Q32 portion verifies the paid amount -> PAID.
        payment_state = "UNKNOWN"
        claim = matched_claims[index - 1]
        # Demo policy: a valid invoice bound to the right employee/dossier is the
        # employee-paid basis, with no separate payer confirmation (chốt
        # 14/10/2026). It is a demo-policy basis, never a bank-verified fact.
        if _invoice_is_employee_paid_basis(entry.document, organization, scope.employee):
            payments.append(
                ExpensePayment(
                    external_key=f"invoice:{scope.activity}:{expense_id}",
                    payer=scope.employee,
                    payee="vendor:evidence",
                    amount=int(amount),
                    expense_id=expense_id,
                    received_state="CLEAR",
                    refs=refs,
                    basis_kind="EMPLOYEE_PAID_INVOICE",
                    responsible_actor=scope.employee,
                )
            )
            eligibility = "ELIGIBLE"
            payment_state = "PAID"
        elif claim is not None and bound_ok:
            claim_amount = int(_as_decimal(claim.value) or 0)
            payments.append(
                ExpensePayment(
                    external_key=f"q32:{scope.activity}:{expense_id}",
                    payer=claim.actor,
                    payee="vendor:evidence",
                    amount=claim_amount,
                    expense_id=expense_id,
                    received_state="CLEAR",
                    refs=claim.refs,
                    basis_kind="EMPLOYEE_DECLARATION_Q32",
                    responsible_actor=claim.actor,
                )
            )
            eligibility = "ELIGIBLE"
            payment_state = "PAID"
        elif claim is not None:
            # The declaration is not usable as a bounded E (the total exceeds a
            # limit, or S is unknown); keep the cost as a FACT to resolve, never
            # a silent E=0 or an out-of-bound E.
            issues.append(
                BusinessIssue(
                    id=f"issue:fact:paid-basis:{expense_id}",
                    kind="FACT",
                    field_or_rule=f"expense:{expense_id}:paid_basis",
                    owner="employee",
                    basis="Khoản chi vượt ngưỡng tự xử lý hoặc thiếu lịch sử để xác định S.",
                    refs=claim.refs,
                    question="Xác minh căn cứ người trả (chứng từ thanh toán) cho khoản chi này.",
                )
            )
        else:
            eligibility = "UNKNOWN"

        expenses.append(
            Expense(
                id=expense_id,
                economic_key=_economic_key(report, refs, index),
                activity=scope.activity,
                incurred=Fact[int](
                    key=f"{expense_id}:incurred", value=int(amount), state="KNOWN", refs=refs
                ),
                incurred_at=as_of,
                payments=tuple(payments),
                eligibility=eligibility,  # type: ignore[arg-type]
                refs=refs,
                payment_state=payment_state,  # type: ignore[arg-type]
            )
        )

    # completeness: every material source is resolved and at least one expense
    # is admitted; an empty/unknown-only report is NOT complete.
    expense_set_complete = bool(expenses) and not material_unresolved

    return AssessmentInput(
        scope=scope,
        expense_facts=tuple(expenses),
        observations=report.observations,
        relations=report.relations,
        confirmations=confirmations,
        ledger=tuple(merged_ledger),
        coverage=effective_coverage,
        policy=policies,
        grants=grants,
        budget=budgets,
        exceptions=(),
        previous_eligibility=None,
        read_set=read_set,
        as_of=as_of,
        admission_issues=tuple(issues),
        admission_problems=tuple(problems),
        expense_set_complete=expense_set_complete,
    )


def _claim_for(
    claims: dict[str, Confirmation],
    refs: tuple[EvidenceRef, ...],
    report: ReadResult,
    index: int,
) -> Confirmation | None:
    """The Q32 confirmation that matches this admitted expense, if any.

    A single-row root with a single claim is unambiguous. With multiple rows the
    claim must name a document number that appears in the matched document's
    refs (its `document_number` FOUND value).
    """
    if not claims:
        return None
    if len(claims) == 1 and index == 1:
        return next(iter(claims.values()))
    numbers = {
        str(_field(d, "document_number"))
        for d in report.documents
        if _field(d, "document_number") is not None
    }
    for number, claim in claims.items():
        if number in numbers:
            return claim
    return None


def _economic_key(
    report: ReadResult, refs: tuple[EvidenceRef, ...], index: int
) -> str:
    """Canonical cost identity: issuer + document number, else the row id."""
    for document in report.documents:
        if document.document_type not in _ORIGINAL_EXPENSE_TYPES:
            continue
        number = _field(document, "document_number")
        issuer = _field(document, "issuer_name")
        if number is not None:
            return f"invoice:{issuer or 'unknown'}:{number}"
    return f"expense:{index}"
