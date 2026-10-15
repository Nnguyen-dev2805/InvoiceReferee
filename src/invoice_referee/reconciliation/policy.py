"""Policy/authority assessment: issues, authorizations and the proposed effect.

Contracts §2, §4–§5. Pure: a function of the immutable AssessmentInput and its
projection. A grant is scoped to one action, one scope and an effective
interval; the demo limits are E <= 8m (RECOGNIZE_COST), abs(S) <= 4m
(ISSUE_PAYMENT/ISSUE_COLLECTION) and the approver's 20m per action.
"""

from __future__ import annotations

from invoice_referee.domain.case import AssessmentInput, AssessmentResult, FinancialEffect
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.finance import Projection
from invoice_referee.domain.issues import BusinessIssue
from invoice_referee.domain.policy import Grant

RECOGNIZE_LIMIT = 8_000_000
ISSUE_LIMIT = 4_000_000
APPROVER_LIMIT = 20_000_000
# The system's autonomy is bounded by the system actor's own grants; a human
# grant (approver) lets a person resolve an AUTHORITY issue, it does not let
# the system auto-complete past its own limits (§2, §5).
SYSTEM_ACTOR = "system:referee"


def _evidence_refs(
    input: AssessmentInput,
    *,
    fields: tuple[str, ...] = (),
    expense: bool = False,
    coverage: bool = False,
    budget: bool = False,
) -> tuple[EvidenceRef, ...]:
    """The source evidence a card rests on (contracts §7: cards carry refs).

    An issue/card is grounded in the observations, expense, coverage or budget
    records that establish its fact, so a scored card can show real refs.
    """
    refs: list[EvidenceRef] = []
    for observation in input.observations:
        if observation.field in fields:
            refs.append(observation.ref)
    if expense:
        for item in input.expense_facts:
            refs.extend(item.refs)
    if coverage and input.coverage is not None:
        refs.extend(input.coverage.witness_refs)
    if budget:
        for decision in input.budget:
            refs.extend(decision.refs)
    return tuple(refs)


def _issue(
    issue_id: str,
    kind: str,
    field_or_rule: str,
    owner: str,
    basis: str,
    question: str,
    refs: tuple[EvidenceRef, ...] = (),
) -> BusinessIssue:
    return BusinessIssue(
        id=issue_id,
        kind=kind,  # type: ignore[arg-type]
        field_or_rule=field_or_rule,
        owner=owner,
        basis=basis,
        question=question,
        refs=refs,
    )


def _scope_covers(input: AssessmentInput, grant_scope: str) -> bool:
    """A grant covers an activity when its scope is that activity or the tenant.

    Contracts §5: a grant has an explicit scope (the system grant is scoped to
    one activity/profile); a tenant-wide grant is the demo's ``tenant:<id>``
    convention. A grant scoped to another activity never authorizes this one.
    """
    return grant_scope in (input.scope.activity, input.scope.tenant)


def _profile_covers(input: AssessmentInput, grant: Grant) -> bool:
    """A grant with an explicit allowed_profiles list only covers those (R3)."""
    if not grant.allowed_profiles:
        return True
    return input.scope.profile in grant.allowed_profiles


def _grant_covers(
    input: AssessmentInput, action: str, amount: int, actor: str | None = None
) -> bool:
    when = input.as_of
    for grant in input.grants:
        if action not in grant.actions:
            continue
        if actor is not None and grant.actor != actor:
            continue
        if not _scope_covers(input, grant.scope):
            continue
        if not _profile_covers(input, grant):
            continue
        if grant.effective_from <= when and (grant.effective_to is None or when <= grant.effective_to):
            if grant.max_amount >= amount:
                return True
    return False


def _has_grant_ignoring_amount(input: AssessmentInput, action: str) -> bool:
    when = input.as_of
    for grant in input.grants:
        if action not in grant.actions:
            continue
        if not _scope_covers(input, grant.scope):
            continue
        if not _profile_covers(input, grant):
            continue
        if grant.effective_from <= when and (grant.effective_to is None or when <= grant.effective_to):
            return True
    return False


