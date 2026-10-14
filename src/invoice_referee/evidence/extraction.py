"""Typed document extraction with provenance (contracts §12.3; plan E5).

One model call per document returns state-aware field candidates. Code then
verifies each FOUND value against the OCR text: the quote must appear in this
document's own pages, and the normalized value must be supported by the quote.
A real quote with a mismatching value, a paraphrase, or a quote from another
source is demoted (never FOUND). Code assigns line ids; model ids are dropped.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentAnalysis,
    DocumentClassification,
    DocumentLine,
    DocumentProfileIssue,
    FieldCandidate,
    OcrSourceResult,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroSchemaError

_DIGITS = re.compile(r"\d")
_NUMBER = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)")

# Model synonyms → the profile vocabulary (plan §12). Code owns this map so a
# correctly-read invoice is not reported as missing required fields.
_FIELD_ALIASES: dict[str, str] = {
    # Invoice-level synonyms only. Generic words (amount, number, date) are NOT
    # aliased: a settlement row's `amount` means `line_amount`, not `total_amount`
    # (plan §12), and aliasing it would corrupt row matching.
    "invoice_number": "document_number",
    "invoice_no": "document_number",
    "seller_name": "issuer_name",
    "seller": "issuer_name",
    "seller_tax_code": "issuer_tax_code",
    "seller_tax_id": "issuer_tax_code",
    "issuer_tax_id": "issuer_tax_code",
    "invoice_date": "document_date",
    "issue_date": "document_date",
    "symbol": "serial_number",
    "symbol_code": "serial_number",
    "serial": "serial_number",
    "template": "template_number",
    "payment_method": "payment_method_text",
    "grand_total": "total_amount",
    "vat": "tax",
    "vat_amount": "tax",
    "buyer_tax_id": "buyer_tax_code",
    "currency_code": "currency",
}


def canonical_field_name(name: str) -> str:
    """Map a model field synonym to the code-owned profile vocabulary."""
    key = (name or "").strip()
    return _FIELD_ALIASES.get(key, key)


def _normalize_number(text: str) -> Decimal | None:
    match = _NUMBER.search(text or "")
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(".", "").replace(" ", ""))
    except InvalidOperation:
        return None


def _source_pages_text(ocr: OcrSourceResult, page_range: tuple[int, int]) -> str:
    start, end = page_range
    return "\n".join(
        page.markdown for page in ocr.pages if start <= page.page <= end
    )


def _quote_supported(quote: str, haystack: str) -> bool:
    if not quote.strip():
        return False
    return quote.strip() in haystack


_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _date_supported(iso: str, quote: str) -> bool | None:
    """An ISO date is supported when its y/m/d appear in the quote's own date.

    Handles a source date written as prose ("Ngày 10 tháng 10 năm 2026").
    Returns None when the value is not an ISO date.
    """
    match = _ISO_DATE.match(iso)
    if match is None:
        return None
    year, month, day = (int(g) for g in match.groups())
    nums = {int(n) for n in re.findall(r"\d+", quote)}
    return {year, month, day} <= nums


def _value_supported(value: object, quote: str) -> bool:
    """The normalized value must be derivable from the exact quote."""
    if value is None:
        return False
    text = str(value).strip()
    # A normalized date (ISO) is supported when the quote carries the same date.
    date_ok = _date_supported(text, quote)
    if date_ok is not None:
        return date_ok
    # Money/number: the digits must appear in the quote (formatting aside).
    if _DIGITS.search(text) and _DIGITS.search(quote):
        quote_num = _normalize_number(quote)
        value_num = _normalize_number(text)
        if quote_num is not None and value_num is not None:
            return quote_num == value_num
        return text in quote
    return text in quote or text.lower() in quote.lower()


def _ref(ocr: OcrSourceResult, page: int, quote: str) -> EvidenceRef:
    return EvidenceRef(
        source_id=ocr.source_id,
        source_sha256=ocr.source_digest,
        page=page,
        exact_quote=quote or "document",
    )


def _validate_field(
    entry: object,
    *,
    ocr: OcrSourceResult,
    haystack: str,
    default_page: int,
) -> FieldCandidate:
    """Build one FieldCandidate, verifying provenance for FOUND (plan E5).

    A quote must be in this document's own pages AND the normalized value must
    be derivable from that quote; otherwise the field is demoted to UNREADABLE.
    Used for both top-level fields and per-row line fields.
    """
    if not isinstance(entry, dict):
        return FieldCandidate(field="", state="NOT_APPLICABLE")
    state = str(entry.get("state") or "NOT_APPLICABLE")
    # Accept the canonical `field` and the `name` alias a model may emit, then
    # map model synonyms to the profile vocabulary (plan §12).
    field_name = canonical_field_name(
        str(entry.get("field") or entry.get("name") or entry.get("field_name") or "")
    )
    if state != "FOUND":
        return FieldCandidate(field=field_name, state=state)  # type: ignore[arg-type]
    quote = str(entry.get("quote") or entry.get("exact_quote") or "")
    page = int(entry.get("page") or default_page)
    value = entry.get("value")
    # A FOUND value needs an exact quote from the source AND a value derivable
    # from it; without a quote it cannot be FOUND (plan E5).
    if not quote or not _quote_supported(quote, haystack) or not _value_supported(value, quote):
        return FieldCandidate(field=field_name, state="UNREADABLE")
    return FieldCandidate(
        field=field_name,
        state="FOUND",
        value=value if isinstance(value, (str, int, Decimal, bool)) else str(value),
        refs=(_ref(ocr, page, quote),),
    )


async def extract_document(
    ocr: OcrSourceResult,
    classification: DocumentClassification,
    *,
    llm: object,
    budget: RunBudget,
) -> DocumentAnalysis:
    """Extract one document's fields/lines and verify provenance (plan E5)."""
    haystack = _source_pages_text(ocr, classification.page_range)
    system = (
        "Extract the fields of this document from its OCR text. Reply as JSON "
        "{\"fields\": [...], \"lines\": [...]}. Each field object uses EXACTLY "
        "these keys: field (the field name), state (one of FOUND, NOT_PRESENT, "
        "UNREADABLE, AMBIGUOUS, NOT_APPLICABLE), value (only when state=FOUND), "
        "quote (the exact substring copied from the OCR text; required when "
        "state=FOUND), page (1-based). Do not rename these keys (never use "
        "'name'). Never invent a value; a missing value is NOT_PRESENT, not zero."
    )
    user = _serialize(ocr, classification)
    payload = await _call_with_one_repair(llm, system=system, user=user, budget=budget)
    if payload is None:
        return _unresolved(ocr, classification)

    raw_fields = payload.get("fields")
    raw_lines = payload.get("lines") or []
    if not isinstance(raw_fields, list) or not isinstance(raw_lines, list):
        return _unresolved(ocr, classification)

    fields: list[FieldCandidate] = [
        _validate_field(entry, ocr=ocr, haystack=haystack, default_page=classification.page_range[0])
        for entry in raw_fields
        if isinstance(entry, dict)
    ]

    lines: list[DocumentLine] = []
    for index, entry in enumerate(raw_lines, start=1):
        if not isinstance(entry, dict):
            continue
        # Code owns the line id; the model's id is discarded. Line fields get
        # the same provenance validation as top-level fields (plan E5).
        line_fields = tuple(
            _validate_field(f, ocr=ocr, haystack=haystack, default_page=classification.page_range[0])
            for f in entry.get("fields", [])
            if isinstance(f, dict)
        )
        lines.append(DocumentLine(id=f"{classification.document_id}:line:{index}", fields=line_fields))

    return DocumentAnalysis(
        source_id=ocr.source_id,
        document_id=classification.document_id,
        document_type=classification.document_type,
        roles=classification.roles,
        role_refs=classification.role_refs,
        page_range=classification.page_range,
        block_ids=classification.block_ids,
        classification_confidence=classification.classification_confidence,
        alternative_document_types=classification.alternative_document_types,
        classification_refs=classification.refs,
        fields=tuple(fields),
        line_items=tuple(lines),
        confidence_status="UNRESOLVED",
        confidence_refs=(),
        profile_status="UNKNOWN",
        profile_findings=(),
        refs=classification.refs,
        warnings=(),
    )


