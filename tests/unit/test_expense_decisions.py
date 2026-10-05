"""T03 tests — expense decisions: rule matrix, boundaries, authority, reducer.

RED first: this file fails with ``ModuleNotFoundError`` until
``invoice_referee.policy.{expenses,inventory,decision}`` exist. Expected values
are constructed independently here from concrete inputs (no production
evaluator is called to derive a gold answer), so a failure means the
contract/rule is wrong.

Coverage follows the T03 brief step 1 (authority boundaries, amount conflict,
inventory N/A) and step 5 (authority-only over 5m, exact approval, known PERSONAL
refusal, disabled config).
"""
from __future__ import annotations

import pytest

from invoice_referee.domain.models import Authorization, EvidenceBundle
from invoice_referee.policy.decision import evaluate, next_action
from tests.builders import demo_policy, resolved_bundle, routine_snapshot

# Rule matrix from Rulebook §3 — asserted independently of production constants.
REQUIRED_RULES = {
    'SRC-01', 'SRC-02', 'SRC-03', 'CTX-01', 'MODE-01', 'MODE-02',
    'SCOPE-01', 'SCOPE-02', 'ELIG-01', 'AMT-01', 'AMT-02',
    'AUTH-01', 'INV-01', 'INV-02',
}


def _with_claim(snapshot, **updates):
    return snapshot.model_copy(update={'claim': snapshot.claim.model_copy(update=updates)})


def _auth(snapshot, *, kind, amount, mode, action_id='auth-1', **overrides):
    base = dict(
        action_id=action_id,
        kind=kind,
        case_version=snapshot.case_version,
        policy_version=snapshot.policy.version,
        profile=snapshot.claim.profile,
        purpose=snapshot.claim.purpose,
        amount_vnd=amount,
        mode=mode,
        reason='Căn cứ duyệt demo',
    )
    base.update(overrides)
    return Authorization(**base)


def _with_auth(snapshot, authorization, *, active=True):
    return snapshot.model_copy(update={
        'authorizations': [authorization],
        'active_action_ids': [authorization.action_id] if active else [],
    })


# --- Step 1 RED: authority boundaries and amount conflict ----------------------

@pytest.mark.parametrize('amount, action', [
    (2_000_000, 'CREATE_PAYMENT_REQUEST'),
    (2_000_001, 'ESCALATE'),
    (5_000_000, 'ESCALATE'),
])
def test_authority_boundaries(amount, action):
    decision = evaluate(routine_snapshot(amount), resolved_bundle(str(amount)))
    assert decision.action == action
    if amount <= 2_000_000:
        assert decision.accepted_amount_vnd == amount
        assert decision.completion_basis == 'ROUTINE_AUTO'
    else:
        assert any(i.issue_class == 'BEYOND_AUTHORITY' for i in decision.issues)
        assert not any(i.issue_class == 'OUTSIDE_POLICY' for i in decision.issues)


def test_no_supporting_does_not_waive_amount_conflict():
    decision = evaluate(routine_snapshot(1_480_000), resolved_bundle('1280000'))
    assert decision.action == 'REQUEST_INFO'
    issue = next(i for i in decision.issues if 'AMT-01' in i.blockers)
    assert issue.owner_mode == 'EMPLOYEE'
    assert '200.000' in issue.question


# --- Step 2: exact boundary inclusivity ----------------------------------------

def test_auto_approval_max_is_inclusive_at_two_million():
    decision = evaluate(routine_snapshot(2_000_000), resolved_bundle('2000000'))
    assert decision.action == 'CREATE_PAYMENT_REQUEST'
    assert decision.accepted_amount_vnd == 2_000_000
    assert decision.completion_basis == 'ROUTINE_AUTO'
    assert decision.issues == []


def test_beyond_authority_routes_to_approver_at_any_amount():
    # The single authority rule: over auto_approval_max is owned by APPROVER,
    # whatever the amount (no separate 5M policy-limit tier).
    decision = evaluate(routine_snapshot(3_000_000), resolved_bundle('3000000'))
    issue = next(i for i in decision.issues if i.issue_class == 'BEYOND_AUTHORITY')
    assert issue.owner_mode == 'APPROVER'
    assert decision.action == 'ESCALATE'


def test_above_five_million_is_authority_only_not_outside_policy():
    decision = evaluate(routine_snapshot(5_000_001), resolved_bundle('5000001'))
    classes = {i.issue_class for i in decision.issues}
    assert classes == {'BEYOND_AUTHORITY'}
    assert decision.action == 'ESCALATE'
    owners = {i.owner_mode for i in decision.issues}
    assert owners == {'APPROVER'}


