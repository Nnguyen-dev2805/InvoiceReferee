"""Deterministic inventory consistency checks over LLM-extracted facts."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable

from invoice_referee.domain import (
    ConflictAnalysis,
    InventoryAnalysis,
    InventoryDocumentFacts,
    InventoryLineItemFact,
    RuleFinding,
)

PRIMARY_ROLE = "PRIMARY_DOCUMENT"
SUPPORTING_ROLE = "SUPPORTING_DOCUMENT"
MAX_RELATED_DATE_GAP_DAYS = 7
MONEY_TOLERANCE = Decimal("1")

UNIT_FACTORS: dict[str, tuple[str, Decimal]] = {
    "g": ("mass", Decimal("1")),
    "gram": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "kilogram": ("mass", Decimal("1000")),
    "tan": ("mass", Decimal("1000000")),
    "cai": ("each", Decimal("1")),
    "chiec": ("each", Decimal("1")),
    "don vi": ("each", Decimal("1")),
    "unit": ("each", Decimal("1")),
}


def _is_context_only_ref(value: str) -> bool:
    return value == "EMPLOYEE_CLAIM" or value.startswith(
        ("EMPLOYEE_CLAIM:", "TEXT_REPORT:")
    )


def _plain_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    without_marks = "".join(
        character for character in normalized if unicodedata.category(character) != "Mn"
    )
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", without_marks).lower().split())


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    candidate = value.strip().replace(" ", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", candidate):
        return None
    try:
        return Decimal(candidate)
    except InvalidOperation:
        return None


def _unit(value: str | None) -> tuple[str, Decimal] | None:
    normalized = _plain_text(value)
    if not normalized:
        return None
    return UNIT_FACTORS.get(normalized, (normalized, Decimal("1")))


def _source_refs(*items: InventoryLineItemFact) -> list[str]:
    refs = [ref for item in items for ref in item.source_refs]
    return list(dict.fromkeys(refs or [item.item_id for item in items]))


def _document_label(
    evidence_id: str,
    document_names: dict[str, str],
) -> str:
    return document_names.get(evidence_id, evidence_id)


def _date_value(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _transaction_findings(
    primary_documents: list[InventoryDocumentFacts],
    supporting_documents: list[InventoryDocumentFacts],
    document_names: dict[str, str],
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    primary_tax_codes = {
        _plain_text(document.supplier_tax_code)
        for document in primary_documents
        if document.supplier_tax_code
    }
    primary_dates = [
        parsed
        for document in primary_documents
        if (parsed := _date_value(document.document_date)) is not None
    ]

    for document in supporting_documents:
        supporting_tax_code = _plain_text(document.supplier_tax_code)
        if (
            supporting_tax_code
            and primary_tax_codes
            and supporting_tax_code not in primary_tax_codes
        ):
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_SUPPLIER_MISMATCH",
                    status="FAIL",
                    message=(
                        f"Nhà cung cấp trên {_document_label(document.evidence_id, document_names)} "
                        "không khớp với chứng từ chính. Vui lòng xác nhận hai nguồn "
                        "có thuộc cùng giao dịch không."
                    ),
                    source_refs=[document.evidence_id],
                )
            )

        supporting_date = _date_value(document.document_date)
        if supporting_date and primary_dates:
            nearest_gap = min(
                abs((supporting_date - primary_date).days)
                for primary_date in primary_dates
            )
            if nearest_gap > MAX_RELATED_DATE_GAP_DAYS:
                findings.append(
                    RuleFinding(
                        rule_id="INVENTORY_DATE_MISMATCH",
                        status="FAIL",
                        message=(
                            f"Ngày trên {_document_label(document.evidence_id, document_names)} "
                            "cách ngày chứng từ chính quá 7 ngày. Vui lòng xác nhận "
                            "hai nguồn có thuộc cùng lô hàng không."
                        ),
                        source_refs=[document.evidence_id],
                    )
                )

        if document.receipt_status in {"RECEIVED_PARTIAL", "PENDING", "REJECTED"}:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_RECEIPT_STATUS_CONFLICT",
                    status="FAIL",
                    message=(
                        f"{_document_label(document.evidence_id, document_names)} "
                        f"đang có trạng thái {document.receipt_status}, chưa thể xác nhận "
                        "đã nhận đủ hàng."
                    ),
                    source_refs=[document.evidence_id],
                )
            )
        elif document.receipt_status == "UNKNOWN":
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_RECEIPT_STATUS_UNKNOWN",
                    status="FAIL",
                    message=(
                        f"Chưa xác định được trạng thái nhận hàng trên "
                        f"{_document_label(document.evidence_id, document_names)}."
                    ),
                    source_refs=[document.evidence_id],
                )
            )
    return findings


def _comparison_findings(
    primary: InventoryLineItemFact,
    supporting: InventoryLineItemFact,
    supporting_source_id: str,
    document_names: dict[str, str],
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    source_label = _document_label(supporting_source_id, document_names)
    refs = _source_refs(primary, supporting)

    primary_quantity = _decimal(primary.quantity)
    supporting_quantity = _decimal(supporting.quantity)
    if primary_quantity is None or supporting_quantity is None:
        findings.append(
            RuleFinding(
                rule_id="INVENTORY_QUANTITY_UNKNOWN",
                status="FAIL",
                message=(
                    f"Chưa đủ số lượng để đối chiếu mặt hàng '{primary.raw_name}' "
                    f"giữa chứng từ chính và {source_label}."
                ),
                source_refs=refs,
            )
        )
    else:
        primary_unit = _unit(primary.unit)
        supporting_unit = _unit(supporting.unit)
        if primary_unit is None or supporting_unit is None:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_UNIT_UNKNOWN",
                    status="FAIL",
                    message=(
                        f"Chưa xác định được đơn vị tính của '{primary.raw_name}' để "
                        f"đối chiếu với {source_label}."
                    ),
                    source_refs=refs,
                )
            )
        elif primary_unit[0] != supporting_unit[0]:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_UNIT_MISMATCH",
                    status="FAIL",
                    message=(
                        f"Đơn vị của '{primary.raw_name}' không thống nhất: "
                        f"{primary.unit or 'không rõ'} và {supporting.unit or 'không rõ'}."
                    ),
                    source_refs=refs,
                )
            )
        elif primary_quantity * primary_unit[1] != supporting_quantity * supporting_unit[1]:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_QUANTITY_MISMATCH",
                    status="FAIL",
                    message=(
                        f"Số lượng '{primary.raw_name}' không khớp: chứng từ chính ghi "
                        f"{primary.quantity} {primary.unit or ''}, còn {source_label} ghi "
                        f"{supporting.quantity} {supporting.unit or ''}."
                    ),
                    source_refs=refs,
                )
            )

    for rule_id, label, primary_raw, supporting_raw in (
        (
            "INVENTORY_UNIT_PRICE_MISMATCH",
            "Đơn giá",
            primary.unit_price,
            supporting.unit_price,
        ),
        (
            "INVENTORY_LINE_AMOUNT_MISMATCH",
            "Thành tiền",
            primary.line_amount,
            supporting.line_amount,
        ),
    ):
        if primary_raw is None or supporting_raw is None:
            continue
        primary_value = _decimal(primary_raw)
        supporting_value = _decimal(supporting_raw)
        if primary_value is None or supporting_value is None:
            findings.append(
                RuleFinding(
                    rule_id=rule_id.replace("MISMATCH", "UNKNOWN"),
                    status="FAIL",
                    message=(
                        f"Chưa đọc được {label.lower()} của '{primary.raw_name}' "
                        "ở dạng có thể đối chiếu."
                    ),
                    source_refs=refs,
                )
            )
        elif abs(primary_value - supporting_value) > MONEY_TOLERANCE:
            findings.append(
                RuleFinding(
                    rule_id=rule_id,
                    status="FAIL",
                    message=(
                        f"{label} của '{primary.raw_name}' không khớp: chứng từ chính "
                        f"ghi {primary_raw}, còn {source_label} ghi {supporting_raw}."
                    ),
                    source_refs=refs,
                )
            )
    return findings


def _unique_facts(
    facts: Iterable[InventoryDocumentFacts],
) -> tuple[dict[str, InventoryDocumentFacts], set[str]]:
    by_id: dict[str, InventoryDocumentFacts] = {}
    duplicates: set[str] = set()
    for fact in facts:
        if fact.evidence_id in by_id:
            duplicates.add(fact.evidence_id)
        by_id[fact.evidence_id] = fact
    return by_id, duplicates


def evaluate_inventory_consistency(
    analysis: InventoryAnalysis | ConflictAnalysis,
    document_roles: dict[str, str],
    document_names: dict[str, str],
) -> list[RuleFinding]:
    """Evaluate inventory facts without allowing the LLM to decide the result."""

    facts_by_id, duplicate_ids = _unique_facts(analysis.document_facts)
    expected_ids = set(document_roles)
    findings: list[RuleFinding] = []

    if duplicate_ids or set(facts_by_id) != expected_ids:
        coverage_findings: list[RuleFinding] = []
        for evidence_id in sorted(expected_ids.difference(facts_by_id)):
            role_label = (
                "chứng từ chính"
                if document_roles[evidence_id] == PRIMARY_ROLE
                else "chứng từ hỗ trợ"
            )
            coverage_findings.append(
                RuleFinding(
                    rule_id="INVENTORY_EXTRACTION_COVERAGE_INVALID",
                    status="ERROR",
                    message=(
                        f"Policy kiểm kê chưa trích xuất {role_label} "
                        f"'{_document_label(evidence_id, document_names)}'. Các "
                        "thông tin chưa có gồm: loại chứng từ; nhà cung cấp và "
                        "MST; ngày chứng từ; trạng thái nhận hàng; danh sách hàng "
                        "hóa với tên, số lượng, đơn vị, đơn giá và thành tiền."
                    ),
                    source_refs=[evidence_id],
                )
            )
        for evidence_id in sorted(set(facts_by_id).difference(expected_ids)):
            coverage_findings.append(
                RuleFinding(
                    rule_id="INVENTORY_EXTRACTION_COVERAGE_INVALID",
                    status="ERROR",
                    message=(
                        "Policy kiểm kê trả dữ liệu cho một nguồn không tồn tại "
                        f"trong hồ sơ: {evidence_id}."
                    ),
                    source_refs=[evidence_id],
                )
            )
        for evidence_id in sorted(duplicate_ids):
            coverage_findings.append(
                RuleFinding(
                    rule_id="INVENTORY_EXTRACTION_COVERAGE_INVALID",
                    status="ERROR",
                    message=(
                        "Policy kiểm kê trả trùng dữ liệu cho "
                        f"'{_document_label(evidence_id, document_names)}'."
                    ),
                    source_refs=[evidence_id],
                )
            )
        return coverage_findings

    if analysis.applicability == "UNKNOWN":
        return [
            RuleFinding(
                rule_id="INVENTORY_APPLICABILITY_UNKNOWN",
                status="FAIL",
                message=(
                    "Chưa xác định được hồ sơ có phát sinh nghiệp vụ nhận hoặc "
                    "kiểm kê hàng hóa hay không."
                ),
                source_refs=sorted(expected_ids),
            )
        ]
    if analysis.applicability == "NOT_APPLICABLE":
        return [
            RuleFinding(
                rule_id="INVENTORY_NOT_APPLICABLE",
                status="PASS",
                message="Hồ sơ không phát sinh nghiệp vụ cần đối chiếu nhập kho.",
                source_refs=sorted(expected_ids),
            )
        ]

    for conflict in getattr(analysis, "potential_conflicts", []):
        if any(_is_context_only_ref(ref) for ref in conflict.source_refs):
            continue
        allowed_refs = expected_ids
        invalid_refs = set(conflict.source_refs).difference(allowed_refs)
        if invalid_refs:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_CONFLICT_REFERENCE_INVALID",
                    status="ERROR",
                    message=(
                        "Conflict Agent dẫn chiếu nguồn không tồn tại trong hồ sơ."
                    ),
                    source_refs=sorted(invalid_refs),
                )
            )
            continue
        findings.append(
            RuleFinding(
                rule_id=f"INVENTORY_SEMANTIC_CONFLICT_{conflict.code}",
                status="FAIL",
                message=conflict.human_question or conflict.description,
                source_refs=conflict.source_refs,
            )
        )

    primary_documents = [
        facts_by_id[evidence_id]
        for evidence_id, role in document_roles.items()
        if role == PRIMARY_ROLE
    ]
    formal_supporting_documents = [
        facts_by_id[evidence_id]
        for evidence_id, role in document_roles.items()
        if role == SUPPORTING_ROLE
    ]
    supporting_documents = [*formal_supporting_documents]

    if not primary_documents or not supporting_documents:
        return [
            RuleFinding(
                rule_id="INVENTORY_SOURCE_REQUIRED",
                status="FAIL",
                message=(
                    "Khoản mua hàng chưa có phiếu nhập kho, phiếu kiểm kê, biên "
                    "bản giao nhận hoặc report đính kèm đủ rõ để đối chiếu."
                ),
                source_refs=sorted(expected_ids),
            )
        ]

    findings.extend(
        _transaction_findings(primary_documents, supporting_documents, document_names)
    )

    primary_items = {
        item.item_id: (document.evidence_id, item)
        for document in primary_documents
        for item in document.items
    }
    all_supporting_items = {
        item.item_id: (document.evidence_id, item)
        for document in supporting_documents
        for item in document.items
    }
    required_supporting_documents = formal_supporting_documents
    required_supporting_ids = {
        item.item_id
        for document in required_supporting_documents
        for item in document.items
    }
    if not primary_items or not required_supporting_ids:
        findings.append(
            RuleFinding(
                rule_id="INVENTORY_ITEMS_REQUIRED",
                status="FAIL",
                message="Chưa đủ danh sách hàng hóa ở hai nguồn để đối chiếu từng dòng.",
                source_refs=sorted(expected_ids),
            )
        )
        return findings

    matches: dict[str, list[str]] = {}
    used_supporting_ids: set[str] = set()
    context_item_ids = {
        item.item_id
        for item in (analysis.text_report.items if analysis.text_report else [])
    }
    for match in analysis.suggested_item_matches:
        if not match.semantic_match:
            continue
        if (
            match.supporting_item_id in context_item_ids
            or _is_context_only_ref(match.supporting_item_id)
        ):
            continue
        if (
            match.primary_item_id not in primary_items
            or match.supporting_item_id not in all_supporting_items
            or match.supporting_item_id in used_supporting_ids
        ):
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_ITEM_MAPPING_INVALID",
                    status="ERROR",
                    message="Conflict Agent trả ánh xạ dòng hàng không hợp lệ.",
                    source_refs=[match.primary_item_id, match.supporting_item_id],
                )
            )
            continue
        matches.setdefault(match.primary_item_id, []).append(match.supporting_item_id)
        used_supporting_ids.add(match.supporting_item_id)

    for primary_id, (_, primary_item) in primary_items.items():
        if any(
            supporting_id in required_supporting_ids
            for supporting_id in matches.get(primary_id, [])
        ):
            continue
        candidates = [
            supporting_id
            for supporting_id, (_, supporting_item) in all_supporting_items.items()
            if supporting_id in required_supporting_ids
            if supporting_id not in used_supporting_ids
            and _plain_text(primary_item.raw_name) == _plain_text(supporting_item.raw_name)
        ]
        if len(candidates) == 1:
            matches.setdefault(primary_id, []).append(candidates[0])
            used_supporting_ids.add(candidates[0])

    for primary_id, (_, primary_item) in primary_items.items():
        supporting_ids = matches.get(primary_id, [])
        required_matches = [
            supporting_id
            for supporting_id in supporting_ids
            if supporting_id in required_supporting_ids
        ]
        if not required_matches:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_PRIMARY_ITEM_UNMATCHED",
                    status="FAIL",
                    message=(
                        f"Chưa tìm thấy dòng nhận hàng tương ứng cho "
                        f"'{primary_item.raw_name}'."
                    ),
                    source_refs=primary_item.source_refs or [primary_id],
                )
            )
            continue
        for supporting_id in supporting_ids:
            supporting_source_id, supporting_item = all_supporting_items[supporting_id]
            findings.extend(
                _comparison_findings(
                    primary_item,
                    supporting_item,
                    supporting_source_id,
                    document_names,
                )
            )

    for supporting_id, (_, supporting_item) in all_supporting_items.items():
        if supporting_id not in required_supporting_ids:
            continue
        if supporting_id not in used_supporting_ids:
            findings.append(
                RuleFinding(
                    rule_id="INVENTORY_SUPPORTING_ITEM_UNMATCHED",
                    status="FAIL",
                    message=(
                        f"Nguồn nhận hàng có dòng '{supporting_item.raw_name}' nhưng "
                        "không tìm thấy dòng tương ứng trên chứng từ chính."
                    ),
                    source_refs=supporting_item.source_refs or [supporting_id],
                )
            )

    if not any(finding.status in {"FAIL", "ERROR"} for finding in findings):
        findings.append(
            RuleFinding(
                rule_id="INVENTORY_CONSISTENCY",
                status="PASS",
                message=(
                    "Hàng hóa, số lượng và các giá trị có thể đối chiếu thống nhất "
                    "giữa chứng từ chính và nguồn nhận hàng."
                ),
                source_refs=sorted(expected_ids),
            )
        )
    return findings
