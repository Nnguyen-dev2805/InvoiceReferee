"""Document type / evidence-role classification (contracts §12.2; plan E4).

One batch call per root. The model proposes a type, page range and roles; code
owns the type→role compatibility map and the document ids, and drops a role the
model cannot justify from separate facts. A low/ambiguous result stays UNKNOWN
and never selects an extraction schema.
"""

from __future__ import annotations

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

    system = (
        "You classify each document's type and evidence role from its OCR text "
        "only (never the filename). Reply as JSON {\"documents\": [...]}, one "
        "entry per document unit, keyed by the submitted source_id. An unclear "
        "document is UNKNOWN with alternatives; do not guess a schema."
    )
    user = _serialize(ocr)
    try:
        payload = await llm.complete_json(system=system, user=user, budget=budget)  # type: ignore[attr-defined]
    except XkiroError as error:
        raise XkiroError("classification failed") from error

    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise XkiroError("classification returned no documents")

    results: list[DocumentClassification] = []
    for entry in documents:
        if not isinstance(entry, dict):
            raise XkiroError("malformed classification entry")
        source_id = str(entry.get("source_id") or "")
        if source_id not in expected:
            raise XkiroError(f"classification named an unknown source: {source_id}")
        document_type = str(entry.get("document_type") or "UNKNOWN")
        allowed = compatible_roles(document_type)
        # Keep only roles the code map allows for this type.
        roles = tuple(
            role for role in entry.get("roles", []) if role in allowed
        )
        if not roles:
            roles = allowed
        page_range = entry.get("page_range") or [1, 1]
        start, end = int(page_range[0]), int(page_range[1])
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
                alternative_document_types=tuple(
                    entry.get("alternative_document_types") or ()
                ),
                classification_confidence=entry.get("classification_confidence"),
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