def evaluate_policy(
    input: AssessmentInput, projection: Projection
) -> tuple[tuple[BusinessIssue, ...], tuple[str, ...], FinancialEffect | None]:
    """Return (issues, required_authorizations, allowed_effect)."""
    issues: list[BusinessIssue] = []
    authorizations: list[str] = []
    activity = input.scope.activity

    # FACT: a required fact that is unresolved blocks any money conclusion.
    if projection.T.state != "KNOWN":
        issues.append(
            _issue(
                "issue:fact:incurred",
                "FACT",
                "expense:T",
                "employee",
                "Chi phí công việc chưa được xác minh.",
                "Cung cấp chứng từ chi phí hợp lệ cho hoạt động này.",
                _evidence_refs(input, fields=("incurred", "amount"), expense=True),
            )
        )
    if projection.A.state == "UNKNOWN" or projection.P.state == "UNKNOWN":
        issues.append(
            _issue(
                "issue:fact:history",
                "FACT",
                "ledger:coverage",
                "accountant",
                "Thiếu lịch sử đối chiếu ứng/hoàn cho scope này.",
                "Xác minh coverage lịch sử (scope/thời gian/loại dòng tiền).",
                _evidence_refs(input, fields=("coverage", "advance", "reimbursed", "returned")),
            )
        )
    # When EVERY admitted cost is in dispute (TC08), the payer basis is already
    # known — only the amount is unresolved, and the specific dispute FACT owns
    # that question. Asking "who paid?" would be a false/duplicate question, so
    # the generic payer FACT is suppressed for that case.
    all_disputed = bool(input.expense_facts) and all(
        expense.id in input.disputed_expense_ids for expense in input.expense_facts
    )
    invoice_payer_questions = {
        issue.field_or_rule
        for issue in input.admission_issues
        if issue.kind == "FACT"
        and issue.field_or_rule.startswith("expense:")
        and issue.field_or_rule.endswith(":employee_paid")
    }
    unresolved_payment_count = sum(
        expense.payment_state == "UNKNOWN" for expense in input.expense_facts
    )
    has_invoice_specific_coverage = (
        unresolved_payment_count > 0
        and len(invoice_payer_questions) >= unresolved_payment_count
    )
    if (
        projection.E.state == "UNKNOWN"
        and not all_disputed
        and not has_invoice_specific_coverage
    ):
        # An incurred cost with no established payer is a FACT owned by the
        # verifier; it must not become an E=0 money conclusion (§3, §10.2).
        issues.append(
            _issue(
                "issue:fact:payer",
                "FACT",
                "expense:payer",
                "employee",
                "Chưa xác minh ai thực tế đã trả khoản chi này.",
                "Xác minh người trả (chứng từ thanh toán hoặc xác nhận có trách nhiệm).",
                _evidence_refs(input, fields=("incurred", "paid_employee", "paid_company"), expense=True),
            )
        )

    # E recognition limit: the system self-recognizes up to 8m.
    if projection.E.state == "KNOWN":
        e_value = int(projection.E.value or 0)
        if e_value > RECOGNIZE_LIMIT and not _grant_covers(
            input, "RECOGNIZE_COST", e_value, actor=SYSTEM_ACTOR
        ):
            authorizations.append("RECOGNIZE_COST")
            issues.append(
                _issue(
                    "issue:authority:recognize",
                    "AUTHORITY",
                    "RECOGNIZE_COST",
                    "approver",
                    f"Chi phí đủ điều kiện {e_value} vượt mức tự công nhận {RECOGNIZE_LIMIT}.",
                    "Cấp quyết định công nhận chi phí trong phạm vi được giao.",
                    _evidence_refs(input, fields=("paid_employee", "incurred"), expense=True),
                )
            )

    allowed_effect: FinancialEffect | None = None
    if projection.S.state == "KNOWN":
        s_value = int(projection.S.value or 0)
        if s_value != 0:
            action = "ISSUE_PAYMENT" if s_value > 0 else "ISSUE_COLLECTION"
            amount = abs(s_value)
            if amount <= ISSUE_LIMIT and _grant_covers(
                input, action, amount, actor=SYSTEM_ACTOR
            ):
                allowed_effect = FinancialEffect(
                    direction="PAY" if s_value > 0 else "COLLECT",
                    amount=amount,
                    employee=input.scope.employee,
                    activity=activity,
                    basis=f"S={s_value}",
                )
            else:
                authorizations.append(action)
                issues.append(
                    _issue(
                        "issue:authority:issue",
                        "AUTHORITY",
                        action,
                        "approver",
                        f"Cần phát hành {action} {amount} vượt quyền tự xử lý {ISSUE_LIMIT}.",
                        "Cấp quyết định phát hành yêu cầu chi/thu trong phạm vi.",
                        _evidence_refs(input, fields=("incurred", "paid_employee"), expense=True),
                    )
                )

    # Any material FACT/POLICY/AUTHORITY gate still open means no proposal:
    # allowed_effect is a proposal only when every gate is clean (§4).
    if issues:
        allowed_effect = None

    return tuple(issues), tuple(authorizations), allowed_effect
