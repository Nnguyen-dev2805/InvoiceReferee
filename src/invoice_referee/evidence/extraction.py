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
from invoice_referee.source_dates import date_is_supported, parse_source_date

_DIGITS = re.compile(r"\d")
_NUMBER = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)")
# A percentage token ("8%", "8 %") is a RATE, never a money/quantity value. The
# tokenizer must drop it or `Thuế GTGT (8%): 400.000` would offer `8` as money.
_PERCENT = re.compile(r"\d+(?:[.,]\d+)?\s*%")
# A digit-run inside an alphanumeric identifier ("IR26E", "1C26TAA") is part of a
# code, not a money/quantity token: `IR26E` must not offer `26` as a value.
_TOKEN = re.compile(r"\d[\d.,]*")

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

# SETTLEMENT_FORM synonyms, scoped by document_type so the invoice vocabulary is
# untouched. The model reads a settlement form by its own natural labels
# (`requester_name`, `work_location`, `total_expense`, …); without this map a
# correctly-read form is reported as missing every required field (false
# NEEDS_HUMAN). Mapping is by document type only — `total_amount_numeric` on a
# form is the printed total, but `total_amount` on an invoice is not aliased.
_SETTLEMENT_FORM_ALIASES: dict[str, str] = {
    "requester_name": "declared_name",
    "requester": "declared_name",
    "employee_name": "declared_name",
    "work_location": "trip_destination",
    "destination": "trip_destination",
    "start_date": "trip_start",
    "trip_from": "trip_start",
    "end_date": "trip_end",
    "trip_to": "trip_end",
    "subject": "purpose",
    "reason": "purpose",
    "total_expense": "printed_total",
    "total_amount_numeric": "printed_total",
    "total_expense_in_words": "amount_words",
    "total_expense_words": "amount_words",
    "total_amount_words": "amount_words",
    "advance_amount": "declared_advance",
    "advanced_amount": "declared_advance",
    "advance_no": "advance_reference",
    "advance_code": "advance_reference",
    "advance_ref": "advance_reference",
    "dossier_no": "advance_reference",
    "refund_amount": "printed_return",
    "return_amount": "printed_return",
    "additional_payment_requested": "printed_reimbursement",
    "reimbursement_amount": "printed_reimbursement",
}

# Receipt-like synonyms, scoped by document type (16/10/2026, TC25 LIVE):
# a collection/paper/hotel receipt read by its printed labels (`receipt_number`,
# `amount`, `receipt_date`) maps to the profile vocabulary. TRANSPORT_TICKET is
# excluded on purpose: its money field is `fare_amount`, not `total_amount`.
_RECEIPT_FORM_ALIASES: dict[str, str] = {
    "receipt_number": "document_number",
    "receipt_no": "document_number",
    "receipt_date": "document_date",
    "amount": "total_amount",
    "receipt_amount": "total_amount",
    "total": "total_amount",
}

_RECEIPT_FORM_TYPES = frozenset(
    {"PAPER_RECEIPT", "HOTEL_RECEIPT", "COLLECTION_RECEIPT"}
)


def canonical_field_name(name: str, document_type: str | None = None) -> str:
    """Map a model field synonym to the code-owned profile vocabulary.

    The alias table is scoped by document type: a SETTLEMENT_FORM form is read by
    its own labels (`requester_name`, `total_expense`, …), so those map only when
    the caller states the document type. Without a type, only the invoice table
    applies (kept for backward-compatible callers).
    """
    key = (name or "").strip()
    if document_type == "SETTLEMENT_FORM":
        return _SETTLEMENT_FORM_ALIASES.get(key, _FIELD_ALIASES.get(key, key))
    if document_type in _RECEIPT_FORM_TYPES:
        return _RECEIPT_FORM_ALIASES.get(key, _FIELD_ALIASES.get(key, key))
    return _FIELD_ALIASES.get(key, key)


def _normalize_number(text: str) -> Decimal | None:
    match = _NUMBER.search(text or "")
    if match is None:
        return None
    try:
        return Decimal(match.group(1).replace(".", "").replace(" ", ""))
    except InvalidOperation:
        return None


