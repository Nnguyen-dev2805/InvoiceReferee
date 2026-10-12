"""Numeric candidate parsing and unit normalization (T02, System §5 / Rulebook §4).

Pure, dependency-free helpers (stdlib ``decimal`` only):

- ``parse_candidates`` lists every value a raw numeric string can mean under the
  published grammars. Ambiguous input (e.g. ``'1.234'``) yields BOTH candidates
  instead of a silent pick; the caller decides USABLE vs UNCERTAIN.
- ``normalize_quantity`` converts a quantity to a base unit using explicit
  factors under an explicit 50-digit context, never the ambient one.

Hard gates (parser technical bounds, not company allowances): exponent/NaN/
Infinity rejected, money ≤ 15 integer digits, quantity/unit-price ≤ 12 integer +
6 fractional digits, nonpositive quantity rejected. Signed/credit documents are
out of scope and handled upstream (SCOPE-02), so the parser does not accept signs.
"""
from __future__ import annotations

import re
from decimal import Context, Decimal, localcontext
from typing import Literal

from invoice_referee.domain.models import DomainError

# Explicit 50-digit context; arithmetic must not inherit the ambient context.
DECIMAL_CONTEXT = Context(prec=50)

# Base-unit conversion factors. Opaque units (no factor) are compared directly.
UNIT_FACTORS: dict[str, tuple[str, str]] = {
    'g': ('g', '1'),
    'kg': ('g', '1000'),
    'tấn': ('g', '1000000'),
}

_NumericKind = Literal['MONEY', 'QUANTITY', 'PRICE']
_Locale = Literal['VI', 'US', 'CANONICAL']
_GRAMMARS_KINDS = ('MONEY', 'QUANTITY', 'PRICE')

_MONEY_MAX_INT_DIGITS = 15
_QUANTITY_MAX_INT_DIGITS = 12
_QUANTITY_MAX_FRAC_DIGITS = 6

# Published grammars, matched with ``fullmatch`` (no implicit separator guessing).
_CANONICAL_RE = re.compile(r'\d+(?:\.\d+)?')
_VI_RE = re.compile(r'\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?')
_US_RE = re.compile(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?')

# Known currency tokens only; arbitrary punctuation is never stripped.
_CURRENCY_TOKENS = ('đồng', 'vnd', 'usd', '₫', 'đ', '$')
_CURRENCY_RE = re.compile(
    '|'.join(re.escape(tok) for tok in sorted(_CURRENCY_TOKENS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _strip_known_tokens(raw: str) -> str:
    return _CURRENCY_RE.sub('', raw).strip()


def _decimal_from_canonical(text: str) -> Decimal:
    return Decimal(text)


def _decimal_from_vi(text: str) -> Decimal:
    # Grouped-dot thousands, decimal comma.
    return Decimal(text.replace('.', '').replace(',', '.'))


def _decimal_from_us(text: str) -> Decimal:
    # Grouped-comma thousands, decimal dot.
    return Decimal(text.replace(',', ''))


_GRAMMARS = {
    'CANONICAL': (_CANONICAL_RE, _decimal_from_canonical),
    'VI': (_VI_RE, _decimal_from_vi),
    'US': (_US_RE, _decimal_from_us),
}


def _integer_digits(int_part: str) -> int:
    """Significant integer digits (leading zeros do not count)."""
    return len(int_part.lstrip('0'))


def _within_bounds(value: Decimal, kind: str) -> bool:
    int_part, _, frac_part = format(value, 'f').partition('.')
    if kind == 'MONEY':
        return _integer_digits(int_part) <= _MONEY_MAX_INT_DIGITS
    return (
        _integer_digits(int_part) <= _QUANTITY_MAX_INT_DIGITS
        and len(frac_part) <= _QUANTITY_MAX_FRAC_DIGITS
    )


def _accepts(value: Decimal, kind: str) -> bool:
    if not _within_bounds(value, kind):
        return False
    if kind == 'QUANTITY' and value <= 0:
        return False
    return True


def _candidates_for(text: str, grammar: str, kind: str) -> Decimal | None:
    regex, parser = _GRAMMARS[grammar]
    if regex.fullmatch(text) is None:
        return None
    value = parser(text)
    if not value.is_finite():
        return None
    return value if _accepts(value, kind) else None


def parse_candidates(
    raw: str,
    kind: _NumericKind,
    locale: _Locale | None,
) -> tuple[Decimal, ...]:
    """Return every Decimal a raw string can mean, deduped and ascending.

    ``locale=None`` returns the union of the CANONICAL, VI and US grammars so an
    ambiguous value keeps all readings (``'1.234'`` -> ``1.234`` and ``1234``).
    An explicit locale restricts to that grammar. Unparseable or out-of-domain
    input yields ``()`` — never a guessed or rounded value. An unknown ``kind``
    or ``locale`` fails closed with ``DomainError('INVALID_INPUT')`` rather than
    leaking a ``KeyError`` or silently applying another field's bounds.
    """
    if kind not in _GRAMMARS_KINDS:
        raise DomainError('INVALID_INPUT', f'unknown numeric kind {kind!r}')
    if locale is not None and locale not in _GRAMMARS:
        raise DomainError('INVALID_INPUT', f'unknown numeric locale {locale!r}')

    text = _strip_known_tokens(raw)
    if not text:
        return ()

    grammars = _GRAMMARS.keys() if locale is None else (locale,)
    found: set[Decimal] = set()
    for grammar in grammars:
        value = _candidates_for(text, grammar, kind)
        if value is not None:
            found.add(value)
    return tuple(sorted(found))


def normalize_quantity(value: Decimal, unit: str) -> tuple[Decimal, str]:
    """Convert ``value`` to a base unit using explicit factors.

    ``g``/``kg``/``tấn`` convert to grams; an unknown (opaque) unit is returned
    unchanged so two identical opaque units compare directly and different ones
    stay unconverted (the caller treats that as unknown). Arithmetic runs under
    ``DECIMAL_CONTEXT`` (precision 50), never the ambient context.
    """
    normalized = unit.strip().lower()
    base, factor = UNIT_FACTORS.get(normalized, (normalized, '1'))
    with localcontext(DECIMAL_CONTEXT):
        return value * Decimal(factor), base
