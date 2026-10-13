"""Deterministic document classification and required-field gate for UC-03."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from invoice_referee.domain import (
    DocumentFieldImportance,
    DocumentFieldState,
    DocumentValidityIssue,
    DocumentValidityResult,
    DocumentValidityStatus,
    ExpenseDocumentFacts,
    ExpenseDocumentRole,
    ExpenseDocumentType,
    ORIGINAL_EXPENSE_DOCUMENT_TYPES,
    PaperSettlementFacts,
    SUPPORTING_EXPENSE_DOCUMENT_TYPES,
)


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    required_fields: tuple[str, ...]
    any_of_fields: tuple[tuple[str, ...], ...] = ()


# These rules belong to a document type, not to a filename or a hand-written
# OCR phrase.  They are shared by the confidence gate and the validity gate.
FIELD_IMPORTANCE_BY_TYPE: dict[ExpenseDocumentType, dict[str, DocumentFieldImportance]] = {
    ExpenseDocumentType.E_INVOICE: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "issuer_tax_code": DocumentFieldImportance.CRITICAL,
        "buyer_name": DocumentFieldImportance.CORROBORATABLE,
        "buyer_tax_code": DocumentFieldImportance.CRITICAL,
        "document_number": DocumentFieldImportance.CRITICAL,
        "template_number": DocumentFieldImportance.CRITICAL,
        "serial_number": DocumentFieldImportance.CRITICAL,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
        "line_items": DocumentFieldImportance.CORROBORATABLE,
    },
    ExpenseDocumentType.PAPER_RECEIPT: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
    },
    ExpenseDocumentType.HOTEL_RECEIPT: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
    },
    ExpenseDocumentType.TRANSPORT_TICKET: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "document_number": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
    },
    ExpenseDocumentType.COLLECTION_RECEIPT: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "buyer_name": DocumentFieldImportance.CORROBORATABLE,
        "document_number": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
    },
    ExpenseDocumentType.CARD_SLIP: {
        "issuer_name": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
        "transaction_reference": DocumentFieldImportance.CORROBORATABLE,
    },
    ExpenseDocumentType.PAYMENT_PROOF: {
        "payee_name": DocumentFieldImportance.CORROBORATABLE,
        "document_date": DocumentFieldImportance.CORROBORATABLE,
        "total_amount": DocumentFieldImportance.CRITICAL,
        "transaction_reference": DocumentFieldImportance.CORROBORATABLE,
        "transaction_status": DocumentFieldImportance.CRITICAL,
    },
}


def field_importance(
    document_type: ExpenseDocumentType,
    field_name: str,
) -> DocumentFieldImportance:
    return FIELD_IMPORTANCE_BY_TYPE.get(document_type, {}).get(
        field_name,
        DocumentFieldImportance.CORROBORATABLE,
    )


FIELD_LABELS = {
    "issuer_name": "tên đơn vị phát hành/người bán",
    "issuer_tax_code": "mã số thuế người bán",
    "buyer_name": "tên người mua/đơn vị mua",
    "buyer_tax_code": "mã số thuế người mua",
    "document_number": "số chứng từ",
    "template_number": "mẫu số hóa đơn",
    "serial_number": "ký hiệu hóa đơn",
    "document_date": "ngày chứng từ",
    "total_amount": "tổng số tiền",
    "line_items": "nội dung hàng hóa/dịch vụ",
    "payer_name": "người chuyển tiền",
    "payee_name": "người nhận tiền",
    "transaction_reference": "mã giao dịch",
    "transaction_status": "trạng thái giao dịch",
    "confirmation_present": "xác nhận hoặc chữ ký trên chứng từ",
    "purpose": "nội dung/mục đích hoàn ứng",
    "lines": "bảng các khoản chi",
    "advance_amount": "số tiền đã tạm ứng",
}


DOCUMENT_PROFILES: dict[ExpenseDocumentType, DocumentProfile] = {
    ExpenseDocumentType.E_INVOICE: DocumentProfile(
        required_fields=(
            "issuer_name",
            "issuer_tax_code",
            "buyer_name",
            "buyer_tax_code",
            "document_number",
            "template_number",
            "serial_number",
            "document_date",
            "total_amount",
            "line_items",
        )
    ),
    ExpenseDocumentType.PAPER_RECEIPT: DocumentProfile(
        required_fields=("issuer_name", "document_date", "total_amount")
    ),
    ExpenseDocumentType.HOTEL_RECEIPT: DocumentProfile(
        required_fields=("issuer_name", "document_date", "total_amount")
    ),
    ExpenseDocumentType.TRANSPORT_TICKET: DocumentProfile(
        required_fields=(
            "issuer_name",
            "document_number",
            "document_date",
            "total_amount",
        )
    ),
    ExpenseDocumentType.COLLECTION_RECEIPT: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_number",
            "document_date",
            "total_amount",
        )
    ),
    ExpenseDocumentType.CARD_SLIP: DocumentProfile(
        required_fields=(
            "issuer_name",
            "document_date",
            "total_amount",
            "transaction_reference",
        )
    ),
    ExpenseDocumentType.PAYMENT_PROOF: DocumentProfile(
        required_fields=(
            "payee_name",
            "document_date",
            "total_amount",
            "transaction_reference",
            "transaction_status",
        )
    ),
    ExpenseDocumentType.CONTRACT: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_number",
            "document_date",
        ),
        any_of_fields=(("total_amount", "line_items"),),
    ),
    ExpenseDocumentType.QUOTATION: DocumentProfile(
        required_fields=("issuer_name", "document_date", "total_amount", "line_items")
    ),
    ExpenseDocumentType.PURCHASE_ORDER: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_number",
            "document_date",
            "total_amount",
            "line_items",
        )
    ),
    ExpenseDocumentType.ACCEPTANCE_RECORD: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_date",
            "line_items",
            "confirmation_present",
        )
    ),
    ExpenseDocumentType.DELIVERY_NOTE: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_number",
            "document_date",
            "line_items",
            "confirmation_present",
        )
    ),
    ExpenseDocumentType.GOODS_RECEIPT: DocumentProfile(
        required_fields=(
            "issuer_name",
            "buyer_name",
            "document_number",
            "document_date",
            "line_items",
            "confirmation_present",
        )
    ),
    ExpenseDocumentType.SUPPLIER_CONFIRMATION: DocumentProfile(
        required_fields=(
            "issuer_name",
            "document_date",
            "confirmation_present",
        ),
        any_of_fields=(("total_amount", "line_items"),),
    ),
}

NON_BLOCKING_WARNING_MARKERS = (
    "lỗi chính tả",
    "sai chính tả",
    "thiếu dấu",
    "tên hàng",
    "mô tả hàng",
    "tên dịch vụ",
)

WARNING_FIELD_MARKERS = {
    "issuer_tax_code": ("mst bên bán", "mã số thuế bên bán", "mst người bán"),
    "buyer_tax_code": ("mst bên mua", "mã số thuế bên mua", "mst người mua"),
    "document_number": ("số hóa đơn", "số chứng từ"),
    "template_number": ("mẫu số",),
    "serial_number": ("ký hiệu",),
    "document_date": ("ngày hóa đơn", "ngày chứng từ"),
    "total_amount": (
        "tổng tiền",
        "tổng thanh toán",
        "thành tiền",
        "số tiền",
        "bằng chữ",
    ),
    "transaction_reference": ("mã giao dịch",),
    "transaction_status": ("trạng thái giao dịch",),
    "confirmation_present": ("chữ ký", "xác nhận"),
}

UNIVERSAL_BLOCKING_WARNING_MARKERS = (
    "giá trị pháp lý",
    "mâu thuẫn",
    "không khớp",
    "sai lệch",
)


def document_role_for_type(document_type: ExpenseDocumentType) -> ExpenseDocumentRole:
    if document_type in ORIGINAL_EXPENSE_DOCUMENT_TYPES:
        return ExpenseDocumentRole.ORIGINAL_EVIDENCE
    if document_type in SUPPORTING_EXPENSE_DOCUMENT_TYPES:
        return ExpenseDocumentRole.SUPPORTING_DOCUMENT
    return ExpenseDocumentRole.UNKNOWN


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    if isinstance(value, bool):
        return value
    return True


def _field_is_usable(facts: ExpenseDocumentFacts, field_name: str) -> bool:
    state = facts.field_states.get(field_name)
    if state in {
        DocumentFieldState.ABSENT,
        DocumentFieldState.UNREADABLE,
        DocumentFieldState.INVALID,
    }:
        return False
    return _has_value(getattr(facts, field_name, None))


def _normalized_tax_code(value: str) -> str:
    return re.sub(r"[\s.]", "", value.strip())


def _valid_vietnam_tax_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{10}(?:-\d{3})?", _normalized_tax_code(value)))


def _missing_issue(
    field_name: str,
    *,
    document_type: ExpenseDocumentType | None = None,
) -> DocumentValidityIssue:
    label = FIELD_LABELS.get(field_name, field_name)
    importance = (
        field_importance(document_type, field_name)
        if document_type is not None
        else DocumentFieldImportance.CRITICAL
    )
    return DocumentValidityIssue(
        code="REQUIRED_FIELD_UNCLEAR",
        field=field_name,
        message=f"Chưa xác định rõ {label}.",
        question=f"Vui lòng kiểm tra chứng từ và xác nhận {label}.",
        # Evidence fields may be corroborated after matching.  A missing core
        # field on the settlement request itself cannot: there is no reliable
        # source from which to reconstruct the employee's declaration.
        blocking=document_type is None,
        importance=importance,
        corroboratable=(
            document_type is not None
            and importance == DocumentFieldImportance.CORROBORATABLE
        ),
    )


def _owned_source_refs(document_id: str, source_refs: list[str]) -> list[str]:
    prefix = f"DOC:{document_id}"
    owned = [
        source_ref
        for source_ref in source_refs
        if source_ref == prefix or source_ref.startswith(f"{prefix}:")
    ]
    return list(dict.fromkeys(owned)) or [prefix]


def _warning_is_blocking(
    warning: str,
    *,
    document_type: ExpenseDocumentType | None,
    required_fields: set[str],
) -> bool:
    normalized = warning.strip().casefold()
    if any(marker in normalized for marker in NON_BLOCKING_WARNING_MARKERS):
        return False
    if "không phải hóa đơn gtgt" in normalized:
        return document_type == ExpenseDocumentType.E_INVOICE
    warning_fields = {
        field_name
        for field_name, markers in WARNING_FIELD_MARKERS.items()
        if any(marker in normalized for marker in markers)
    }
    if "mã số thuế" in normalized or "mst" in normalized:
        warning_fields.update({"issuer_tax_code", "buyer_tax_code"})
    if warning_fields:
        return bool(warning_fields.intersection(required_fields))
    return any(
        marker in normalized for marker in UNIVERSAL_BLOCKING_WARNING_MARKERS
    )


def validate_expense_document(
    facts: ExpenseDocumentFacts,
    *,
    company_tax_codes: frozenset[str] = frozenset(),
) -> DocumentValidityResult:
    """Validate one extracted evidence before it can enter any matching step."""

    document_type = facts.document_type
    role = document_role_for_type(document_type)
    source_refs = _owned_source_refs(facts.document_id, facts.source_refs)
    issues: list[DocumentValidityIssue] = []
    profile = DOCUMENT_PROFILES.get(document_type)

    if profile is None or role == ExpenseDocumentRole.UNKNOWN:
        issues.append(
            DocumentValidityIssue(
                code="DOCUMENT_TYPE_UNCLEAR",
                field="document_type",
                message="Chưa phân loại được chứng từ vào một loại được UC03 hỗ trợ.",
                question=(
                    "Vui lòng xác nhận đây là hóa đơn, bill, vé, bằng chứng thanh "
                    "toán hay tài liệu bổ sung nào."
                ),
            )
        )
        required_fields: list[str] = []
    else:
        required_fields = list(profile.required_fields)
        for field_name in profile.required_fields:
            if not _field_is_usable(facts, field_name):
                issues.append(_missing_issue(field_name, document_type=document_type))
        for alternatives in profile.any_of_fields:
            if not any(_field_is_usable(facts, name) for name in alternatives):
                labels = " hoặc ".join(FIELD_LABELS.get(name, name) for name in alternatives)
                issues.append(
                    DocumentValidityIssue(
                        code="REQUIRED_FIELD_GROUP_UNCLEAR",
                        field="|".join(alternatives),
                        message=f"Chưa xác định rõ {labels}.",
                        question=f"Vui lòng kiểm tra chứng từ và xác nhận {labels}.",
                        blocking=False,
                        importance=DocumentFieldImportance.CORROBORATABLE,
                        corroboratable=True,
                    )
                )

    if (
        facts.classification_confidence is not None
        and facts.classification_confidence < 0.60
        and facts.alternative_document_types
    ):
        alternatives = ", ".join(item.value for item in facts.alternative_document_types)
        issues.append(
            DocumentValidityIssue(
                code="DOCUMENT_TYPE_AMBIGUOUS",
                field="document_type",
                message=f"Loại chứng từ còn mơ hồ; các khả năng khác: {alternatives}.",
                question="Vui lòng xác nhận loại của chứng từ này.",
            )
        )

    if document_type == ExpenseDocumentType.E_INVOICE:
        for field_name in ("issuer_tax_code", "buyer_tax_code"):
            value = getattr(facts, field_name)
            if _has_value(value) and not _valid_vietnam_tax_code(str(value)):
                label = FIELD_LABELS[field_name]
                issues.append(
                    DocumentValidityIssue(
                        code="INVALID_TAX_CODE_FORMAT",
                        field=field_name,
                        message=f"{label.capitalize()} '{value}' không có định dạng MST hợp lệ.",
                        question=f"Vui lòng kiểm tra và xác nhận {label}.",
                    )
                )
        buyer_name = (facts.buyer_name or "").strip().casefold()
        if buyer_name in {"khách lẻ", "khach le", "người mua không lấy hóa đơn"}:
            issues.append(
                DocumentValidityIssue(
                    code="BUYER_IDENTITY_UNCLEAR",
                    field="buyer_name",
                    message="Thông tin bên mua chỉ ghi khách lẻ, chưa xác định là chi phí của công ty.",
                    question="Vui lòng xác nhận đơn vị mua hàng và mục đích sử dụng hóa đơn.",
                )
            )
        if (
            facts.buyer_tax_code
            and _field_is_usable(facts, "buyer_tax_code")
            and _valid_vietnam_tax_code(facts.buyer_tax_code)
            and company_tax_codes
        ):
            configured = {_normalized_tax_code(code) for code in company_tax_codes}
            if _normalized_tax_code(facts.buyer_tax_code) not in configured:
                issues.append(
                    DocumentValidityIssue(
                        code="BUYER_TAX_CODE_MISMATCH",
                        field="buyer_tax_code",
                        message=(
                            f"MST người mua {facts.buyer_tax_code} không thuộc danh sách "
                            "MST doanh nghiệp đã cấu hình."
                        ),
                        question="Vui lòng xác nhận hóa đơn này có thuộc doanh nghiệp hay không.",
                    )
                )

    if document_type == ExpenseDocumentType.PAYMENT_PROOF and facts.transaction_status:
        normalized_status = facts.transaction_status.strip().casefold()
        successful_markers = (
            "thành công",
            "hoàn tất",
            "đã chuyển",
            "successful",
            "completed",
            "success",
        )
        if not any(marker in normalized_status for marker in successful_markers):
            issues.append(
                DocumentValidityIssue(
                    code="PAYMENT_NOT_CONFIRMED",
                    field="transaction_status",
                    message=(
                        f"Trạng thái giao dịch '{facts.transaction_status}' chưa chứng minh "
                        "thanh toán đã hoàn tất."
                    ),
                    question="Vui lòng cung cấp giao dịch đã hoàn tất hoặc xác nhận trạng thái thanh toán.",
                )
            )

    for warning in facts.extraction_warnings:
        blocking = _warning_is_blocking(
            warning,
            document_type=document_type,
            required_fields=set(required_fields),
        )
        issues.append(
            DocumentValidityIssue(
                code="DOCUMENT_DATA_WARNING",
                message=(
                    f"Chứng từ có dữ liệu trọng yếu cần xác nhận: {warning}"
                    if blocking
                    else f"Chứng từ có thông tin cần lưu ý nhưng vẫn đủ đối chiếu: {warning}"
                ),
                question=(
                    "Vui lòng kiểm tra bản gốc và xác nhận dữ liệu được cảnh báo."
                    if blocking
                    else None
                ),
                blocking=blocking,
            )
        )

    blocking_issues = [issue for issue in issues if issue.blocking]
    outside_policy = any(
        issue.code == "BUYER_TAX_CODE_MISMATCH" for issue in blocking_issues
    )
    status = (
        DocumentValidityStatus.OUTSIDE_POLICY
        if outside_policy
        else DocumentValidityStatus.NEEDS_HUMAN
        if blocking_issues
        else DocumentValidityStatus.CLEAR
    )
    present_fields = [
        name
        for name in required_fields
        if _field_is_usable(facts, name)
    ]
    return DocumentValidityResult(
        document_id=facts.document_id,
        document_type=document_type.value,
        document_role=role,
        status=status,
        eligible_for_matching=status == DocumentValidityStatus.CLEAR,
        required_fields=required_fields,
        present_fields=present_fields,
        issues=issues,
        source_refs=source_refs,
    )


def validate_paper_settlement_document(
    facts: PaperSettlementFacts,
    *,
    advance_amount_required: bool,
) -> DocumentValidityResult:
    """Validate the paper request itself before matching its rows to evidence."""

    issues: list[DocumentValidityIssue] = []
    required_fields = ["purpose", "total_amount", "lines"]
    if advance_amount_required:
        required_fields.append("advance_amount")

    for field_name in required_fields:
        if not _has_value(getattr(facts, field_name, None)):
            issues.append(_missing_issue(field_name))

    for index, line in enumerate(facts.lines, start=1):
        if not _has_value(line.description):
            issues.append(
                DocumentValidityIssue(
                    code="PAPER_LINE_DESCRIPTION_UNCLEAR",
                    field=f"lines.{index}.description",
                    message=f"Dòng chi phí {index} chưa có nội dung rõ ràng.",
                    question=f"Vui lòng xác nhận nội dung dòng chi phí {index} trên đơn.",
                )
            )
        if line.amount is None or line.amount <= 0:
            issues.append(
                DocumentValidityIssue(
                    code="PAPER_LINE_AMOUNT_UNCLEAR",
                    field=f"lines.{index}.amount",
                    message=f"Dòng chi phí {index} chưa có số tiền hợp lệ.",
                    question=f"Vui lòng xác nhận số tiền dòng chi phí {index} trên đơn.",
                )
            )

    for warning in facts.extraction_warnings:
        blocking = _warning_is_blocking(
            warning,
            document_type=None,
            required_fields=set(required_fields),
        )
        issues.append(
            DocumentValidityIssue(
                code="PAPER_FORM_DATA_WARNING",
                message=(
                    f"Đơn giấy có dữ liệu trọng yếu cần xác nhận: {warning}"
                    if blocking
                    else f"Đơn giấy có thông tin cần lưu ý nhưng vẫn đủ xử lý: {warning}"
                ),
                question=(
                    "Vui lòng đối chiếu bản gốc và xác nhận dữ liệu đúng trên đơn giấy."
                    if blocking
                    else None
                ),
                blocking=blocking,
            )
        )

    source_refs = _owned_source_refs(facts.document_id, facts.source_refs)
    blocking_issues = [issue for issue in issues if issue.blocking]
    status = (
        DocumentValidityStatus.NEEDS_HUMAN
        if blocking_issues
        else DocumentValidityStatus.CLEAR
    )
    return DocumentValidityResult(
        document_id=facts.document_id,
        document_type="PAPER_SETTLEMENT_REQUEST",
        document_role=ExpenseDocumentRole.REQUEST_FORM,
        status=status,
        eligible_for_matching=status == DocumentValidityStatus.CLEAR,
        required_fields=required_fields,
        present_fields=[
            name for name in required_fields if _has_value(getattr(facts, name, None))
        ],
        issues=issues,
        source_refs=source_refs,
    )
