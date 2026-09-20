"""Human confirmation of extracted fields and handoff to canonical evidence.

``FieldReview`` records an explicit human decision (confirm / correct / mark
unknown). ``apply_field_reviews`` applies those decisions while preserving the
original candidate, actor, and reason. ``reviewed_invoice_to_evidence`` converts
a fully reviewed extraction into the raw evidence dict the existing production
``review()`` path consumes — without turning an unknown field into "" or 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from invoice_referee.domain import models as m
from invoice_referee.ingestion.extraction_validation import (
    CRITICAL_FIELDS,
    CRITICAL_LINE_FIELDS,
)

# Statuses that mean a critical field cannot be trusted for confident processing.
_UNTRUSTED = {
    m.FieldStatus.MISSING,
    m.FieldStatus.INVALID,
    m.FieldStatus.CONFLICTING,
    m.FieldStatus.NEEDS_CONFIRMATION,
}

# A critical field is human-resolved when it reaches one of these.
_RESOLVED = {m.FieldStatus.CONFIRMED, m.FieldStatus.CORRECTED}


@dataclass(frozen=True)
class FieldReview:
    action: str  # CONFIRM | CORRECT | MARK_UNKNOWN
    value: Any = None
    reason: str = ""

    @classmethod
    def confirm(cls) -> "FieldReview":
        return cls("CONFIRM")

    @classmethod
    def correct(cls, value: Any, *, reason: str) -> "FieldReview":
        if not reason.strip():
            raise ValueError("a correction requires a reason")
        return cls("CORRECT", value=value, reason=reason)

    @classmethod
    def mark_unknown(cls, reason: str) -> "FieldReview":
        if not reason.strip():
            raise ValueError("marking a field unknown requires a reason")
        return cls("MARK_UNKNOWN", value=None, reason=reason)


def _apply_one(candidate: m.FieldCandidate, review: FieldReview, actor: str) -> None:
    if review.action == "CONFIRM":
        candidate.status = m.FieldStatus.CONFIRMED
        return

    # Preserve the original machine candidate before overwriting.
    if candidate.original_normalized_value is None and candidate.original_raw_text is None:
        candidate.original_normalized_value = candidate.normalized_value
        candidate.original_raw_text = candidate.raw_text

    if review.action == "CORRECT":
        candidate.normalized_value = review.value
        candidate.status = m.FieldStatus.CORRECTED
        candidate.extraction_method = "HUMAN"
        candidate.warnings = list(candidate.warnings) + [f"corrected by {actor}: {review.reason}"]
    elif review.action == "MARK_UNKNOWN":
        candidate.normalized_value = None
        candidate.status = m.FieldStatus.MISSING
        candidate.extraction_method = "HUMAN"
        candidate.warnings = list(candidate.warnings) + [
            f"marked unknown by {actor}: {review.reason}"
        ]
    else:
        raise ValueError(f"unknown review action: {review.action}")


def _parse_line_key(key: str) -> Optional[tuple[int, str]]:
    """Parse ``line_items[{index}].{field}`` -> (index, field)."""
    if not key.startswith("line_items["):
        return None
    try:
        index_part, field_part = key[len("line_items["):].split("].", 1)
        return int(index_part), field_part
    except (ValueError, IndexError):
        return None


def apply_field_reviews(
    result: m.InvoiceExtractionResult,
    reviews: dict[str, FieldReview],
    actor: str,
) -> m.InvoiceExtractionResult:
    """Apply human review decisions to header and line-item candidates."""
    for key, review in reviews.items():
        line_ref = _parse_line_key(key)
        if line_ref is not None:
            index, field_name = line_ref
            if 0 <= index < len(result.line_items) and field_name in result.line_items[index]:
                _apply_one(result.line_items[index][field_name], review, actor)
            continue
        if key in result.fields:
            _apply_one(result.fields[key], review, actor)

    result.status = (
        m.ExtractionStatus.REVIEWED
        if _all_critical_resolved(result)
        else m.ExtractionStatus.NEEDS_REVIEW
    )
    return result


def _all_critical_resolved(result: m.InvoiceExtractionResult) -> bool:
    for name in CRITICAL_FIELDS:
        candidate = result.fields.get(name)
        if candidate is not None and candidate.status not in _RESOLVED:
            return False
    for line in result.line_items:
        for name in CRITICAL_LINE_FIELDS:
            candidate = line.get(name)
            if candidate is not None and candidate.status not in _RESOLVED:
                return False
    return True


def _is_untrusted(candidate: Optional[m.FieldCandidate]) -> bool:
    return candidate is not None and candidate.status in _UNTRUSTED


def reviewed_invoice_to_evidence(
    result: m.InvoiceExtractionResult,
    base_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Merge reviewed fields into ``base_evidence`` as an OCR-sourced invoice.

    Only reviewed field values are written; an unknown critical field stays
    ``None`` and flags the invoice so the business pipeline cannot confidently
    auto-process it.
    """
    from invoice_referee.ingestion.normalization import normalize_id

    evidence = dict(base_evidence)
    invoice = dict(evidence.get("invoice") or {})

    for name, candidate in result.fields.items():
        invoice[name] = candidate.normalized_value

    line_items = []
    for line in result.line_items:
        line_items.append({name: cand.normalized_value for name, cand in line.items()})
    if line_items:
        invoice["items"] = line_items

    invoice_id = normalize_id(base_evidence.get("invoice_id")) or (
        f"INV-{result.document_id.removeprefix('DOC-')}"
    )
    invoice["invoice_id"] = invoice_id
    invoice["source_type"] = "OCR"

    flagged = any(_is_untrusted(result.fields.get(n)) for n in CRITICAL_FIELDS)
    for line in result.line_items:
        if any(_is_untrusted(line.get(n)) for n in CRITICAL_LINE_FIELDS):
            flagged = True
    invoice["flagged"] = flagged

    evidence["invoice"] = invoice
    evidence["extraction_metadata"] = {
        "document_id": result.document_id,
        "status": result.status.value,
        "warnings": list(result.warnings),
        "field_provenance": {
            name: {
                "extraction_method": cand.extraction_method,
                "page_number": cand.page_number,
                "evidence_block_ids": list(cand.evidence_block_ids),
                "status": cand.status.value,
            }
            for name, cand in result.fields.items()
        },
    }
    return evidence
