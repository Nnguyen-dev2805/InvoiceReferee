"""T01 contract tests — strict records, demo-policy activation, snapshot hash.

These tests assert real behavior of the frozen T01 contracts (master plan §3).
Expected values are built independently in ``tests/builders.py``; no production
evaluator is called to derive a gold answer.
"""
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from invoice_referee.config import activate_demo_policy, load_policy, snapshot_hash
from invoice_referee.domain.models import (
    AuditEvent,
    Authorization,
    Claim,
    Decision,
    DomainError,
    PaymentRequest,
    PolicyConfig,
    SourceRegistry,
    StoppedRun,
)
from tests.builders import (
    demo_policy,
    document_facts,
    human_action,
    resolved_bundle,
    routine_snapshot,
    text_registry,
)

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'demo-policy.json'


# --- Claim amount: strict positive integer, missing != invalid -----------------

@pytest.mark.parametrize('amount', [True, 1.5, -1, 0, '1200000'])
def test_provided_amount_is_strict_positive_integer(amount):
    data = routine_snapshot().claim.model_dump()
    data['requested_amount_vnd'] = amount
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


def test_missing_amount_is_not_invalid_format():
    data = routine_snapshot().claim.model_dump()
    data['requested_amount_vnd'] = None
    assert Claim.model_validate(data).requested_amount_vnd is None


def test_amount_upper_bound_is_15_digits():
    data = routine_snapshot().claim.model_dump()
    data['requested_amount_vnd'] = 999_999_999_999_999
    assert Claim.model_validate(data).requested_amount_vnd == 999_999_999_999_999
    data['requested_amount_vnd'] = 1_000_000_000_000_000
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


# --- Money integrity: strict positive integer on every money field -------------

def _payment_request(**overrides):
    base = dict(
        id='pr-1', case_id='case-demo', run_id='run-1', payee='emp-demo',
        amount_vnd=1_200_000, currency='VND', completion_basis='ROUTINE_AUTO',
        status='CREATED', policy_version='demo-expense-v0.1-proposed',
    )
    base.update(overrides)
    return base


def _authorization(**overrides):
    base = dict(
        action_id='auth-1', kind='AMOUNT_APPROVAL', case_version=1,
        policy_version='demo-expense-v0.1-proposed', profile='TRAVEL',
        purpose='Công tác demo', amount_vnd=1_200_000, mode='APPROVER',
        reason='Duyệt trong quyền',
    )
    base.update(overrides)
    return base


@pytest.mark.parametrize('bad', [True, 1.0, -1, 0, '1200000'])
def test_payment_request_amount_is_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        PaymentRequest.model_validate(_payment_request(amount_vnd=bad))


@pytest.mark.parametrize('bad', [True, 1.0, -1, 0, '1200000'])
def test_authorization_amount_is_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        Authorization.model_validate(_authorization(amount_vnd=bad))


@pytest.mark.parametrize('bad', [True, 1.0, -1, 0, '1200000'])
def test_decision_accepted_amount_is_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        Decision.model_validate({'action': 'CREATE_PAYMENT_REQUEST', 'accepted_amount_vnd': bad})


def test_decision_accepted_amount_may_be_absent():
    assert Decision.model_validate({'action': 'NONE'}).accepted_amount_vnd is None


def test_audit_event_allows_policy_global_case_id_none():
    event = AuditEvent(
        id='ev-1', case_id=None, run_id=None, case_version=None,
        timestamp='2026-10-04T00:00:00Z', kind='POLICY_CHANGE', stage='policy',
        reason='Kích hoạt policy demo',
    )
    assert event.case_id is None


# --- Record strictness: extra forbidden, frozen, enum identity -----------------

def test_extra_field_is_forbidden():
    data = routine_snapshot().claim.model_dump()
    data['unexpected_field'] = 'x'
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


def test_record_is_immutable():
    claim = routine_snapshot().claim
    with pytest.raises(ValidationError):
        claim.purpose = 'changed'


def test_invalid_profile_enum_rejected():
    data = routine_snapshot().claim.model_dump()
    data['profile'] = 'NOT_A_PROFILE'
    with pytest.raises(ValidationError):
        Claim.model_validate(data)


# --- Policy config identity and proposed demo values ---------------------------

def test_policy_requires_currency_and_version():
    base = demo_policy().model_dump()
    for missing in ('currency', 'version'):
        data = dict(base)
        del data[missing]
        with pytest.raises(ValidationError):
            PolicyConfig.model_validate(data)


def test_config_file_encodes_proposed_demo_values():
    policy = load_policy(CONFIG_PATH)
    assert policy.currency == 'VND'
    assert policy.auto_approval_max == 2_000_000
    assert policy.standard_policy_max == 5_000_000
    assert policy.inventory_date_gap_days == 7
    assert policy.comparison_money_tolerance == '1'
    assert policy.normalized_unit_price_tolerance == '0'
    assert policy.word_review_threshold == '0.85'


def test_demo_policy_fixture_is_active_but_config_file_is_inactive():
    fixture = demo_policy()
    assert fixture.active is True
    assert fixture.origin == 'proposed_test_fixture'
    loaded = load_policy(CONFIG_PATH)
    assert loaded.active is False
    assert loaded.origin == 'proposed'
    assert loaded.activation_id is None