# --- Step 5: authorizations, refusals and config -------------------------------

def test_amount_approval_exact_enables_human_authorized_request():
    snap = routine_snapshot(2_000_001)
    snap = _with_auth(snap, _auth(snap, kind='AMOUNT_APPROVAL', amount=2_000_001, mode='APPROVER'))
    decision = evaluate(snap, resolved_bundle('2000001'))
    assert decision.action == 'CREATE_PAYMENT_REQUEST'
    assert decision.completion_basis == 'HUMAN_AUTHORIZED'
    assert decision.accepted_amount_vnd == 2_000_001


def test_mismatched_authorization_does_not_authorize():
    snap = routine_snapshot(2_000_001)
    # Authorization bound to a different case version is not applicable.
    snap = _with_auth(snap, _auth(snap, kind='AMOUNT_APPROVAL', amount=2_000_001,
                                 mode='APPROVER', case_version=snap.case_version + 1))
    decision = evaluate(snap, resolved_bundle('2000001'))
    assert decision.action == 'ESCALATE'
    assert any(i.issue_class == 'BEYOND_AUTHORITY' for i in decision.issues)


def test_known_personal_purpose_is_refused():
    snap = _with_claim(routine_snapshot(1_200_000), purpose_type='PERSONAL')
    decision = evaluate(snap, resolved_bundle('1200000'))
    assert decision.action == 'REJECT'
    assert any('ELIG-01' in c.rule_id and c.status == 'FAIL' for c in decision.checks)


def test_known_company_payer_is_refused_before_providers():
    snap = _with_claim(routine_snapshot(1_200_000), payer_type='COMPANY')
    decision = evaluate(snap, resolved_bundle('1200000'))
    assert decision.action == 'REJECT'
    assert any(c.rule_id == 'MODE-01' and c.status == 'FAIL' for c in decision.checks)


def test_inactive_policy_is_technical_none():
    snap = routine_snapshot(1_200_000).model_copy(update={'policy': demo_policy(active=False)})
    decision = evaluate(snap, resolved_bundle('1200000'))
    assert decision.action == 'NONE'
    assert decision.technical_code == 'CONFIG_NOT_ACTIVE'
    assert decision.completion_basis is None


# --- Inventory N/A does not waive the whole case -------------------------------

def test_inventory_checks_are_not_applicable_for_travel():
    decision = evaluate(routine_snapshot(1_200_000), resolved_bundle('1200000'))
    for rule in ('INV-01', 'INV-02'):
        check = next(c for c in decision.checks if c.rule_id == rule)
        assert check.status == 'NOT_APPLICABLE'


def test_inventory_not_applicable_does_not_make_case_eligible():
    # Missing primary bill: SRC-01 factual blocker must win even though INV is N/A.
    snap = routine_snapshot(1_200_000).model_copy(update={'evidence': []})
    decision = evaluate(snap, EvidenceBundle())
    assert decision.action == 'REQUEST_INFO'
    assert any('SRC-01' in i.blockers for i in decision.issues)


def test_every_rule_in_the_matrix_is_reported():
    decision = evaluate(routine_snapshot(1_200_000), resolved_bundle('1200000'))
    assert REQUIRED_RULES <= {c.rule_id for c in decision.checks}


# --- Reducer anchor (applied after full coverage validation) -------------------

def test_amount_approval_authorizes_over_five_million():
    snap = routine_snapshot(5_000_001)
    approval = _auth(snap, kind='AMOUNT_APPROVAL', amount=5_000_001, mode='APPROVER')
    snap = _with_auth(snap, approval)
    decision = evaluate(snap, resolved_bundle('5000001'))
    assert decision.action == 'CREATE_PAYMENT_REQUEST'
    assert decision.completion_basis == 'HUMAN_AUTHORIZED'
    assert decision.accepted_amount_vnd == 5_000_001


def test_other_profile_is_outside_policy_scope():
    snap = _with_claim(routine_snapshot(1_200_000), profile='OTHER')
    decision = evaluate(snap, resolved_bundle('1200000'))
    assert decision.action == 'ESCALATE'
    issue = next(i for i in decision.issues if i.issue_class == 'OUTSIDE_POLICY')
    assert issue.owner_mode == 'APPROVER'
    assert any(c.rule_id == 'SCOPE-01' and c.status == 'FAIL' for c in decision.checks)


