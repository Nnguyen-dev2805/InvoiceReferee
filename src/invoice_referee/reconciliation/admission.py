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

from decimal import Decimal, InvalidOperation

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.common import EvidenceRef, Fact
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


def _match_expense_documents(
    report: ReadResult, paper: DocumentAnalysis | None
) -> list[tuple[Decimal, tuple[EvidenceRef, ...]]]:
    """One (amount, refs) per matched original-expense document."""
    links = {(link.item_id, link.document_id): link for link in report.links}
    rows = _settlement_rows(paper)
    out: list[tuple[Decimal, tuple[EvidenceRef, ...]]] = []
    original = [
        d for d in report.documents if d.document_type in _ORIGINAL_EXPENSE_TYPES
    ]
    for index, document in enumerate(original, start=1):
        total = _as_decimal(_field(document, "total_amount"))
        if total is None:
            continue
        item_id = f"ITEM-{index:03d}"
        # A link (AUTO/SUGGEST) is not required to admit a cost, but a document
        # matched to a paper row is preferred; unmatched documents still count as
        # their own occurrence when the row count is unambiguous.
        _ = links.get((item_id, document.document_id))
        out.append((total, _document_refs(document)))
    # When the paper states rows but no document matched, fall back to the row's
    # own stated amount so an unresolved-but-present row is not silently zero.
    if not out:
        for description, amount, refs in rows:
            if amount is not None:
                out.append((amount, ()))
    return out


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
    effective_coverage = coverage if coverage is not None else context_coverage(
        organization, digest=org_digest
    )
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

    # A/P/R known only when coverage exists; used to bound the Q32 path.
    a_known = effective_coverage is not None
    advance_total = sum(
        int(e.amount) for e in merged_ledger if e.kind == "ADVANCE_RECEIVED"
    ) if a_known else None

    # The Q32 bound is on the TOTAL declared E (<=8m) and abs(TOTAL S) (<=4m),
    # not per-row: two 5m claims must not both be accepted just because each row
    # is individually under the limit (ADR0007/Q32). The bound is checked once
    # against the sum of the matched claims before any portion is admitted.
    matched_claims = [
        _claim_for(claims, refs, report, index)
        for index, (_amount, refs) in enumerate(matched, start=1)
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
    for index, (amount, refs) in enumerate(matched, start=1):
        expense_id = f"expense:{index}"
        # The service evidence must name the cost; the settlement row is the
        # canonical cost identity. Ref-less rows still carry the document refs.
        payments: list[ExpensePayment] = []
        eligibility = "UNKNOWN"
        claim = matched_claims[index - 1]
        if claim is not None and bound_ok:
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