def _numeric_tokens(quote: str) -> set[int]:
    """The standalone numeric tokens a quote really offers as money/quantity.

    A percentage ("8%") is a rate and an alphanumeric code digit-run ("IR26E")
    is part of an identifier: neither is a money token. The tokenizer removes
    percentages, then keeps only digit-runs that are NOT glued to a letter on
    either side, so `Thuế GTGT (8%): 400.000` offers exactly {400000}.
    """
    stripped = _PERCENT.sub(" ", quote or "")
    tokens: set[int] = set()
    for match in _TOKEN.finditer(stripped):
        start, end = match.start(), match.end()
        before = stripped[start - 1] if start > 0 else ""
        after = stripped[end] if end < len(stripped) else ""
        if before.isalpha() or after.isalpha():
            continue  # part of an identifier, not a standalone number
        try:
            tokens.add(int(match.group(0).replace(".", "").replace(" ", "")))
        except ValueError:
            continue
    return tokens


def _digits_only(text: str) -> bool:
    """Whether the text is a bare money/number after stripping currency words."""
    stripped = re.sub(r"(?i)\b(vnd|đ|dong|đồng)\b", "", text).strip()
    return bool(stripped) and re.fullmatch(r"[\d.,\s]+", stripped) is not None


def _alnum(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.lower())


def _source_pages_text(ocr: OcrSourceResult, page_range: tuple[int, int]) -> str:
    start, end = page_range
    return "\n".join(page.markdown for page in ocr.pages if start <= page.page <= end)


def _quote_supported(quote: str, haystack: str) -> bool:
    if not quote.strip():
        return False
    return quote.strip() in haystack


