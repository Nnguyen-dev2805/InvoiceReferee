"""T05 tests — provider boundary: OCR registry, per-document analysis, cross-source.

RED first: this file fails with ``ModuleNotFoundError`` until
``invoice_referee.extraction.{providers,validation}`` exist. Expected values are
built from ``tests/builders.py`` (gold-independent) and hand-written fake
transports; no network and no production evaluator derives an answer.

Coverage follows the T05 brief: ownership guard, coverage/quality rejection,
shared repair budget (one repair per invocation), cross-source extra repair,
native OCR word scores (never fabricated), payload/prose boundary, applicability
decided by code, and missing-score → UNCERTAIN.
"""
from datetime import datetime, timezone
import json

import pytest

from invoice_referee.domain.models import (
    AnalysisRequest,
    DocumentFacts,
    DomainError,
    Evidence,
    FieldFact,
    QualityObservation,
    RawOcr,
    SourceRef,
)
from invoice_referee.extraction.providers import (
    FakeProviders,
    LiveProviders,
    _usage_dict,
    _validate_mapping,
    analysis_payload,
    cross_source_payload,
    registry_from_ocr,
)
from invoice_referee.extraction.validation import (
    is_applicable,
    shared_repair_allowed,
    validate_document,
)
from tests.builders import document_facts, resolved_bundle, routine_snapshot, text_registry

EVIDENCE_ID = 'e-1'


# --- Local helpers -------------------------------------------------------------

def _request(template='SIMPLE_ITEMIZED', *, amount='1200000', score='0.99'):
    evidence = routine_snapshot().evidence[0]
    assert evidence.id == EVIDENCE_ID
    registry = text_registry(evidence_id=EVIDENCE_ID, amount=amount, score=score)
    return AnalysisRequest(
        evidence=evidence,
        registry=registry,
        required_fields=['merchant', 'date', 'currency', 'total'],
        threshold_version='threshold-b1-085',
    )


def _document(template='SIMPLE_ITEMIZED', *, amount='1200000'):
    return document_facts(amount=amount, evidence_id=EVIDENCE_ID, template=template)


def _valid_document_json() -> str:
    # Hand-built model wire fixture; domain builders/validators stay unchanged.
    def fact(raw, source):
        return {'raw':raw,'src':[source],'reading':'READABLE','verify':False}
    return json.dumps({'kind':'BILL','template':'SIMPLE_ITEMIZED',
        'fields':{'merchant':fact('Nhà cung cấp Demo','r1'),
                  'date':fact('2026-10-01','r2'),'currency':fact('VND','r3'),
                  'total':fact('1200000','r4')},
        'items':[{'name':fact('Vật tư demo','r5'),'quantity':fact('1','r6'),
                  'unit':fact('kg','r7'),'unit_price':fact('1200000','r8'),
                  'line_amount':fact('1200000','r9')}], 'covered_item_regions':[]},ensure_ascii=False)


def _missing_fact(field: str) -> FieldFact:
    return FieldFact(
        field=field, raw_value='', normalized_value='', refs=[],
        source_kind='DOCUMENT', observations=[], usability='MISSING',
    )


# --- Fake httpx client (records exact request shape, returns queued responses) --

class _FakeHttpResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _FakeHttpClient:
    """Mirrors ``httpx.Client.post(path, json=...)`` for both provider APIs."""

    def __init__(self, queue):
        self._queue = list(queue)
        self.calls = []

    def post(self, path, json=None):
        self.calls.append({'path': path, 'json': json})
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeHttpResponse(item)


def _chat_ok(content):
    return {'choices': [{'message': {'content': content}}], 'usage': None}


def _fake_chat(items):
    """Queue for the chat endpoint; bare strings become valid JSON responses."""
    return _FakeHttpClient([_chat_ok(i) if isinstance(i, str) else i for i in items])


# --- Step 1: ownership guard ---------------------------------------------------

