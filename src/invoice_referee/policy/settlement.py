"""Deterministic MVP policy for UC-03 expense settlements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from invoice_referee.domain import (
    DecisionTarget,
    ExpenseCategory,
    SettlementDraft,
    SettlementFinding,
    SettlementType,
    SubmissionSourceType,
    UncertaintyType,
)


@dataclass(frozen=True, slots=True)
class SettlementPolicyConfig:
    policy_id: str = "DEMO-EXPENSE-2026"
    policy_version: str = "1.0"
    data_classification: str = "SYNTHETIC"
    submission_window_days: int = 30
    authority_amount_vnd: Decimal = Decimal("50000000")
    category_limits: dict[ExpenseCategory, Decimal] = field(
        default_factory=lambda: {
            ExpenseCategory.CLIENT_MEAL: Decimal("5000000"),
            ExpenseCategory.TAXI: Decimal("2000000"),
        }
    )
    prohibited_categories: frozenset[ExpenseCategory] = frozenset(
        {ExpenseCategory.PERSONAL}
    )


def _pass(rule_id: str, message: str) -> SettlementFinding:
    return SettlementFinding(rule_id=rule_id, status="PASS", message=message)


def evaluate_settlement_policy(
    draft: SettlementDraft,
    *,
    has_paper_form: bool,
    duplicate_document_names: list[str] | None = None,
    today: date | None = None,
    config: SettlementPolicyConfig | None = None,
) -> list[SettlementFinding]:
    """Evaluate facts known at intake without asking an LLM to make policy."""

    policy = config or SettlementPolicyConfig()
    current_date = today or date.today()
    findings: list[SettlementFinding] = []

    if draft.business_context.purpose.strip():
        findings.append(_pass("SET_CONTEXT_001", "Đã có mục đích khoản chi."))
    else:
        findings.append(
            SettlementFinding(
                rule_id="SET_CONTEXT_001",
                status="FAIL",
                message="Hồ sơ chưa nêu mục đích phục vụ công việc.",
                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                target=DecisionTarget.EMPLOYEE,
                question="Vui lòng bổ sung mục đích công việc của các khoản chi.",
            )
        )

    if draft.source_type == SubmissionSourceType.PAPER_SCAN and not has_paper_form:
        findings.append(
            SettlementFinding(
                rule_id="SET_INPUT_001",
                status="FAIL",
                message="Hồ sơ dạng giấy chưa có giấy đề nghị hoàn ứng/quyết toán.",
                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                target=DecisionTarget.EMPLOYEE,
                question="Vui lòng tải giấy đề nghị hoàn ứng/quyết toán đã lập.",
            )
        )
    else:
        findings.append(_pass("SET_INPUT_001", "Đã có dữ liệu đề nghị chính."))

    if draft.settlement_type == SettlementType.ADVANCE_SETTLEMENT:
        if not draft.advance_id or draft.allocated_advance_amount <= 0:
            findings.append(
                SettlementFinding(
                    rule_id="SET_ADV_001",
                    status="FAIL",
                    message="Hồ sơ hoàn ứng chưa xác định đủ khoản tạm ứng liên quan.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.EMPLOYEE,
                    question=(
                        "Vui lòng bổ sung mã khoản tạm ứng và số tiền tạm ứng "
                        "được phân bổ cho hồ sơ này."
                    ),
                )
            )
        else:
            findings.append(_pass("SET_ADV_001", "Đã khai báo khoản tạm ứng."))
    elif draft.advance_id or draft.allocated_advance_amount != 0:
        findings.append(
            SettlementFinding(
                rule_id="SET_ADV_001",
                status="FAIL",
                message="Hồ sơ nhân viên tự chi lại đang gắn thông tin tạm ứng.",
                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                target=DecisionTarget.EMPLOYEE,
                question=(
                    "Vui lòng xác nhận đây là hoàn trả chi phí nhân viên tự chi "
                    "hay quyết toán một khoản tạm ứng."
                ),
            )
        )
    else:
        findings.append(_pass("SET_ADV_001", "Loại quyết toán phù hợp dữ liệu tạm ứng."))

    for item in draft.expense_items:
        item_ref = f"FORM:EXPENSE_ITEM:{item.item_id}"
        if not item.evidence_names and not item.policy_exception_code:
            findings.append(
                SettlementFinding(
                    rule_id="SET_DOC_001",
                    status="FAIL",
                    message=f"Khoản '{item.description}' chưa có chứng từ.",
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.EMPLOYEE,
                    question=(
                        f"Vui lòng bổ sung chứng từ cho khoản '{item.description}' "
                        "hoặc nêu mã ngoại lệ được phép."
                    ),
                    source_refs=[item_ref],
                )
            )

        if item.category in policy.prohibited_categories:
            findings.append(
                SettlementFinding(
                    rule_id="SET_CATEGORY_001",
                    status="FAIL",
                    message=f"Khoản '{item.description}' thuộc danh mục chi cá nhân.",
                    uncertainty_type=UncertaintyType.OUTSIDE_POLICY,
                    target=DecisionTarget.ACCOUNTANT,
                    source_refs=[item_ref],
                )
            )

        category_limit = policy.category_limits.get(item.category)
        if category_limit is not None and item.claimed_amount > category_limit:
            findings.append(
                SettlementFinding(
                    rule_id="SET_LIMIT_001",
                    status="FAIL",
                    message=(
                        f"Khoản '{item.description}' trị giá {item.claimed_amount:,.0f} "
                        f"VND vượt hạn mức demo {category_limit:,.0f} VND."
                    ),
                    uncertainty_type=UncertaintyType.OUTSIDE_POLICY,
                    target=DecisionTarget.CHIEF_ACCOUNTANT,
                    source_refs=[item_ref],
                )
            )

        if item.expense_date:
            age_days = (current_date - item.expense_date).days
            if age_days > policy.submission_window_days:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_DEADLINE_001",
                        status="FAIL",
                        message=(
                            f"Khoản '{item.description}' được nộp sau "
                            f"{policy.submission_window_days} ngày theo policy demo."
                        ),
                        uncertainty_type=UncertaintyType.OUTSIDE_POLICY,
                        target=DecisionTarget.ACCOUNTANT,
                        source_refs=[item_ref],
                    )
                )

    if not any(
        item.category in policy.prohibited_categories
        for item in draft.expense_items
    ):
        findings.append(_pass("SET_CATEGORY_001", "Không có danh mục bị cấm rõ ràng."))
    if not any(
        policy.category_limits.get(item.category) is not None
        and item.claimed_amount > policy.category_limits[item.category]
        for item in draft.expense_items
    ):
        findings.append(
            _pass("SET_LIMIT_001", "Các khoản nằm trong hạn mức danh mục demo.")
        )

    if draft.currency == "VND" and draft.claimed_total > policy.authority_amount_vnd:
        findings.append(
            SettlementFinding(
                rule_id="SET_AUTH_001",
                status="FAIL",
                message=(
                    f"Tổng hồ sơ {draft.claimed_total:,.0f} VND vượt thẩm quyền "
                    f"demo {policy.authority_amount_vnd:,.0f} VND."
                ),
                uncertainty_type=UncertaintyType.BEYOND_AUTHORITY,
                target=DecisionTarget.DIRECTOR,
            )
        )
    else:
        findings.append(_pass("SET_AUTH_001", "Tổng hồ sơ trong thẩm quyền demo."))

    duplicates = duplicate_document_names or []
    if duplicates:
        findings.append(
            SettlementFinding(
                rule_id="SET_DUP_001",
                status="FAIL",
                message="Phát hiện chứng từ trùng hồ sơ đã lưu: " + ", ".join(duplicates),
                uncertainty_type=UncertaintyType.SUSPICIOUS,
                target=DecisionTarget.ACCOUNTANT,
            )
        )
    else:
        findings.append(
            _pass("SET_DUP_001", "Không phát hiện file chứng từ trùng lịch sử.")
        )

    return findings

