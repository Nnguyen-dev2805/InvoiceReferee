"""JSON extraction adapter — the required Sprint 1 ingestion path.

Structured JSON is already field-addressable, so this adapter simply wraps a raw
dict into the canonical :class:`ExtractedDocument` contract without OCR or LLM
extraction. It never decides whether values match or are valid, and it never
guesses missing fields.
"""

from __future__ import annotations

from typing import Any

from invoice_referee.domain import models as m


def extract_document(
    raw: dict[str, Any],
    document_type: str,
    source_ref: str = "inline",
    extractor: str = "json_adapter",
) -> m.ExtractedDocument:
    """Wrap a raw JSON dict into an :class:`ExtractedDocument`.

    ``parse_warnings`` supplied by the caller (e.g. an upstream OCR step) are
    carried through so downstream uncertainty handling can see them.
    """
    fields = {k: v for k, v in raw.items() if k != "parse_warnings"}
    parse_warnings = list(raw.get("parse_warnings", []))
    return m.ExtractedDocument(
        document_type=document_type,
        source_type=m.SourceType.JSON,
        source_ref=source_ref,
        extractor=extractor,
        fields=fields,
        parse_warnings=parse_warnings,
    )
