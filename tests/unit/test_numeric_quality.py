"""T02 tests — numeric candidate parsing/normalization and derived field quality.

RED first: this file fails with ``ModuleNotFoundError`` until
``invoice_referee.policy.{numeric,quality}`` exist. Expected values are built
independently here (Decimal literals, explicit records) and never derived by
calling the production evaluator, so a failure means the contract is wrong.

Coverage follows the T02 brief: step 1 (ambiguity / precision / coverage RED)
and step 4 (bad refs, word scores, unassigned words, the exact threshold
boundary, ambiguous normalization, sourced vs unsourced corrections).
"""
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from invoice_referee.domain.models import (
    DomainError,
    FieldFact,
    QualityObservation,
    SourceBlock,
    SourceRef,
    SourceRegistry,
    SourceWord,
)
from invoice_referee.policy.numeric import normalize_quantity, parse_candidates
from invoice_referee.policy.quality import derive_fact
from tests.builders import document_facts, human_action, routine_snapshot, text_registry

THRESHOLD = Decimal('0.85')


# --- Local fixtures ------------------------------------------------------------

def _make_registry(*, evidence_id='e-primary', block_id='b-1', page_index=0,
                   locator='total', text='1200000', word_ids=('w-total',),
                   scores=('0.99',)):
    words = [
        SourceWord(id=wid, text=text, score=score)
        for wid, score in zip(word_ids, scores)
    ]
    block = SourceBlock(
        evidence_id=evidence_id, page_index=page_index, block_id=block_id,
        text=text, words=words, locators={locator: list(word_ids)},
    )
    return SourceRegistry(evidence_id=evidence_id, blocks=[block])


def _make_ref(*, evidence_id='e-primary', block_id='b-1', page_index=0,
              locator='total', raw_value='1200000'):
    return SourceRef(
        evidence_id=evidence_id, page_index=page_index, block_id=block_id,
        locator=locator, raw_value=raw_value,
    )


def _make_fact(*, field='total', raw_value='1200000', normalized_value='1200000',
               refs=None, reading='READABLE', requires_verification=False,
               source_kind='DOCUMENT', usability='USABLE'):
    if refs is None:
        refs = [_make_ref(raw_value=raw_value)]
    return FieldFact(
        field=field, raw_value=raw_value, normalized_value=normalized_value,
        refs=list(refs), source_kind=source_kind,
        observations=[QualityObservation(
            field=field, reading=reading, requires_verification=requires_verification,
            refs=list(refs),
        )],
        usability=usability, normalization_trace=[f'{field}: "{raw_value}"'],
    )


def _confirmation(fact, *, kind='CONFIRM_FIELD', mode='REVIEWER', value=None, refs=None):
    chosen = fact.refs if refs is None else refs
    payload = {
        'field': fact.field,
        'value': fact.raw_value if value is None else value,
        'refs': [r.model_dump(mode='json') for r in chosen],
    }
    return human_action(routine_snapshot(), kind=kind, mode=mode, payload=payload)


# --- Step 1 RED: ambiguity, precision inheritance, coverage --------------------

def test_ambiguous_quantity_keeps_both_candidates():
    assert set(parse_candidates('1.234', 'QUANTITY', None)) == {Decimal('1.234'), Decimal('1234')}


def test_normalization_does_not_inherit_precision():
    with localcontext() as ctx:
        ctx.prec = 2
        assert normalize_quantity(Decimal('123456.789'), 'kg') == (Decimal('123456789'), 'g')


def test_missing_numeric_scores_cannot_auto_pass():
    fact = document_facts(score=None).fields['total']
    derived = derive_fact(fact, text_registry(score=None), True, Decimal('0.85'), None)
    assert derived.usability == 'UNCERTAIN'


# --- Step 2: explicit grammars, bounds, known tokens ---------------------------

def test_vi_grammar_reads_grouped_dot_decimal_comma():
    assert parse_candidates('1.234,56', 'MONEY', 'VI') == (Decimal('1234.56'),)


def test_us_grammar_reads_grouped_comma_decimal_dot():
    assert parse_candidates('1,234.56', 'MONEY', 'US') == (Decimal('1234.56'),)


def test_canonical_grammar_reads_plain_dot_decimal():
    assert parse_candidates('1.234', 'MONEY', 'CANONICAL') == (Decimal('1.234'),)


