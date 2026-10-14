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

from datetime import datetime, timezone
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
    context_category_policies,
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


# Code-owned category keywords (T3), ASCII-normalized to match `_normalize_text`.
# The model may also propose a category; this is the deterministic fallback over
# the settlement row + document text.
_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TAXI", ("taxi", "grab", "xe om", "xe cong nghe")),
    ("WORK_CLIENT_MEAL", ("tiep khach", "an uong", "nha hang", "bua an", "cafe", "chieu dai")),
    ("LODGING", ("khach san", "luu tru", "hotel", "phong nghi")),
    ("TRAVEL", ("ve may bay", "ve tau", "ve xe", "di chuyen", "cong tac phi")),
    ("OFFICE_PURCHASE", ("van phong pham", "may in", "thiet bi", "giay in", "muc in", "mua sam")),
    ("OPERATIONS", ("sua chua", "bao tri", "in an", "dich vu", "van hanh")),
    ("PERSONAL", ("ca nhan", "gia dinh")),
)


def _normalize_text(value: object) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def _infer_category(description: str, documents: tuple[DocumentAnalysis, ...]) -> str | None:
    haystack = _normalize_text(description)
    for document in documents:
        for candidate in document.fields:
            if candidate.state == "FOUND" and candidate.field in ("description", "service_charge"):
                haystack += " " + _normalize_text(candidate.value)
        for line in document.line_items:
            for candidate in line.fields:
                if candidate.state == "FOUND" and candidate.field == "description":
                    haystack += " " + _normalize_text(candidate.value)
    for category, tokens in _CATEGORY_KEYWORDS:
        if any(token in haystack for token in tokens):
            return category
    return None


def _source_date(document: DocumentAnalysis | None) -> datetime | None:
    if document is None:
        return None
    for name in ("document_date", "event_at"):
        raw = _field(document, name)
        if raw is None:
            continue
        text = str(raw)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
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
    """One admitted cost: its amount, refs, matched document and row context."""

    amount: Decimal
    refs: tuple[EvidenceRef, ...]
    document: DocumentAnalysis | None
    description: str = ""
    no_evidence_reason: str | None = None
    paper_refs: tuple[EvidenceRef, ...] = ()


def _normalize_ref(value: str) -> str:
    import re

    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _refs_match(a: str, b: str) -> bool:
    """Whether two invoice references name the same document.

    A real model may read the invoice number with the serial prefix
    ("IR26E00000101") while the paper row references the numeric part
    ("00000101"). Two refs match when normalized they are equal or one is a
    suffix of the other (the numeric document number is the stable part).
    """
    na, nb = _normalize_ref(a), _normalize_ref(b)
    if not na or not nb:
        return False
    return na == nb or na.endswith(nb) or nb.endswith(na)


def _match_expense_documents(
    report: ReadResult, paper: DocumentAnalysis | None
) -> list[_MatchedExpense]:
    """One admitted cost per settlement row, matched to an original document.

    Each paper row is a cost. A row links to an original document by its invoice
    reference; an uncovered row is preserved (not silently dropped) so its missing
    required evidence can be raised as a FACT/POLICY (T5). When the paper has no
    rows, each original document is its own cost.
    """
    rows = _settlement_rows(paper)
    original = [
        d for d in report.documents if d.document_type in _ORIGINAL_EXPENSE_TYPES
    ]
    by_ref: dict[str, DocumentAnalysis] = {}
    for document in original:
        number = _field(document, "document_number")
        if number is not None:
            by_ref[_normalize_ref(str(number))] = document
    out: list[_MatchedExpense] = []

    def _find_doc(ref: str) -> DocumentAnalysis | None:
        for key, document in by_ref.items():
            if _refs_match(ref, key):
                return document
        return None
    if rows:
        for line in paper.line_items if paper is not None else ():
            description = str(_line_field(line, "description") or "")
            amount = _as_decimal(_line_field(line, "amount"))
            reason_value = _line_field(line, "no_evidence_reason")
            reason = str(reason_value) if reason_value is not None else None
            refs_value = _line_field(line, "invoice_refs") or ()
            if isinstance(refs_value, str):
                refs_value = (refs_value,)
            matched_doc = None
            for ref in refs_value:
                matched_doc = _find_doc(str(ref))
                if matched_doc is not None:
                    break
            # The admitted cost is the ROW's stated amount (bounded by the source
            # total), not the whole document total: two rows may share one invoice
            # and must not each count the full source (T4, TC23).
            cost = amount
            if cost is None and matched_doc is not None:
                cost = _as_decimal(_field(matched_doc, "total_amount"))
            if cost is None:
                continue
            out.append(_MatchedExpense(
                cost, _document_refs(matched_doc) if matched_doc is not None else (),
                matched_doc, description, reason,
            ))
        # Any original document not referenced by a row is a relevance FACT (T4,
        # TC24): preserved as a zero-cost marker is wrong, so it is reported and
        # NOT admitted as a second cost.
        matched_docs = {id(d.document) for d in out if d.document is not None}
        return out, tuple(d for d in original if id(d) not in matched_docs)
    # No paper rows: each original document is its own cost.
    for document in original:
        total = _as_decimal(_field(document, "total_amount"))
        if total is None:
            continue
        out.append(_MatchedExpense(total, _document_refs(document), document, ""))
    return out, ()


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


