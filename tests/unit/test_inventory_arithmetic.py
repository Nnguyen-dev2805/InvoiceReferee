"""T03 tests — inventory/arithmetic and units/consistency independence.

RED first: fails with ``ModuleNotFoundError`` until the T03 modules exist.
Expected arithmetic values are computed here with an independent
``expected_line_amount`` helper (Rulebook §4), never by calling the production
evaluator.

Coverage: brief step 3 — SIMPLE_ITEMIZED line = qty x price (ROUND_HALF_UP per
line), line/total tolerance 1d, ITEMIZED_WITH_ADJUSTMENTS requires all terms
(no default 0), unknown template -> UNKNOWN, kg/g equivalence and a
kg-vs-g price-basis conflict, both sources agreeing yet arithmetic still
blocking, duplicate item IDs rejected before dict construction, unsupported
unit conversions -> UNKNOWN, mapping one-to-one coverage, TOTAL_ONLY N/A only
when no item region needs arithmetic.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext

import pytest

from invoice_referee.domain.models import (
    DocumentFacts,
    EvidenceBundle,
    FieldFact,
    ItemFacts,
    MappingProposal,
    QualityObservation,
    SourceBlock,
    SourceRef,
    SourceRegistry,
    SourceWord,
)
from invoice_referee.policy.decision import evaluate
from invoice_referee.policy.inventory import inventory_checks
from tests.builders import demo_policy, resolved_bundle, routine_snapshot

THRESHOLD = Decimal('0.85')


def expected_line_amount(quantity: Decimal, price: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 50
        return (quantity * price).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


# --- Independent document/registry construction --------------------------------

def _fact(field: str, raw: str, evidence_id: str, block_id: str, locator: str, word_id: str):
    ref = SourceRef(evidence_id=evidence_id, page_index=0, block_id=block_id,
                    locator=locator, raw_value=raw)
    fact = FieldFact(
        field=field, raw_value=raw, normalized_value=raw, refs=[ref],
        source_kind='DOCUMENT',
        observations=[QualityObservation(field=field, reading='READABLE',
                                         requires_verification=False, refs=[ref])],
        usability='USABLE', normalization_trace=[f'{field}:{raw}'],
    )
    return fact, SourceWord(id=word_id, text=raw, score='0.99')


def _block(evidence_id: str, block_id: str, locators: dict[str, tuple[FieldFact, SourceWord]]):
    words = [w for _f, w in locators.values()]
    return SourceBlock(
        evidence_id=evidence_id, page_index=0, block_id=block_id,
        text=' '.join(w.text for w in words),
        words=words, locators={loc: [w.id] for loc, (_f, w) in locators.items()},
    )


def _make_doc(
    evidence_id: str,
    *,
    kind: str = 'BILL',
    template: str = 'SIMPLE_ITEMIZED',
    merchant: str = 'Nhà cung cấp Demo',
    date: str = '2026-10-01',
    currency: str = 'VND',
    total: str = '900000',
    items: list[dict] | None = None,
    covered: list[str] | None = None,
    uncovered_regions: list[str] | None = None,
):
    """Build one document + registry whose facts resolve with score 0.99."""
    header: dict[str, tuple[FieldFact, SourceWord]] = {}
    fields: dict[str, FieldFact] = {}
    for name, raw in (('merchant', merchant), ('date', date),
                      ('currency', currency), ('total', total)):
        f, w = _fact(name, raw, evidence_id, 'b-h', name, f'w-h-{name}')
        fields[name] = f
        header[name] = (f, w)
    blocks = [_block(evidence_id, 'b-h', header)]

    item_records: list[ItemFacts] = []
    for idx, item in enumerate(items or []):
        iid = item['id']
        block_id = f'b-i-{idx}'
        local: dict[str, tuple[FieldFact, SourceWord]] = {}
        parts: dict[str, FieldFact] = {}
        for name, raw in (('name', item.get('name', 'Hàng')), ('quantity', item['quantity']),
                          ('unit', item['unit']), ('unit_price', item['unit_price']),
                          ('line_amount', item['line_amount'])):
            loc = f'{idx}_{name}'
            f, w = _fact(name, raw, evidence_id, block_id, loc, f'w-{loc}')
            parts[name] = f
            local[loc] = (f, w)
        blocks.append(_block(evidence_id, block_id, local))
        item_records.append(ItemFacts(
            id=iid, name=parts['name'], quantity=parts['quantity'], unit=parts['unit'],
            unit_price=parts['unit_price'], line_amount=parts['line_amount'],
        ))

    registry = SourceRegistry(evidence_id=evidence_id, blocks=blocks,
                              uncovered_item_regions=list(uncovered_regions or []))
    doc = DocumentFacts(
        evidence_id=evidence_id, kind=kind, template=template, fields=fields,
        items=item_records, covered_item_regions=list(covered or []),
    )
    return doc, registry


def _bundle(*docs_and_regs, mapping=None) -> EvidenceBundle:
    documents = [d for d, _r in docs_and_regs]
    registries = {d.evidence_id: r for d, r in docs_and_regs}
    return EvidenceBundle(documents=documents, registries=registries, mapping=mapping)


def _check(decision, rule_id):
    return next(c for c in decision.checks if c.rule_id == rule_id)


def _item(iid, *, qty, unit, price, line, name='Hàng'):
    return {'id': iid, 'name': name, 'quantity': qty, 'unit': unit,
            'unit_price': price, 'line_amount': line}


# --- SIMPLE_ITEMIZED arithmetic -------------------------------------------------

def test_line_amount_is_quantity_times_price_half_up():
    assert expected_line_amount(Decimal('3'), Decimal('100')) == Decimal('300')
    assert expected_line_amount(Decimal('0.5'), Decimal('3')) == Decimal('2')  # 1.5 -> 2
    assert expected_line_amount(Decimal('0.5'), Decimal('5')) == Decimal('3')  # 2.5 -> 3


def test_simple_itemized_pass_and_line_total_tolerance():
    doc, reg = _make_doc('e-primary', total='900000',
                         items=[_item('i1', qty='1', unit='kg', price='900000', line='900000')])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(900_000), bundle)
    assert _check(decision, 'AMT-02').status == 'PASS'


def test_one_dong_line_difference_is_within_tolerance():
    doc, reg = _make_doc('e-primary', total='300',
                         items=[_item('i1', qty='3', unit='cái', price='100', line='299')])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(300), bundle)
    assert _check(decision, 'AMT-02').status == 'PASS'


def test_line_mismatch_beyond_one_dong_fails_arithmetic():
    doc, reg = _make_doc('e-primary', total='300',
                         items=[_item('i1', qty='3', unit='cái', price='100', line='297')])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(300), bundle)
    assert _check(decision, 'AMT-02').status == 'FAIL'
    assert any('AMT-02' in i.blockers for i in decision.issues)


def test_arithmetic_conflict_blocks_even_when_sources_agree():
    # Both bill and receipt say 2 x 100 = 1: consistency agrees, arithmetic blocks.
    item = _item('i1', qty='2', unit='cái', price='100', line='1')
    primary, preg = _make_doc('e-primary', total='1', items=[item])
    receipt, rreg = _make_doc('e-receipt', kind='GOODS_RECEIPT', total='1', items=[item])
    mapping = MappingProposal(pairs=[('i1', 'i1')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    decision = evaluate(routine_snapshot(1, profile='WORK_PURCHASE'), bundle)
    assert _check(decision, 'AMT-02').status == 'FAIL'
    assert _check(decision, 'INV-02').status == 'PASS'  # sources agree
    assert decision.action == 'REQUEST_INFO'


def test_unknown_template_is_unknown_not_pass():
    doc, reg = _make_doc('e-primary', template='UNKNOWN', total='900000')
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(900_000), bundle)
    assert _check(decision, 'AMT-02').status == 'UNKNOWN'


def test_total_only_is_not_applicable_without_item_region():
    doc, reg = _make_doc('e-primary', template='TOTAL_ONLY', total='900000')
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(900_000), bundle)
    assert _check(decision, 'AMT-02').status == 'NOT_APPLICABLE'


def test_total_only_with_uncovered_item_region_is_unknown():
    doc, reg = _make_doc('e-primary', template='TOTAL_ONLY', total='900000',
                         uncovered_regions=['line-1'])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(900_000), bundle)
    assert _check(decision, 'AMT-02').status == 'UNKNOWN'


def test_total_only_with_item_facts_cannot_skip_arithmetic():
    doc, reg = _make_doc('e-primary', template='TOTAL_ONLY', total='100',
                         items=[_item('i1', qty='1', unit='cái', price='100', line='100')])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(100), bundle)
    assert _check(decision, 'AMT-02').status == 'UNKNOWN'


# --- ITEMIZED_WITH_ADJUSTMENTS --------------------------------------------------

def test_adjustments_template_missing_term_is_unknown_not_default_zero():
    # discount term absent -> must not default to 0; arithmetic UNKNOWN.
    doc, reg = _make_doc('e-primary', template='ITEMIZED_WITH_ADJUSTMENTS', total='900000')
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(900_000), bundle)
    assert _check(decision, 'AMT-02').status == 'UNKNOWN'


# --- Units and price basis ------------------------------------------------------

def test_kg_and_g_equivalent_unit_price_passes_inventory():
    bundle = resolved_bundle('900000', profile='WORK_PURCHASE')
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'PASS'


def test_kg_vs_g_price_basis_conflict_is_flagged():
    # 1000 VND/kg vs 1.5 VND/g -> 1 vs 1.5 VND/g: conflict at tolerance 0.
    primary, preg = _make_doc(
        'e-primary', total='1000',
        items=[_item('i1', qty='1', unit='kg', price='1000', line='1000')])
    receipt, rreg = _make_doc(
        'e-receipt', kind='GOODS_RECEIPT', total='1000',
        items=[_item('i1', qty='1', unit='g', price='1.5', line='2')])
    mapping = MappingProposal(pairs=[('i1', 'i1')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'FAIL'


def test_incompatible_units_are_unknown_not_a_ratio_guess():
    primary, preg = _make_doc(
        'e-primary', total='1000',
        items=[_item('i1', qty='1', unit='kg', price='1000', line='1000')])
    receipt, rreg = _make_doc(
        'e-receipt', kind='GOODS_RECEIPT', total='1000',
        items=[_item('i1', qty='1', unit='lít', price='1000', line='1000')])
    mapping = MappingProposal(pairs=[('i1', 'i1')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'UNKNOWN'


# --- Mapping coverage and duplicate IDs ----------------------------------------

def test_reordered_items_with_correct_mapping_pass():
    primary, preg = _make_doc('e-primary', total='300', items=[
        _item('i1', qty='1', unit='cái', price='100', line='100'),
        _item('i2', qty='1', unit='cái', price='200', line='200'),
    ])
    receipt, rreg = _make_doc('e-receipt', kind='GOODS_RECEIPT', total='300', items=[
        _item('r2', qty='1', unit='cái', price='200', line='200'),
        _item('r1', qty='1', unit='cái', price='100', line='100'),
    ])
    mapping = MappingProposal(pairs=[('i1', 'r1'), ('i2', 'r2')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'PASS'


def test_bad_pair_target_fails_coverage():
    primary, preg = _make_doc('e-primary', total='100',
                              items=[_item('i1', qty='1', unit='cái', price='100', line='100')])
    receipt, rreg = _make_doc('e-receipt', kind='GOODS_RECEIPT', total='100',
                              items=[_item('r1', qty='1', unit='cái', price='100', line='100')])
    mapping = MappingProposal(pairs=[('i1', 'missing')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'FAIL'


def test_extra_unmatched_item_fails_coverage():
    primary, preg = _make_doc('e-primary', total='300', items=[
        _item('i1', qty='1', unit='cái', price='100', line='100'),
        _item('i2', qty='1', unit='cái', price='200', line='200'),
    ])
    receipt, rreg = _make_doc('e-receipt', kind='GOODS_RECEIPT', total='300', items=[
        _item('r1', qty='1', unit='cái', price='100', line='100'),
        _item('r2', qty='1', unit='cái', price='200', line='200'),
    ])
    mapping = MappingProposal(pairs=[('i1', 'r1')], refs=[], conflicts=[])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status == 'FAIL'


def test_mapping_conflicts_block_even_when_item_numbers_match():
    # Item ids/quantities/prices line up, but the provider flagged a semantic
    # mapping conflict. INV-02 must not PASS and the case must not be approved.
    item = _item('i1', qty='1', unit='cái', price='100', line='100')
    primary, preg = _make_doc('e-primary', total='100', items=[item])
    receipt, rreg = _make_doc('e-receipt', kind='GOODS_RECEIPT', total='100', items=[item])
    mapping = MappingProposal(
        pairs=[('i1', 'i1')], refs=[], conflicts=['item name mismatch'])
    bundle = _bundle((primary, preg), (receipt, rreg), mapping=mapping)
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-02'].status != 'PASS'
    decision = evaluate(routine_snapshot(100, profile='WORK_PURCHASE'), bundle)
    assert decision.action != 'CREATE_PAYMENT_REQUEST'


def test_duplicate_item_ids_are_technical_invalid_analysis():
    doc, reg = _make_doc('e-primary', total='200', items=[
        _item('dup', qty='1', unit='cái', price='100', line='100'),
        _item('dup', qty='1', unit='cái', price='100', line='100'),
    ])
    bundle = _bundle((doc, reg))
    decision = evaluate(routine_snapshot(200), bundle)
    assert _check(decision, 'SRC-03').status == 'FAIL'
    assert decision.action == 'NONE'
    assert decision.technical_code == 'INVALID_ANALYSIS'


# --- Inventory applicability ----------------------------------------------------

def test_inventory_checks_not_applicable_without_goods_receipt():
    bundle = resolved_bundle('1200000', profile='TRAVEL')
    checks = {c.rule_id: c for c in inventory_checks(bundle, demo_policy())}
    assert checks['INV-01'].status == 'NOT_APPLICABLE'
    assert checks['INV-02'].status == 'NOT_APPLICABLE'


def test_work_purchase_without_received_full_fails_inv01():
    snap = routine_snapshot(900_000, profile='WORK_PURCHASE')
    snap = snap.model_copy(update={'claim': snap.claim.model_copy(update={'received_full': None})})
    decision = evaluate(snap, resolved_bundle('900000', profile='WORK_PURCHASE'))
    assert _check(decision, 'INV-01').status == 'FAIL'
    assert decision.action == 'REQUEST_INFO'
    assert any('INV-01' in i.blockers for i in decision.issues)
