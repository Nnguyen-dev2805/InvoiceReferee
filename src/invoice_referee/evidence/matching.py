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
from invoice_referee.reconciliation.document_arithmetic import is_settlement_summary_row

ORIGINAL_EXPENSE_DOCUMENT_TYPES = frozenset(
    {"E_INVOICE", "PAPER_RECEIPT", "TRANSPORT_TICKET", "HOTEL_RECEIPT", "COLLECTION_RECEIPT"}
)

GENERIC_PARTY_TOKENS = {
    "a", "an", "cap", "cong", "cung", "doanh", "khac", "nha", "nghiep", "phan", "tap",
    "toan", "trach", "nhiem", "huu", "han", "tnhh", "ty", "mua", "tu",
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


def _invoice_ref_matches_number(reference: str, document_number: str) -> bool:
    """Match a full invoice number to its standalone serial reference.

    A shorter suffix is accepted only when it starts after a non-digit (for
    example ``IR26E00000101`` vs ``00000101``). This avoids treating a tail
    such as ``001`` as the same identifier as the larger numeric value ``2001``.
    """
    ref = _normalize_identifier(reference)
    number = _normalize_identifier(document_number)
    if not ref or not number:
        return False
    if ref == number:
        return True
    shorter, longer = (ref, number) if len(ref) < len(number) else (number, ref)
    if not longer.endswith(shorter):
        return False
    preceding = longer[len(longer) - len(shorter) - 1]
    return not preceding.isdigit()


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


def _party_identity_similarity(left: str, right: str | None) -> float:
    left_tokens = {t for t in _normalize_text(left).split() if t not in GENERIC_PARTY_TOKENS and len(t) > 1}
    right_tokens = {t for t in _normalize_text(right).split() if t not in GENERIC_PARTY_TOKENS and len(t) > 1}
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


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
    """Parse a model/source money value to Decimal (VN formatting included).

    A real provider returns "3.240.000 đ"; the shared parser handles it.
    """
    from invoice_referee.domain.common import parse_vnd

    parsed = parse_vnd(value)
    return None if parsed is None else Decimal(parsed)


def _refs(document: DocumentAnalysis) -> tuple[EvidenceRef, ...]:
    refs = [*document.refs, *(r for f in document.fields for r in f.refs),
            *(r for row in document.line_items for f in row.fields for r in f.refs)]
    return tuple(dict.fromkeys(refs))


def match_paper_evidence(
    paper: DocumentAnalysis,
    documents: tuple[DocumentAnalysis, ...],
) -> EvidenceMatchingResult:
    """Match documents to settlement-form rows (pure, evidence-only)."""
    if paper.document_type != "SETTLEMENT_FORM":
        raise ValueError("match_paper_evidence requires a SETTLEMENT_FORM paper")
    matchable = tuple(d for d in documents if d.document_type != "UNKNOWN")

    links: list[EvidenceLink] = []
    allocated: dict[str, Decimal] = {}

    for position, row in enumerate(paper.line_items, start=1):
        item_id = f"ITEM-{position:03d}"
        description = _line_description(row)
        if is_settlement_summary_row(description):
            continue
        amount = _as_decimal(_line_field(row, "amount"))
        reason = _line_field(row, "no_evidence_reason")
        refs_value = _line_field(row, "invoice_refs")
        normalized_refs = {
            _normalize_identifier(r) for r in (refs_value or ()) if _normalize_identifier(r)
        }

        # A numeric serial is an exact identifier only if it resolves to one
        # document in this candidate set. Duplicate serials stay suggestions.
        ref_candidates: dict[str, list[str]] = {}
        for ref in normalized_refs:
            ref_candidates[ref] = [
                document.document_id
                for document in matchable
                if (number := document_field(document, "document_number")) is not None
                and _invoice_ref_matches_number(ref, str(number))
            ]
        unique_exact_documents = {
            candidate_ids[0]
            for candidate_ids in ref_candidates.values()
            if len(candidate_ids) == 1
        }
        ambiguous_exact_documents = {
            document_id
            for candidate_ids in ref_candidates.values()
            if len(candidate_ids) > 1
            for document_id in candidate_ids
        }

        row_links: list[EvidenceLink] = []
        for document in matchable:
            number = document_field(document, "document_number")
            total = _as_decimal(document_field(document, "total_amount"))
            issuer = document_field(document, "issuer_name")
            invoice_exact = (
                document.document_id in unique_exact_documents
                and document.document_id not in ambiguous_exact_documents
            )
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
                if document.document_id in ambiguous_exact_documents:
                    explanation += " Số hóa đơn trùng với nhiều chứng từ; cần chọn đúng hóa đơn."

            if score < Decimal("0.50"):
                continue
            status = "AUTO_LINK" if score >= Decimal("0.75") else "SUGGEST_LINK"
            if document.document_id in ambiguous_exact_documents:
                status = "SUGGEST_LINK"
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

        links.extend(sorted(row_links, key=lambda link: link.score, reverse=True))
    return project_evidence_matches(paper, documents, tuple(links))


def project_evidence_matches(
    paper: DocumentAnalysis, documents: tuple[DocumentAnalysis, ...],
    links: tuple[EvidenceLink, ...],
) -> EvidenceMatchingResult:
    """Validate allocations and rebuild every derived match view from one mapping."""
    matchable = tuple(d for d in documents if d.document_type not in {"UNKNOWN", "SETTLEMENT_FORM"})
    by_id = {d.document_id: d for d in matchable}
    rows, findings, projected = [], [], []
    auto_linked: set[str] = set()
    allocated: dict[str, Decimal] = {}
    for position, row in enumerate(paper.line_items, start=1):
        item_id = f"ITEM-{position:03d}"
        description = _line_description(row)
        if is_settlement_summary_row(description):
            continue
        amount = _as_decimal(_line_field(row, "amount"))
        reason = _line_field(row, "no_evidence_reason")
        row_links = []
        allocation_before_row = dict(allocated)
        seen_documents = set()
        for link in links:
            document = by_id.get(link.document_id)
            if link.item_id != item_id or document is None or link.document_id in seen_documents:
                continue
            seen_documents.add(link.document_id)
            status = link.status
            part = None
            total = _as_decimal(document_field(document, "total_amount"))
            refs_value = _line_field(row, "invoice_refs") or ()
            number = document_field(document, "document_number")
            explicit = number is not None and any(_invoice_ref_matches_number(str(r), str(number)) for r in refs_value)
            if status == "AUTO_LINK":
                supported_refs = _refs(document)
                provenance_ok = any(ref in supported_refs and ref.source_id == document.source_id
                                    for ref in link.refs)
                conflicting_number = bool(refs_value and number is not None and not explicit)
                llm_invalid = link.method == "LLM_RESOLVED" and (
                    amount is None or total is None or abs(amount-total) > Decimal("1")
                    or not any(r.source_id == document.source_id for r in link.refs))
                if (conflicting_number or llm_invalid or link.source_id != document.source_id
                    or not provenance_ok or (link.method == "INVOICE_NUMBER_EXACT" and not explicit)):
                    status = "SUGGEST_LINK"
                part = amount if (explicit or link.method == "LLM_RESOLVED") and amount is not None else total
                used = allocated.get(link.document_id, Decimal("0"))
                if (status != "AUTO_LINK" or part is None or total is None or part < 0 or used + part > total
                    or (link.document_id in allocated and not explicit)
                    or (link.method == "LLM_RESOLVED" and document.profile_status != "CLEAR")):
                    status, part = "SUGGEST_LINK", None
                else:
                    allocated[link.document_id] = used + part
            row_links.append(link.model_copy(update={"status": status, "allocated_amount": part}))
        row_total = sum((link.allocated_amount or Decimal("0") for link in row_links
                         if link.status == "AUTO_LINK"
                         and by_id[link.document_id].document_type in ORIGINAL_EXPENSE_DOCUMENT_TYPES), Decimal("0"))
        if amount is not None and row_total > amount + Decimal("1"):
            findings.append(EvidenceMatchFinding(code="SET_PAPER_AMOUNT_001", status="UNRESOLVED",
                message=f"Khoản '{description}' ghi {amount} nhưng tổng phân bổ {row_total}.", refs=paper.refs))
            row_links = [link.model_copy(update={"status": "SUGGEST_LINK", "allocated_amount": None})
                         if link.status == "AUTO_LINK" else link for link in row_links]
            allocated = allocation_before_row
        projected.extend(row_links)
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

    unmatched = tuple(dict.fromkeys(d.source_id for d in matchable if d.document_id not in auto_linked))
    if unmatched:
        findings.append(EvidenceMatchFinding(code="SET_PAPER_UNMATCHED_001", status="UNRESOLVED",
            message=f"Có {len(unmatched)} evidence chưa ghép được khoản chi.", refs=paper.refs))
    return EvidenceMatchingResult(links=tuple(projected), rows=tuple(rows), findings=tuple(findings), unmatched_source_ids=unmatched)


async def resolve_evidence_suggestions(
    result: EvidenceMatchingResult, documents: tuple[DocumentAnalysis, ...], *,
    paper: DocumentAnalysis, llm: object, budget: RunBudget,
) -> EvidenceMatchingResult:
    """Resolve only existing pairs from source-backed structured facts."""
    import json
    import math
    from invoice_referee.evidence.prompts import EVIDENCE_LINK_SYSTEM_PROMPT, MATCHING_VERSION
    from invoice_referee.evidence.structured_output import complete_structured
    from invoice_referee.evidence.xkiro import XkiroError, XkiroSchemaError
    suggestions = [link for link in result.links if link.status == "SUGGEST_LINK"]
    if not suggestions:
        return result
    by_id = {d.document_id: d for d in documents}
    paper_rows = {f"ITEM-{i:03d}": row for i, row in enumerate(paper.line_items, 1)
                  if not is_settlement_summary_row(_line_description(row))}
    def facts(document):
        return {f.field: f.value for f in document.fields if f.state == "FOUND"}
    candidates = []
    for link in suggestions:
        row, doc = paper_rows.get(link.item_id), by_id.get(link.document_id)
        if row is not None and doc is not None:
            candidates.append({"item_id": link.item_id, "document_id": link.document_id,
                "row": facts(row), "document": {**facts(doc),
                    "line_items": [{"description": _line_description(line)} for line in doc.line_items]},
                "score": str(link.score), "explanation": link.explanation})
    def validate(payload):
        if not isinstance(payload.get("promotions"), list):
            raise XkiroSchemaError("promotions must be an array")
        for entry in payload["promotions"]:
            if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) for k in ("item_id", "document_id")):
                raise XkiroSchemaError("promotion item_id/document_id must be strings")
            confidence = entry.get("confidence")
            if type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise XkiroSchemaError("promotion confidence must be finite in [0,1]")
            if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
                raise XkiroSchemaError("promotion rationale is required")
            if not isinstance(entry.get("basis"), list) or any(not isinstance(b, dict) for b in entry["basis"]):
                raise XkiroSchemaError("promotion basis must be an array of objects")
            for basis in entry["basis"]:
                if not all(isinstance(basis.get(k), str) for k in ("kind", "left_field", "right_field")):
                    raise XkiroSchemaError("basis kind and selectors must be strings")
                if basis["kind"] not in {"AMOUNT", "DOCUMENT_NUMBER", "ISSUER", "SERVICE"}:
                    raise XkiroSchemaError("basis kind is invalid")
        return payload
    try:
        payload = await complete_structured(llm, system=EVIDENCE_LINK_SYSTEM_PROMPT,
            user=json.dumps({"suggestions": candidates}, ensure_ascii=False, default=str),
            budget=budget, validate=validate, stage="resolve-evidence-suggestions",
            prompt_version=MATCHING_VERSION, schema_version="evidence-promotions-json-v2")
    except XkiroError:
        return result
    pairs = {(l.item_id, l.document_id) for l in suggestions}
    accepted = {}
    for entry in payload["promotions"]:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("item_id"), entry.get("document_id"))
        confidence = entry.get("confidence")
        if key not in pairs or type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0.90 <= confidence <= 1:
            continue
        row, doc = paper_rows.get(key[0]), by_id.get(key[1])
        if row is None or doc is None or doc.profile_status != "CLEAR":
            continue
        declared_refs = _line_field(row, "invoice_refs") or ()
        number = document_field(doc, "document_number")
        if declared_refs and number is not None and not any(_invoice_ref_matches_number(str(ref), str(number)) for ref in declared_refs):
            continue
        amount, total = _as_decimal(_line_field(row, "amount")), _as_decimal(document_field(doc, "total_amount"))
        if amount is None or total is None or abs(amount-total) > Decimal("1"):
            continue
        basis = entry.get("basis")
        if not isinstance(basis, list) or not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
            continue
        supported = set()
        invalid_semantic_basis = False
        explicit_number_match = bool(number is not None and any(
            _invoice_ref_matches_number(str(ref), str(number)) for ref in declared_refs
        ))
        issuer = document_field(doc, "issuer_name")
        issuer_match = bool(issuer and _party_identity_similarity(_line_description(row), str(issuer)) >= 0.90)
        service_descriptions = [_line_description(line) for line in doc.line_items]
        description = _line_description(row)
        service_match = bool(description and service_descriptions and any(
            _semantic_similarity(description, doc) >= 0.45
            and _normalize_text(description) in _normalize_text(source_description)
            for source_description in service_descriptions
        ))
        for item in basis:
            if not isinstance(item, dict):
                continue
            selector = (item.get("kind"), item.get("left_field"), item.get("right_field"))
            if selector == ("AMOUNT", "row.amount", "document.total_amount"):
                supported.add("AMOUNT")
            elif selector == ("DOCUMENT_NUMBER", "row.invoice_refs", "document.document_number"):
                if explicit_number_match:
                    supported.add("DOCUMENT_NUMBER")
            elif selector == ("ISSUER", "row.description", "document.issuer_name"):
                if issuer_match:
                    supported.add("ISSUER")
                else:
                    invalid_semantic_basis = True
                    break
            elif selector == ("SERVICE", "row.description", "document.line_items[*].description"):
                if service_match:
                    supported.add("SERVICE")
                else:
                    invalid_semantic_basis = True
                    break
        if invalid_semantic_basis or "AMOUNT" not in supported or not supported - {"AMOUNT"}:
            continue
        # Identical or competing candidates require a distinguishing signal;
        # selecting an ID or claiming higher confidence does not supply one.
        competing = [c for c in candidates if c["item_id"] == key[0] and c["document_id"] != key[1]]
        if competing:
            continue
        accepted[key] = entry
    if not accepted:
        return result
    links = tuple(link.model_copy(update={"status": "AUTO_LINK", "method": "LLM_RESOLVED",
                      "explanation": accepted[(link.item_id, link.document_id)]["rationale"],
                      "refs": tuple(dict.fromkeys((*link.refs, *_refs(by_id[link.document_id]), *paper.refs,
                          *(r for f in paper_rows[link.item_id].fields for r in f.refs))))})
                  if (link.item_id, link.document_id) in accepted else link for link in result.links)
    projected = project_evidence_matches(paper, documents, links)
    owned_codes = {"SET_PAPER_LINE_AMOUNT_001", "SET_PAPER_MATCH_001", "SET_PAPER_AMOUNT_001",
                   "SET_PAPER_EVIDENCE_REQUIRED", "SET_PAPER_UNMATCHED_001"}
    retained = tuple(f for f in result.findings if f.code not in owned_codes)
    return projected.model_copy(update={"findings": (*retained, *projected.findings)})