def _value_supported(
    value: object, quote: str, *, field_name: str | None = None
) -> bool:
    """The normalized value must be derivable from the exact quote.

    Token-based provenance (not "the first number in the quote"): a money value
    is supported when it appears as a standalone numeric token of the quote — a
    percentage ("8%") or a digit-run glued to letters ("IR26E") is not money. An
    identifier value ("IR26E00000101") is supported when its alphanumeric
    skeleton, or each of its digit-runs, appears in the quote, so a serial-prefix
    reading still binds to its own parts and a wrong number is rejected.
    """
    if value is None:
        return False
    # A row's `invoice_refs` is a list; every element must appear in the quote.
    if isinstance(value, (list, tuple)):
        if not value:
            return False
        return all(
            _value_supported(item, quote, field_name=field_name) for item in value
        )
    text = str(value).strip()
    if field_name == "transaction_status":
        # Deterministic enum normalization, not fuzzy inference. Compare the
        # entire value after a recognized label so negation cannot become paid.
        import unicodedata

        def status(raw: str) -> str | None:
            raw = unicodedata.normalize("NFKD", raw.casefold().replace("đ", "d"))
            raw = "".join(c for c in raw if not unicodedata.combining(c))
            raw = re.sub(
                r"^(?:trang thai giao dich|trang thai|transaction status|status)\s*:\s*",
                "",
                raw.strip(),
            )
            raw = " ".join(raw.replace("_", " ").split())
            return {
                "hoan tat": "COMPLETED",
                "thanh cong": "COMPLETED",
                "completed": "COMPLETED",
                "success": "COMPLETED",
                "successful": "COMPLETED",
                "pending": "PENDING",
                "processing": "PENDING",
                "dang xu ly": "PENDING",
                "failed": "FAILED",
                "that bai": "FAILED",
                "khong thanh cong": "FAILED",
                "cancelled": "FAILED",
            }.get(raw)

        source_status = status(quote)
        if status(text) is not None:
            return status(text) == source_status
        # Preserve an unknown source status only verbatim. Never accept a
        # substring such as COMPLETED inside NOT COMPLETED.
        return " ".join(text.casefold().split()) == " ".join(quote.casefold().split())
    # A normalized date (ISO) is supported when the quote carries the same date.
    date_ok = date_is_supported(text, quote, field_name=field_name)
    if date_ok is not None:
        return date_ok
    # Money/number: the value must be a real numeric token of the quote.
    if _digits_only(text):
        value_num = _normalize_number(text)
        if value_num is None:
            return False
        return int(value_num) in _numeric_tokens(quote)
    # Identifier/code (has letters): bind by the alphanumeric skeleton, or by the
    # value's own document-number digit-run, so a serial-prefix reading
    # ("IR26E00000101") still matches the quote's serial + number parts while a
    # wrong number is rejected.
    if _DIGITS.search(text):
        quote_alnum = _alnum(quote)
        if _alnum(text) in quote_alnum:
            return True
        runs = re.findall(r"\d+", text)
        if not runs:
            return False
        longest = max(runs, key=len)
        return int(longest) in _numeric_tokens(quote)
    # Text values may be returned as a normalized single line while the source
    # quote preserves OCR line breaks. Collapse whitespace only for this
    # derivability check; the EvidenceRef keeps the exact, unmodified quote.
    normalized_text = " ".join(text.split())
    normalized_quote = " ".join(quote.split())
    if not normalized_text:
        return False
    return (
        normalized_text in normalized_quote
        or normalized_text.casefold() in normalized_quote.casefold()
    )


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
    document_type: str | None = None,
    allowed_pages: tuple[int, int] | None = None,
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
        str(entry.get("field") or entry.get("name") or entry.get("field_name") or ""),
        document_type,
    )
    if state == "AMBIGUOUS":
        from invoice_referee.domain.documents import ValueAlternative

        alternatives = []
        seen = set()
        for alternative in entry.get("alternatives", []):
            candidate = _validate_field(
                {**alternative, "field": field_name, "state": "FOUND"},
                ocr=ocr,
                haystack=haystack,
                default_page=default_page,
                document_type=document_type,
                allowed_pages=allowed_pages,
            )
            key = repr(candidate.value)
            if candidate.state == "FOUND" and key not in seen:
                alternatives.append(
                    ValueAlternative(value=candidate.value, refs=candidate.refs)
                )
                seen.add(key)
        if len(alternatives) < 2:
            return FieldCandidate(field=field_name, state="UNREADABLE")
        return FieldCandidate(
            field=field_name, state="AMBIGUOUS", alternatives=tuple(alternatives)
        )
    if state != "FOUND":
        return FieldCandidate(field=field_name, state=state)  # type: ignore[arg-type]
    quote = str(entry.get("quote") or entry.get("exact_quote") or "")
    try:
        page = int(entry.get("page") or default_page)
    except (TypeError, ValueError):
        return FieldCandidate(field=field_name, state="UNREADABLE")
    if allowed_pages is not None and not allowed_pages[0] <= page <= allowed_pages[1]:
        return FieldCandidate(field=field_name, state="UNREADABLE")
    page_text = next((p.markdown for p in ocr.pages if p.page == page), "")
    value = entry.get("value")
    if field_name == "invoice_refs" and isinstance(value, str):
        # Some providers encode the array as a JSON string. Decode only this
        # field and still validate every reference against its own source quote.
        import json

        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            decoded = [value]
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) for item in decoded
        ):
            return FieldCandidate(field=field_name, state="UNREADABLE")
        value = decoded
    # A FOUND value needs an exact quote from the source AND a value derivable
    # from it; without a quote it cannot be FOUND (plan E5).
    if (
        not quote
        or not _quote_supported(quote, haystack)
        or not _quote_supported(quote, page_text)
        or not _value_supported(value, quote, field_name=field_name)
    ):
        return FieldCandidate(field=field_name, state="UNREADABLE")
    if field_name in {"document_date", "event_at", "trip_start", "trip_end"}:
        day = parse_source_date(str(value))
        if day is None:
            return FieldCandidate(field=field_name, state="UNREADABLE")
        # Preserve source timestamps at their original precision; date-only values use ISO.
        if not re.search(r"[T ]\d{2}:\d{2}", str(value)):
            value = day.isoformat()
    return FieldCandidate(
        field=field_name,
        state="FOUND",
        value=_normalize_value(value),
        refs=(_ref(ocr, page, quote),),
    )


def _normalize_value(value: object) -> str | int | Decimal | bool | tuple[str, ...]:
    """Coerce a model value to the FieldCandidate value vocabulary.

    A row's `invoice_refs` arrives as a JSON list of strings; the DTO stores a
    tuple, so the code (not the model) normalizes it. Any other non-scalar is
    stringified so provenance is still bound to the quote.
    """
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    if isinstance(value, (str, int, Decimal, bool)):
        return value
    return str(value)


def _field_vocabulary(document_type: str) -> str:
    """The profile's field names for a document type, as a prompt fragment.

    Code-owned: the profile decides the vocabulary; the prompt only advertises
    it so the model does not invent its own labels.
    """
    from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES

    profile = DOCUMENT_PROFILES.get(document_type)
    if profile is None or not profile.allowed_fields:
        return ""
    return ", ".join(profile.allowed_fields)


