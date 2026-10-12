"""Small model-facing wire format; enrich into the unchanged domain contract.

Source IDs are request-local. Metadata/scores stay code-owned, and ambiguous
normalization produces an uncertain fact instead of a guessed number.
"""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext

from pydantic import BaseModel, ConfigDict, Field, field_validator

from invoice_referee.domain.models import (
    AnalysisRequest, DocumentFacts, DocumentKind, DocumentTemplate, DomainError,
    FieldFact, ItemFacts, QualityObservation, Reading, SourceRef,
)
from invoice_referee.extraction.validation import (
    B1_WORD_REVIEW_THRESHOLD, NUMERIC_FIELDS, validate_document,
)
from invoice_referee.policy.numeric import DECIMAL_CONTEXT, parse_candidates

SCHEMA_VERSION = 'compact-document-v1'
_WORD = '__compact_word__'
_SPAN = '__compact_span__'
_VERIFICATION_READINGS = ('UNREADABLE', 'UNKNOWN')
_SEPARATORS = re.compile(r'[\s|]+')
_SEPARATOR_CELL = re.compile(r'^:?-{2,}:?$')
_CURRENCY_AFFIXES = ('đ', '₫', 'vnd', 'vnđ')
_ADJUSTMENT_FIELDS = frozenset({'subtotal', 'tax', 'fees', 'discount'})