def test_locale_none_returns_sorted_deduped_union():
    assert parse_candidates('1.234', 'QUANTITY', None) == (Decimal('1.234'), Decimal('1234'))


def test_ambiguous_parse_is_not_collapsed_to_one_value():
    candidates = parse_candidates('1.234', 'QUANTITY', None)
    assert len(candidates) == 2
    assert candidates == tuple(sorted(candidates))


@pytest.mark.parametrize('raw', ['1e3', '1E3', 'NaN', 'nan', 'Infinity', '-Infinity', '1.2.3'])
def test_exponent_nan_infinity_and_junk_rejected(raw):
    assert parse_candidates(raw, 'MONEY', None) == ()


def test_money_bound_is_15_integer_digits():
    assert parse_candidates('123456789012345', 'MONEY', 'CANONICAL') == (Decimal('123456789012345'),)
    assert parse_candidates('1234567890123456', 'MONEY', 'CANONICAL') == ()


def test_quantity_bound_is_12_int_6_frac():
    assert parse_candidates('123456789012.123456', 'QUANTITY', 'CANONICAL') == (
        Decimal('123456789012.123456'),
    )
    assert parse_candidates('1234567890123', 'QUANTITY', 'CANONICAL') == ()
    assert parse_candidates('1.1234567', 'QUANTITY', 'CANONICAL') == ()


def test_nonpositive_quantity_rejected_but_zero_money_allowed():
    assert parse_candidates('0', 'QUANTITY', None) == ()
    assert parse_candidates('0', 'MONEY', 'CANONICAL') == (Decimal('0'),)


def test_known_currency_tokens_are_stripped():
    assert parse_candidates('1.200.000₫', 'MONEY', 'VI') == (Decimal('1200000'),)
    assert parse_candidates('1200000 VND', 'MONEY', None) == (Decimal('1200000'),)


def test_empty_raw_yields_no_candidates():
    assert parse_candidates('', 'MONEY', None) == ()


@pytest.mark.parametrize('kind', ['TOTAL', 'money', ''])
def test_unknown_kind_fails_closed(kind):
    with pytest.raises(DomainError) as exc:
        parse_candidates('1', kind, None)
    assert exc.value.code == 'INVALID_INPUT'


@pytest.mark.parametrize('locale', ['EN', 'vi', ''])
def test_unknown_locale_fails_closed(locale):
    with pytest.raises(DomainError) as exc:
        parse_candidates('1', 'MONEY', locale)
    assert exc.value.code == 'INVALID_INPUT'


# --- Step 2: unit normalization ------------------------------------------------

def test_normalize_quantity_converts_g_kg_tan_to_grams():
    assert normalize_quantity(Decimal('5'), 'g') == (Decimal('5'), 'g')
    assert normalize_quantity(Decimal('2.5'), 'kg') == (Decimal('2500'), 'g')
    assert normalize_quantity(Decimal('0.5'), 'tấn') == (Decimal('500000'), 'g')
    assert normalize_quantity(Decimal('1'), ' KG ') == (Decimal('1000'), 'g')


def test_normalize_quantity_leaves_opaque_units_unconverted():
    assert normalize_quantity(Decimal('3'), 'thùng') == (Decimal('3'), 'thùng')
    assert normalize_quantity(Decimal('3'), 'hộp') == (Decimal('3'), 'hộp')


# --- Step 3: derived usability and coverage ------------------------------------

def test_numeric_fact_usable_when_all_scores_pass():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(), True, THRESHOLD, None)
    assert derived.usability == 'USABLE'
    assert derived is not fact
    assert fact.usability == 'USABLE'  # original record untouched


def test_numeric_fact_uncertain_when_score_below_threshold():
    fact = _make_fact()
    assert derive_fact(fact, _make_registry(scores=('0.849',)), True, THRESHOLD, None).usability == 'UNCERTAIN'


def test_threshold_is_inclusive():
    fact = _make_fact()
    assert derive_fact(fact, _make_registry(scores=('0.85',)), True, THRESHOLD, None).usability == 'USABLE'


def test_readable_observation_does_not_waive_missing_score():
    fact = _make_fact(reading='READABLE', requires_verification=False)
    assert derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD, None).usability == 'UNCERTAIN'