def test_wrong_evidence_ownership_is_invalid_analysis():
    request = _request()
    doc = document_facts(evidence_id='unrelated-evidence')
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_registry_evidence_mismatch_is_invalid_analysis():
    request = _request()
    foreign_registry = text_registry(evidence_id='e-other')
    request = request.model_copy(update={'registry': foreign_registry})
    with pytest.raises(DomainError) as exc:
        validate_document(_document(), request)
    assert exc.value.code == 'INVALID_ANALYSIS'


# --- Reject: uniqueness, refs, coverage, contradiction -------------------------

def test_duplicate_item_ids_rejected():
    request = _request()
    doc = _document()
    doc = doc.model_copy(update={'items': [doc.items[0], doc.items[0]]})
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_foreign_ref_rejected():
    request = _request()
    doc = _document()
    total = doc.fields['total']
    bad_ref = SourceRef(
        evidence_id='e-other', page_index=0, block_id='b-1', locator='total',
        raw_value=total.raw_value,
    )
    doc = doc.model_copy(
        update={'fields': {**doc.fields, 'total': total.model_copy(update={'refs': [bad_ref]})}}
    )
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_unknown_locator_ref_rejected():
    request = _request()
    doc = _document()
    total = doc.fields['total']
    bad_ref = total.refs[0].model_copy(update={'locator': 'not-in-registry'})
    doc = doc.model_copy(
        update={'fields': {**doc.fields, 'total': total.model_copy(update={'refs': [bad_ref]})}}
    )
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_total_only_rejected_when_registry_has_uncovered_regions():
    request = _request(template='TOTAL_ONLY')
    registry = request.registry.model_copy(update={'uncovered_item_regions': ['r-9']})
    request = request.model_copy(update={'registry': registry})
    doc = _document(template='TOTAL_ONLY')
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_valid_itemized_with_own_region_labels_passes_despite_ocr_ids():
    # OCR region ids are opaque/internal (e.g. 'b-1-t0'); the document uses its
    # own labels ('line-1'). A valid SIMPLE_ITEMIZED document must still pass.
    request = _request(template='SIMPLE_ITEMIZED')
    registry = request.registry.model_copy(update={'uncovered_item_regions': ['b-1-t0']})
    request = request.model_copy(update={'registry': registry})
    doc = _document(template='SIMPLE_ITEMIZED')  # covered_item_regions=['line-1']
    validated = validate_document(doc, request)
    assert validated.template == 'SIMPLE_ITEMIZED'
    assert validated.items  # breakdown terms preserved


def test_itemized_with_ocr_regions_and_no_matching_labels_still_passes():
    request = _request(template='SIMPLE_ITEMIZED')
    registry = request.registry.model_copy(
        update={'uncovered_item_regions': ['tbl-1', 'tbl-2']}
    )
    request = request.model_copy(update={'registry': registry})
    doc = _document(template='SIMPLE_ITEMIZED').model_copy(
        update={'covered_item_regions': ['my-line-a', 'my-line-b']}
    )
    assert validate_document(doc, request).items


def test_itemized_template_without_items_rejected():
    request = _request(template='SIMPLE_ITEMIZED')
    doc = _document(template='SIMPLE_ITEMIZED').model_copy(
        update={'items': [], 'covered_item_regions': []}
    )
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_unreadable_without_verification_is_contradiction():
    request = _request()
    doc = _document()
    total = doc.fields['total']
    contradiction = QualityObservation(
        field='total', reading='UNREADABLE', requires_verification=False, refs=list(total.refs)
    )
    doc = doc.model_copy(
        update={
            'fields': {
                **doc.fields,
                'total': total.model_copy(update={'observations': [contradiction]}),
            }
        }
    )
    with pytest.raises(DomainError) as exc:
        validate_document(doc, request)
    assert exc.value.code == 'INVALID_ANALYSIS'


# --- Quality: missing score / empty raw are NOT a pass -------------------------

def test_missing_word_score_derives_uncertain_not_usable():
    request = _request(score=None)
    validated = validate_document(_document(), request)
    assert validated.fields['total'].usability == 'UNCERTAIN'
    # Non-numeric header fields do not require a numeric score.
    assert validated.fields['merchant'].usability == 'USABLE'


