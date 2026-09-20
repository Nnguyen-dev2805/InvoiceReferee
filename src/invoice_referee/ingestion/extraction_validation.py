"""Validate extracted field candidates and assign confirmation status.

Reports facts and required-confirmation status only. It applies no PO policy and
produces no Agent action. Rule order (OCR design §10), applied before confidence
thresholds:

1. missing value           -> MISSING
2. failed normalization     -> INVALID
3. OCR/native-text conflict -> CONFLICTING
4. LLM-assisted mapping     -> NEEDS_CONFIRMATION (regardless of confidence)
5. low confidence           -> NEEDS_CONFIRMATION
   (critical < 0.90, non-critical < 0.80, or missing confidence)

Prototype thresholds are configuration, not accuracy claims.
"""

from __future__ import annotations

from invoice_referee.domain import models as m

CRITICAL_FIELDS = {
    "invoice_number",
    "invoice_series",
    "invoice_type",
    "vendor_tax_code",
    "vendor_id",
    "po_id",
    "invoice_date",
    "currency",
    "total_amount",
}

CRITICAL_LINE_FIELDS = {"item_id", "invoiced_quantity", "unit_price", "line_total"}

CRITICAL_CONFIDENCE = 0.90
NON_CRITICAL_CONFIDENCE = 0.80


def _has_conflict(candidate: m.FieldCandidate) -> bool:
    return any("native" in w.lower() and "text" in w.lower() for w in candidate.warnings)


def _validate_candidate(candidate: m.FieldCandidate, *, critical: bool) -> m.FieldStatus:
    # Preserve statuses a human has already set.
    if candidate.status in (m.FieldStatus.CONFIRMED, m.FieldStatus.CORRECTED):
        return candidate.status

    if candidate.normalized_value is None:
        return m.FieldStatus.MISSING

    if candidate.status is m.FieldStatus.INVALID:
        return m.FieldStatus.INVALID

    if _has_conflict(candidate):
        return m.FieldStatus.CONFLICTING

    if candidate.extraction_method == "LLM_ASSISTED":
        return m.FieldStatus.NEEDS_CONFIRMATION

    threshold = CRITICAL_CONFIDENCE if critical else NON_CRITICAL_CONFIDENCE
    if candidate.confidence is None or candidate.confidence < threshold:
        return m.FieldStatus.NEEDS_CONFIRMATION

    return m.FieldStatus.EXTRACTED


def validate_extraction(result: m.InvoiceExtractionResult) -> m.InvoiceExtractionResult:
    for name, candidate in result.fields.items():
        candidate.status = _validate_candidate(candidate, critical=name in CRITICAL_FIELDS)

    for line in result.line_items:
        for name, candidate in line.items():
            candidate.status = _validate_candidate(
                candidate, critical=name in CRITICAL_LINE_FIELDS
            )

    _validate_line_arithmetic(result)
    return result


def _validate_line_arithmetic(result: m.InvoiceExtractionResult) -> None:
    """Warn (never silently fix) when quantity*price != line_total or lines != total."""
    line_total_sum = 0
    have_all_line_totals = bool(result.line_items)

    for line in result.line_items:
        qty = _value(line.get("invoiced_quantity"))
        price = _value(line.get("unit_price"))
        total = _value(line.get("line_total"))
        if qty is not None and price is not None and total is not None:
            if qty * price != total:
                line["line_total"].warnings.append(
                    f"line arithmetic mismatch: {qty} x {price} != {total}"
                )
        if total is None:
            have_all_line_totals = False
        else:
            line_total_sum += total

    header_total = _value(result.fields.get("total_amount"))
    if header_total is not None and have_all_line_totals and line_total_sum != header_total:
        result.warnings.append(
            f"sum of line totals ({line_total_sum}) does not equal invoice total ({header_total})"
        )


def _value(candidate):
    return candidate.normalized_value if candidate is not None else None
