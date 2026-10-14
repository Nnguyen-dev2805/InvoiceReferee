"""Pure per-expense category/deadline evaluation (T3; contracts §3–§5).

Appends category/date and personal-exclusion decisions to the existing
FACT/POLICY/AUTHORITY outcome. The Reconciler remains the financial owner: this
module returns typed `BusinessIssue`s only, never an instruction.

Rules (user-approved Hoangha import):
- work/client meal <=5,000,000 VND per canonical expense;
- taxi/ride <=2,000,000 VND per canonical expense;
- submission within 30 calendar days of the established expense date;
- personal expense is not recognized as a business expense.

The cap applies to ONE canonical expense (a whole admitted cost), not to freely
split paper rows. A category with no explicit cap still passes the ordinary gates;
a missing category that materially changes the decision is a FACT.
"""

from __future__ import annotations

from datetime import datetime

from invoice_referee.domain.case import AssessmentInput
from invoice_referee.domain.issues import BusinessIssue
from invoice_referee.domain.policy import CategoryPolicy

# A category that has no explicit per-item cap but is still a recognized
# business family (office purchase, operations, travel, lodging, …). An absent
# category is FACT when it materially changes the decision.
_KNOWN_UNCAPPED = frozenset(
    {"TRAVEL", "LODGING", "OFFICE_PURCHASE", "OPERATIONS", "OTHER"}
)


def _active_policy(input: AssessmentInput, as_of: datetime) -> CategoryPolicy | None:
    for policy in input.category_policy:
        if policy.effective_from <= as_of and (policy.effective_to is None or as_of <= policy.effective_to):
            return policy
    return None


def _issue(issue_id: str, kind: str, field_or_rule: str, owner: str, basis: str, question: str, refs=()) -> BusinessIssue:
    return BusinessIssue(
        id=issue_id, kind=kind,  # type: ignore[arg-type]
        field_or_rule=field_or_rule, owner=owner, basis=basis, question=question, refs=tuple(refs),
    )


def evaluate_categories(
    input: AssessmentInput, *, as_of: datetime
) -> tuple[BusinessIssue, ...]:
    """Return the category/deadline/exclusion issues for the admitted expenses."""
    policy = _active_policy(input, as_of)
    if policy is None:
        return ()
    issues: list[BusinessIssue] = []
    for expense in input.expense_facts:
        amount = int(expense.incurred.value or 0)
        category = expense.category
        if category is None:
            issues.append(_issue(
                f"issue:fact:category:{expense.id}", "FACT", "expense:category", "employee",
                f"Khoản '{expense.id}' chưa xác định loại chi phí.",
                "Xác định loại chi phí (công tác/tiếp khách, taxi, văn phòng, cá nhân…) để áp đúng hạn mức.",
                expense.refs,
            ))
            continue
        if category in policy.excluded_categories:
            issues.append(_issue(
                f"issue:policy:category:{expense.id}", "POLICY", f"category:{category}", "approver",
                f"Khoản '{expense.id}' thuộc loại bị loại trừ ({category}); không là chi phí công việc.",
                "Xác nhận loại trừ khỏi chi phí công việc (giữ nghĩa vụ tiền thực tế).",
                expense.refs,
            ))
            continue
        cap = policy.per_item_caps.get(category)
        if cap is not None and amount > cap:
            issues.append(_issue(
                f"issue:policy:category:{expense.id}", "POLICY", f"category:{category}", "approver",
                f"Khoản '{expense.id}' ({category}) {amount} vượt hạn mức {cap} mỗi khoản.",
                "Quyết định ngoại lệ cho khoản vượt hạn mức loại chi phí (đúng rule/khoản/scope).",
                expense.refs,
            ))
        # Submission window.
        if policy.submission_window_days is not None:
            if expense.source_date is None:
                issues.append(_issue(
                    f"issue:fact:source_date:{expense.id}", "FACT", "expense:source_date", "employee",
                    f"Khoản '{expense.id}' thiếu ngày phát sinh đã xác lập.",
                    "Bổ sung ngày chi có căn cứ (không dùng ngày nộp thay thế).",
                    expense.refs,
                ))
            else:
                days = (as_of - expense.source_date).days
                if days > policy.submission_window_days:
                    issues.append(_issue(
                        f"issue:policy:deadline:{expense.id}", "POLICY", "expense:deadline", "approver",
                        f"Khoản '{expense.id}' nộp sau {days} ngày (quá hạn {policy.submission_window_days} ngày).",
                        "Quyết định ngoại lệ cho khoản nộp quá hạn (đúng rule/khoản/scope).",
                        expense.refs,
                    ))
    return tuple(issues)