@pytest.mark.parametrize('reading', ['UNREADABLE', 'UNKNOWN'])
def test_verification_reading_without_flag_is_invalid_analysis(reading):
    fact = _make_fact(reading=reading, requires_verification=False)
    with pytest.raises(DomainError) as exc:
        derive_fact(fact, _make_registry(), True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_verification_reading_with_flag_is_uncertain_not_auto_usable():
    fact = _make_fact(reading='UNREADABLE', requires_verification=True)
    assert derive_fact(fact, _make_registry(scores=('0.99',)), True, THRESHOLD, None).usability == 'UNCERTAIN'


def test_unknown_block_id_is_invalid_analysis():
    fact = _make_fact(refs=[_make_ref(block_id='b-999')])
    with pytest.raises(DomainError) as exc:
        derive_fact(fact, _make_registry(), True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_ref_from_other_evidence_is_invalid_analysis():
    fact = _make_fact(refs=[_make_ref(evidence_id='e-other')])
    with pytest.raises(DomainError) as exc:
        derive_fact(fact, _make_registry(), True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_unknown_locator_is_invalid_analysis():
    fact = _make_fact(refs=[_make_ref(locator='nope')])
    with pytest.raises(DomainError) as exc:
        derive_fact(fact, _make_registry(), True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_unknown_word_id_is_invalid_analysis():
    reg = SourceRegistry(
        evidence_id='e-primary',
        blocks=[SourceBlock(
            evidence_id='e-primary', page_index=0, block_id='b-1', text='1200000',
            words=[SourceWord(id='w-total', text='1200000', score='0.99')],
            locators={'total': ['w-missing']},
        )],
    )
    with pytest.raises(DomainError) as exc:
        derive_fact(_make_fact(), reg, True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_unassigned_word_is_not_accepted_as_coverage():
    reg = SourceRegistry(
        evidence_id='e-primary',
        blocks=[SourceBlock(
            evidence_id='e-primary', page_index=0, block_id='b-1', text='1200000',
            words=[], locators={'total': ['w-total']},
        )],
        unassigned_words=[SourceWord(id='w-total', text='1200000', score='0.99')],
    )
    with pytest.raises(DomainError) as exc:
        derive_fact(_make_fact(), reg, True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_locator_with_no_words_is_uncertain():
    reg = SourceRegistry(
        evidence_id='e-primary',
        blocks=[SourceBlock(
            evidence_id='e-primary', page_index=0, block_id='b-1', text='1200000',
            words=[], locators={'total': []},
        )],
    )
    assert derive_fact(_make_fact(), reg, True, THRESHOLD, None).usability == 'UNCERTAIN'


def test_score_outside_zero_one_is_invalid_analysis():
    with pytest.raises(DomainError) as exc:
        derive_fact(_make_fact(), _make_registry(scores=('1.5',)), True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_out_of_range_score_reported_even_when_another_word_is_missing():
    reg = _make_registry(word_ids=('w-a', 'w-b'), scores=(None, '2.0'))
    with pytest.raises(DomainError) as exc:
        derive_fact(_make_fact(), reg, True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_registry_rejects_duplicate_word_ids():
    dup = SourceWord(id='w-total', text='1200000', score='0.99')
    with pytest.raises(ValidationError):
        SourceRegistry(
            evidence_id='e-primary',
            blocks=[SourceBlock(
                evidence_id='e-primary', page_index=0, block_id='b-1', text='1200000',
                words=[dup, dup], locators={'total': ['w-total']},
            )],
        )


def test_empty_source_is_missing():
    fact = _make_fact(raw_value='', normalized_value='', refs=[])
    assert derive_fact(fact, _make_registry(), True, THRESHOLD, None).usability == 'MISSING'


def test_claimed_value_without_source_is_unusable():
    fact = _make_fact(refs=[])
    assert derive_fact(fact, _make_registry(), True, THRESHOLD, None).usability == 'UNUSABLE'


# --- Ruling 1: raw value must live at the resolved locus, trace non-empty -------

def test_raw_value_mismatching_locus_text_is_uncertain():
    # fact claims 1200000 but the ref resolves to source text '999'
    fact = _make_fact(raw_value='1200000', refs=[_make_ref(raw_value='1200000')])
    assert derive_fact(fact, _make_registry(text='999'), True, THRESHOLD, None).usability == 'UNCERTAIN'


def test_empty_normalization_trace_is_uncertain():
    fact = _make_fact()
    fact = fact.model_copy(update={'normalization_trace': []})
    assert derive_fact(fact, _make_registry(), True, THRESHOLD, None).usability == 'UNCERTAIN'


def test_locus_mismatch_is_rescued_by_reviewer_confirmation():
    fact = _make_fact(raw_value='1200000', refs=[_make_ref(raw_value='1200000')])
    derived = derive_fact(fact, _make_registry(text='999'), True, THRESHOLD, _confirmation(fact))
    assert derived.usability == 'USABLE'


def test_builder_path_stays_usable_with_locus_and_trace():
    fact = document_facts(amount='1200000').fields['total']
    derived = derive_fact(fact, text_registry(amount='1200000'), True, THRESHOLD, None)
    assert derived.usability == 'USABLE'


def test_canonical_equivalence_between_raw_and_locus_text():
    # The builders emit canonical strings; an equivalent numeric form still matches.
    fact = _make_fact(raw_value='1200000')
    assert derive_fact(fact, _make_registry(text='1200000.0'), True, THRESHOLD, None).usability == 'USABLE'


# --- Ruling 2: a foreign block (different evidence) cannot resolve --------------

def test_foreign_block_evidence_is_invalid_analysis():
    reg = SourceRegistry(
        evidence_id='e-primary',
        blocks=[SourceBlock(
            evidence_id='e-other', page_index=0, block_id='b-1', text='1200000',
            words=[SourceWord(id='w-total', text='1200000', score='0.99')],
            locators={'total': ['w-total']},
        )],
    )
    with pytest.raises(DomainError) as exc:
        derive_fact(_make_fact(), reg, True, THRESHOLD, None)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_non_numeric_fact_usable_with_valid_source_ignoring_low_score():
    fact = _make_fact(
        field='merchant', raw_value='Nhà cung cấp Demo', normalized_value='Nhà cung cấp Demo',
        refs=[_make_ref(locator='merchant', raw_value='Nhà cung cấp Demo')],
    )
    reg = _make_registry(locator='merchant', text='Nhà cung cấp Demo',
                         word_ids=('w-merchant',), scores=('0.10',))
    assert derive_fact(fact, reg, False, THRESHOLD, None).usability == 'USABLE'


# --- Step 4: sourced reviewer confirmation vs unsourced correction -------------

def test_reviewer_confirmation_makes_low_score_fact_usable():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD, _confirmation(fact))
    assert derived.usability == 'USABLE'


def test_reviewer_confirmation_rescues_empty_source_fact():
    fact = _make_fact(refs=[])
    derived = derive_fact(fact, _make_registry(), True, THRESHOLD,
                          _confirmation(fact, refs=[_make_ref()]))
    assert derived.usability == 'USABLE'


def test_confirmation_with_wrong_value_is_not_usable():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD,
                          _confirmation(fact, value='999'))
    assert derived.usability == 'UNCERTAIN'


def test_unsourced_correction_is_not_usable():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD,
                          _confirmation(fact, kind='PROPOSE_CORRECTION'))
    assert derived.usability == 'UNCERTAIN'


def test_employee_confirmation_is_not_usable():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD,
                          _confirmation(fact, mode='EMPLOYEE'))
    assert derived.usability == 'UNCERTAIN'


def test_confirmation_without_refs_is_not_usable():
    fact = _make_fact()
    derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD,
                          _confirmation(fact, refs=[]))
    assert derived.usability == 'UNCERTAIN'


def test_confirmation_field_spelling_both_accepted():
    """Pin the DELIBERATE T08 spelling rule for CONFIRM_FIELD.

    Both the bare fact field ('total') and the canonical path
    ('e-primary.fields.total') are accepted; a DIFFERENT trailing field is not.
    """
    fact = _make_fact(field='total')
    for spelling in ('total', 'e-primary.fields.total'):
        derived = derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD,
                              _confirmation(fact, value='1200000').model_copy(
                                  update={'payload': {**_confirmation(fact).payload, 'field': spelling}}))
        assert derived.usability == 'USABLE', spelling
    wrong = _confirmation(fact).model_copy(
        update={'payload': {**_confirmation(fact).payload, 'field': 'e-primary.fields.merchant'}})
    assert derive_fact(fact, _make_registry(scores=(None,)), True, THRESHOLD, wrong).usability == 'UNCERTAIN'