class _Wire(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class _Field(_Wire):
    raw: str
    src: list[str]
    reading: Reading
    verify: bool

    @field_validator('src')
    @classmethod
    def unique_sources(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('duplicate source IDs in field')
        return values


class _Item(_Wire):
    name: _Field | None
    quantity: _Field | None
    unit: _Field | None
    unit_price: _Field | None
    line_amount: _Field | None


class _Document(_Wire):
    kind: DocumentKind
    template: DocumentTemplate
    fields: dict[str, _Field | None]
    items: list[_Item] = Field(max_length=200)
    covered_item_regions: list[str]
    # Terms the model declares present on the document; subset of the known
    # adjustment fields, no duplicates. Undeclared terms contribute 0 downstream.
    adjustment_terms: list[str] = Field(default_factory=list)

    @field_validator('adjustment_terms')
    @classmethod
    def known_unique_terms(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('duplicate adjustment term')
        unknown = [term for term in values if term not in _ADJUSTMENT_FIELDS]
        if unknown:
            raise ValueError(f'unknown adjustment term(s): {unknown}')
        return values


def source_catalog(request: AnalysisRequest) -> dict[str, SourceRef]:
    if request.registry.evidence_id != request.evidence.id:
        raise DomainError('INVALID_ANALYSIS', 'Registry belongs to another evidence.')
    # Add aliases to existing words only: no synthetic tokens or invented scores.
    # Field spans are code-owned metadata and never become model-visible IDs.
    for block in request.registry.blocks:
        if block.evidence_id != request.evidence.id:
            raise DomainError('INVALID_ANALYSIS', 'Block belongs to another evidence.')
        for word in block.words:
            key = _WORD + word.id
            if key in block.locators and block.locators[key] != [word.id]:
                raise DomainError('INVALID_ANALYSIS', 'Reserved source alias collision.')
            block.locators[key] = [word.id]
    result = {}
    for word_aliases in (False, True):
        for block in request.registry.blocks:
            words = {word.id: word.text for word in block.words}
            for locator, word_ids in block.locators.items():
                if locator.startswith(_SPAN) or locator.startswith(_WORD) != word_aliases:
                    continue
                if any(word_id not in words for word_id in word_ids):
                    raise DomainError('INVALID_ANALYSIS', 'Source locator has missing words.')
                result[f'r{len(result) + 1}'] = SourceRef(
                    evidence_id=request.evidence.id, page_index=block.page_index,
                    block_id=block.block_id, locator=locator,
                    raw_value=''.join(words[word_id] for word_id in word_ids),
                )
    return result


def model_sources(request: AnalysisRequest) -> list[dict]:
    catalog = source_catalog(request)
    word_ids = {(r.block_id, r.locator.removeprefix(_WORD)): key for key, r in catalog.items()
                if r.locator.startswith(_WORD)}
    result = []
    for key, ref in catalog.items():
        if ref.locator.startswith(_WORD):
            continue
        block = next(b for b in request.registry.blocks if b.block_id == ref.block_id and b.page_index == ref.page_index)
        words = {w.id: w.text for w in block.words}
        result.append({'id':key, 'text':ref.raw_value, 'tokens':[
            {'id':word_ids[(block.block_id, wid)], 'text':words[wid]}
            for wid in block.locators[ref.locator]]})
    return result


def _text_key(value: str) -> tuple:
    """Separator-insensitive key that never merges digits across a separator.

    Removing whitespace/``|`` would turn ``'1 2'``/``'1|2'`` into ``'12'`` and let
    the model claim a value that does not exist in the source. Split on the
    separators instead: every non-empty token must be equal, so ``'1 2'`` and
    ``'12'`` stay different while ``'Item A'`` and ``'ItemA'`` still compare equal
    token-wise only when their single tokens match exactly.
    """
    return tuple(token.casefold() for token in _SEPARATORS.split(value) if token)


def _grounded(source_words: list[str], target: str) -> bool:
    """True when ``target`` is grounded in the cited source WORDS.

    Tokens are compared as separate units, so ``'1'``+``'2'`` never collapse into
    ``'12'``; a currency affix may share a native amount word (``'đ'`` inside
    ``'120.000đ'``) without inventing a value.
    """
    target_tokens = _text_key(target)
    if not target_tokens:
        return False
    source_tokens = tuple(token for word in source_words for token in _text_key(word))
    span = len(target_tokens)
    if any(
        source_tokens[i:i + span] == target_tokens
        for i in range(len(source_tokens) - span + 1)
    ):
        return True
    if len(target_tokens) == 1 and target_tokens[0] in _CURRENCY_AFFIXES:
        return any(word.strip().casefold().endswith(target_tokens[0]) for word in source_words)
    return False


def _find_block(request: AnalysisRequest, block_id: str, page_index: int):
    return next((b for b in request.registry.blocks
                 if b.block_id == block_id and b.page_index == page_index), None)


def _bound_raw(field: _Field, catalog: dict[str, SourceRef], request: AnalysisRequest) -> bool:
    """The claimed raw value must be grounded in the cited sources' OWN words.

    Sources are rebuilt from each locator's words (never concatenated), so a row
    locator covering several cells cannot let ``'1'``+``'2'`` become ``'12'``. The
    value may span several CITED sources in order — a legal name wrapped across
    two OCR lines cites both lines and must still ground.
    """
    for source_id in field.src:
        if source_id not in catalog:
            raise DomainError('INVALID_ANALYSIS', f'Unknown source ID {source_id!r}.')
    if not (field.raw and field.src):
        return False
    source_words: list[str] = []
    for source_id in field.src:
        ref = catalog[source_id]
        block = _find_block(request, ref.block_id, ref.page_index)
        if block is None or ref.locator not in block.locators:
            return False
        words = {word.id: word.text for word in block.words}
        if any(word_id not in words for word_id in block.locators[ref.locator]):
            return False
        source_words.extend(words[word_id] for word_id in block.locators[ref.locator])
    return _grounded(source_words, field.raw)


def _words_pass_quality(request: AnalysisRequest, refs) -> bool:
    """True when every resolved word has a real score meeting the B1 threshold."""
    threshold = B1_WORD_REVIEW_THRESHOLD
    for ref in refs:
        block = next((b for b in request.registry.blocks
                      if b.block_id == ref.block_id and b.page_index == ref.page_index), None)
        if block is None or ref.locator not in block.locators:
            return False
        words = {word.id: word for word in block.words}
        for word_id in block.locators[ref.locator]:
            word = words.get(word_id)
            if word is None or word.score is None:
                return False
            try:
                if Decimal(word.score) < threshold:
                    return False
            except (InvalidOperation, ValueError):
                return False
    return True


def _number_locale(document: _Document, catalog: dict[str, SourceRef], request) -> str | None:
    """Only unambiguous, source-backed, quality-passing punctuation grounds a locale."""
    hints = set()
    fields = list(document.fields.items())
    for item in document.items:
        fields.extend((name, getattr(item, name)) for name in ('quantity', 'unit_price', 'line_amount'))
    for name, field in fields:
        if field is None or name not in NUMERIC_FIELDS or not _bound_raw(field, catalog, request):
            continue
        # A hint may only come from a fact whose own quality is sound: an
        # UNREADABLE/UNKNOWN reading or a low/missing word score cannot resolve
        # another field's locale ambiguity.
        if field.reading in _VERIFICATION_READINGS:
            continue
        refs, _raw, exact = _field_scope(field, catalog, request, name)
        if not exact or not _words_pass_quality(request, refs):
            continue
        kind = 'QUANTITY' if name == 'quantity' else 'PRICE' if name == 'unit_price' else 'MONEY'
        vi = parse_candidates(field.raw, kind, 'VI')
        us = parse_candidates(field.raw, kind, 'US')
        if vi and not us:
            hints.add('VI')
        elif us and not vi:
            hints.add('US')
    return next(iter(hints)) if len(hints) == 1 else None


def _normalized(name: str, raw: str, locale: str | None):
    if name in NUMERIC_FIELDS:
        kind = 'QUANTITY' if name == 'quantity' else 'PRICE' if name == 'unit_price' else 'MONEY'
        values = parse_candidates(raw, kind, locale)
        if len(values) != 1:
            return None
        with localcontext(DECIMAL_CONTEXT):
            return format(values[0].normalize(), 'f')
    if name == 'date':
        formats = ['%Y-%m-%d']
        if locale != 'US':
            formats.extend(('%d/%m/%Y', '%d-%m-%Y'))
        if locale != 'VI':
            formats.append('%m/%d/%Y')
        values = set()
        for pattern in formats:
            try:
                values.add(datetime.strptime(raw.strip(), pattern).date().isoformat())
            except ValueError:
                continue
        return next(iter(values)) if len(values) == 1 else None
    if name == 'currency':
        value = raw.strip().casefold()
        if value in ('đ', '₫', 'đồng', 'vnđ', 'vnd'):
            return 'VND'
        return value.upper() if re.fullmatch('[a-z]{3}', value) else None
    return raw.strip()


def _field_scope(value: _Field, catalog, request: AnalysisRequest, name: str):
    """Resolve a unique contiguous span of actual words, never guessed glyphs.

    Words are compared as SEPARATE tokens (never concatenated) so ``'1'``+``'2'``
    cannot masquerade as ``'12'``; a currency affix may keep its native amount word
    without inventing a score for the suffix.
    """
    refs = [catalog[source_id] for source_id in value.src]
    identities = {(r.block_id, r.page_index) for r in refs}
    if len(identities) != 1:
        return refs, value.raw, False
    block_id, page = next(iter(identities))
    block = next(b for b in request.registry.blocks if b.block_id == block_id and b.page_index == page)
    allowed = {wid for ref in refs for wid in block.locators[ref.locator]}
    target = _text_key(value.raw)
    target_len = len(''.join(target))
    matches = []
    for start, word in enumerate(block.words):
        if word.id not in allowed:
            continue
        parts: list[str] = []
        ids: list[str] = []
        for end in range(start, len(block.words)):
            current = block.words[end]
            if current.id not in allowed:
                break
            parts.append(current.text)
            ids.append(current.id)
            # ``joined`` (space-separated) is only for TOKEN matching; the span's
            # raw_value is the native word concatenation so derive_fact's
            # ``''.join(word.text)`` locus check compares like-for-like.
            joined = ' '.join(parts)
            native = ''.join(parts)
            key = _text_key(joined)
            if key == target:
                matches.append((list(ids), native))
            if len(''.join(key)) > target_len:
                # A currency affix shares a native amount word; retain the whole
                # word and its real score, not a fabricated score for the suffix.
                if (start == end and name == 'currency' and len(target) == 1
                        and target[0] in _CURRENCY_AFFIXES
                        and joined.strip().casefold().endswith(target[0])):
                    matches.append((list(ids), native))
                break
    if len(matches) != 1:
        return refs, value.raw, False
    ids, raw = matches[0]
    locator = _SPAN + hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:24]
    block.locators[locator] = ids
    return [SourceRef(evidence_id=request.evidence.id, page_index=page, block_id=block_id,
                      locator=locator, raw_value=raw)], raw, True


def _fact(name: str, value: _Field | None, catalog, locale, request) -> FieldFact:
    if value is None:
        return FieldFact(field=name, raw_value='', normalized_value=None, refs=[],
                         source_kind='DOCUMENT', observations=[], usability='MISSING')
    bound = _bound_raw(value, catalog, request)
    refs, raw, exact = _field_scope(value, catalog, request, name) if bound else (
        [catalog[s] for s in value.src], value.raw, False)
    normalized = _normalized(name, value.raw, locale) if exact else None
    trace = [f'{name}: source {raw!r}, extracted {value.raw!r} -> {normalized!r}'] if normalized is not None else []
    return FieldFact(field=name, raw_value=raw, normalized_value=normalized,
        refs=refs, source_kind='DOCUMENT', usability='UNCERTAIN', normalization_trace=trace,
        observations=[QualityObservation(field=name, reading=value.reading,
                         requires_verification=value.verify, refs=refs)])


def _table_rows(request: AnalysisRequest, catalog) -> set[str]:
    """Recognize common qty/price/amount markdown tables by row STRUCTURE.

    A data line under a recognized header whose quantity/price/amount columns are
    all PRESENT is an item row even when a cell is unreadable/uncertain (``?``) or
    out of domain (``0``): the row still exists in the source and must be
    accounted for, never silently dropped because its numbers failed to parse.
    Separator (``|---|``), header and footer lines (empty numeric cells) are
    excluded; no row count is invented.
    """
    row_specs = []
    aliases = ({'sl', 'qty', 'quantity', 'số lượng'},
               {'đg', 'đơn giá', 'unit price', 'unit_price'},
               {'tt', 'thành tiền', 'line amount', 'line_amount'})
    for block in request.registry.blocks:
        columns = None
        for line in block.text.splitlines():
            if '|' not in line:
                columns = None
                continue
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if cells and all(_SEPARATOR_CELL.match(cell) for cell in cells):
                continue
            keys = [cell.casefold() for cell in cells]
            if all(any(key in group for key in keys) for group in aliases):
                columns = [next(i for i, key in enumerate(keys) if key in group) for group in aliases]
                continue
            if columns is None or max(columns) >= len(cells):
                continue
            if all(cells[i] for i in columns):
                row_specs.append((block.block_id, block.page_index, _text_key(''.join(cells))))
    rows = set()
    for block_id, page, text in row_specs:
        matches = [key for key, ref in catalog.items() if key not in rows and not ref.locator.startswith(_WORD) and
                   ref.block_id == block_id and ref.page_index == page and _text_key(ref.raw_value) == text]
        if not matches:
            raise DomainError('INVALID_ANALYSIS', 'Item row does not have a unique source locator.')
        rows.add(matches[0])
    return rows


def _coverage(document: _Document, request: AnalysisRequest, catalog) -> None:
    known = set(request.registry.uncovered_item_regions)
    claimed = set(document.covered_item_regions)
    if claimed - known or len(claimed) != len(document.covered_item_regions):
        raise DomainError('INVALID_ANALYSIS', 'Unknown or repeated item region.')
    expected = _table_rows(request, catalog)
    if document.template == 'TOTAL_ONLY' and expected:
        raise DomainError('INVALID_ANALYSIS', 'TOTAL_ONLY cannot omit recognized item rows.')
    if document.template not in ('SIMPLE_ITEMIZED', 'ITEMIZED_WITH_ADJUSTMENTS'):
        return  # Existing validator still rejects TOTAL_ONLY over item regions.
    if claimed != known:
        raise DomainError('INVALID_ANALYSIS', 'Missing OCR item region coverage.')
    covered = set()
    signatures = set()
    for item in document.items:
        ids = set()
        signature = []
        for name in ('quantity', 'unit_price', 'line_amount'):
            value = getattr(item, name)
            if value is not None:
                _bound_raw(value, catalog, request)
                signature.extend(value.src)
                if value.raw:
                    ids.update(value.src)
        signature = tuple(sorted(set(signature)))
        if signature and signature in signatures:
            raise DomainError('INVALID_ANALYSIS', 'Repeated item source row.')
        signatures.add(signature)
        selected_words = set()
        for source_id in ids:
            ref = catalog[source_id]
            block = next(b for b in request.registry.blocks if b.block_id == ref.block_id and b.page_index == ref.page_index)
            selected_words.update(block.locators[ref.locator])
        row_ids = set()
        for row_id in expected:
            ref = catalog[row_id]
            block = next(b for b in request.registry.blocks if b.block_id == ref.block_id and b.page_index == ref.page_index)
            if selected_words & set(block.locators[ref.locator]):
                row_ids.add(row_id)
        if len(row_ids) > 1 or covered & row_ids:
            raise DomainError('INVALID_ANALYSIS', 'Merged or repeated item source rows.')
        covered.update(row_ids)
    if expected - covered:
        raise DomainError('INVALID_ANALYSIS', 'Missing source item rows.')


def parse_compact_document(text: str, request: AnalysisRequest) -> DocumentFacts:
    document = _Document.model_validate(json.loads(text))
    catalog = source_catalog(request)
    _coverage(document, request, catalog)
    locale = _number_locale(document, catalog, request)
    fields = {name: _fact(name, value, catalog, locale, request) for name, value in document.fields.items()}
    for name in request.required_fields:
        if name != 'items' and name not in fields:
            fields[name] = _fact(name, None, catalog, locale, request)
    items = [ItemFacts(id=f'item-{i + 1}', **{name:_fact(name, getattr(item, name), catalog, locale, request)
             for name in ('name', 'quantity', 'unit', 'unit_price', 'line_amount')})
             for i, item in enumerate(document.items)]
    result = DocumentFacts(evidence_id=request.evidence.id, kind=document.kind,
        template=document.template, fields=fields, items=items,
        covered_item_regions=document.covered_item_regions,
        declared_adjustment_terms=list(document.adjustment_terms))
    return validate_document(result, request)
