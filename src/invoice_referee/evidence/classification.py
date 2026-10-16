"""Document type / evidence-role classification (contracts §12.2; plan E4).

One batch call per root. The model proposes a type, page range and roles; code
owns the type→role compatibility map and the document ids, and drops a role the
model cannot justify from separate facts. A low/ambiguous result stays UNKNOWN
and never selects an extraction schema.
"""

from __future__ import annotations

import math

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentClassification,
    DocumentEvidenceRole,
    OcrSourceResult,
)
from invoice_referee.evidence.trace import RunBudget
from invoice_referee.evidence.xkiro import XkiroError

# Code-owned default role map (plan E4 Step 3). Original types carry the
# expense; supporting types never count as original evidence.
_ORIGINAL_TYPES = (
    "E_INVOICE",
    "PAPER_RECEIPT",
    "TRANSPORT_TICKET",
    "HOTEL_RECEIPT",
    "COLLECTION_RECEIPT",
)
_SUPPORTING_TYPES = (
    "CARD_SLIP",
    "PAYMENT_PROOF",
    "CONTRACT",
    "QUOTATION",
    "PURCHASE_ORDER",
    "ACCEPTANCE_RECORD",
    "DELIVERY_NOTE",
    "GOODS_RECEIPT",
    "SUPPLIER_CONFIRMATION",
)

DEFAULT_TYPE_ROLES: dict[str, tuple[DocumentEvidenceRole, ...]] = {
    "SETTLEMENT_FORM": ("SETTLEMENT_DECLARATION",),
    **{t: ("ORIGINAL_EXPENSE_EVIDENCE",) for t in _ORIGINAL_TYPES},
    **{t: ("SUPPORTING_DOCUMENT",) for t in _SUPPORTING_TYPES},
    "OTHER": ("SUPPORTING_DOCUMENT",),
    "UNKNOWN": ("UNKNOWN",),
}


def compatible_roles(document_type: str) -> tuple[DocumentEvidenceRole, ...]:
    """The roles code allows for a type; the model cannot add others."""
    return DEFAULT_TYPE_ROLES.get(document_type, ("UNKNOWN",))


def _first_str(entry: dict, *keys: str) -> str:
    """The first non-empty string among `keys` (tolerant of model aliases)."""
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _role_list(entry: dict) -> tuple[str, ...]:
    """Roles from `roles` or the `evidence_role` alias; a bare string is a list."""
    raw = entry.get("roles")
    if raw is None:
        raw = entry.get("evidence_role")
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    if isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    return ()


def _as_page_range(raw: object, page_text: dict[int, str]) -> tuple[int, int]:
    """A model may omit page_range; default to the whole source, clamped."""
    pages = sorted(page_text) or [1]
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            start, end = int(raw[0]), int(raw[1])
            if start >= 1 and end >= start:
                return start, end
        except (TypeError, ValueError):
            pass
    return pages[0], pages[-1]


def _ref(source_id: str, digest: str, page: int, quote: str) -> EvidenceRef:
    return EvidenceRef(
        source_id=source_id,
        source_sha256=digest,
        page=page,
        exact_quote=quote or "document",
    )