def _buyer_name(document: DocumentAnalysis) -> str | None:
    value = _field(document, "buyer_name")
    return str(value) if value is not None else None


def _invoice_binding(
    document: DocumentAnalysis | None,
    paper: DocumentAnalysis | None,
    organization: OrganizationContext,
    employee: str,
) -> tuple[bool, BusinessIssue | None]:
    """Whether a valid invoice binds to the employee, plus any blocking FACT.

    Two ways to bind (T2, demo employee-paid policy):
    1. the invoice names a buyer PERSON who matches the dossier employee; or
    2. composite: the invoice names only the company buyer, the company matches the
       scoped organization identity, the paper claimant matches the employee, and
       the paper row links the invoice (its invoice reference).

    A present natural-person buyer that mismatches, or a company buyer that
    mismatches, is a blocking FACT (never a silent pass). An invoice that names
    neither a buyer person nor a matching company buyer does not bind.
    """
    if document is None or document.profile_status != "CLEAR":
        return False, None
    if document.document_type not in _ORIGINAL_EXPENSE_TYPES:
        return False, None
    if _field(document, "total_amount") is None:
        return False, None
    context_name = _claimant_name(organization, employee)
    if context_name is None:
        return False, None
    person = _buyer_person_name(document)
    if person is not None:
        if _normalize_name(person[0]) == _normalize_name(context_name):
            return True, None
        return False, BusinessIssue(
            id="issue:fact:claimant-binding", kind="FACT",
            field_or_rule="expense:claimant_binding", owner="employee",
            basis=f"Chứng từ ghi người mua '{person[0]}', hồ sơ gắn '{context_name}'.",
            refs=person[1],
            question="Xác nhận/correct người mua trên chứng từ hoặc sửa lại cho đúng.",
        )
    # Composite binding: company buyer + paper claimant + row invoice link.
    buyer_company = _buyer_name(document)
    company_name = organization.company_name
    if buyer_company is None or company_name is None:
        return False, None
    if _normalize_name(buyer_company) != _normalize_name(company_name):
        return False, BusinessIssue(
            id="issue:fact:buyer-binding", kind="FACT",
            field_or_rule="expense:buyer_binding", owner="employee",
            basis=f"Bên mua trên hóa đơn '{buyer_company}' không khớp tổ chức '{company_name}'.",
            refs=_document_refs(document)[:1],
            question="Xác nhận bên mua trên hóa đơn khớp tổ chức của hồ sơ.",
        )
    # The paper claimant must match, and a paper row must reference this invoice.
    if _declared_name(paper) is not None:
        declared, _ = _declared_name(paper)  # type: ignore[misc]
        if _normalize_name(declared) != _normalize_name(context_name):
            return False, None
    number = _field(document, "document_number")
    if number is None or paper is None:
        return False, None
    target = str(number)
    for line in paper.line_items:
        refs_value = _line_field(line, "invoice_refs") or ()
        if isinstance(refs_value, str):
            refs_value = (refs_value,)
        if any(_refs_match(str(r), target) for r in refs_value):
            return True, None
    return False, None