async def _call_with_one_repair(
    llm: object, *, system: str, user: str, budget: RunBudget
) -> dict | None:
    """One extraction call; on a schema error, at most one repair call."""
    try:
        return await llm.complete_json(system=system, user=user, budget=budget)  # type: ignore[attr-defined]
    except XkiroSchemaError:
        try:
            return await llm.complete_json(system=system, user=user, budget=budget)  # type: ignore[attr-defined]
        except XkiroSchemaError:
            return None


def _unresolved(
    ocr: OcrSourceResult, classification: DocumentClassification
) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id=ocr.source_id,
        document_id=classification.document_id,
        document_type=classification.document_type,
        roles=classification.roles,
        role_refs=classification.role_refs,
        page_range=classification.page_range,
        block_ids=classification.block_ids,
        fields=(),
        line_items=(),
        confidence_status="UNRESOLVED",
        profile_status="NEEDS_HUMAN",
        profile_findings=(
            DocumentProfileIssue(
                code="EXTRACTION_FAILED",
                field=None,
                status="UNRESOLVED",
                message="extraction schema invalid after one repair",
                blocking=True,
            ),
        ),
        refs=classification.refs,
    )


def _serialize(ocr: OcrSourceResult, classification: DocumentClassification) -> str:
    import json

    start, end = classification.page_range
    return json.dumps(
        {
            "document_type": classification.document_type,
            "roles": list(classification.roles),
            "pages": [
                {"page": page.page, "markdown": page.markdown}
                for page in ocr.pages
                if start <= page.page <= end
            ],
        },
        ensure_ascii=False,
    )
