"""Inventory, item arithmetic and cross-source consistency (T03, Rulebook §4/§3).

Pure evaluators. Two concerns, kept SEPARATE:

- ``arithmetic_checks`` (AMT-02) verifies line = quantity x unit price
  (ROUND_HALF_UP per line to đồng) and sum(lines) vs total with the 1đ
  tolerance. Two sources can agree and both be wrong, so this must block
  independently of consistency.
- ``inventory_checks`` (INV-01/INV-02) applies only when the profile needs a
  goods receipt: a formal receipt and received-full confirmation (INV-01), and
  one-to-one item mapping plus unit/date/supplier consistency (INV-02).

Duplicate item IDs are rejected BEFORE any dict construction (never drop or
overwrite a line). Unit prices are compared exactly (tolerance 0) on the same
normalized basis; quantities are normalized to a base unit first; different
opaque units without a valid conversion are UNKNOWN, never a guessed ratio.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from invoice_referee.domain.models import (
    CheckResult,
    DocumentFacts,
    EvidenceBundle,
    ItemFacts,
    PolicyConfig,
    SourceRegistry,
)
from invoice_referee.policy.numeric import DECIMAL_CONTEXT, UNIT_FACTORS
from invoice_referee.policy.quality import derive_fact

_PROFILE_REQUIRES_RECEIPT = {'WORK_PURCHASE'}

# Adjustment terms required for ITEMIZED_WITH_ADJUSTMENTS; unclear term must not
# default to 0.
_ADJUSTMENT_TERMS = ('subtotal', 'tax', 'fees', 'discount')


def _derive_value(
    fact, registry: SourceRegistry, policy: PolicyConfig
) -> Decimal | None:
    if fact is None:
        return None
    threshold = Decimal(policy.word_review_threshold)
    derived = derive_fact(fact, registry, True, threshold, None)
    if derived.usability != 'USABLE':
        return None
    try:
        with localcontext(DECIMAL_CONTEXT):
            value = Decimal(str(derived.normalized_value))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _line_amount(quantity: Decimal, price: Decimal) -> Decimal:
    with localcontext(DECIMAL_CONTEXT):
        return (quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _document_arithmetic(
    doc: DocumentFacts, registry: SourceRegistry, policy: PolicyConfig
) -> str:
    """Return one of PASS / FAIL / UNKNOWN / NOT_APPLICABLE for AMT-02."""
    if doc.template == 'UNKNOWN':
        return 'UNKNOWN'
    if doc.template == 'TOTAL_ONLY':
        # TOTAL_ONLY is only valid when no item region needs a breakdown. Items
        # carrying quantity/unit-price facts contradict the declared template, so
        # arithmetic must be checked (UNKNOWN) rather than skipped.
        needs = (
            bool(doc.covered_item_regions)
            or bool(registry.uncovered_item_regions)
            or bool(doc.items)
        )
        return 'UNKNOWN' if needs else 'NOT_APPLICABLE'
    if doc.template == 'ITEMIZED_WITH_ADJUSTMENTS':
        if any(name not in doc.fields for name in _ADJUSTMENT_TERMS):
            return 'UNKNOWN'  # a missing term must not default to 0
        return 'UNKNOWN'  # subtotal/tax/fees/discount basis not modeled in T03 inputs

    # SIMPLE_ITEMIZED
    tolerance = Decimal(policy.comparison_money_tolerance)
    if not doc.items:
        return 'UNKNOWN'
    line_total = Decimal('0')
    for item in doc.items:
        quantity = _derive_value(item.quantity, registry, policy)
        price = _derive_value(item.unit_price, registry, policy)
        line = _derive_value(item.line_amount, registry, policy)
        if quantity is None or price is None or line is None:
            return 'UNKNOWN'
        if abs(_line_amount(quantity, price) - line) > tolerance:
            return 'FAIL'
        line_total += line
    total = _derive_value(doc.fields.get('total'), registry, policy)
    if total is None:
        return 'UNKNOWN'
    if abs(line_total - total) > tolerance:
        return 'FAIL'
    return 'PASS'


def arithmetic_checks(bundle: EvidenceBundle, policy: PolicyConfig) -> list[CheckResult]:
    """AMT-02 across all documents (worst status wins); independent of INV-02."""
    statuses: list[str] = []
    refs = []
    for doc in bundle.documents:
        registry = bundle.registries.get(doc.evidence_id)
        if registry is None:
            statuses.append('UNKNOWN')
            continue
        statuses.append(_document_arithmetic(doc, registry, policy))
    if any(s == 'FAIL' for s in statuses):
        status = 'FAIL'
        reason = 'Arithmetic có mâu thuẫn ở phép kiểm áp dụng.'
    elif any(s == 'UNKNOWN' for s in statuses):
        status = 'UNKNOWN'
        reason = 'Template/basis chưa đủ để kiểm arithmetic.'
    elif any(s == 'PASS' for s in statuses):
        status = 'PASS'
        reason = 'Line = quantity x price và tổng khớp trong tolerance.'
    else:
        status = 'NOT_APPLICABLE'
        reason = 'TOTAL_ONLY không có vùng item cần breakdown.'
    return [CheckResult(
        rule_id='AMT-02', status=status, dependencies=['items', 'total'], refs=refs,
        reason=reason, issue_ids=[],
    )]


def _price_per_base(price: Decimal, unit: str) -> tuple[Decimal, str]:
    base, factor = UNIT_FACTORS.get(unit.strip().lower(), (unit.strip().lower(), '1'))
    with localcontext(DECIMAL_CONTEXT):
        return price / Decimal(factor), base


def _items_by_id(doc: DocumentFacts) -> dict[str, ItemFacts]:
    result: dict[str, ItemFacts] = {}
    for item in doc.items:  # duplicate IDs already rejected upstream
        result[item.id] = item
    return result


def _consistency_status(
    bundle: EvidenceBundle, policy: PolicyConfig
) -> tuple[str, list[str]]:
    """INV-02 status plus machine-readable conflict reasons."""
    primary = next((d for d in bundle.documents if d.kind == 'BILL'), None)
    receipt = next((d for d in bundle.documents if d.kind == 'GOODS_RECEIPT'), None)
    if primary is None or receipt is None:
        return 'UNKNOWN', ['missing primary or receipt document']
    if bundle.mapping is None:
        return 'FAIL', ['no mapping proposal']

    # Provider-flagged semantic mapping conflicts are contradictory output and
    # must never be dropped before aggregation (AGENTS.md). Even when item
    # numbers happen to line up, a flagged conflict is a factual blocker
    # (Rulebook §3 INV-02), so INV-02 cannot PASS.
    if bundle.mapping.conflicts:
        return 'UNKNOWN', ['mapping conflicts: ' + '; '.join(bundle.mapping.conflicts)]

    preg = bundle.registries.get(primary.evidence_id)
    rreg = bundle.registries.get(receipt.evidence_id)
    if preg is None or rreg is None:
        return 'UNKNOWN', ['missing registry for document']

    # Reject duplicate item IDs BEFORE building any dict, so a line can never be
    # dropped or overwritten. The reducer reports this as technical SRC-03.
    for doc in (primary, receipt):
        ids = [item.id for item in doc.items]
        if len(ids) != len(set(ids)):
            return 'FAIL', [f'duplicate item ID in {doc.evidence_id}']

    primary_items = _items_by_id(primary)
    receipt_items = _items_by_id(receipt)
    seen_primary: set[str] = set()
    seen_receipt: set[str] = set()
    conflicts: list[str] = []
    unknown: list[str] = []

    for pair in bundle.mapping.pairs:
        if len(pair) != 2:
            conflicts.append('malformed mapping pair')
            continue
        pid, rid = pair
        if pid not in primary_items or rid not in receipt_items:
            conflicts.append(f'unresolved mapping pair {pid}->{rid}')
            continue
        if pid in seen_primary or rid in seen_receipt:
            conflicts.append(f'duplicate mapping for {pid}/{rid}')
            continue
        seen_primary.add(pid)
        seen_receipt.add(rid)
        status, detail = _compare_items(
            primary_items[pid], receipt_items[rid], preg, rreg, policy)
        if status == 'FAIL':
            conflicts.append(detail)
        elif status == 'UNKNOWN':
            unknown.append(detail)

    # Full one-to-one coverage: no unmatched line may be silently ignored.
    if set(primary_items) - seen_primary:
        conflicts.append('unmatched primary item(s): ' + ','.join(sorted(set(primary_items) - seen_primary)))
    if set(receipt_items) - seen_receipt:
        conflicts.append('unmatched receipt item(s): ' + ','.join(sorted(set(receipt_items) - seen_receipt)))

    if conflicts:
        return 'FAIL', conflicts
    if unknown:
        return 'UNKNOWN', unknown
    return 'PASS', []


def _compare_items(
    p_item: ItemFacts,
    r_item: ItemFacts,
    preg: SourceRegistry,
    rreg: SourceRegistry,
    policy: PolicyConfig,
) -> tuple[str, str]:
    p_unit_name = str(p_item.unit.normalized_value)
    r_unit_name = str(r_item.unit.normalized_value)
    p_price = _derive_value(p_item.unit_price, preg, policy)
    r_price = _derive_value(r_item.unit_price, rreg, policy)
    p_qty = _derive_value(p_item.quantity, preg, policy)
    r_qty = _derive_value(r_item.quantity, rreg, policy)
    if None in (p_price, r_price, p_qty, r_qty):
        return 'UNKNOWN', f'unusable item numeric for {p_item.id}/{r_item.id}'

    # Unit price on the same normalized basis, exact (tolerance 0).
    p_price_base, p_base = _price_per_base(p_price, p_unit_name)
    r_price_base, r_base = _price_per_base(r_price, r_unit_name)
    if p_base != r_base:
        return 'UNKNOWN', f'incompatible units {p_unit_name} vs {r_unit_name}'
    if abs(p_price_base - r_price_base) > Decimal(policy.normalized_unit_price_tolerance):
        return 'FAIL', f'unit-price basis mismatch {p_item.id}/{r_item.id}'

    # Quantities on the same base unit (only when units are convertible).
    p_qty_base, p_qbase = _normalize_qty(p_qty, p_unit_name)
    r_qty_base, r_qbase = _normalize_qty(r_qty, r_unit_name)
    if p_qbase == r_qbase and p_qty_base != r_qty_base:
        return 'FAIL', f'quantity mismatch {p_item.id}/{r_item.id}'
    return 'PASS', ''


def _normalize_qty(qty: Decimal, unit: str) -> tuple[Decimal, str]:
    base, factor = UNIT_FACTORS.get(unit.strip().lower(), (unit.strip().lower(), '1'))
    with localcontext(DECIMAL_CONTEXT):
        return qty * Decimal(factor), base


def _supplier_date_status(bundle: EvidenceBundle, policy: PolicyConfig) -> tuple[str, str]:
    primary = next((d for d in bundle.documents if d.kind == 'BILL'), None)
    receipt = next((d for d in bundle.documents if d.kind == 'GOODS_RECEIPT'), None)
    if primary is None or receipt is None:
        return 'UNKNOWN', 'missing document'
    p_merchant = primary.fields.get('merchant')
    r_merchant = receipt.fields.get('merchant')
    if p_merchant and r_merchant and p_merchant.normalized_value != r_merchant.normalized_value:
        return 'FAIL', 'supplier mismatch'

    p_date = _parse_date(str(primary.fields['date'].normalized_value)) if 'date' in primary.fields else None
    r_date = _parse_date(str(receipt.fields['date'].normalized_value)) if 'date' in receipt.fields else None
    if p_date is not None and r_date is not None:
        gap = abs((r_date - p_date).days)
        if gap > policy.inventory_date_gap_days:  # inclusive: gap <= 7 passes
            return 'FAIL', f'date gap {gap} > {policy.inventory_date_gap_days} ngày'
    return 'PASS', ''


def _parse_date(value: str):
    from datetime import date

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def inventory_checks(
    bundle: EvidenceBundle,
    policy: PolicyConfig,
    *,
    profile: str | None = None,
    received_full: bool | None = None,
) -> list[CheckResult]:
    """INV-01/INV-02; NOT_APPLICABLE when the profile needs no goods receipt.

    ``profile``/``received_full`` are optional so the evaluator can pass the
    declaration; a two-argument call infers applicability from the bundle.
    """
    has_receipt = any(d.kind == 'GOODS_RECEIPT' for d in bundle.documents)
    if profile is not None:
        requires = profile in _PROFILE_REQUIRES_RECEIPT
    else:
        requires = has_receipt

    if not requires:
        return [
            CheckResult(rule_id='INV-01', status='NOT_APPLICABLE', dependencies=[], refs=[],
                        reason='Profile không cần nguồn giao nhận.', issue_ids=[]),
            CheckResult(rule_id='INV-02', status='NOT_APPLICABLE', dependencies=[], refs=[],
                        reason='Profile không cần đối chiếu inventory.', issue_ids=[]),
        ]

    checks: list[CheckResult] = []

    # INV-01: formal receipt present and received-full confirmed.
    if not has_receipt:
        checks.append(CheckResult(
            rule_id='INV-01', status='FAIL', dependencies=['GOODS_RECEIPT'], refs=[],
            reason='Thiếu formal receipt cho hàng đã nhận.', issue_ids=['INV-01:receipt']))
    elif received_full is None:
        checks.append(CheckResult(
            rule_id='INV-01', status='FAIL', dependencies=['received_full'], refs=[],
            reason='Chưa xác nhận đã nhận đủ hàng.', issue_ids=['INV-01:received_full']))
    elif received_full is False:
        checks.append(CheckResult(
            rule_id='INV-01', status='FAIL', dependencies=['received_full'], refs=[],
            reason='Khai báo chưa nhận đủ hàng.', issue_ids=['INV-01:received_full']))
    else:
        checks.append(CheckResult(
            rule_id='INV-01', status='PASS', dependencies=['GOODS_RECEIPT', 'received_full'],
            refs=[], reason='Có receipt và xác nhận nhận đủ.', issue_ids=[]))

    # INV-02: mapping/quantity/units/dates/supplier consistency.
    status, details = _consistency_status(bundle, policy)
    supplier_status, supplier_detail = _supplier_date_status(bundle, policy)
    if supplier_status == 'FAIL':
        status = 'FAIL'
        details = [*details, supplier_detail]
    issue_ids = ['INV-02:consistency'] if status in ('FAIL', 'UNKNOWN') else []
    reason = 'Đối chiếu inventory ổn.' if status == 'PASS' else '; '.join(details) or 'Chưa đủ căn cứ đối chiếu.'
    checks.append(CheckResult(
        rule_id='INV-02', status=status,
        dependencies=['mapping', 'items', 'units'], refs=[],
        reason=reason, issue_ids=issue_ids))
    return checks