def _invoice_is_employee_paid_basis(
    document: DocumentAnalysis | None,
    organization: OrganizationContext,
    employee: str,
    *,
    paper: DocumentAnalysis | None = None,
) -> bool:
    """Whether a valid, bound, clear original invoice establishes the employee-paid cost."""
    bound, _issue = _invoice_binding(document, paper, organization, employee)
    return bound


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
    category_policies = context_category_policies(
        organization, digest=org_digest, profile=scope.profile
    )

    # Classify each material source as resolved or unresolved.
    material_unresolved = any(
        d.profile_status != "CLEAR" for d in report.documents
    ) or any(
        d.document_type == "UNKNOWN" for d in report.documents
    )

    matched, unreferenced_documents = _match_expense_documents(report, paper)
    claims = _claim_index(confirmations)

    # Allocation: the sum of the rows that share one source must not exceed that
    # source's total (T4, TC22). A payment proof is not a second invoice, so it is
    # not counted here (only original-expense types are matched above).
    allocation_totals: dict[str, int] = {}
    for entry in matched:
        if entry.document is None:
            continue
        key = entry.document.document_id
        allocation_totals[key] = allocation_totals.get(key, 0) + int(entry.amount)
    for entry in matched:
        if entry.document is None:
            continue
        doc_total = _as_decimal(_field(entry.document, "total_amount"))
        if doc_total is None:
            continue
        if allocation_totals[entry.document.document_id] > int(doc_total):
            issues.append(
                BusinessIssue(
                    id=f"issue:fact:allocation:{entry.document.document_id}",
                    kind="FACT",
                    field_or_rule=f"expense:allocation:{entry.document.document_id}",
                    owner="employee",
                    basis=(
                        f"Tổng phân bổ {allocation_totals[entry.document.document_id]} vượt "
                        f"tổng chứng từ {int(doc_total)}."
                    ),
                    refs=entry.document.refs,
                    question="Xác nhận phân bổ các dòng trên chứng từ không vượt tổng chứng từ.",
                )
            )
    # An extra source the paper does not reference is a relevance FACT (TC24),
    # never silently added as a cost or dropped.
    for document in unreferenced_documents:
        issues.append(
            BusinessIssue(
                id=f"issue:fact:relevance:{document.document_id}",
                kind="FACT",
                field_or_rule=f"expense:relevance:{document.document_id}",
                owner="employee",
                basis="Có chứng từ chưa được tham chiếu bởi dòng nào trên giấy đề nghị.",
                refs=document.refs,
                question="Xác nhận chứng từ này có liên quan tới hồ sơ hay không (bổ sung/khoanh vùng).",
            )
        )

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
        # 14/10/2026). Composite binding allows a company-buyer-only invoice when
        # the paper claimant + company identity + row link agree (T2). It is a
        # demo-policy basis, never a bank-verified fact.
        invoice_bound, binding_fact = _invoice_binding(
            entry.document, paper, organization, scope.employee
        )
        if binding_fact is not None:
            issues.append(binding_fact)
        # A paper row with no matched original evidence is not silently dropped:
        # its service/value/payment basis is unestablished, so it is a FACT. A
        # stated reason is a declaration, not proof (T5). The POLICY escalation
        # (`expense:missing_required_evidence`) and its scoped exception are
        # applied by the policy engine once the facts are established.
        if entry.document is None:
            issues.append(
                BusinessIssue(
                    id=f"issue:fact:missing_evidence:{expense_id}",
                    kind="FACT",
                    field_or_rule=f"{expense_id}:missing_evidence",
                    owner="employee",
                    basis=(
                        f"Khoản '{entry.description or expense_id}' chưa có chứng từ gốc "
                        "xác lập dịch vụ/số tiền/nhân viên đã trả."
                        + (f" Lý do khai: {entry.no_evidence_reason}." if entry.no_evidence_reason else "")
                    ),
                    refs=entry.paper_refs,
                    question=(
                        "Cung cấp chứng từ gốc hoặc xác lập dịch vụ/số tiền/người trả cho khoản này."
                    ),
                )
            )
        if invoice_bound:
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
                category=_infer_category(
                    entry.description, (entry.document,) if entry.document else ()
                ),
                source_date=_source_date(entry.document),
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
        category_policy=category_policies,
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
