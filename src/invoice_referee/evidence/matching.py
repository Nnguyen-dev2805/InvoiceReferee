"""Hoangha evidence matching, ported and evidence-only (contracts §12.4; E6).

Ported from Hoangha `application/paper_evidence_matching.py` at pinned revision
`1ee33487…`: identifier/text normalization, amount/semantic/party scoring,
`<0.50` omitted / `[0.50,0.75)` suggestion / `>=0.75` auto-link, and stable
second-row demotion. The final projection differs deliberately: original totals
sum only original documents, a missing amount stays `None` (never a zero
fallback), and a source-stated reason is metadata — not a policy exception.
A second-row reuse is allowed only with an explicit amount-bounded allocation.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentAnalysis,
    DocumentLine,
    DocumentRowMatch,
    EvidenceLink,
    EvidenceMatchFinding,
    EvidenceMatchingResult,
    FieldCandidate,
)

ORIGINAL_EXPENSE_DOCUMENT_TYPES = frozenset(
    {"E_INVOICE", "PAPER_RECEIPT", "TRANSPORT_TICKET", "HOTEL_RECEIPT", "COLLECTION_RECEIPT"}
)

GENERIC_PARTY_TOKENS = {
    "co", "cong", "doanh", "nghiep", "phan", "tap", "toan", "trach",
    "nhiem", "huu", "han", "tnhh", "ty", "mua", "tu",
}

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TAXI", ("taxi", "grab", "be car", "xe om")),
    ("CLIENT_MEAL", ("an uong", "nha hang", "tiep khach", "cafe")),
    ("HOTEL", ("khach san", "hotel", "luu tru")),
    ("TRAVEL", ("ve may bay", "ve tau", "ve xe", "di chuyen")),
    ("OFFICE_SUPPLIES", ("van phong pham", "giay in", "but", "muc in")),
)


def _normalize_identifier(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _party_similarity(line_description: str, issuer_name: str | None) -> float:
    line_tokens = {
        t for t in _normalize_text(line_description).split()
        if t not in GENERIC_PARTY_TOKENS and len(t) > 1
    }
    issuer_tokens = {
        t for t in _normalize_text(issuer_name).split()
        if t not in GENERIC_PARTY_TOKENS and len(t) > 1
    }
    if not line_tokens or not issuer_tokens:
        return 0.0
    return len(line_tokens & issuer_tokens) / min(len(line_tokens), len(issuer_tokens))


def _semantic_similarity(line_description: str, document: DocumentAnalysis) -> float:
    evidence_text = " ".join(
        [document_field(document, "issuer_name") or ""]
        + [_line_description(line) for line in document.line_items]
    )
    left = _normalize_text(line_description)
    right = _normalize_text(evidence_text)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _infer_category(description: str, documents: tuple[DocumentAnalysis, ...]) -> str:
    text = _normalize_text(
        " ".join([description, *[_line_description(line) for d in documents for line in d.line_items]])
    )
    for category, tokens in _CATEGORY_KEYWORDS:
        if any(token in text for token in tokens):
            return category
    return "OTHER"


def document_field(document: DocumentAnalysis, field: str):
    for candidate in document.fields:
        if candidate.field == field and candidate.state == "FOUND":
            return candidate.value
    return None


def _line_field(line: DocumentLine, field: str):
    for candidate in line.fields:
        if candidate.field == field and candidate.state == "FOUND":
            return candidate.value
    return None


def _line_description(line: DocumentLine) -> str:
    value = _line_field(line, "description")
    return str(value) if value is not None else ""


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _refs(document: DocumentAnalysis) -> tuple[EvidenceRef, ...]:
    return document.refs


def match_paper_evidence(
    paper: DocumentAnalysis,
    documents: tuple[DocumentAnalysis, ...],
) -> EvidenceMatchingResult:
    """Match documents to settlement-form rows (pure, evidence-only)."""
    if paper.document_type != "SETTLEMENT_FORM":
        raise ValueError("match_paper_evidence requires a SETTLEMENT_FORM paper")
    matchable = tuple(d for d in documents if d.document_type != "UNKNOWN")

    links: list[EvidenceLink] = []
    rows: list[DocumentRowMatch] = []
    findings: list[EvidenceMatchFinding] = []
    auto_linked: set[str] = set()
    allocated: dict[str, Decimal] = {}

    for position, row in enumerate(paper.line_items, start=1):
        item_id = f"ITEM-{position:03d}"
        description = _line_description(row)
        amount = _as_decimal(_line_field(row, "amount"))
        reason = _line_field(row, "no_evidence_reason")
        refs_value = _line_field(row, "invoice_refs")
        normalized_refs = {
            _normalize_identifier(r) for r in (refs_value or ()) if _normalize_identifier(r)
        }

        row_links: list[EvidenceLink] = []
        for document in matchable:
            number = document_field(document, "document_number")
            total = _as_decimal(document_field(document, "total_amount"))
            issuer = document_field(document, "issuer_name")
            invoice_number = _normalize_identifier(str(number) if number is not None else None)
            invoice_exact = bool(invoice_number and invoice_number in normalized_refs)
            amount_exact = bool(
                amount is not None and total is not None and abs(amount - total) <= Decimal("1")
            )
            semantic = _semantic_similarity(description, document)
            party = _party_similarity(description, str(issuer) if issuer is not None else None)

            if invoice_exact:
                score = Decimal("1")
                method = "INVOICE_NUMBER_EXACT"
                explanation = f"Số chứng từ {number} trùng tham chiếu trên đơn."
            else:
                score = (Decimal("0.60") if amount_exact else Decimal("0")) + Decimal(
                    str(min(semantic, 1.0))
                ) * Decimal("0.30")
                if party >= 0.80:
                    score += Decimal("0.20")
                elif party >= 0.50:
                    score += Decimal("0.12")
                if document.document_type not in ORIGINAL_EXPENSE_DOCUMENT_TYPES:
                    score += Decimal("0.10")
                score = min(score, Decimal("1"))
                method = "AMOUNT_AND_CONTENT"
                signals = []
                if amount_exact:
                    signals.append("số tiền")
                if semantic >= 0.45:
                    signals.append("nội dung")
                if party >= 0.50:
                    signals.append("đơn vị phát hành")
                explanation = "Khớp " + " và ".join(signals) if signals else "Không đủ dữ kiện để ghép."

            if score < Decimal("0.50"):
                continue
            status = "AUTO_LINK" if score >= Decimal("0.75") else "SUGGEST_LINK"
            allocated_amount = total if status == "AUTO_LINK" else None
            if status == "AUTO_LINK":
                # An explicit-ref match consumes the row's stated amount; any
                # other auto-link consumes the whole source total. Every
                # explicit allocation must be amount-bounded by the source
                # total, including the first use.
                already = allocated.get(document.document_id)
                if invoice_exact and amount is not None:
                    over = total is not None and (already or Decimal("0")) + amount > total
                    if over:
                        status = "SUGGEST_LINK"
                        allocated_amount = None
                        explanation += " Phân bổ vượt giá trị chứng từ; cần xác nhận."
                    else:
                        allocated[document.document_id] = (
                            already or Decimal("0")
                        ) + amount
                        allocated_amount = amount
                elif already is None:
                    allocated[document.document_id] = total if total is not None else Decimal("0")
                else:
                    status = "SUGGEST_LINK"
                    allocated_amount = None
                    explanation += " Evidence đã ghép khoản khác; cần xác nhận phân bổ."
            row_links.append(
                EvidenceLink(
                    item_id=item_id,
                    source_id=document.source_id,
                    document_id=document.document_id,
                    status=status,  # type: ignore[arg-type]
                    method=method,  # type: ignore[arg-type]
                    score=score,
                    allocated_amount=allocated_amount,
                    explanation=explanation,
                    refs=_refs(document),
                )
            )

        row_links.sort(key=lambda link: link.score, reverse=True)
        links.extend(row_links)
        auto_links = [link for link in row_links if link.status == "AUTO_LINK"]
        auto_linked.update(link.document_id for link in auto_links)

        has_original = any(
            next((d for d in matchable if d.document_id == link.document_id), None).document_type
            in ORIGINAL_EXPENSE_DOCUMENT_TYPES
            for link in auto_links
            if next((d for d in matchable if d.document_id == link.document_id), None)
        )
        has_alternative = bool(auto_links) and not has_original
        original_total = sum(
            (link.allocated_amount for link in auto_links
             if link.allocated_amount is not None
             and next((d for d in matchable if d.document_id == link.document_id), None).document_type
             in ORIGINAL_EXPENSE_DOCUMENT_TYPES),
            start=Decimal("0"),
        )
        original_total_value = original_total if has_original else None

        if has_original:
            evidence_status = "ORIGINAL_EVIDENCE"
        elif has_alternative:
            evidence_status = "ALTERNATIVE_EVIDENCE"
        else:
            evidence_status = "NO_EVIDENCE"
        alternative_type = "PAYMENT_PROOF" if has_alternative else None

        rows.append(
            DocumentRowMatch(
                item_id=item_id,
                paper_amount=amount,
                category_candidate=_infer_category(description, tuple(
                    d for d in matchable if d.document_id in {link.document_id for link in auto_links}
                )),  # type: ignore[arg-type]
                evidence_status=evidence_status,  # type: ignore[arg-type]
                alternative_evidence_type=alternative_type,  # type: ignore[arg-type]
                matched_document_date=None,
                original_total=original_total_value,
                allocated_total=original_total_value,
                no_evidence_reason=str(reason) if reason is not None else None,
                refs=paper.refs,
            )
        )

        if amount is None:
            findings.append(
                EvidenceMatchFinding(
                    code="SET_PAPER_LINE_AMOUNT_001",
                    status="UNRESOLVED",
                    message=f"Chưa xác định số tiền của khoản '{description}'.",
                    refs=paper.refs,
                )
            )
        if auto_links:
            findings.append(
                EvidenceMatchFinding(
                    code="SET_PAPER_MATCH_001",
                    status="PASS",
                    message=f"Đã ghép {len(auto_links)} evidence với khoản '{description}'.",
                    refs=paper.refs,
                )
            )
            if (
                amount is not None
                and original_total_value is not None
                and abs(original_total_value - amount) > Decimal("1")
            ):
                findings.append(
                    EvidenceMatchFinding(
                        code="SET_PAPER_AMOUNT_001",
                        status="UNRESOLVED",
                        message=(
                            f"Khoản '{description}' ghi {amount} nhưng evidence gốc có "
                            f"tổng {original_total_value}."
                        ),
                        refs=paper.refs,
                    )
                )
        else:
            findings.append(
                EvidenceMatchFinding(
                    code="SET_PAPER_EVIDENCE_REQUIRED",
                    status="UNRESOLVED",
                    message=f"Khoản '{description}' chưa có evidence phù hợp.",
                    refs=paper.refs,
                )
            )

    unmatched = tuple(
        d.source_id
        for d in matchable
        if d.document_id not in auto_linked
        and not any(link.document_id == d.document_id for link in links)
    )
    if unmatched:
        findings.append(
            EvidenceMatchFinding(
                code="SET_PAPER_UNMATCHED_001",
                status="UNRESOLVED",
                message=f"Có {len(unmatched)} evidence chưa ghép được khoản chi.",
                refs=paper.refs,
            )
        )
    return EvidenceMatchingResult(
        links=tuple(links),
        rows=tuple(rows),
        findings=tuple(findings),
        unmatched_source_ids=unmatched,
    )


async def resolve_evidence_suggestions(
    result: EvidenceMatchingResult,
    documents: tuple[DocumentAnalysis, ...],
    *,
    llm: object,
    budget: RunBudget,
) -> EvidenceMatchingResult:
    """One batched suggestion-resolution call (contracts §12.4; plan E6 Step 9).

    The model may promote only an existing SUGGEST_LINK pair at confidence
    >= 0.90; it can never create a new pair or receive raw OCR. With no
    suggestions, no call is made.
    """
    from invoice_referee.evidence.trace import RunBudget as _RunBudget  # noqa: F401
    from invoice_referee.evidence.xkiro import XkiroError

    suggestions = [link for link in result.links if link.status == "SUGGEST_LINK"]
    if not suggestions:
        return result

    system = (
        "You may promote an existing suggested evidence link to a confirmed link "
        "only when you are at least 0.90 confident. Never create a new link. "
        "Reply as JSON {\"promotions\": [{\"document_id\", \"item_id\", \"confidence\"}]}."
    )
    user = _serialize_suggestions(suggestions)
    try:
        payload = await llm.complete_json(system=system, user=user, budget=budget)  # type: ignore[attr-defined]
    except XkiroError:
        return result

    promotions = payload.get("promotions") or []
    pairs = {(link.item_id, link.document_id) for link in suggestions}
    promote: set[tuple[str, str]] = set()
    for entry in promotions:
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id") or "")
        document_id = str(entry.get("document_id") or "")
        confidence = entry.get("confidence")
        if (item_id, document_id) not in pairs:
            continue
        if isinstance(confidence, (int, float)) and float(confidence) >= 0.90:
            promote.add((item_id, document_id))

    if not promote:
        return result
    new_links = tuple(
        link.model_copy(update={"status": "AUTO_LINK", "method": "LLM_RESOLVED"})
        if (link.item_id, link.document_id) in promote
        else link
        for link in result.links
    )
    return result.model_copy(update={"links": new_links})


def _serialize_suggestions(suggestions: list[EvidenceLink]) -> str:
    import json

    return json.dumps(
        {
            "suggestions": [
                {
                    "item_id": link.item_id,
                    "document_id": link.document_id,
                    "score": str(link.score),
                    "explanation": link.explanation,
                }
                for link in suggestions
            ]
        },
        ensure_ascii=False,
    )