def test_foreign_currency_is_scope_issue_not_a_normal_purchase():
    from invoice_referee.domain.models import EvidenceBundle

    from tests.builders import document_facts, text_registry

    base = document_facts('1200000')
    currency = base.fields['currency'].model_copy(update={'normalized_value': 'USD'})
    doc = base.model_copy(update={'fields': {**base.fields, 'currency': currency}})
    bundle = EvidenceBundle(documents=[doc], registries={'e-primary': text_registry(amount='1200000')})
    decision = evaluate(routine_snapshot(1_200_000), bundle)
    assert any(c.rule_id == 'SCOPE-02' and c.status == 'FAIL' for c in decision.checks)
    assert decision.action == 'ESCALATE'


def test_credit_note_is_scope_issue():
    from invoice_referee.domain.models import EvidenceBundle

    from tests.builders import document_facts, text_registry

    doc = document_facts('1200000').model_copy(update={'kind': 'CREDIT_NOTE'})
    bundle = EvidenceBundle(documents=[doc], registries={'e-primary': text_registry(amount='1200000')})
    decision = evaluate(routine_snapshot(1_200_000), bundle)
    assert any(c.rule_id == 'SCOPE-02' and c.status == 'FAIL' for c in decision.checks)


def test_unknown_payer_requests_info_not_assume_employee_paid():
    snap = _with_claim(routine_snapshot(1_200_000), payer_type='UNKNOWN')
    decision = evaluate(snap, resolved_bundle('1200000'))
    assert decision.action == 'REQUEST_INFO'
    assert any(c.rule_id == 'MODE-02' and c.status == 'FAIL' for c in decision.checks)


def test_each_rule_id_appears_at_most_once_for_work_purchase():
    decision = evaluate(
        routine_snapshot(900_000, profile='WORK_PURCHASE'),
        resolved_bundle('900000', profile='WORK_PURCHASE'),
    )
    rule_ids = [c.rule_id for c in decision.checks]
    assert len(rule_ids) == len(set(rule_ids))


def test_registry_less_document_is_flagged_not_dropped():
    from invoice_referee.domain.models import EvidenceBundle

    from tests.builders import document_facts

    doc = document_facts('1200000')
    bundle = EvidenceBundle(documents=[doc], registries={})  # no registry for doc
    decision = evaluate(routine_snapshot(1_200_000), bundle)
    for rule in ('SRC-02', 'SRC-03', 'SCOPE-02'):
        check = next(c for c in decision.checks if c.rule_id == rule)
        assert check.status == 'UNKNOWN'


def test_declared_primary_with_non_bill_kind_is_not_reported_as_missing_bill():
    from invoice_referee.domain.models import EvidenceBundle

    from tests.builders import document_facts, text_registry

    doc = document_facts('1200000').model_copy(update={'kind': 'CREDIT_NOTE'})
    bundle = EvidenceBundle(documents=[doc], registries={'e-primary': text_registry(amount='1200000')})
    decision = evaluate(routine_snapshot(1_200_000), bundle)
    assert next(c for c in decision.checks if c.rule_id == 'SRC-01').status == 'PASS'
    assert next(c for c in decision.checks if c.rule_id == 'SCOPE-02').status == 'FAIL'


def test_unusable_currency_fact_is_scope_unknown_not_pass():
    from invoice_referee.domain.models import EvidenceBundle

    from tests.builders import document_facts, text_registry

    base = document_facts('1200000')
    # A claimed currency with no resolvable source derives UNUSABLE; SCOPE-02
    # must not read the raw value and PASS.
    currency = base.fields['currency'].model_copy(update={'refs': []})
    doc = base.model_copy(update={'fields': {**base.fields, 'currency': currency}})
    bundle = EvidenceBundle(documents=[doc], registries={'e-primary': text_registry(amount='1200000')})
    decision = evaluate(routine_snapshot(1_200_000), bundle)
    assert next(c for c in decision.checks if c.rule_id == 'SCOPE-02').status == 'UNKNOWN'


def test_next_action_priority_order():
    from invoice_referee.domain.models import Issue

    def issue(cls, status='OPEN'):
        return Issue(id='i', stable_key='k', issue_class=cls, owner_mode='EMPLOYEE',
                     question='q', refs=[], blockers=[], status=status)

    assert next_action(technical=True, refusal=False, issues=[]) == 'NONE'
    assert next_action(technical=False, refusal=True, issues=[]) == 'REJECT'
    assert next_action(technical=False, refusal=False,
                       issues=[issue('FACTUAL_UNKNOWN'), issue('BEYOND_AUTHORITY')]) == 'REQUEST_INFO'
    assert next_action(technical=False, refusal=False,
                       issues=[issue('OUTSIDE_POLICY')]) == 'ESCALATE'
    assert next_action(technical=False, refusal=False, issues=[]) == 'CREATE_PAYMENT_REQUEST'