def test_low_word_score_derives_uncertain():
    request = _request(score='0.5')
    validated = validate_document(_document(), request)
    assert validated.fields['total'].usability == 'UNCERTAIN'


def test_empty_raw_fact_stays_missing():
    request = _request()
    doc = _document()
    doc = doc.model_copy(update={'fields': {**doc.fields, 'total': _missing_fact('total')}})
    validated = validate_document(doc, request)
    assert validated.fields['total'].usability == 'MISSING'


def test_model_usable_claim_is_overridden_by_real_coverage():
    request = _request(score=None)
    doc = _document()
    total = doc.fields['total'].model_copy(update={'usability': 'USABLE'})
    doc = doc.model_copy(update={'fields': {**doc.fields, 'total': total}})
    validated = validate_document(doc, request)
    assert validated.fields['total'].usability == 'UNCERTAIN'


def test_honest_unreadable_needs_verification_is_uncertain_not_rejected():
    request = _request()
    doc = _document()
    total = doc.fields['total']
    honest = QualityObservation(
        field='total', reading='UNREADABLE', requires_verification=True, refs=list(total.refs)
    )
    doc = doc.model_copy(
        update={'fields': {**doc.fields, 'total': total.model_copy(update={'observations': [honest]})}}
    )
    validated = validate_document(doc, request)
    assert validated.fields['total'].usability == 'UNCERTAIN'


# --- Applicability is decided by code ------------------------------------------

def test_total_only_cannot_waive_breakdown_when_regions_uncovered():
    request = _request(template='TOTAL_ONLY')
    registry = request.registry.model_copy(update={'uncovered_item_regions': ['r-1']})
    assert is_applicable(_document(template='TOTAL_ONLY'), 'breakdown', registry) is True


def test_breakdown_not_applicable_for_clean_total_only():
    request = _request(template='TOTAL_ONLY')
    doc = _document(template='TOTAL_ONLY')
    assert is_applicable(doc, 'breakdown', request.registry) is False


def test_breakdown_applicable_when_facts_carry_quantity_and_price():
    request = _request(template='SIMPLE_ITEMIZED')
    doc = _document(template='SIMPLE_ITEMIZED')
    assert is_applicable(doc, 'breakdown', request.registry) is True


def test_inventory_applicable_only_for_receipt_or_items():
    request = _request(template='TOTAL_ONLY')
    bill = _document(template='TOTAL_ONLY')
    assert is_applicable(bill, 'inventory', request.registry) is False
    receipt = _document(template='SIMPLE_ITEMIZED')
    assert is_applicable(receipt, 'inventory', request.registry) is True


# --- Shared repair budget ------------------------------------------------------

def test_shared_repair_budget_is_one():
    assert shared_repair_allowed(0) is True
    assert shared_repair_allowed(1) is False
    assert shared_repair_allowed(2) is False


def test_analyze_stops_after_one_shared_repair():
    client = _fake_chat(['not json', '{"bad": "schema"}', _valid_document_json()])
    providers = LiveProviders(chat_client=client)
    with pytest.raises(DomainError) as exc:
        providers.analyze(_request())
    assert exc.value.code == 'INVALID_ANALYSIS'
    assert len(client.calls) == 2  # third (correct) response is never requested


def test_analyze_recovers_after_single_repair():
    client = _fake_chat(['not json', _valid_document_json()])
    providers = LiveProviders(chat_client=client)
    doc = providers.analyze(_request())
    assert doc.evidence_id == EVIDENCE_ID
    assert len(client.calls) == 2
    assert [i.stage for i in providers.identities].count('analyze') == 2


def test_cross_source_gets_one_extra_repair():
    client = _fake_chat(['bad', 'still bad', '{"pairs": [], "refs": [], "conflicts": []}'])
    providers = LiveProviders(chat_client=client)
    proposal = providers.cross_source(resolved_bundle())
    assert proposal.pairs == []
    assert len(client.calls) == 3  # 1 shared + 1 cross-source coverage repair


