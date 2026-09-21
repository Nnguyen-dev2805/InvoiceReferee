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

# Fields a human must confirm before OCR evidence may enter review().
# ``currency`` and ``invoice_type`` are deliberately absent: Sprint 1 is
# VND-only and treats an original invoice as the default, and OCR has no
# extractor for either. A *supplied but unsupported* value for them is caught
# by ``normalization.to_supplier_invoice``, which flags the invoice instead.
CRITICAL_FIELDS = {
    "invoice_number",
    "invoice_series",
    "vendor_tax_code",
    "vendor_id",
    "po_id",
    "invoice_date",
    "total_amount",
}

CRITICAL_LINE_FIELDS = {"item_id", "invoiced_quantity", "unit_price", "line_total"}

CRITICAL_CONFIDENCE = 0.90
NON_CRITICAL_CONFIDENCE = 0.80


def _has_conflict(candidate: m.FieldCandidate) -> bool:
    return any("native" in w.lower() and "text" in w.lower() for w in candidate.warnings)


# Extraction methods that require human confirmation regardless of OCR confidence
# or mapping score. Fuzzy/spatial-OCR/provider/annotation methods always need a
# human in the loop because their evidence is not exact.
_NEEDS_CONFIRMATION_METHODS = frozenset({
    "LLM_ASSISTED",
    "FUZZY_SPATIAL",
    "PROVIDER_ANNOTATION",
})


def _validate_candidate(candidate: m.FieldCandidate, *, critical: bool) -> m.FieldStatus:
    # Preserve statuses a human has already set.
    if candidate.status in (m.FieldStatus.CONFIRMED, m.FieldStatus.CORRECTED):
        return candidate.status

    if candidate.normalized_value is None:
        return m.FieldStatus.MISSING

    if candidate.status is m.FieldStatus.INVALID:
        return m.FieldStatus.INVALID

    if candidate.status is m.FieldStatus.CONFLICTING:
        return m.FieldStatus.CONFLICTING

    if _has_conflict(candidate):
        return m.FieldStatus.CONFLICTING

    if candidate.extraction_method in _NEEDS_CONFIRMATION_METHODS:
        return m.FieldStatus.NEEDS_CONFIRMATION

    if candidate.extraction_method == "LLM_ASSISTED":
        return m.FieldStatus.NEEDS_CONFIRMATION

    # Use provider OCR confidence (not mapping_score) for the OCR threshold.
    # mapping_score reflects label match quality, not image/word readability.
    threshold = CRITICAL_CONFIDENCE if critical else NON_CRITICAL_CONFIDENCE
    conf = candidate.provider_confidence
    if conf is None:
        # Legacy candidates with no provider_confidence fall back to confidence.
        conf = candidate.confidence
    if conf is None or conf < threshold:
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
    _validate_summary_components(result)
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
                _warn_once(
                    line["line_total"].warnings,
                    f"line arithmetic mismatch: {qty} x {price} != {total}",
                )
        if total is None:
            have_all_line_totals = False
        else:
            line_total_sum += total

    header_total = _value(result.fields.get("total_amount"))
    if header_total is not None and have_all_line_totals and line_total_sum != header_total:
        _warn_once(
            result.warnings,
            f"sum of line totals ({line_total_sum}) does not equal invoice total ({header_total})",
        )


def _value(candidate):
    return candidate.normalized_value if candidate is not None else None


def _warn_once(warnings: list[str], message: str) -> None:
    """Append ``message`` unless already present.

    ``validate_extraction`` runs more than once over the same result (inside
    ``validate_extraction`` is called more than once on the same result, so a naive
    append would duplicate every arithmetic warning.
    """
    if message not in warnings:
        warnings.append(message)


_SUMMARY_COMPONENT_FIELDS = ("subtotal_amount", "tax_amount", "discount_amount", "shipping_amount")


def _validate_summary_components(result: m.InvoiceExtractionResult) -> None:
    """Warn when present summary components don't reconcile with the grand total.

    Only fires when *all* components AND the header total are present: a partial
    set triggers no arithmetic claim (plan quality invariant: be conservative).
    The formula: subtotal + tax - discount + shipping == total.
    """
    present = {name: _value(result.fields.get(name)) for name in _SUMMARY_COMPONENT_FIELDS}
    if any(v is None for v in present.values()):
        return
    header_total = _value(result.fields.get("total_amount"))
    if header_total is None:
        return
    subtotal = present["subtotal_amount"]
    tax = present["tax_amount"]
    discount = present["discount_amount"]
    shipping = present["shipping_amount"]
    expected = subtotal + tax + shipping - discount
    if expected != header_total:
        _warn_once(
            result.warnings,
            f"sum of components (subtotal {subtotal} + tax {tax} + shipping "
            f"{shipping} - discount {discount} = {expected}) does not equal "
            f"invoice total ({header_total})",
        )