async def extract_document(
    ocr: OcrSourceResult,
    classification: DocumentClassification,
    *,
    llm: object,
    budget: RunBudget,
) -> DocumentAnalysis:
    """Extract one document's fields/lines and verify provenance (plan E5)."""
    haystack = _source_pages_text(ocr, classification.page_range)
    # Name the target field vocabulary for this document type, or the model
    # invents its own labels (e.g. `department` for the trip destination) and a
    # correctly-read form is reported as missing required fields. The profile is
    # code-owned; the prompt only advertises it.
    from invoice_referee.evidence.prompts import (
        build_extraction_prompt,
        EXTRACTION_VERSION,
    )

    system = build_extraction_prompt(
        classification.document_type,
        tuple(
            f.strip()
            for f in _field_vocabulary(classification.document_type).split(",")
            if f.strip()
        ),
    )
    user = _serialize(ocr, classification)
    from invoice_referee.evidence.telemetry import llm_trace_context

    with llm_trace_context(
        stage="extract",
        prompt_version="document-extraction-v3",
        schema_version="document-fields-and-line-items-json-v1",
    ):
        payload = await _call_with_one_repair(
            llm, system=system, user=user, budget=budget
        )
    if payload is None:
        return _unresolved(ocr, classification)

    raw_fields = payload.get("fields")
    # The pinned prompt asks for `line_items`; a model may still answer with the
    # older `lines` key, so accept either (plan E5).
    raw_lines = payload.get("line_items")
    if raw_lines is None:
        raw_lines = payload.get("lines") or []
    if not isinstance(raw_fields, list) or not isinstance(raw_lines, list):
        return _unresolved(ocr, classification)

    document_type = classification.document_type
    fields: list[FieldCandidate] = [
        _validate_field(
            entry,
            ocr=ocr,
            haystack=haystack,
            default_page=classification.page_range[0],
            document_type=document_type,
            allowed_pages=classification.page_range,
        )
        for entry in raw_fields
        if isinstance(entry, dict)
    ]

    lines: list[DocumentLine] = []
    for entry in raw_lines:
        # Only a structured row ({fields: [...]}) is a line item. A raw OCR text
        # string is not a row and must not be turned into a fabricated field.
        # On a settlement form, preserve a blank marker so malformed row output
        # stays unresolved instead of making the row-total check disappear.
        if not isinstance(entry, dict):
            if document_type == "SETTLEMENT_FORM":
                lines.append(
                    DocumentLine(
                        id=f"{classification.document_id}:line:{len(lines) + 1}"
                    )
                )
            continue
        # Code owns the line id; the model's id is discarded. Line fields get
        # the same provenance validation as top-level fields (plan E5).
        line_fields = tuple(
            _validate_field(
                f,
                ocr=ocr,
                haystack=haystack,
                default_page=classification.page_range[0],
                document_type=document_type,
                allowed_pages=classification.page_range,
            )
            for f in entry.get("fields", [])
            if isinstance(f, dict)
        )
        index = len(lines) + 1
        lines.append(
            DocumentLine(
                id=f"{classification.document_id}:line:{index}", fields=line_fields
            )
        )

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
    from invoice_referee.evidence.structured_output import complete_structured

    def validate(payload: dict) -> dict:
        if not isinstance(payload.get("fields"), list):
            raise XkiroSchemaError("fields must be an array")
        lines = payload.get("line_items", payload.get("lines", []))
        if not isinstance(lines, list):
            raise XkiroSchemaError("line_items must be an array")
        from invoice_referee.domain.documents import FIELD_STATES

        entries = list(payload["fields"])
        for row in lines:
            if isinstance(row, dict) and isinstance(row.get("fields"), list):
                entries.extend(row["fields"])
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise XkiroSchemaError(f"field[{index}] must be an object")
            state = entry.get("state")
            if not isinstance(state, str) or state not in FIELD_STATES:
                raise XkiroSchemaError(f"field[{index}].state is not a FieldState")
            name = entry.get("field") or entry.get("name") or entry.get("field_name")
            if not isinstance(name, str) or not name:
                raise XkiroSchemaError(
                    f"field[{index}].field must be a non-empty string"
                )
            from invoice_referee.domain.documents import MONEY_FIELD_HINTS

            values = [entry.get("value")]
            if isinstance(entry.get("alternatives"), list):
                values.extend(
                    alt.get("value")
                    for alt in entry["alternatives"]
                    if isinstance(alt, dict)
                )
            if any(
                isinstance(value, bool)
                or (
                    isinstance(value, float)
                    and any(h in name for h in MONEY_FIELD_HINTS)
                )
                for value in values
            ):
                raise XkiroSchemaError(
                    f"field[{index}] has an invalid boolean/float value"
                )
            page = entry.get("page")
            if page is not None and (type(page) is not int or page < 1):
                raise XkiroSchemaError(
                    f"field[{index}].page must be a positive integer"
                )
            if state == "AMBIGUOUS":
                alternatives = entry.get("alternatives")
                if (
                    not isinstance(alternatives, list)
                    or len(alternatives) < 2
                    or any(
                        not isinstance(alt, dict)
                        or "value" not in alt
                        or not isinstance(alt.get("quote"), str)
                        or (
                            "page" in alt
                            and (type(alt["page"]) is not int or alt["page"] < 1)
                        )
                        for alt in alternatives
                    )
                ):
                    raise XkiroSchemaError(
                        f"field[{index}] needs at least two well-formed alternatives"
                    )
        for index, row in enumerate(lines):
            if isinstance(row, dict) and not isinstance(row.get("fields", []), list):
                raise XkiroSchemaError(f"line_items[{index}].fields must be an array")
        return payload

    try:
        return await complete_structured(
            llm,
            system=system,
            user=user,
            budget=budget,
            validate=validate,
            stage="extract",
            prompt_version="document-extraction-v3",
            schema_version="document-fields-and-line-items-json-v1",
        )
    except Exception as error:
        from invoice_referee.evidence.kimi import KimiSchemaError as _KimiSchemaError

        if isinstance(error, (XkiroSchemaError, _KimiSchemaError)):
            return None
        raise


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
            "source_id": ocr.source_id,
            "document_id": classification.document_id,
            "page_range": list(classification.page_range),
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


