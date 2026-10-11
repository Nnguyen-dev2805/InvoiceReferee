"""Deterministic, explainable matching for OCR-derived paper settlement lines."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from invoice_referee.domain import (
    DecisionTarget,
    ExpenseDocumentFacts,
    ExpenseDocumentType,
    ORIGINAL_EXPENSE_DOCUMENT_TYPES,
    PaperSettlementFacts,
    SettlementFinding,
    UncertaintyType,
)

GENERIC_PARTY_TOKENS = {
    "co",
    "cong",
    "doanh",
    "nghiep",
    "phan",
    "tap",
    "toan",
    "trach",
    "nhiem",
    "huu",
    "han",
    "tnhh",
    "ty",
    "mua",
    "tu",
}


def _normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _party_similarity(line_description: str, issuer_name: str | None) -> float:
    line_tokens = {
        token
        for token in _normalize_text(line_description).split()
        if token not in GENERIC_PARTY_TOKENS and len(token) > 1
    }
    issuer_tokens = {
        token
        for token in _normalize_text(issuer_name).split()
        if token not in GENERIC_PARTY_TOKENS and len(token) > 1
    }
    if not line_tokens or not issuer_tokens:
        return 0.0
    return len(line_tokens & issuer_tokens) / min(
        len(line_tokens),
        len(issuer_tokens),
    )


def _semantic_similarity(line_description: str, fact: ExpenseDocumentFacts) -> float:
    evidence_text = " ".join(
        [
            fact.issuer_name or "",
            *(item.description for item in fact.line_items),
        ]
    )
    left = _normalize_text(line_description)
    right = _normalize_text(evidence_text)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def match_paper_evidence(
    paper: PaperSettlementFacts,
    evidence_facts: list[ExpenseDocumentFacts],
    evidence_documents: list[dict[str, Any]],
    *,
    fallback_no_evidence_reason: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[SettlementFinding]]:
    """Match documents to paper rows and emit findings without hiding ambiguity."""

    documents_by_id = {
        str(document["document_id"]): document for document in evidence_documents
    }
    items: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    findings: list[SettlementFinding] = []
    auto_linked_documents: set[str] = set()
    fallback_reason = (fallback_no_evidence_reason or "").strip()
    required_line_count = sum(line.requires_evidence for line in paper.lines)

    for position, line in enumerate(paper.lines, start=1):
        item_id = f"ITEM-{position:03d}"
        line_reason = (line.no_evidence_reason or "").strip()
        # A case-level explanation is safe to assign automatically only when
        # there is exactly one evidence-required row. Otherwise the accountant
        # must know which expense the explanation belongs to.
        reason = line_reason or (
            fallback_reason if required_line_count == 1 else ""
        )
        has_unmapped_fallback = bool(
            fallback_reason and not reason and line.requires_evidence
        )
        item_links: list[dict[str, Any]] = []
        normalized_refs = {
            normalized
            for reference in line.invoice_refs
            for normalized in [_normalize_identifier(reference)]
            if normalized
        }

        for fact in evidence_facts:
            document = documents_by_id.get(fact.document_id)
            if document is None:
                continue
            invoice_number = _normalize_identifier(fact.document_number)
            invoice_exact = bool(invoice_number and invoice_number in normalized_refs)
            amount_exact = bool(
                line.amount is not None
                and fact.total_amount is not None
                and abs(line.amount - fact.total_amount) <= Decimal("1")
            )
            semantic = _semantic_similarity(line.description, fact)
            party_similarity = _party_similarity(
                line.description,
                fact.issuer_name,
            )

            if invoice_exact:
                score = 1.0
                method = "INVOICE_NUMBER_EXACT"
                explanation = (
                    f"Số chứng từ {fact.document_number} trùng tham chiếu trên đơn."
                )
            else:
                score = (0.60 if amount_exact else 0.0) + min(semantic, 1.0) * 0.30
                if party_similarity >= 0.80:
                    score += 0.20
                elif party_similarity >= 0.50:
                    score += 0.12
                if fact.document_type not in ORIGINAL_EXPENSE_DOCUMENT_TYPES:
                    score += 0.10
                score = min(score, 1.0)
                method = "AMOUNT_AND_CONTENT"
                signals = []
                if amount_exact:
                    signals.append("số tiền")
                if semantic >= 0.45:
                    signals.append("nội dung")
                if party_similarity >= 0.50:
                    signals.append("đơn vị phát hành")
                explanation = (
                    "Khớp " + " và ".join(signals)
                    if signals
                    else "Không có định danh hoặc dữ kiện đủ mạnh để ghép."
                )

            if score < 0.50:
                continue
            status = "AUTO_LINK" if score >= 0.75 else "SUGGEST_LINK"
            if status == "AUTO_LINK" and fact.document_id in auto_linked_documents:
                status = "SUGGEST_LINK"
                explanation += (
                    " Evidence này đã được tự ghép với một khoản khác nên cần "
                    "kế toán xác nhận phân bổ."
                )
            item_links.append(
                {
                    "item_id": item_id,
                    "document_id": fact.document_id,
                    "link_status": status,
                    "link_method": method,
                    "score": score,
                    "explanation": explanation,
                    "filename": document["original_name"],
                    "total_amount": fact.total_amount,
                    "document_number": fact.document_number,
                    "document_type": fact.document_type,
                }
            )

        item_links.sort(key=lambda link: link["score"], reverse=True)
        auto_links = [link for link in item_links if link["link_status"] == "AUTO_LINK"]
        suggested_links = [
            link for link in item_links if link["link_status"] == "SUGGEST_LINK"
        ]
        links.extend(item_links)
        auto_linked_documents.update(link["document_id"] for link in auto_links)
        source_refs = [*line.source_refs]
        source_refs.extend(f"DOC:{link['document_id']}" for link in item_links)

        has_original_evidence = any(
            link["document_type"] in ORIGINAL_EXPENSE_DOCUMENT_TYPES
            for link in auto_links
        )
        has_alternative_evidence = bool(auto_links) and not has_original_evidence
        items.append(
            {
                "item_id": item_id,
                "category": "OTHER",
                "description": line.description,
                "claimed_amount": line.amount or Decimal("0"),
                "currency": "VND",
                "evidence_status": (
                    "ORIGINAL_EVIDENCE"
                    if has_original_evidence
                    else "ALTERNATIVE_EVIDENCE"
                    if has_alternative_evidence
                    else "NO_EVIDENCE"
                    if reason
                    else "ORIGINAL_EVIDENCE"
                ),
                "alternative_evidence_type": (
                    "PAYMENT_PROOF"
                    if has_alternative_evidence
                    and any(
                        link["document_type"] == ExpenseDocumentType.PAYMENT_PROOF
                        for link in auto_links
                    )
                    else "OTHER"
                    if has_alternative_evidence
                    else None
                ),
                "evidence_exception_reason": reason or None,
                "policy_exception_code": "PAPER_EVIDENCE_EXCEPTION" if reason else None,
                "evidence_names": [link["filename"] for link in auto_links],
            }
        )

        if line.amount is None:
            findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_LINE_AMOUNT_001",
                    status="FAIL",
                    message=(
                        f"Chưa xác định được số tiền của khoản "
                        f"'{line.description}' trên đơn giấy."
                    ),
                    uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                    target=DecisionTarget.ACCOUNTANT,
                    question=(
                        f"Vui lòng xác nhận số tiền của khoản "
                        f"'{line.description}'."
                    ),
                    source_refs=source_refs,
                )
            )

        if line.requires_evidence and not auto_links:
            if suggested_links:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_MATCH_001",
                        status="FAIL",
                        message=(
                            f"Khoản '{line.description}' có evidence gần phù hợp "
                            "nhưng chưa đủ chắc chắn để tự ghép."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question="Vui lòng xác nhận evidence thuộc khoản chi này.",
                        source_refs=source_refs,
                    )
                )
            elif reason:
                findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_EVIDENCE_EXCEPTION",
                        status="FAIL",
                        message=(
                            f"Khoản '{line.description}' yêu cầu evidence nhưng "
                            f"chỉ có giải trình: {reason}"
                        ),
                        uncertainty_type=UncertaintyType.OUTSIDE_POLICY,
                        target=DecisionTarget.ACCOUNTANT,
                        source_refs=source_refs,
                    )
                )
            else:
                detail = (
                    " Hồ sơ có giải trình chung nhưng chưa chỉ rõ giải trình "
                    "thuộc khoản nào."
                    if has_unmapped_fallback
                    else ""
                )
                findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_EVIDENCE_REQUIRED",
                        status="FAIL",
                        message=(
                            f"Khoản '{line.description}' ghi cần tài liệu đính kèm "
                            "nhưng chưa có evidence phù hợp hoặc giải trình riêng."
                            + detail
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.EMPLOYEE,
                        question=(
                            f"Vui lòng bổ sung evidence hoặc nêu rõ lý do cho khoản "
                            f"'{line.description}'."
                        ),
                        source_refs=source_refs,
                    )
                )
            continue

        if not line.requires_evidence and reason and not auto_links:
            findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_EVIDENCE_EXCEPTION",
                    status="FAIL",
                    message=(
                        f"Khoản '{line.description}' được ghi chú không có "
                        f"chứng từ: {reason}"
                    ),
                    uncertainty_type=UncertaintyType.OUTSIDE_POLICY,
                    target=DecisionTarget.ACCOUNTANT,
                    question=(
                        "Vui lòng xác nhận ghi chú trên đơn có đủ căn cứ để "
                        "chấp nhận khoản không có chứng từ này hay không."
                    ),
                    source_refs=source_refs,
                )
            )
            continue

        if auto_links:
            findings.append(
                SettlementFinding(
                    rule_id="SET_PAPER_MATCH_001",
                    status="PASS",
                    message=(
                        f"Đã ghép {len(auto_links)} evidence với khoản "
                        f"'{line.description}'."
                    ),
                    source_refs=source_refs,
                )
            )
            amount_links = [
                link
                for link in auto_links
                if link["document_type"] != ExpenseDocumentType.PAYMENT_PROOF
            ] or auto_links
            matched_total = sum(
                (
                    link["total_amount"]
                    for link in amount_links
                    if link["total_amount"] is not None
                ),
                start=Decimal("0"),
            )
            totals_complete = all(
                link["total_amount"] is not None for link in amount_links
            )
            if line.amount is not None and totals_complete and abs(
                matched_total - line.amount
            ) > Decimal("1"):
                findings.append(
                    SettlementFinding(
                        rule_id="SET_PAPER_AMOUNT_001",
                        status="FAIL",
                        message=(
                            f"Khoản '{line.description}' ghi {line.amount:,.0f} VND "
                            f"nhưng evidence đã ghép có tổng {matched_total:,.0f} VND."
                        ),
                        uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                        target=DecisionTarget.ACCOUNTANT,
                        question="Vui lòng xác nhận số tiền hoặc evidence của khoản này.",
                        source_refs=source_refs,
                    )
                )

    unmatched = [
        document
        for document in evidence_documents
        if document["document_id"] not in auto_linked_documents
        and not any(
            link["document_id"] == document["document_id"]
            and link["link_status"] == "SUGGEST_LINK"
            for link in links
        )
    ]
    if unmatched:
        findings.append(
            SettlementFinding(
                rule_id="SET_PAPER_UNMATCHED_001",
                status="FAIL",
                message=(
                    "Có evidence chưa xác định được khoản chi: "
                    + ", ".join(document["original_name"] for document in unmatched)
                ),
                uncertainty_type=UncertaintyType.FACTUAL_UNKNOWN,
                target=DecisionTarget.ACCOUNTANT,
                question="Vui lòng xác nhận evidence thuộc khoản chi nào.",
                source_refs=[
                    f"DOC:{document['document_id']}" for document in unmatched
                ],
            )
        )

    return items, links, findings
