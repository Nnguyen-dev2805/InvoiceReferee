"""Derived field usability from real source coverage (T02, System §3).

A field having a value does not make it usable. ``derive_fact`` resolves the
fact's refs against the ACTUAL ``SourceRegistry`` and returns a NEW ``FieldFact``
whose ``usability`` reflects the evidence:

- ``USABLE``    — source/raw/normalization valid and required quality met, or a
                  valid reviewer ``CONFIRM_FIELD`` for the exact field/value.
- ``MISSING``   — no raw value at all.
- ``UNCERTAIN`` — a candidate exists but coverage is missing/low, or the field
                  carries an unreadable/unknown observation needing verification.
- ``UNUSABLE``  — a value is claimed without a resolvable source.

Contract violations raise ``DomainError('INVALID_ANALYSIS')`` instead of being
downgraded to a quality result: bad/foreign refs, unknown locators/word IDs,
duplicate/odd scores, and an UNREADABLE/UNKNOWN observation that claims no
verification is required. A model READABLE reading never waives missing or
low-score numeric coverage; scores are review parameters, not probabilities.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Sequence

from pydantic import ValidationError

from invoice_referee.domain.models import (
    DomainError,
    FieldFact,
    HumanAction,
    QualityObservation,
    SourceRef,
    SourceRegistry,
    SourceWord,
)
from invoice_referee.policy.numeric import DECIMAL_CONTEXT

_VERIFICATION_READINGS = ('UNREADABLE', 'UNKNOWN')


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_ANALYSIS', message)


def _find_block(registry: SourceRegistry, ref: SourceRef):
    for block in registry.blocks:
        if (
            block.block_id == ref.block_id
            and block.page_index == ref.page_index
            and block.evidence_id == ref.evidence_id
        ):
            return block
    return None


def _resolve_words(
    refs: Sequence[SourceRef], registry: SourceRegistry
) -> list[tuple[SourceRef, list[SourceWord]]]:
    """Resolve each ref to its owning words; raise INVALID_ANALYSIS on any miss."""
    resolved: list[tuple[SourceRef, list[SourceWord]]] = []
    for ref in refs:
        if ref.evidence_id != registry.evidence_id:
            raise _invalid(f'ref evidence {ref.evidence_id!r} not in registry {registry.evidence_id!r}')
        block = _find_block(registry, ref)
        if block is None:
            raise _invalid(f'ref block {ref.block_id!r}@{ref.page_index} not in registry')
        if ref.locator not in block.locators:
            raise _invalid(f'locator {ref.locator!r} not in block {ref.block_id!r}')
        words: list[SourceWord] = []
        for word_id in block.locators[ref.locator]:
            word = next((w for w in block.words if w.id == word_id), None)
            if word is None:
                raise _invalid(f'locator {ref.locator!r} points at unknown word {word_id!r}')
            words.append(word)
        resolved.append((ref, words))
    return resolved


def _flatten(resolved: Sequence[tuple[SourceRef, list[SourceWord]]]) -> list[SourceWord]:
    return [word for _ref, words in resolved for word in words]


def _score_decimal(word: SourceWord) -> Decimal | None:
    if word.score is None:
        return None
    try:
        return Decimal(word.score)
    except (InvalidOperation, ValueError):
        raise _invalid(f'word {word.id!r} has unparseable score {word.score!r}')


def _validate_scores(words: Sequence[SourceWord]) -> None:
    """A present score outside 0..1 violates the registry contract."""
    for word in words:
        score = _score_decimal(word)
        if score is not None and not (Decimal('0') <= score <= Decimal('1')):
            raise _invalid(f'word {word.id!r} score {word.score!r} outside 0..1')


def _coverage_passes(words: Sequence[SourceWord], threshold: Decimal) -> bool:
    """All relevant words present with a score >= threshold (missing fails)."""
    if not words:
        return False
    return all(
        (score := _score_decimal(word)) is not None and score >= threshold
        for word in words
    )


def _ref_key(ref: SourceRef) -> tuple[str, int, str, str, str]:
    return (ref.evidence_id, ref.page_index, ref.block_id, ref.locator, ref.raw_value)


def _canonical_text(text: str) -> str:
    """Canonicalize a raw string the way the builders do (``format(..., 'f')``).

    Numeric strings compare by value (so ``'1200000'`` and ``'1200000.0'`` agree);
    non-numeric text falls back to a stripped literal.
    """
    stripped = text.strip()
    try:
        with localcontext(DECIMAL_CONTEXT):
            value = Decimal(stripped)
            if value.is_finite():
                return format(value.normalize(), 'f')
    except (InvalidOperation, ValueError):
        pass
    return stripped


def _raw_matches_locus(
    fact: FieldFact, resolved: Sequence[tuple[SourceRef, list[SourceWord]]]
) -> bool:
    """True when ``fact.raw_value`` actually appears at each resolved locus."""
    for _ref, words in resolved:
        locus_text = ''.join(word.text for word in words)
        if _canonical_text(fact.raw_value) != _canonical_text(locus_text):
            return False
    return True


def _has_unreadable_observation(observations: Sequence[QualityObservation]) -> bool:
    return any(obs.reading in _VERIFICATION_READINGS for obs in observations)


def _contradicts_quality(observations: Sequence[QualityObservation]) -> bool:
    """UNREADABLE/UNKNOWN with requires_verification=False is a contract conflict."""
    return any(
        obs.reading in _VERIFICATION_READINGS and not obs.requires_verification
        for obs in observations
    )


def _confirmation_matches(
    fact: FieldFact, confirmation: HumanAction | None, registry: SourceRegistry
) -> bool:
    """True only for a REVIEWER CONFIRM_FIELD on this field/value with owned refs."""
    if confirmation is None:
        return False
    if confirmation.kind != 'CONFIRM_FIELD' or confirmation.mode != 'REVIEWER':
        return False
    payload = confirmation.payload
    if payload.get('field') != fact.field:
        return False
    if str(payload.get('value')) != fact.raw_value:
        return False
    raw_refs = payload.get('refs')
    if not raw_refs:
        return False
    try:
        refs = [SourceRef.model_validate(entry) for entry in raw_refs]
    except ValidationError:
        return False
    if fact.refs and {_ref_key(r) for r in refs} != {_ref_key(r) for r in fact.refs}:
        return False
    _resolve_words(refs, registry)  # owned refs must resolve; bad refs => INVALID_ANALYSIS
    return True


def derive_fact(
    fact: FieldFact,
    registry: SourceRegistry,
    numeric: bool,
    threshold: Decimal,
    confirmation: HumanAction | None,
) -> FieldFact:
    """Return a copy of ``fact`` with usability derived from real coverage.

    Callers MUST pass ``numeric=True`` for every required numeric field
    (money/quantity/unit-price/line-amount). With ``numeric=False`` a resolvable
    document fact is treated as USABLE without score-gating, so forgetting the
    flag silently auto-passes numeric quality — the signature is unchanged for
    ledger compatibility, but the flag is not optional in practice.
    """
    def with_usability(value: str) -> FieldFact:
        return fact.model_copy(update={'usability': value})

    # An UNREADABLE/UNKNOWN observation that claims no verification is needed is
    # a contract contradiction, never a quality PASS — regardless of raw/refs.
    if _contradicts_quality(fact.observations):
        raise _invalid(
            f'field {fact.field!r}: UNREADABLE/UNKNOWN observation claims no verification'
        )

    if not fact.raw_value:
        return with_usability('MISSING')

    if not fact.refs:
        if _confirmation_matches(fact, confirmation, registry):
            return with_usability('USABLE')
        return with_usability('UNUSABLE')

    resolved = _resolve_words(fact.refs, registry)
    words = _flatten(resolved)

    # A present score outside 0..1 is a contract violation regardless of any
    # later quality outcome.
    _validate_scores(words)

    # Source/raw/normalization must be valid: the claimed raw value has to live
    # at the resolved locus, and the normalization must be traced. Fail closed to
    # UNCERTAIN (a reviewer CONFIRM_FIELD can still make it USABLE) — this is not
    # a contract error like a bad/foreign ref.
    if not fact.normalization_trace or not _raw_matches_locus(fact, resolved):
        if _confirmation_matches(fact, confirmation, registry):
            return with_usability('USABLE')
        return with_usability('UNCERTAIN')

    if _has_unreadable_observation(fact.observations):
        # requires_verification must be True here (contradiction already raised).
        if _confirmation_matches(fact, confirmation, registry):
            return with_usability('USABLE')
        return with_usability('UNCERTAIN')

    if not numeric:
        return with_usability('USABLE')

    if _coverage_passes(words, threshold):
        return with_usability('USABLE')
    if _confirmation_matches(fact, confirmation, registry):
        return with_usability('USABLE')
    return with_usability('UNCERTAIN')