def _serialize_role_aware(
    ocr: OcrSourceResult,
    *,
    document_id: str,
    page_range: tuple[int, int],
    upload_role: str,
) -> str:
    import json

    start, end = page_range
    return json.dumps(
        {
            "source_id": ocr.source_id,
            "document_id": document_id,
            "page_range": [start, end],
            "upload_role": upload_role,
            "pages": [
                {"page": page.page, "markdown": page.markdown}
                for page in ocr.pages
                if start <= page.page <= end
            ],
        },
        ensure_ascii=False,
    )


def _pseudo_classification(
    ocr: OcrSourceResult,
    *,
    document_type: str,
    page_range: tuple[int, int],
    confidence: float | None = None,
) -> DocumentClassification:
    """Code-owned unit for role-aware extraction (no standalone classifier)."""
    from invoice_referee.evidence.classification import compatible_roles

    try:
        roles = compatible_roles(document_type)
    except Exception:
        roles = ("UNKNOWN",)
    return DocumentClassification(
        document_id=f"{ocr.source_id}:{page_range[0]}-{page_range[1]}:{document_type}",
        source_id=ocr.source_id,
        page_range=page_range,
        document_type=document_type,  # type: ignore[arg-type]
        roles=roles,  # type: ignore[arg-type]
        classification_confidence=confidence,
    )