def test_activation_records_demo_scope():
    policy = activate_demo_policy(demo_policy(active=False), 'Dùng rulebook mô phỏng cho demo')
    assert policy.active and policy.activation_id
    assert policy.origin == 'developer_activated_demo'


def test_activation_requires_non_empty_reason():
    with pytest.raises(DomainError) as exc:
        activate_demo_policy(demo_policy(active=False), '   ')
    assert exc.value.code == 'INVALID_INPUT'


def test_stopped_run_is_domain_error_with_stopped_code():
    err = StoppedRun()
    assert isinstance(err, DomainError)
    assert err.code == 'STOPPED'


# --- SourceRegistry integrity --------------------------------------------------

def test_registry_rejects_duplicate_block_ids():
    reg = text_registry()
    blocks = list(reg.blocks) + [reg.blocks[0]]
    with pytest.raises(ValidationError):
        SourceRegistry(evidence_id=reg.evidence_id, blocks=blocks)


def test_registry_rejects_duplicate_word_ids():
    reg = text_registry()
    dup = reg.blocks[0].words[0]
    first = reg.blocks[0].model_copy(update={'words': list(reg.blocks[0].words) + [dup]})
    with pytest.raises(ValidationError):
        SourceRegistry(evidence_id=reg.evidence_id, blocks=[first, *reg.blocks[1:]])


# --- Snapshot hash -------------------------------------------------------------

def _manual_hash(snapshot):
    payload = snapshot.model_dump(mode='json', exclude={'input_hash'})
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def test_snapshot_hash_is_stable_and_excludes_input_hash():
    snap = routine_snapshot()
    assert snapshot_hash(snap) == _manual_hash(snap)
    assert snapshot_hash(routine_snapshot()) == snapshot_hash(snap)
    assert snapshot_hash(snap.model_copy(update={'input_hash': 'other'})) == snapshot_hash(snap)


def test_snapshot_hash_changes_with_amount_policy_and_actions():
    snap = routine_snapshot()
    base = snapshot_hash(snap)

    claim = snap.claim.model_copy(update={'requested_amount_vnd': snap.claim.requested_amount_vnd + 1})
    assert snapshot_hash(snap.model_copy(update={'claim': claim})) != base

    policy = snap.policy.model_copy(update={'auto_approval_max': 1})
    assert snapshot_hash(snap.model_copy(update={'policy': policy})) != base

    assert snapshot_hash(snap.model_copy(update={'active_action_ids': ['a-1']})) != base


# --- Builders: independent synthetic data --------------------------------------

def test_routine_snapshot_provides_required_evidence_per_profile():
    travel = routine_snapshot(profile='TRAVEL')
    assert [e.role for e in travel.evidence] == ['PRIMARY_BILL']
    assert travel.claim.payer_type == 'PERSONAL'

    work = routine_snapshot(profile='WORK_PURCHASE')
    assert {e.role for e in work.evidence} == {'PRIMARY_BILL', 'GOODS_RECEIPT'}
    assert work.claim.received_full is True


def test_document_facts_refs_resolve_in_registry():
    doc = document_facts(amount='1200000')
    reg = text_registry(amount='1200000')
    known = {(b.block_id, loc) for b in reg.blocks for loc in b.locators}
    assert doc.evidence_id == reg.evidence_id == 'e-primary'
    for field in doc.fields.values():
        for ref in field.refs:
            assert ref.evidence_id == doc.evidence_id
            assert (ref.block_id, ref.locator) in known


def test_work_purchase_bundle_unit_equivalence_900000():
    bundle = resolved_bundle('900000', profile='WORK_PURCHASE')
    primary = next(d for d in bundle.documents if d.evidence_id == 'e-primary')
    receipt = next(d for d in bundle.documents if d.evidence_id == 'e-receipt')
    p_item = primary.items[0]
    r_item = receipt.items[0]

    assert p_item.id == 'i-primary-1'
    assert r_item.id == 'i-receipt-1'
    assert p_item.quantity.normalized_value == '1'
    assert p_item.unit.normalized_value == 'kg'
    assert p_item.unit_price.normalized_value == '900000'
    assert r_item.quantity.normalized_value == '1000'
    assert r_item.unit.normalized_value == 'g'
    assert r_item.unit_price.normalized_value == '900'
    assert p_item.line_amount.normalized_value == '900000'
    assert r_item.line_amount.normalized_value == '900000'
    assert bundle.mapping is not None
    assert ('i-primary-1', 'i-receipt-1') in bundle.mapping.pairs


def test_human_action_has_identity_and_scope():
    snap = routine_snapshot()
    action = human_action(
        snap, kind='CONFIRM_FIELD', mode='REVIEWER', payload={'field': 'total'}, issue_id='iss-1'
    )
    assert action.id and action.case_id == snap.case_id
    assert action.case_version == snap.case_version
    assert action.issue_id == 'iss-1'
    assert action.mode == 'REVIEWER'
    assert action.kind == 'CONFIRM_FIELD'