def test_cross_source_second_invalid_is_technical():
    client = _fake_chat(['bad', 'still bad', 'bad again', 'bad'])
    providers = LiveProviders(chat_client=client)
    with pytest.raises(DomainError) as exc:
        providers.cross_source(resolved_bundle())
    assert exc.value.code == 'INVALID_ANALYSIS'
    assert len(client.calls) == 3  # stops at budget, never loops until valid


def test_transport_failure_is_provider_failed():
    client = _fake_chat([RuntimeError('network down')])
    providers = LiveProviders(chat_client=client)
    with pytest.raises(DomainError) as exc:
        providers.analyze(_request())
    assert exc.value.code == 'PROVIDER_FAILED'


def test_missing_key_is_config_not_active():
    providers = LiveProviders(kimi_api_key=None, chat_client=None)
    with pytest.raises(DomainError) as exc:
        providers.analyze(_request())
    assert exc.value.code == 'CONFIG_NOT_ACTIVE'


def test_repair_calls_and_reasons_recorded():
    client = _fake_chat(['not json', _valid_document_json()])
    providers = LiveProviders(chat_client=client)
    providers.analyze(_request())
    assert providers.repair_calls == 1
    assert len(providers.repair_reasons) == 1
    assert providers.repair_reasons[0].startswith('analyze:')


def test_no_repair_leaves_repair_calls_zero():
    client = _fake_chat([_valid_document_json()])
    providers = LiveProviders(chat_client=client)
    providers.analyze(_request())
    assert providers.repair_calls == 0
    assert providers.repair_reasons == []


def test_fake_providers_exposes_repair_fields():
    providers = FakeProviders(documents={}, registries={})
    assert providers.repair_calls == 0
    assert providers.repair_reasons == []


def test_missing_token_counts_are_none_not_zero():
    assert _usage_dict(None) == {
        'prompt_tokens': None, 'completion_tokens': None, 'total_tokens': None
    }


# --- Payload boundary (no prose / case IDs / labels) ---------------------------

def test_analysis_payload_has_only_registry_scope():
    request = _request()
    payload = analysis_payload(request)
    assert set(payload) == {
        'evidence_id', 'role', 'markdown', 'sources', 'item_regions',
        'required_fields', 'threshold_version', 'schema_version',
    }
    assert payload['threshold_version'] == request.threshold_version
    dumped = str(payload)
    assert 'case-demo' not in dumped          # no case ID
    assert 'Công tác demo' not in dumped      # no employee prose / purpose
    assert 'emp-demo' not in dumped           # no employee identity


def test_analysis_payload_sends_source_text_not_word_scores():
    """The model cites request-local IDs; code keeps scores and ref metadata."""
    request = _request()
    payload = analysis_payload(request)
    # lines map every locator to its text; no per-word score objects leak through.
    assert payload['sources'], 'expected a non-empty source catalog'
    assert all(isinstance(entry['text'], str) for entry in payload['sources'])
    assert 'score' not in dumped_keys(payload)
    assert payload['markdown']


def dumped_keys(obj):
    """Collect every dict key anywhere in a nested payload."""
    keys = set()
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            keys.update(cur)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return keys


def test_cross_source_payload_has_only_facts():
    payload = cross_source_payload(resolved_bundle(profile='WORK_PURCHASE'))
    assert set(payload) == {'documents', 'schema_version'}
    assert 'case-demo' not in str(payload)


def test_analyze_request_shape_uses_json_object_mode():
    client = _fake_chat([_valid_document_json()])
    providers = LiveProviders(chat_client=client)
    providers.analyze(_request())
    call = client.calls[0]
    assert call['path'] == '/chat/completions'
    body = call['json']
    assert body['response_format'] == {'type': 'json_object'}
    assert body['model'] == 'kimi-k2.6'


# --- OCR transport + registry_from_ocr -----------------------------------------

def test_ocr_request_shape_and_registry_from_ocr(tmp_path):
    pdf = tmp_path / 'bill.pdf'
    pdf.write_bytes(b'%PDF-1.4 synthetic')
    evidence = Evidence(
        id='e-x', case_id='case-demo', role='PRIMARY_BILL', original_name='bill.pdf',
        stored_path=str(pdf), sha256='0' * 64, mime='application/pdf', size=16,
    )
    ocr_response = {
        'pages': [{
            'index': 0,
            'markdown': 'Merchant\n1200000',
            'confidence_scores': {
                'word_confidence_scores': [
                    {'text': 'Merchant', 'confidence': 0.98, 'start_index': 0},
                    {'text': '1200000', 'confidence': 0.91, 'start_index': 9},
                ],
                'average_page_confidence_score': 0.94,
                'minimum_page_confidence_score': 0.91,
            },
        }],
        'model': 'mistral-ocr-latest',
        'usage_info': {'pages_processed': 1, 'doc_size_bytes': None},
    }
    fake = _FakeHttpClient([ocr_response])
    providers = LiveProviders(ocr_client=fake)
    raw = providers.ocr(evidence)

    request = fake.calls[0]['json']
    assert fake.calls[0]['path'] == '/ocr'
    assert request['model'] == 'mistral-ocr-latest'
    assert request['confidence_scores_granularity'] == 'word'
    assert request['include_blocks'] is True
    assert request['document']['type'] == 'document_url'

    assert isinstance(raw, RawOcr)
    assert raw.provider == 'mistral'

    registry = registry_from_ocr(evidence, raw)
    assert registry.evidence_id == 'e-x'
    block = registry.blocks[0]
    scores = {w.text: w.score for w in block.words}
    assert scores['1200000'] == '0.91'
    assert block.locators  # words assigned to a citable line locator


def test_registry_from_ocr_keeps_missing_scores_missing():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [{'index': 0, 'markdown': '1200000 kg'}]},
        received_at=datetime.now(timezone.utc),
    )
    registry = registry_from_ocr(evidence, raw)
    assert all(word.score is None for word in registry.blocks[0].words)


def test_registry_from_ocr_empty_pages_is_empty_registry():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': []}, received_at=datetime.now(timezone.utc),
    )
    registry = registry_from_ocr(evidence, raw)
    assert registry.blocks == []


def test_registry_from_ocr_tolerates_flat_word_scores():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [{
            'index': 0, 'markdown': '1200000',
            'word_confidence_scores': [{'text': '1200000', 'confidence': 0.77, 'start_index': 0}],
        }]},
        received_at=datetime.now(timezone.utc),
    )
    registry = registry_from_ocr(evidence, raw)
    assert registry.blocks[0].words[0].score == '0.77'


def test_registry_from_ocr_broken_structure_is_provider_failed():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'nope': 1}, received_at=datetime.now(timezone.utc),
    )
    with pytest.raises(DomainError) as exc:
        registry_from_ocr(evidence, raw)
    assert exc.value.code == 'PROVIDER_FAILED'


def test_registry_from_ocr_non_int_page_index_is_provider_failed():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [{'index': 'zero', 'markdown': 'x'}]},
        received_at=datetime.now(timezone.utc),
    )
    with pytest.raises(DomainError) as exc:
        registry_from_ocr(evidence, raw)
    assert exc.value.code == 'PROVIDER_FAILED'


def test_registry_from_ocr_duplicate_page_index_is_provider_failed():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [
            {'index': 0, 'markdown': 'a'},
            {'index': 0, 'markdown': 'b'},
        ]},
        received_at=datetime.now(timezone.utc),
    )
    with pytest.raises(DomainError) as exc:
        registry_from_ocr(evidence, raw)
    assert exc.value.code == 'PROVIDER_FAILED'


def test_registry_from_ocr_populates_uncovered_item_regions_from_tables():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [{
            'index': 0, 'markdown': 'Hàng hoá',
            'blocks': [
                {'type': 'text', 'content': 'Hàng hoá'},
                {'type': 'table', 'table_id': 'tbl-1', 'content': '...'},
            ],
            'tables': [{'id': 'tbl-1', 'content': '...', 'format_': 'markdown'}],
        }]},
        received_at=datetime.now(timezone.utc),
    )
    registry = registry_from_ocr(evidence, raw)
    assert registry.uncovered_item_regions == ['tbl-1']


def test_registry_from_ocr_plain_text_has_no_item_regions():
    evidence = routine_snapshot().evidence[0]
    raw = RawOcr(
        provider='mistral', model_id='mistral-ocr-latest',
        payload={'pages': [{'index': 0, 'markdown': '1200000'}]},
        received_at=datetime.now(timezone.utc),
    )
    assert registry_from_ocr(evidence, raw).uncovered_item_regions == []


# --- FakeProviders: same signatures + .calls trace -----------------------------

def test_fake_providers_signatures_and_calls():
    doc = _document()
    request = _request()
    providers = FakeProviders(documents={EVIDENCE_ID: doc}, registries={})
    out = providers.analyze(request)
    assert isinstance(out, DocumentFacts)
    assert out.evidence_id == EVIDENCE_ID
    assert providers.calls == [f'analyze:{EVIDENCE_ID}']
    assert providers.identities[0].stage == 'analyze'

    bundle = resolved_bundle()
    proposal = providers.cross_source(bundle)
    assert proposal.pairs == []
    assert providers.calls[-1] == 'cross_source'

    raw = providers.ocr(request.evidence)
    assert providers.calls[-1] == f'ocr:{EVIDENCE_ID}'
    assert isinstance(raw, RawOcr)


def test_fake_providers_is_subclassable_for_malformed():
    class Malformed(FakeProviders):
        def analyze(self, request):
            self.calls.append(f'analyze:{request.evidence.id}')
            raise DomainError('INVALID_ANALYSIS', 'malformed')

    providers = Malformed(documents={}, registries={})
    with pytest.raises(DomainError):
        providers.analyze(_request())
    assert providers.calls == [f'analyze:{EVIDENCE_ID}']


# --- Fix round 1: threshold in hash, env config, mapping refs, numeric fields ---

def test_threshold_version_changes_analyze_request_hash():
    providers = LiveProviders(chat_client=_fake_chat([_valid_document_json()]))
    providers.analyze(_request())
    hash_a = providers.identities[-1].request_hash

    other = _request().model_copy(update={'threshold_version': 'threshold-b2-090'})
    providers2 = LiveProviders(chat_client=_fake_chat([_valid_document_json()]))
    providers2.analyze(other)
    hash_b = providers2.identities[-1].request_hash

    assert hash_a != hash_b


def test_live_providers_read_env_model_and_base_url(monkeypatch):
    monkeypatch.setenv('KIMI_MODEL', 'kimi-env-model')
    monkeypatch.setenv('MISTRAL_OCR_MODEL', 'mistral-env-model')
    providers = LiveProviders()
    assert providers.kimi_model == 'kimi-env-model'
    assert providers.mistral_model == 'mistral-env-model'
    # Explicit argument still wins over the environment.
    assert LiveProviders(kimi_model='explicit').kimi_model == 'explicit'


def test_mapping_refs_must_resolve_in_bundle():
    from invoice_referee.domain.models import MappingProposal, SourceRef

    bundle = resolved_bundle(profile='WORK_PURCHASE')
    primary = bundle.documents[0]
    good_ref = primary.fields['total'].refs[0]
    _validate_mapping(
        MappingProposal(pairs=[('i-primary-1', 'i-receipt-1')], refs=[good_ref]),
        bundle,
    )
    bad_ref = SourceRef(
        evidence_id='e-primary', page_index=0, block_id='b-1', locator='nope', raw_value='x'
    )
    with pytest.raises(DomainError) as exc:
        _validate_mapping(MappingProposal(pairs=[], refs=[bad_ref]), bundle)
    assert exc.value.code == 'INVALID_ANALYSIS'


def test_adjustment_fields_are_score_gated():
    from invoice_referee.extraction.validation import NUMERIC_FIELDS

    for field in ('subtotal', 'tax', 'fees', 'discount'):
        assert field in NUMERIC_FIELDS