async def classify_documents(
    ocr: tuple[OcrSourceResult, ...],
    *,
    llm: object,
    budget: RunBudget,
) -> tuple[DocumentClassification, ...]:
    """One batch classification call per root (plan E4).

    The response is keyed by submitted source ids only; an unexpected id, a
    malformed entry, or an incompatible model role is rejected or dropped.
    """
    if not ocr:
        return ()
    expected = {source.source_id for source in ocr}
    digest_by_id = {source.source_id: source.source_digest for source in ocr}
    page_text = {
        source.source_id: {page.page: page.markdown for page in source.pages} for source in ocr
    }

    from invoice_referee.evidence.prompts import build_classification_prompt, CLASSIFICATION_VERSION
    from invoice_referee.evidence.structured_output import complete_structured
    from invoice_referee.evidence.xkiro import XkiroSchemaError

    def validate(payload: dict) -> dict:
        documents = payload.get("documents")
        if not isinstance(documents, list) or any(not isinstance(d, dict) for d in documents):
            raise XkiroSchemaError("documents must be an array of objects")
        covered = {sid: set() for sid in expected}
        for document in documents:
            sid = document.get("source_id")
            if isinstance(sid, str) and sid in page_text:
                start, end = _as_page_range(document.get("page_range"), page_text[sid])
                if start < min(page_text[sid]) or end > max(page_text[sid]):
                    raise XkiroSchemaError("classification page_range outside submitted pages")
                covered[sid].update(range(start, end + 1))
        if any(set(page_text[sid]) - covered[sid] for sid in expected):
            raise XkiroSchemaError("classification must cover every submitted source/page")
        return payload

    payload = await complete_structured(llm, system=build_classification_prompt(tuple(DEFAULT_TYPE_ROLES)),
        user=_serialize(ocr), budget=budget, validate=validate, stage="classify",
        prompt_version=CLASSIFICATION_VERSION, schema_version="document-classification-json-v1")

    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise XkiroError("classification returned no documents")

    results: list[DocumentClassification] = []
    claimed_pages: dict[str, list[range]] = {}
    for entry in documents:
        if not isinstance(entry, dict):
            raise XkiroError("malformed classification entry")
        source_id = str(entry.get("source_id") or "")
        if source_id not in expected:
            raise XkiroError(f"classification named an unknown source: {source_id}")
        # Accept the canonical keys and the aliases a model may emit instead
        # (type / evidence_role). A free-form label outside the taxonomy maps to
        # UNKNOWN — never a guessed schema, never a crash.
        proposed_type = _first_str(entry, "document_type", "type", "documentType", "doc_type")
        confidence = entry.get("classification_confidence", entry.get("confidence"))
        confidence_valid = (
            type(confidence) in (int, float) and math.isfinite(confidence)
            and 0 <= confidence <= 1
        )
        document_type = proposed_type if proposed_type in DEFAULT_TYPE_ROLES else "UNKNOWN"
        if not confidence_valid or confidence < 0.5:
            document_type = "UNKNOWN"
        alternatives = tuple(
            alt for alt in (entry.get("alternative_document_types") or ())
            if isinstance(alt, str) and alt in DEFAULT_TYPE_ROLES and alt != "UNKNOWN"
        )
        if document_type == "UNKNOWN" and not alternatives and proposed_type in DEFAULT_TYPE_ROLES and proposed_type != "UNKNOWN":
            alternatives = (proposed_type,)
        roles = ("UNKNOWN",) if document_type == "UNKNOWN" else tuple(
            role for role in _role_list(entry) if role in compatible_roles(document_type)
        ) or compatible_roles(document_type)
        confidence_value = confidence if confidence_valid else None
        page_range = _as_page_range(entry.get("page_range"), page_text[source_id])
        start, end = page_range
        # The model proposes a range; code validates it against the OCR pages
        # and rejects an out-of-range or overlapping incompatible unit (plan E4).
        page_numbers = set(page_text[source_id])
        if start < 1 or end < start or not set(range(start, end + 1)) <= page_numbers:
            raise XkiroError(
                f"classification page range {start}-{end} is outside source {source_id}"
            )
        this_range = range(start, end + 1)
        for prior in claimed_pages.get(source_id, []):
            if set(prior) & set(this_range):
                raise XkiroError(f"overlapping document units for source {source_id}")
        claimed_pages.setdefault(source_id, []).append(this_range)
        # Code owns the document id (model ids are discarded).
        document_id = f"{source_id}:{start}-{end}:{document_type}"
        digest = digest_by_id[source_id]
        pages_in_range = range(start, end + 1)
        quote = next(
            (page_text[source_id].get(p, "") for p in pages_in_range if page_text[source_id].get(p)),
            "document",
        )
        results.append(
            DocumentClassification(
                document_id=document_id,
                source_id=source_id,
                page_range=(start, end),
                block_ids=(),
                document_type=document_type,  # type: ignore[arg-type]
                roles=roles,
                role_refs={role: (_ref(source_id, digest, start, quote),) for role in roles},
                alternative_document_types=alternatives,
                classification_confidence=confidence_value,
                signals=tuple(entry.get("signals") or ()),
                refs=(_ref(source_id, digest, start, quote),),
            )
        )
    return tuple(results)


def _serialize(ocr: tuple[OcrSourceResult, ...]) -> str:
    import json

    return json.dumps(
        {
            "documents": [
                {
                    "source_id": source.source_id,
                    "pages": [
                        {"page": page.page, "markdown": page.markdown} for page in source.pages
                    ],
                }
                for source in ocr
            ]
        },
        ensure_ascii=False,
    )