def _build_analysis(
    ocr: OcrSourceResult,
    classification: DocumentClassification,
    *,
    payload: dict,
    document_type: str,
) -> DocumentAnalysis:
    haystack = _source_pages_text(ocr, classification.page_range)
    raw_fields = payload.get("fields")
    raw_lines = payload.get("line_items")
    if raw_lines is None:
        raw_lines = payload.get("lines") or []
    if not isinstance(raw_fields, list) or not isinstance(raw_lines, list):
        return _unresolved(ocr, classification)
    fields: list[FieldCandidate] = [
        _validate_field(
            entry,
            ocr=ocr,
            haystack=haystack,
            default_page=classification.page_range[0],
            document_type=document_type,
            allowed_pages=classification.page_range,
        )
        for entry in raw_fields
        if isinstance(entry, dict)
    ]
    lines: list[DocumentLine] = []
    for entry in raw_lines:
        if not isinstance(entry, dict):
            if document_type == "SETTLEMENT_FORM":
                lines.append(
                    DocumentLine(
                        id=f"{classification.document_id}:line:{len(lines) + 1}"
                    )
                )
            continue
        line_fields = tuple(
            _validate_field(
                f,
                ocr=ocr,
                haystack=haystack,
                default_page=classification.page_range[0],
                document_type=document_type,
                allowed_pages=classification.page_range,
            )
            for f in entry.get("fields", [])
            if isinstance(f, dict)
        )
        index = len(lines) + 1
        lines.append(
            DocumentLine(
                id=f"{classification.document_id}:line:{index}", fields=line_fields
            )
        )
    return DocumentAnalysis(
        source_id=ocr.source_id,
        document_id=classification.document_id,
        document_type=document_type,  # type: ignore[arg-type]
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


async def extract_paper_document(
    ocr: OcrSourceResult, *, llm: object, budget: RunBudget
) -> tuple[DocumentAnalysis, str, str, str]:
    """Extract a paper-role file as SETTLEMENT_FORM + role-fit check (one call).

    Returns (analysis, role_fit, actual_type, role_note). role_fit is FIT, MISFIT
    or UNRESOLVED (call failed). A MISFIT is reported, never forced into a
    settlement shape.
    """
    from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES
    from invoice_referee.evidence.prompts import build_paper_extraction_prompt

    page_range = (1, max((page.page for page in ocr.pages), default=1))
    classification = _pseudo_classification(
        ocr, document_type="SETTLEMENT_FORM", page_range=page_range
    )
    profile = DOCUMENT_PROFILES.get("SETTLEMENT_FORM")
    allowed = tuple(profile.allowed_fields) if profile is not None else ()
    system = build_paper_extraction_prompt(allowed)
    user = _serialize_role_aware(
        ocr,
        document_id=classification.document_id,
        page_range=page_range,
        upload_role="paper",
    )
    payload = await _call_with_one_repair(llm, system=system, user=user, budget=budget)
    if payload is None:
        return _unresolved(ocr, classification), "UNRESOLVED", "UNKNOWN", ""
    analysis = _build_analysis(
        ocr, classification, payload=payload, document_type="SETTLEMENT_FORM"
    )
    role_fit = str(payload.get("role_fit") or "UNRESOLVED").upper()
    if role_fit not in ("FIT", "MISFIT"):
        # Heuristic fallback (no extra model call): a paper with no usable
        # settlement content is flagged MISFIT for human fix, never forced.
        has_content = bool(analysis.fields or analysis.line_items)
        role_fit = "FIT" if has_content else "MISFIT"
    actual_type = str(payload.get("actual_type") or "UNKNOWN").upper()
    role_note = str(payload.get("role_note") or "")
    return analysis, role_fit, actual_type, role_note


async def extract_evidence_document(
    ocr: OcrSourceResult, *, llm: object, budget: RunBudget
) -> DocumentAnalysis:
    """Combined type + facts extraction for one evidence file (one call).

    The model determines document_type from content and extracts with that
    type's vocabulary in the same response. Code validates the returned type
    against the taxonomy and re-checks every field with that type's profile.
    UNKNOWN stays UNKNOWN; nothing is forced into an invoice shape.
    """
    from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES
    from invoice_referee.evidence.prompts import build_evidence_extraction_prompt

    page_range = (1, max((page.page for page in ocr.pages), default=1))
    system = build_evidence_extraction_prompt(tuple(DOCUMENT_PROFILES))
    provisional_id = f"{ocr.source_id}:{page_range[0]}-{page_range[1]}:evidence"
    user = _serialize_role_aware(
        ocr, document_id=provisional_id, page_range=page_range, upload_role="evidence"
    )
    payload = await _call_with_one_repair(llm, system=system, user=user, budget=budget)
    proposed = payload.get("document_type") if isinstance(payload, dict) else None
    document_type = (
        proposed
        if isinstance(proposed, str) and proposed in DOCUMENT_PROFILES
        else "UNKNOWN"
    )
    classification = _pseudo_classification(
        ocr, document_type=document_type, page_range=page_range
    )
    if payload is None:
        return _unresolved(ocr, classification)
    if document_type == "UNKNOWN":
        return DocumentAnalysis(
            source_id=ocr.source_id,
            document_id=classification.document_id,
            document_type="UNKNOWN",
            roles=("UNKNOWN",),
            page_range=page_range,
            classification_confidence=None,
            alternative_document_types=(),
            confidence_status="UNRESOLVED",
            profile_status="UNKNOWN",
            warnings=("evidence_type_unresolved",),
        )
    return _build_analysis(
        ocr, classification, payload=payload, document_type=document_type
    )
