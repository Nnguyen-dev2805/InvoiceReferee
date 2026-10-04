"""Gold-independent synthetic builders for T01 contract tests (master §3.3).

These helpers construct declared input, evidence facts and source registries
directly from concrete values. They NEVER call a production evaluator to derive
an expected answer, so a test failure means the contract/evaluator is wrong, not
that the builder mirrored it.

Consistency rule (master §3.3): ``resolved_bundle(amount)`` passes the SAME
amount into document facts and registry text. Changing the amount in a fact while
leaving registry text at 1,200,000 would be an invalid source, not a valid
boundary test.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from invoice_referee.domain.models import (
    CaseSnapshot,
    Claim,
    DocumentFacts,
    Evidence,
    EvidenceBundle,
    FieldFact,
    HumanAction,
    ItemFacts,
    MappingProposal,
    PolicyConfig,
    QualityObservation,
    SourceBlock,
    SourceRef,
    SourceRegistry,
    SourceWord,
)

POLICY_VERSION = 'demo-expense-v0.1-proposed'
DEMO_MERCHANT = 'Nhà cung cấp Demo'
PRIMARY_DATE = '2026-10-01'
RECEIPT_DATE = '2026-10-02'


def _canonical(value: Decimal) -> str:
    """Canonical decimal string: no separators, no exponent, no trailing zeros."""
    with localcontext() as ctx:
        ctx.prec = 50
        return format(value.normalize(), 'f')


def demo_policy(*, active: bool = True) -> PolicyConfig:
    """Test policy. Origin is ``proposed_test_fixture`` (never a live activation)."""
    return PolicyConfig(
        version=POLICY_VERSION,
        origin='proposed_test_fixture',
        activation_id='fixture-activation' if active else None,
        active=active,
        currency='VND',
        auto_approval_max=2_000_000,
        standard_policy_max=5_000_000,
        inventory_date_gap_days=7,
        comparison_money_tolerance='1',
        normalized_unit_price_tolerance='0',
        word_review_threshold='0.85',
        threshold_version=POLICY_VERSION,
    )


# --- Internal source-model helpers --------------------------------------------

def _header_values(evidence_id: str, amount: str) -> dict[str, str]:
    """Merchant/date/currency/total; dates differ for primary vs receipt."""
    date = RECEIPT_DATE if evidence_id.endswith('receipt') else PRIMARY_DATE
    return {
        'merchant': DEMO_MERCHANT,
        'date': date,
        'currency': 'VND',
        'total': amount,
    }


def _item_basis(evidence_id: str, amount: str) -> dict[str, str]:
    """Item line basis. Receipt is 1000 g at amount/1000 VND/g; primary 1 kg at amount VND/kg."""
    with localcontext() as ctx:
        ctx.prec = 50
        amt = Decimal(amount)
        if evidence_id.endswith('receipt'):
            quantity, unit, unit_price = Decimal(1000), 'g', amt / Decimal(1000)
        else:
            quantity, unit, unit_price = Decimal(1), 'kg', amt
    return {
        'name': 'Vật tư demo',
        'quantity': _canonical(quantity),
        'unit': unit,
        'unit_price': _canonical(unit_price),
        'line_amount': _canonical(amt),
    }


def _source_refs(evidence_id: str, amount: str) -> dict[str, SourceRef]:
    """Refs keyed by locator; (block_id, locator) pairs match ``text_registry``."""
    refs: dict[str, SourceRef] = {}
    for name, value in _header_values(evidence_id, amount).items():
        refs[name] = SourceRef(
            evidence_id=evidence_id, page_index=0, block_id='b-1',
            locator=name, raw_value=value,
        )
    for key, value in _item_basis(evidence_id, amount).items():
        locator = f'item_{key}_1'
        refs[locator] = SourceRef(
            evidence_id=evidence_id, page_index=0, block_id='b-2',
            locator=locator, raw_value=value,
        )
    return refs


def _document_kind(evidence_id: str) -> str:
    return 'GOODS_RECEIPT' if evidence_id.endswith('receipt') else 'BILL'


def _item_id(evidence_id: str) -> str:
    return 'i-receipt-1' if evidence_id.endswith('receipt') else 'i-primary-1'


def _fact(field: str, raw_value: str, ref: SourceRef) -> FieldFact:
    return FieldFact(
        field=field,
        raw_value=raw_value,
        normalized_value=raw_value,
        refs=[ref],
        source_kind='DOCUMENT',
        observations=[
            QualityObservation(
                field=field, reading='READABLE', requires_verification=False, refs=[ref]
            )
        ],
        usability='USABLE',
        normalization_trace=[f'{field}: "{raw_value}" -> "{raw_value}"'],
    )


# --- Public builders ----------------------------------------------------------

def text_registry(
    *, evidence_id: str = 'e-primary', score: str | None = '0.99', amount: str = '1200000'
) -> SourceRegistry:
    """Real registry covering the facts ``document_facts`` creates for this evidence."""
    header = _header_values(evidence_id, amount)
    header_words = [SourceWord(id=f'w-{name}', text=value, score=score) for name, value in header.items()]
    header_locators = {name: [f'w-{name}'] for name in header}
    blocks = [
        SourceBlock(
            evidence_id=evidence_id, page_index=0, block_id='b-1',
            text=' '.join(header.values()), words=header_words, locators=header_locators,
        )
    ]

    basis = _item_basis(evidence_id, amount)
    item_words = [SourceWord(id=f'w-item-{key}', text=value, score=score) for key, value in basis.items()]
    item_locators = {f'item_{key}_1': [f'w-item-{key}'] for key in basis}
    blocks.append(
        SourceBlock(
            evidence_id=evidence_id, page_index=0, block_id='b-2',
            text=' '.join(basis.values()), words=item_words, locators=item_locators,
        )
    )
    return SourceRegistry(evidence_id=evidence_id, blocks=blocks)


def document_facts(
    amount: str = '1200000',
    *,
    evidence_id: str = 'e-primary',
    template: str = 'TOTAL_ONLY',
    score: str | None = '0.99',
) -> DocumentFacts:
    """Document facts whose refs resolve in ``text_registry`` for the same args.

    ``score`` is accepted for symmetry with the registry; facts themselves carry
    no score (scores live on source words).
    """
    del score  # scores live on the registry words, not on facts
    refs = _source_refs(evidence_id, amount)
    fields = {
        name: _fact(name, value, refs[name])
        for name, value in _header_values(evidence_id, amount).items()
    }

    items: list[ItemFacts] = []
    covered: list[str] = []
    if template != 'TOTAL_ONLY':
        basis = _item_basis(evidence_id, amount)
        items = [
            ItemFacts(
                id=_item_id(evidence_id),
                name=_fact('name', basis['name'], refs['item_name_1']),
                quantity=_fact('quantity', basis['quantity'], refs['item_quantity_1']),
                unit=_fact('unit', basis['unit'], refs['item_unit_1']),
                unit_price=_fact('unit_price', basis['unit_price'], refs['item_unit_price_1']),
                line_amount=_fact('line_amount', basis['line_amount'], refs['item_line_amount_1']),
            )
        ]
        covered = ['line-1']

    return DocumentFacts(
        evidence_id=evidence_id,
        kind=_document_kind(evidence_id),
        template=template,
        fields=fields,
        items=items,
        covered_item_regions=covered,
    )


def resolved_bundle(amount: str = '1200000', *, profile: str = 'TRAVEL') -> EvidenceBundle:
    """Usable documents + registries (and mapping for WORK_PURCHASE); no evaluator."""
    if profile == 'WORK_PURCHASE':
        primary = document_facts(amount, evidence_id='e-primary', template='SIMPLE_ITEMIZED')
        receipt = document_facts(amount, evidence_id='e-receipt', template='SIMPLE_ITEMIZED')
        registries = {
            'e-primary': text_registry(evidence_id='e-primary', amount=amount),
            'e-receipt': text_registry(evidence_id='e-receipt', amount=amount),
        }
        mapping = MappingProposal(
            pairs=[('i-primary-1', 'i-receipt-1')],
            refs=[primary.fields['total'].refs[0]],
            conflicts=[],
        )
        return EvidenceBundle(documents=[primary, receipt], registries=registries, mapping=mapping)

    primary = document_facts(amount, evidence_id='e-primary', template='TOTAL_ONLY')
    registries = {'e-primary': text_registry(evidence_id='e-primary', amount=amount)}
    return EvidenceBundle(documents=[primary], registries=registries, mapping=None)


def routine_snapshot(amount: int = 1_200_000, profile: str = 'TRAVEL') -> CaseSnapshot:
    """Declared input plus the required Evidence IDs for the given profile."""
    if profile == 'WORK_PURCHASE':
        purpose, trip, attendees, received_full = 'Mua vật tư demo', '', [], True
    elif profile == 'CLIENT_MEAL':
        purpose, trip, attendees, received_full = 'Tiếp khách demo', '', ['Khách A'], None
    else:
        purpose, trip, attendees, received_full = 'Công tác demo', 'Chuyến công tác demo', [], None

    claim = Claim(
        employee_id='emp-demo',
        profile=profile,
        purpose_type='BUSINESS',
        purpose=purpose,
        trip=trip,
        attendees=attendees,
        requested_amount_vnd=amount,
        payer_type='PERSONAL',
        received_full=received_full,
    )

    roles = ['PRIMARY_BILL']
    if profile == 'WORK_PURCHASE':
        roles.append('GOODS_RECEIPT')
    evidence = [
        Evidence(
            id=f'e-{i}',
            case_id='case-demo',
            role=role,
            original_name=f'{role.lower()}.pdf',
            stored_path=f'data/case-demo/{role.lower()}.pdf',
            sha256=f'{i:064d}',
            mime='application/pdf',
            size=1024,
        )
        for i, role in enumerate(roles, start=1)
    ]

    snapshot = CaseSnapshot(
        case_id='case-demo',
        case_version=1,
        claim=claim,
        evidence=evidence,
        policy=demo_policy(),
        authorizations=[],
        confirmations=[],
        active_action_ids=[],
        input_hash='',
    )
    from invoice_referee.config import snapshot_hash

    return snapshot.model_copy(update={'input_hash': snapshot_hash(snapshot)})


def human_action(
    snapshot: CaseSnapshot,
    *,
    kind: str,
    mode: str,
    payload: dict,
    issue_id: str | None = None,
    reason: str = 'Đã xem chứng từ gốc',
) -> HumanAction:
    """Scoped action with identity/time/version; not itself validated for authority."""
    return HumanAction(
        id=f'ha-{uuid.uuid4().hex[:12]}',
        case_id=snapshot.case_id,
        case_version=snapshot.case_version,
        issue_id=issue_id,
        mode=mode,
        kind=kind,
        payload=payload,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )
