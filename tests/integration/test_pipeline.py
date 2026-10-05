"""T06 integration tests — production pipeline and vertical slice.

RED first: this file fails with ``ModuleNotFoundError`` until
``invoice_referee.application.pipeline`` exists. Expected values come from
``tests/builders.py`` (gold-independent) and ``FakeProviders``; NO network.

These are FAKE-pipeline proofs of wiring (preflight short-circuit, per-document
analysis, active-threshold re-derivation, cross-source gating, error
classification). They do NOT prove live OCR/Kimi quality.
"""
from __future__ import annotations

import pytest

from invoice_referee.application.pipeline import preflight, process
from invoice_referee.config import snapshot_hash
from invoice_referee.domain.models import (
    DocumentFacts,
    DomainError,
    Evidence,
    FieldFact,
    QualityObservation,
    SourceBlock,
    SourceRef,
    SourceRegistry,
    SourceWord,
    StoppedRun,
)
from invoice_referee.extraction.providers import FakeProviders
from tests.builders import (
    demo_policy,
    document_facts,
    resolved_bundle,
    routine_snapshot,
    text_registry,
)


def _writer(tmp_path):
    return lambda name, data: tmp_path / name


def _snapshot_ids(snapshot, ids):
    """Rename evidence ids (builders key kind/items off the id suffix)."""
    evidence = [ev.model_copy(update={'id': ids[i]}) for i, ev in enumerate(snapshot.evidence)]
    snap = snapshot.model_copy(update={'evidence': evidence, 'input_hash': ''})
    return snap.model_copy(update={'input_hash': snapshot_hash(snap)})


def _primary_snapshot(amount=1_200_000):
    """TRAVEL snapshot whose primary evidence id is ``e-primary`` (builder key)."""
    return _snapshot_ids(routine_snapshot(amount), ('e-primary',))


def _travel_providers(amount='1200000', score='0.99'):
    return FakeProviders(
        documents={'e-primary': document_facts(amount, evidence_id='e-primary')},
        registries={'e-primary': text_registry(evidence_id='e-primary', amount=amount, score=score)},
    )


def _work_purchase():
    bundle = resolved_bundle('1200000', profile='WORK_PURCHASE')
    snapshot = _snapshot_ids(routine_snapshot(profile='WORK_PURCHASE'), ('e-primary', 'e-receipt'))
    providers = FakeProviders(
        documents={d.evidence_id: d for d in bundle.documents},
        registries=bundle.registries,
        mapping=bundle.mapping,
    )
    return snapshot, providers


# --- Step 1: preflight short-circuits without provider calls --------------------

def test_missing_primary_does_not_call_provider(tmp_path):
    snapshot = routine_snapshot().model_copy(update={'evidence': []})
    providers = FakeProviders(documents={}, registries={})
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REQUEST_INFO'
    assert result.decision.issues[0].owner_mode == 'EMPLOYEE'
    assert providers.calls == []


def test_inactive_config_is_technical_none_no_provider(tmp_path):
    snapshot = routine_snapshot().model_copy(update={'policy': demo_policy(active=False)})
    providers = _travel_providers()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'NONE'
    assert result.decision.technical_code == 'CONFIG_NOT_ACTIVE'
    assert providers.calls == []


def test_company_payer_refusal_no_provider(tmp_path):
    snapshot = routine_snapshot().model_copy(
        update={'claim': routine_snapshot().claim.model_copy(update={'payer_type': 'COMPANY'})}
    )
    providers = _travel_providers()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REJECT'
    assert providers.calls == []


def test_personal_purpose_refusal_no_provider(tmp_path):
    snapshot = routine_snapshot().model_copy(
        update={'claim': routine_snapshot().claim.model_copy(update={'purpose_type': 'PERSONAL'})}
    )
    providers = _travel_providers()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REJECT'
    assert providers.calls == []


def test_multiple_primary_asks_clarification_no_provider(tmp_path):
    base = routine_snapshot()
    extra = base.evidence[0].model_copy(update={'id': 'e-2'})
    snapshot = base.model_copy(update={'evidence': [*base.evidence, extra], 'input_hash': ''})
    snapshot = snapshot.model_copy(update={'input_hash': snapshot_hash(snapshot)})
    providers = FakeProviders(documents={}, registries={})
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REQUEST_INFO'
    assert providers.calls == []
    assert any('nhiều primary' in i.question.lower() for i in result.decision.issues)


def test_preflight_returns_none_when_providers_must_run():
    assert preflight(routine_snapshot()) is None


