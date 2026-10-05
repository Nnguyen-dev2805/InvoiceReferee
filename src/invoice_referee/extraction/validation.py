"""Contract validation for model-produced ``DocumentFacts`` (T05, System §3/§4).

``validate_document`` is the deterministic gate between a Kimi proposal and the
evaluators. It rejects contract violations (``DomainError('INVALID_ANALYSIS')``)
and fails closed on quality gaps:

- ownership: the document must belong to the analyzed evidence;
- uniqueness: item IDs unique, no ID claimed twice;
- refs: every ref resolves in the request registry and belongs to this evidence;
- coverage: regions the model claims covered must exist in the registry; if the
  registry has uncovered item regions the model must not claim ``TOTAL_ONLY``;
- quality consistency: an UNREADABLE/UNKNOWN observation claiming no verification
  is a contradiction, and a document cannot be ``UNKNOWN`` while asserting it
  needs no verification;
- applicability: a document template proposal may not waive a mandatory check.

Applicability is decided by CODE (``is_applicable``), never by the model: a
model may not mark a mandatory inventory/arithmetic check NOT_APPLICABLE.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from invoice_referee.domain.models import (
    AnalysisRequest,
    DocumentFacts,
    DomainError,
    FieldFact,
    ItemFacts,
    SourceRef,
    SourceRegistry,
)
from invoice_referee.policy.quality import derive_fact

_VERIFICATION_READINGS = ('UNREADABLE', 'UNKNOWN')

# One shared JSON/contract repair per invocation (System §4 / master §Global).
REPAIR_BUDGET = 1

# B1 word-review threshold (Rulebook §1). It is a fixed B1 review parameter, not
# a probability; ``request.threshold_version`` is carried as identity, not parsed
# as the numeric value. T06 re-derives numeric usability with the ACTIVE policy
# threshold before evaluate, so a calibrated B2 threshold still applies.
B1_WORD_REVIEW_THRESHOLD = Decimal('0.85')

# Fields that carry a number the arithmetic/eligibility checks depend on. Includes
# the ITEMIZED_WITH_ADJUSTMENTS terms (subtotal/tax/fees/discount) so those also
# get word-score gating instead of passing on a resolvable ref alone.
NUMERIC_FIELDS = frozenset({
    'total', 'subtotal', 'tax', 'fees', 'discount',
    'quantity', 'unit_price', 'line_amount',
})


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_ANALYSIS', message)


# --- Repair budget -------------------------------------------------------------

def shared_repair_allowed(repair_count: int) -> bool:
    """True while the single shared JSON/contract repair is still available.

    JSON parse, schema, ID uniqueness, source coverage and contradiction checks
    all draw from the SAME budget; a second malformed/invalid response is a
    technical failure, never another retry.
    """
    return repair_count < REPAIR_BUDGET


# --- Applicability (code decides, not the model) -------------------------------

def is_applicable(doc: DocumentFacts, check: str, registry: SourceRegistry) -> bool:
    """Whether ``check`` applies to this document, from structure alone.

    The model's ``template`` is a PROPOSAL. Code overrides it: a ``TOTAL_ONLY``
    claim cannot apply when the registry has uncovered item regions, or when the
    facts already carry quantity/unit-price that arithmetic would need — the
    breakdown check stays applicable so a model cannot waive it.
    """
    if check == 'breakdown':
        if registry.uncovered_item_regions:
            return True
        if doc.template in ('SIMPLE_ITEMIZED', 'ITEMIZED_WITH_ADJUSTMENTS'):
            return True
        return bool(doc.items) and _items_carry_arithmetic_basis(doc.items)
    if check == 'inventory':
        return bool(doc.items) or doc.kind == 'GOODS_RECEIPT'
    raise DomainError('INVALID_INPUT', f'unknown check {check!r}')


def _items_carry_arithmetic_basis(items: Iterable[ItemFacts]) -> bool:
    for item in items:
        if item.quantity.usability != 'MISSING' and item.unit_price.usability != 'MISSING':
            return True
    return False


# --- Contradiction (T02 quality contract) --------------------------------------

def _observation_contradiction(fact: FieldFact) -> bool:
    return any(
        obs.reading in _VERIFICATION_READINGS and not obs.requires_verification
        for obs in fact.observations
    )


def is_contradiction(doc: DocumentFacts) -> bool:
    """True when any fact contradicts its own quality observations.

    A model may not turn an UNREADABLE/UNKNOWN reading into a pass by asserting
    ``requires_verification=false`` (System §3); that is a contract contradiction
    to reject, never a silent USABLE.
    """
    return any(_observation_contradiction(fact) for fact in _all_facts(doc))


# --- Ref / coverage resolution -------------------------------------------------

def _all_facts(doc: DocumentFacts) -> list[FieldFact]:
    facts = list(doc.fields.values())
    for item in doc.items:
        facts.extend([item.name, item.quantity, item.unit, item.unit_price, item.line_amount])
    return facts


def _find_block(registry: SourceRegistry, ref: SourceRef):
    for block in registry.blocks:
        if (
            block.block_id == ref.block_id
            and block.page_index == ref.page_index
            and block.evidence_id == ref.evidence_id
        ):
            return block
    return None


def check_ref(ref: SourceRef, registry: SourceRegistry) -> None:
    """Raise ``INVALID_ANALYSIS`` unless ``ref`` resolves in ``registry``.

    Public so the cross-source mapping validator can resolve a proposal's refs
    against the bundle's registries with the same rule.
    """
    if ref.evidence_id != registry.evidence_id:
        raise _invalid(
            f'ref evidence {ref.evidence_id!r} not in registry {registry.evidence_id!r}'
        )
    block = _find_block(registry, ref)
    if block is None:
        raise _invalid(f'ref block {ref.block_id!r}@{ref.page_index} not in registry')
    if ref.locator not in block.locators:
        raise _invalid(f'locator {ref.locator!r} not in block {ref.block_id!r}')


def _validate_refs(doc: DocumentFacts, registry: SourceRegistry) -> None:
    for fact in _all_facts(doc):
        for ref in fact.refs:
            check_ref(ref, registry)
        for obs in fact.observations:
            for ref in obs.refs:
                check_ref(ref, registry)


def _validate_coverage(doc: DocumentFacts, registry: SourceRegistry) -> None:
    """Enforce the anti-waiver intent against OCR item regions, by direction only.

    ``registry.uncovered_item_regions`` lists item regions OCR detected (table
    blocks/tables). The region vocabulary is OCR-internal and opaque, so this
    check does NOT require the document's ``covered_item_regions`` labels to match
    the OCR ids — a valid itemized document uses its own labels and must pass.
    What is enforced:

    - a document may not answer OCR item regions with ``TOTAL_ONLY`` (which skips
      breakdown) — fail-closed anti-waiver;
    - an itemized template must actually carry items (a bare template claim that
      skips the breakdown is rejected);
    - claiming covered regions with no items is contradictory.
    """
    ocr_regions = set(registry.uncovered_item_regions)
    claimed = set(doc.covered_item_regions)
    if doc.template == 'TOTAL_ONLY' and ocr_regions:
        raise _invalid(
            'TOTAL_ONLY claimed while OCR detected item regions '
            f'{sorted(ocr_regions)}'
        )
    if doc.template in ('SIMPLE_ITEMIZED', 'ITEMIZED_WITH_ADJUSTMENTS') and not doc.items:
        raise _invalid(f'{doc.template} claimed without any items')
    if claimed and not doc.items:
        raise _invalid('covered regions claimed without any items')


# --- Public validator ----------------------------------------------------------

def validate_document(doc: DocumentFacts, request: AnalysisRequest) -> DocumentFacts:
    """Validate ``doc`` against ``request`` and return it with derived usability.

    Raises ``DomainError('INVALID_ANALYSIS')`` for ownership/uniqueness/ref/
    coverage/contradiction violations. On success every field's usability is
    DERIVED from the real registry coverage (never trusted from the model), so
    missing scores, uncovered numeric spans or unreadable readings become
    UNCERTAIN rather than a silent PASS.
    """
    if doc.evidence_id != request.evidence.id:
        raise _invalid(
            f'document evidence {doc.evidence_id!r} != request evidence '
            f'{request.evidence.id!r}'
        )
    if request.registry.evidence_id != request.evidence.id:
        raise _invalid(
            f'registry evidence {request.registry.evidence_id!r} != request evidence '
            f'{request.evidence.id!r}'
        )

    _validate_unique_ids(doc)
    _validate_refs(doc, request.registry)
    _validate_coverage(doc, request.registry)

    if is_contradiction(doc):
        raise _invalid('document contradicts its own quality observations')

    return _derive_usability(doc, request)


def _validate_unique_ids(doc: DocumentFacts) -> None:
    seen: set[str] = set()
    for item in doc.items:
        if item.id in seen:
            raise _invalid(f'duplicate item id {item.id!r}')
        seen.add(item.id)


def _derive_usability(doc: DocumentFacts, request: AnalysisRequest) -> DocumentFacts:
    threshold = B1_WORD_REVIEW_THRESHOLD
    new_fields = {
        name: derive_fact(fact, request.registry, _is_numeric(name), threshold, None)
        for name, fact in doc.fields.items()
    }
    new_items = [
        ItemFacts(
            id=item.id,
            name=derive_fact(item.name, request.registry, False, threshold, None),
            quantity=derive_fact(item.quantity, request.registry, True, threshold, None),
            unit=derive_fact(item.unit, request.registry, False, threshold, None),
            unit_price=derive_fact(item.unit_price, request.registry, True, threshold, None),
            line_amount=derive_fact(item.line_amount, request.registry, True, threshold, None),
        )
        for item in doc.items
    ]
    return doc.model_copy(update={'fields': new_fields, 'items': new_items})


def _is_numeric(field: str) -> bool:
    return field in NUMERIC_FIELDS


__all__ = [
    'B1_WORD_REVIEW_THRESHOLD',
    'REPAIR_BUDGET',
    'NUMERIC_FIELDS',
    'check_ref',
    'is_applicable',
    'is_contradiction',
    'shared_repair_allowed',
    'validate_document',
]