def test_total_only_with_items_cannot_waive_breakdown(tmp_path):
    # Code (is_applicable), not the model, decides applicability: a TOTAL_ONLY
    # claim over facts that carry quantity/unit-price must not skip breakdown.
    snapshot = _primary_snapshot()
    doc = document_facts('1200000', evidence_id='e-primary', template='SIMPLE_ITEMIZED')
    doc = doc.model_copy(update={'template': 'TOTAL_ONLY'})
    providers = FakeProviders(
        documents={'e-primary': doc},
        registries={'e-primary': text_registry(evidence_id='e-primary', amount='1200000')},
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'NONE'
    assert result.decision.technical_code == 'INVALID_ANALYSIS'


# --- Step 2/3: per-document path + pure decision -------------------------------

def test_vertical_slice_routine_travel_creates_request(tmp_path):
    snapshot = _primary_snapshot(1_200_000)
    providers = _travel_providers()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'CREATE_PAYMENT_REQUEST'
    assert result.decision.accepted_amount_vnd == 1_200_000
    assert result.decision.completion_basis == 'ROUTINE_AUTO'
    # Both SDK calls happened and identities were captured.
    assert providers.calls == ['ocr:e-primary', 'analyze:e-primary']
    assert result.provider_calls == 2
    assert len(result.identities) == 2
    assert result.artifacts  # raw OCR + registry + parsed artifacts recorded


def test_over_auto_limit_escalates_to_approver(tmp_path):
    snapshot = _primary_snapshot(2_000_001)
    providers = _travel_providers('2000001')
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'ESCALATE'
    auth = next(i for i in result.decision.issues if i.blockers == ['AUTH-01'])
    assert auth.owner_mode == 'APPROVER'


def test_active_threshold_re_derivation(tmp_path):
    # Word score 0.80 sits below the B1 fixed 0.85 but above a 0.75 policy.
    snapshot = _primary_snapshot()
    providers = _travel_providers(score='0.80')
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.bundle.documents[0].fields['total'].usability == 'UNCERTAIN'
    assert result.decision.action == 'REQUEST_INFO'

    lenient = snapshot.model_copy(
        update={'policy': demo_policy().model_copy(update={'word_review_threshold': '0.75'})}
    )
    providers2 = _travel_providers(score='0.80')
    result2 = process(lenient, providers2, lambda stage: None, _writer(tmp_path))
    assert result2.bundle.documents[0].fields['total'].usability == 'USABLE'
    assert result2.decision.action == 'CREATE_PAYMENT_REQUEST'


def test_work_purchase_runs_inventory_and_cross_source(tmp_path):
    snapshot, providers = _work_purchase()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert 'cross_source' in providers.calls
    assert result.decision.action == 'CREATE_PAYMENT_REQUEST'
    inv02 = next(c for c in result.decision.checks if c.rule_id == 'INV-02')
    assert inv02.status == 'PASS'


def test_work_purchase_unique_names_map_without_model_pairs(tmp_path):
    # The model returns NO pairs, but code self-joins unique normalized names
    # (System §4), so the case reaches the same decision as with pairs.
    snapshot, providers = _work_purchase()
    providers._mapping = None  # FakeProviders.cross_source -> empty MappingProposal
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert 'cross_source' in providers.calls
    assert result.bundle.mapping is not None
    assert result.bundle.mapping.pairs == [('i-primary-1', 'i-receipt-1')]
    assert result.decision.action == 'CREATE_PAYMENT_REQUEST'
    inv02 = next(c for c in result.decision.checks if c.rule_id == 'INV-02')
    assert inv02.status == 'PASS'


def test_work_purchase_numeric_uncertain_asks_reviewer(tmp_path):
    snapshot, providers = _work_purchase()
    # Missing word scores on the primary registry -> required numeric uncertain.
    providers.registries['e-primary'] = text_registry(
        evidence_id='e-primary', amount='1200000', score=None
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REQUEST_INFO'
    assert any(i.owner_mode == 'REVIEWER' for i in result.decision.issues)


def test_payer_unknown_is_mode02(tmp_path):
    snapshot = _primary_snapshot().model_copy(
        update={'claim': _primary_snapshot().claim.model_copy(update={'payer_type': 'UNKNOWN'})}
    )
    providers = _travel_providers()
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REQUEST_INFO'
    assert any(i.stable_key == 'MODE-02|case' for i in result.decision.issues)


# --- Error classification: technical vs business -------------------------------

class _TransportFail(FakeProviders):
    def ocr(self, evidence):
        raise DomainError('PROVIDER_FAILED', 'transport lỗi')


class _InvalidSchema(FakeProviders):
    def analyze(self, request):
        raise DomainError('INVALID_ANALYSIS', 'schema sai')


def test_transport_failure_is_technical_none(tmp_path):
    snapshot = _primary_snapshot()
    providers = _TransportFail(documents={}, registries={})
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'NONE'
    assert result.decision.technical_code == 'PROVIDER_FAILED'


def test_invalid_schema_is_technical_none(tmp_path):
    snapshot = _primary_snapshot()
    providers = _InvalidSchema(
        documents={},
        registries={'e-primary': text_registry(evidence_id='e-primary', amount='1200000')},
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'NONE'
    assert result.decision.technical_code == 'INVALID_ANALYSIS'


# --- Stop semantics ------------------------------------------------------------

def test_stop_before_provider_call_prevents_call(tmp_path):
    snapshot = _primary_snapshot()
    providers = _travel_providers()

    def checkpoint(stage):
        if stage == 'ocr:e-primary:before':
            raise StoppedRun()

    with pytest.raises(StoppedRun):
        process(snapshot, providers, checkpoint, _writer(tmp_path))
    assert providers.calls == []


def test_stop_after_provider_call_does_not_apply_facts(tmp_path):
    snapshot = _primary_snapshot()
    providers = _travel_providers()

    def checkpoint(stage):
        if stage == 'ocr:e-primary:after':
            raise StoppedRun()

    with pytest.raises(StoppedRun):
        process(snapshot, providers, checkpoint, _writer(tmp_path))
    assert providers.calls == ['ocr:e-primary']


# --- Identity / repair accounting ---------------------------------------------

class _RepairingFake(FakeProviders):
    def analyze(self, request):
        doc = super().analyze(request)
        self.repair_calls += 1
        self.repair_reasons.append('analyze: test repair')
        return doc


def test_repair_identities_are_captured(tmp_path):
    snapshot = _primary_snapshot()
    providers = _RepairingFake(
        documents={'e-primary': document_facts('1200000', evidence_id='e-primary')},
        registries={'e-primary': text_registry(evidence_id='e-primary', amount='1200000')},
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.repair_calls == 1
    assert result.decision.action == 'CREATE_PAYMENT_REQUEST'


class _DoubleAnalyze(FakeProviders):
    """Emits an identical StageIdentity twice (a repair sharing its predecessor)."""

    def analyze(self, request):
        doc = super().analyze(request)
        self.identities.append(self.identities[-1])
        return doc


def test_duplicate_repair_identity_is_captured(tmp_path):
    snapshot = _primary_snapshot()
    providers = _DoubleAnalyze(
        documents={'e-primary': document_facts('1200000', evidence_id='e-primary')},
        registries={'e-primary': text_registry(evidence_id='e-primary', amount='1200000')},
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    # ocr + analyze + the repair invocation (identical identity) => 3 retained.
    assert len(result.identities) == 3
    assert result.identities[1] == result.identities[2]


# --- Context evidence: a company-paid contradiction must not be ignored --------

def _context_payer(evidence_id: str, value: str = 'COMPANY'):
    ref = SourceRef(
        evidence_id=evidence_id, page_index=0, block_id='b-ctx', locator='payer', raw_value=value
    )
    registry = SourceRegistry(
        evidence_id=evidence_id,
        blocks=[SourceBlock(
            evidence_id=evidence_id, page_index=0, block_id='b-ctx', text=value,
            words=[SourceWord(id='w-ctx', text=value, score='0.99')],
            locators={'payer': ['w-ctx']},
        )],
    )
    fact = FieldFact(
        field='payer', raw_value=value, normalized_value=value, refs=[ref],
        source_kind='DOCUMENT',
        observations=[QualityObservation(
            field='payer', reading='READABLE', requires_verification=False, refs=[ref])],
        usability='USABLE', normalization_trace=[f'payer: "{value}" -> "{value}"'],
    )
    doc = DocumentFacts(
        evidence_id=evidence_id, kind='UNKNOWN', template='UNKNOWN',
        fields={'payer': fact}, items=[], covered_item_regions=[],
    )
    return doc, registry


def test_context_company_paid_contradiction_is_surfaced(tmp_path):
    snapshot = _primary_snapshot()
    context = Evidence(
        id='e-context', case_id='case-demo', role='CONTEXT', original_name='ctx.pdf',
        stored_path='data/case-demo/ctx.pdf', sha256='c' * 64, mime='application/pdf', size=8,
    )
    snapshot = snapshot.model_copy(update={'evidence': [*snapshot.evidence, context], 'input_hash': ''})
    snapshot = snapshot.model_copy(update={'input_hash': snapshot_hash(snapshot)})

    doc, registry = _context_payer('e-context')
    providers = FakeProviders(
        documents={
            'e-primary': document_facts('1200000', evidence_id='e-primary'),
            'e-context': doc,
        },
        registries={
            'e-primary': text_registry(evidence_id='e-primary', amount='1200000'),
            'e-context': registry,
        },
    )
    result = process(snapshot, providers, lambda stage: None, _writer(tmp_path))
    assert result.decision.action == 'REQUEST_INFO'
    assert any(i.stable_key == 'MODE-02:context' for i in result.decision.issues)
    # Each rule_id appears exactly once (matrix contract).
    mode02 = [c for c in result.decision.checks if c.rule_id == 'MODE-02']
    assert len(mode02) == 1
    assert mode02[0].status == 'FAIL'
