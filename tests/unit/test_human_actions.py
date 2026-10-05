"""T07 unit tests — human-action validation and repository revision semantics.

Scope: ``validate_human_action`` + ``Repository.apply_human_action``/revision.
Full service closure is T08; these tests never build a ``CaseService``.

RED at T07 base: ``invoice_referee.application.human`` does not exist and
``Repository`` does not yet invalidate/derive confirmations the T07 way.
"""
from __future__ import annotations

import pytest

from invoice_referee.application.human import (
    authorization_matches,
    validate_human_action,
)
from invoice_referee.domain.models import (
    Authorization,
    Decision,
    DomainError,
    Issue,
)
from invoice_referee.policy.decision import evaluate
from invoice_referee.storage.repository import Repository
from tests.builders import human_action, resolved_bundle, routine_snapshot
from tests.integration.support import seed_case

AMOUNT = 2_000_001


def _travel(amount: int = AMOUNT):
    snapshot = routine_snapshot(amount)
    decision = evaluate(snapshot, resolved_bundle(str(amount)))
    return snapshot, decision


def _auth_payload(snapshot, amount: int, *, profile=None, purpose=None, policy_version=None):
    return {
        'amount_vnd': amount,
        'profile': snapshot.claim.profile if profile is None else profile,
        'purpose': snapshot.claim.purpose if purpose is None else purpose,
        'policy_version': snapshot.policy.version if policy_version is None else policy_version,
    }


def _matching_exception(snapshot, amount: int) -> Authorization:
    return Authorization(
        action_id='a-exc', kind='POLICY_EXCEPTION', case_version=snapshot.case_version,
        policy_version=snapshot.policy.version, profile=snapshot.claim.profile,
        purpose=snapshot.claim.purpose, amount_vnd=amount, mode='POLICY_OWNER',
        reason='Exception demo',
    )


def _issue(*, id='SRC-02:case', owner='REVIEWER', issue_class='FACTUAL_UNKNOWN'):
    return Issue(id=id, stable_key=id, issue_class=issue_class, owner_mode=owner,
                 question='?', refs=[], blockers=[], status='OPEN')


def _decision_with(issue: Issue) -> Decision:
    return Decision(action='REQUEST_INFO', completion_basis=None, accepted_amount_vnd=None,
                    checks=[], issues=[issue], reasons=[], technical_code=None)


# --- Step 1: wrong role / scope -------------------------------------------------

def test_employee_cannot_approve_amount():
    snapshot, decision = _travel()
    action = human_action(
        snapshot, kind='APPROVE_AMOUNT', mode='EMPLOYEE',
        payload=_auth_payload(snapshot, AMOUNT),
    )
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


def test_reviewer_cannot_grant_policy_exception():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='GRANT_POLICY_EXCEPTION', mode='REVIEWER',
                          payload=_auth_payload(snapshot, AMOUNT))
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_employee_cannot_confirm_field():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='EMPLOYEE', payload={
        'field': f'{evidence_id}.fields.total', 'value': '2000001',
        'refs': [_ref(evidence_id)],
    })
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_approver_cannot_approve_above_standard_max():
    snapshot, decision = _travel(5_000_001)
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, 5_000_001))
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


def test_approver_can_approve_within_standard_policy():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, AMOUNT))
    assert validate_human_action(action, snapshot, decision) is action


def test_approver_can_approve_at_exactly_standard_max():
    # The standard policy limit is inclusive (Rulebook §1): 5,000,000 is allowed.
    snapshot, decision = _travel(5_000_000)
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, 5_000_000))
    assert validate_human_action(action, snapshot, decision) is action


def test_policy_owner_approves_at_exactly_standard_max_without_exception():
    snapshot, decision = _travel(5_000_000)
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='POLICY_OWNER',
                          payload=_auth_payload(snapshot, 5_000_000))
    assert validate_human_action(action, snapshot, decision) is action


def test_policy_owner_above_standard_needs_matching_exception():
    snapshot, decision = _travel(5_000_001)
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='POLICY_OWNER',
                          payload=_auth_payload(snapshot, 5_000_001))
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)

    with_exc = snapshot.model_copy(update={
        'authorizations': [_matching_exception(snapshot, 5_000_001)],
        'active_action_ids': ['a-exc'],
    })
    assert validate_human_action(action, with_exc, decision) is action


def test_approval_authorization_must_match_scope():
    snapshot, decision = _travel()
    wrong_purpose = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                                 payload=_auth_payload(snapshot, AMOUNT, purpose='Khác'))
    with pytest.raises(DomainError):
        validate_human_action(wrong_purpose, snapshot, decision)


# --- Step 2: payload keyset -----------------------------------------------------

def test_extra_payload_key_is_rejected():
    snapshot, decision = _travel()
    payload = {**_auth_payload(snapshot, AMOUNT), 'approve_all': True}
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER', payload=payload)
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert 'approve_all' in exc.value.message


def test_missing_payload_key_is_rejected():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER',
                          payload={'field': 'e-1.fields.total', 'value': '1'})
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_blank_reason_is_rejected():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, AMOUNT), reason='   ')
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_stale_case_version_is_rejected():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, AMOUNT))
    newer = snapshot.model_copy(update={'case_version': snapshot.case_version + 1})
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, newer, decision)
    assert exc.value.code == 'INVALID_ACTION'


# --- Declarations, evidence, proposals -----------------------------------------

def test_employee_can_supply_declaration_subset():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Công tác đã bổ sung'}})
    assert validate_human_action(action, snapshot, decision) is action


def test_declaration_cannot_change_profile():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'profile': 'WORK_PURCHASE'}})
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_declaration_rejects_unknown_claim_field():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'unexpected': 1}})
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


@pytest.mark.parametrize('bad', [
    {'requested_amount_vnd': '1200000'},   # amount must be strict int
    {'payer_type': 'BOGUS'},               # not a PayerType literal
    {'purpose_type': 42},                  # not a PurposeType literal
    {'received_full': 'maybe'},            # not a bool
])
def test_declaration_rejects_malformed_field_values(bad):
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': bad})
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


def test_add_evidence_accepts_only_owned_ids():
    snapshot, decision = _travel()
    good = human_action(snapshot, kind='ADD_EVIDENCE', mode='EMPLOYEE',
                        payload={'evidence_ids': [snapshot.evidence[0].id]})
    assert validate_human_action(good, snapshot, decision) is good

    foreign = human_action(snapshot, kind='ADD_EVIDENCE', mode='EMPLOYEE',
                           payload={'evidence_ids': ['e-does-not-exist']})
    with pytest.raises(DomainError):
        validate_human_action(foreign, snapshot, decision)


def test_propose_correction_is_employee_only_and_needs_no_refs():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='PROPOSE_CORRECTION', mode='EMPLOYEE',
                          payload={'field': 'total', 'value': '2000001'})
    assert validate_human_action(action, snapshot, decision) is action


# --- Confirmations --------------------------------------------------------------

def _ref(evidence_id: str, locator: str = 'total', raw_value: str = '2000001') -> dict:
    return {'evidence_id': evidence_id, 'page_index': 0, 'block_id': 'b-1',
            'locator': locator, 'raw_value': raw_value}


def test_confirm_field_requires_owned_resolvable_refs():
    snapshot, decision = _travel()
    foreign = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': 'e-foreign.fields.total', 'value': '1', 'refs': [_ref('e-foreign')],
    })
    with pytest.raises(DomainError):
        validate_human_action(foreign, snapshot, decision)


def test_confirm_field_requires_valid_path():
    snapshot, decision = _travel()
    bad_path = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': 'total', 'value': '1', 'refs': [_ref(snapshot.evidence[0].id)],
    })
    with pytest.raises(DomainError):
        validate_human_action(bad_path, snapshot, decision)


def test_confirm_field_accepts_owned_path_and_refs():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': f'{evidence_id}.fields.total', 'value': '2000001',
        'refs': [_ref(evidence_id)],
    })
    assert validate_human_action(action, snapshot, decision) is action


def test_numeric_confirmation_must_be_canonical():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    grouped = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': f'{evidence_id}.fields.total', 'value': '2.000.001',
        'refs': [_ref(evidence_id)],
    })
    with pytest.raises(DomainError):
        validate_human_action(grouped, snapshot, decision)


def test_confirm_mapping_rejects_duplicate_ids():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_MAPPING', mode='REVIEWER', payload={
        'pairs': [['i-1', 'r-1'], ['i-1', 'r-2']], 'refs': [_ref(evidence_id)],
    })
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_confirm_mapping_accepts_owned_pairs_and_refs():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_MAPPING', mode='REVIEWER', payload={
        'pairs': [['i-primary-1', 'i-receipt-1']], 'refs': [_ref(evidence_id)],
    })
    assert validate_human_action(action, snapshot, decision) is action


@pytest.mark.parametrize('field', [
    'total',                              # no evidence/segment
    'e-x.fields.total',                   # evidence not owned
    'e-1.fields.bogus',                   # unsupported fields sub-path
    'e-1.items..quantity',                # missing item_id
    'e-1.items.i-1.bogus',                # unsupported item sub-field
    'e-1.items.i-1',                      # missing sub-field
])
def test_confirm_field_rejects_malformed_paths(field):
    snapshot, decision = _travel()
    owned = snapshot.evidence[0].id
    resolved = field.replace('e-1', owned).replace('e-x', 'e-foreign')
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': resolved, 'value': '1200000', 'refs': [_ref(owned)],
    })
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


@pytest.mark.parametrize('value', [1200000, 1200000.0, True])
def test_numeric_confirmation_rejects_non_string(value):
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': f'{evidence_id}.fields.total', 'value': value,
        'refs': [_ref(evidence_id)],
    })
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


# --- DENY -----------------------------------------------------------------------

def test_deny_requires_issue_owner_mode():
    snapshot, _ = _travel()
    issue = _issue(owner='REVIEWER')
    decision = _decision_with(issue)
    wrong = human_action(snapshot, kind='DENY', mode='EMPLOYEE',
                         payload={'issue_id': issue.id}, issue_id=issue.id)
    with pytest.raises(DomainError):
        validate_human_action(wrong, snapshot, decision)

    right = human_action(snapshot, kind='DENY', mode='REVIEWER',
                         payload={'issue_id': issue.id}, issue_id=issue.id)
    assert validate_human_action(right, snapshot, decision) is right


def test_deny_unknown_issue_is_rejected():
    snapshot, _ = _travel()
    decision = _decision_with(_issue())
    action = human_action(snapshot, kind='DENY', mode='REVIEWER',
                          payload={'issue_id': 'missing'}, issue_id='missing')
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


# --- OVERRIDE -------------------------------------------------------------------

def test_override_rejects_unknown_operation():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='OVERRIDE', mode='POLICY_OWNER',
                          payload={'operation': 'MAGIC', 'values': {}})
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_override_validates_underlying_role():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    # EMPLOYEE wrapping CONFIRM_FIELD must still fail the REVIEWER check.
    action = human_action(snapshot, kind='OVERRIDE', mode='EMPLOYEE', payload={
        'operation': 'CONFIRM_FIELD',
        'values': {'field': f'{evidence_id}.fields.total', 'value': '1',
                   'refs': [_ref(evidence_id)]},
    })
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


def test_override_wrapped_payload_keyset_is_enforced():
    snapshot, decision = _travel()
    evidence_id = snapshot.evidence[0].id
    # Missing the required ``refs`` key inside the wrapped CONFIRM_FIELD.
    action = human_action(snapshot, kind='OVERRIDE', mode='REVIEWER', payload={
        'operation': 'CONFIRM_FIELD',
        'values': {'field': f'{evidence_id}.fields.total', 'value': '1'},
    })
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


def test_override_classify_requires_policy_owner_and_other_profile():
    other = routine_snapshot(1_200_000, profile='OTHER')
    decision = evaluate(other, resolved_bundle('1200000', profile='OTHER'))
    action = human_action(other, kind='OVERRIDE', mode='POLICY_OWNER',
                          payload={'operation': 'CLASSIFY_PROFILE', 'values': {'profile': 'TRAVEL'}})
    assert validate_human_action(action, other, decision) is action

    not_owner = human_action(other, kind='OVERRIDE', mode='REVIEWER',
                             payload={'operation': 'CLASSIFY_PROFILE',
                                      'values': {'profile': 'TRAVEL'}})
    with pytest.raises(DomainError):
        validate_human_action(not_owner, other, decision)


@pytest.mark.parametrize('operation, values', [
    ('DENY', {'issue_id': 'SRC-02:case', 'approve_all': True}),
    ('CLASSIFY_PROFILE', {'profile': 'TRAVEL', 'approve_all': True}),
])
def test_override_rejects_extra_keys_in_wrapped_operation(operation, values):
    other = routine_snapshot(1_200_000, profile='OTHER')
    decision = _decision_with(_issue(id='SRC-02:case', owner='EMPLOYEE'))
    mode = 'POLICY_OWNER' if operation == 'CLASSIFY_PROFILE' else 'EMPLOYEE'
    action = human_action(other, kind='OVERRIDE', mode=mode,
                          payload={'operation': operation, 'values': values})
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, other, decision)
    assert exc.value.code == 'INVALID_ACTION'
    assert 'approve_all' in exc.value.message


def test_override_wrapped_authorization_role_rejected():
    """OVERRIDE wrapping APPROVE_AMOUNT must satisfy the APPROVER/POLICY_OWNER role."""
    snapshot, decision = _travel(2_000_001)
    action = human_action(snapshot, kind='OVERRIDE', mode='REVIEWER', payload={
        'operation': 'APPROVE_AMOUNT',
        'values': _auth_payload(snapshot, 2_000_001),
    })
    with pytest.raises(DomainError) as exc:
        validate_human_action(action, snapshot, decision)
    assert exc.value.code == 'INVALID_ACTION'


# --- STOP -----------------------------------------------------------------------

def test_stop_requires_a_run_id():
    snapshot, decision = _travel()
    action = human_action(snapshot, kind='STOP', mode='EMPLOYEE', payload={'run_id': ''})
    with pytest.raises(DomainError):
        validate_human_action(action, snapshot, decision)


# --- authorization_matches ------------------------------------------------------

def test_authorization_matches_requires_exact_scope():
    snapshot, _ = _travel(5_000_001)
    auth = _matching_exception(snapshot, 5_000_001)
    assert authorization_matches(auth, snapshot, 5_000_001)
    assert not authorization_matches(auth, snapshot, 5_000_000)
    stale = snapshot.model_copy(update={'case_version': snapshot.case_version + 1})
    assert not authorization_matches(auth, stale, 5_000_001)


# --- Repository: revision, invalidation, closure --------------------------------

def _create_run_with_request(repo, case, bundle, policy):
    snapshot = repo.snapshot(case.id, policy)
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    return snapshot, run


def _result(snapshot, bundle):
    from invoice_referee.domain.models import PipelineResult

    return PipelineResult(
        decision=evaluate(snapshot, bundle), bundle=bundle, artifacts=[],
        stage_durations_ms={}, provider_calls=0, repair_calls=0,
    )


def test_confirmation_bumps_version_and_invalidates_authorization(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, bundle = seed_case(repo)
    from tests.builders import demo_policy

    snapshot, _ = _create_run_with_request(repo, case, bundle, demo_policy())
    assert repo.get_payment_request(case.id) is not None

    evidence_id = case.evidence[0].id
    action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
        'field': f'{evidence_id}.fields.total', 'value': str(case.claim.requested_amount_vnd),
        'refs': [_ref(evidence_id, raw_value=str(case.claim.requested_amount_vnd))],
    })
    updated = repo.apply_human_action(action)
    assert updated.case_version == case.case_version + 1
    assert repo.get_payment_request(case.id) is None  # revoked in the same txn
    # The confirmation pins the new version; no authorization survives the bump.
    rebuilt = repo.snapshot(case.id, demo_policy())
    assert action.id in rebuilt.active_action_ids
    assert rebuilt.authorizations == []


def test_approval_keeps_version_and_becomes_authorization(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, _ = seed_case(repo)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                          payload=_auth_payload(snapshot, 1_200_000))
    updated = repo.apply_human_action(action)
    assert updated.case_version == case.case_version  # approval does not bump
    rebuilt = repo.snapshot(case.id, demo_policy())
    assert rebuilt.active_action_ids == [action.id]
    assert rebuilt.authorizations[0].amount_vnd == 1_200_000
    assert rebuilt.authorizations[0].kind == 'AMOUNT_APPROVAL'


def test_authorization_from_wrong_mode_is_not_in_force(tmp_path):
    """Defense in depth: a row with a non-authorizing mode never authorizes.

    The validator blocks this upstream; the repository must not surface a
    malformed row as an in-force authorization either.
    """
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, _ = seed_case(repo)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    forged = human_action(snapshot, kind='APPROVE_AMOUNT', mode='REVIEWER',
                          payload=_auth_payload(snapshot, 1_200_000))
    repo.apply_human_action(forged)  # bypasses the validator on purpose
    rebuilt = repo.snapshot(case.id, demo_policy())
    assert rebuilt.authorizations == []


def test_propose_correction_is_not_an_effective_input(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, _ = seed_case(repo)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    before_hash = snapshot.input_hash
    action = human_action(snapshot, kind='PROPOSE_CORRECTION', mode='EMPLOYEE',
                          payload={'field': 'total', 'value': '1200000'})
    repo.apply_human_action(action)
    rebuilt = repo.snapshot(case.id, demo_policy())
    assert action.id not in rebuilt.active_action_ids
    # A proposal is not a fact: it must not appear as a hashed confirmation nor
    # change the snapshot hash (so it cannot silently invalidate a run).
    assert action.id not in [a.id for a in rebuilt.confirmations]
    assert rebuilt.input_hash == before_hash
    assert rebuilt.case_version == case.case_version  # a proposal is not a fact


def test_deny_rejects_case_and_keeps_history(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, _ = seed_case(repo)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    issue = _issue(owner='EMPLOYEE')
    action = human_action(snapshot, kind='DENY', mode='EMPLOYEE',
                          payload={'issue_id': issue.id}, issue_id=issue.id,
                          reason='Nhân viên từ chối bổ sung.')
    repo.apply_human_action(action)
    assert repo.get_case(case.id).workflow_state == 'REJECTED'
    actions = [a for a in repo.snapshot(case.id, demo_policy()).confirmations]
    assert any(a.id == action.id and a.reason for a in actions)  # reason kept, no delete


def test_override_classify_moves_other_to_supported(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, _ = seed_case(repo, profile='OTHER')
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    assert snapshot.claim.profile == 'OTHER'
    action = human_action(snapshot, kind='OVERRIDE', mode='POLICY_OWNER', payload={
        'operation': 'CLASSIFY_PROFILE', 'values': {'profile': 'TRAVEL'},
    })
    updated = repo.apply_human_action(action)
    assert updated.claim.profile == 'TRAVEL'
    assert updated.case_version == case.case_version + 1


# --- Human sequences at repository/evaluation scope (brief step 3) -------------

def test_exception_alone_does_not_authorize_over_five_million(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    amount = 5_000_001
    case, bundle = seed_case(repo, amount=amount)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    grant = human_action(snapshot, kind='GRANT_POLICY_EXCEPTION', mode='POLICY_OWNER',
                         payload=_auth_payload(snapshot, amount))
    validate_human_action(grant, snapshot, evaluate(snapshot, bundle))
    repo.apply_human_action(grant)

    after_exception = repo.snapshot(case.id, demo_policy())
    decision = evaluate(after_exception, bundle)
    # The exception closes LIM-01 only; AUTH-01 still requires a separate approval.
    assert decision.action == 'ESCALATE'
    assert any(c.rule_id == 'LIM-01' and c.status == 'PASS' for c in decision.checks)
    assert any(c.rule_id == 'AUTH-01' and c.status == 'FAIL' for c in decision.checks)


def test_approval_over_five_million_with_exception_creates_human_request(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    amount = 5_000_001
    case, bundle = seed_case(repo, amount=amount)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    repo.apply_human_action(human_action(
        snapshot, kind='GRANT_POLICY_EXCEPTION', mode='POLICY_OWNER',
        payload=_auth_payload(snapshot, amount)))

    after_exception = repo.snapshot(case.id, demo_policy())
    approve = human_action(after_exception, kind='APPROVE_AMOUNT', mode='POLICY_OWNER',
                           payload=_auth_payload(after_exception, amount))
    validate_human_action(approve, after_exception, evaluate(after_exception, bundle))
    repo.apply_human_action(approve)

    final = repo.snapshot(case.id, demo_policy())
    decision = evaluate(final, bundle)
    assert decision.action == 'CREATE_PAYMENT_REQUEST'
    assert decision.completion_basis == 'HUMAN_AUTHORIZED'
    run = repo.create_run(final)
    repo.finalize_run(run.id, _result(final, bundle))
    request = repo.get_payment_request(case.id)
    assert request is not None and request.amount_vnd == amount
    assert request.completion_basis == 'HUMAN_AUTHORIZED'


def test_approver_approval_enables_human_authorized_request(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    amount = 2_000_001
    case, bundle = seed_case(repo, amount=amount)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    assert evaluate(snapshot, bundle).action == 'ESCALATE'  # over auto limit
    run1 = repo.create_run(snapshot)
    repo.finalize_run(run1.id, _result(snapshot, bundle))
    assert repo.get_payment_request(case.id) is None  # zero request while unclear

    after = repo.snapshot(case.id, demo_policy())
    approve = human_action(after, kind='APPROVE_AMOUNT', mode='APPROVER',
                           payload=_auth_payload(after, amount))
    validate_human_action(approve, after, evaluate(after, bundle))
    repo.apply_human_action(approve)

    approved = repo.snapshot(case.id, demo_policy())
    run2 = repo.create_run(approved)
    repo.finalize_run(run2.id, _result(approved, bundle))
    request = repo.get_payment_request(case.id)
    assert request is not None and request.amount_vnd == amount
    assert request.completion_basis == 'HUMAN_AUTHORIZED'
    assert repo.get_case(case.id).workflow_state == 'REQUEST_CREATED'


def test_data_change_after_approval_invalidates_it_and_revokes_request(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    amount = 2_000_001
    case, bundle = seed_case(repo, amount=amount)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    approve = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER',
                           payload=_auth_payload(snapshot, amount))
    repo.apply_human_action(approve)
    approved = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(approved)
    repo.finalize_run(run.id, _result(approved, bundle))
    assert repo.get_payment_request(case.id) is not None

    # A declaration changes effective input: the approval must lose force and
    # the current request is revoked in the same transaction.
    revised = repo.snapshot(case.id, demo_policy())
    repo.apply_human_action(human_action(
        revised, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
        payload={'changes': {'purpose': 'Công tác đã đổi mô tả'}}))

    rebuilt = repo.snapshot(case.id, demo_policy())
    assert rebuilt.case_version == revised.case_version + 1
    assert rebuilt.authorizations == []  # the old approval is out of scope
    assert repo.get_payment_request(case.id) is None
    assert evaluate(rebuilt, bundle).action == 'ESCALATE'  # needs a fresh approval


def test_deny_preserves_the_original_decision_row(tmp_path):
    repo = Repository(tmp_path / 'c.sqlite', tmp_path / 'a')
    case, bundle = seed_case(repo)
    from tests.builders import demo_policy

    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.finalize_run(run.id, _result(snapshot, bundle))
    before = repo._read('SELECT COUNT(*) AS n FROM decisions WHERE case_id = ?', (case.id,))[0]['n']
    assert before == 1

    current = repo.snapshot(case.id, demo_policy())
    issue = _issue(owner='EMPLOYEE')
    repo.apply_human_action(human_action(
        current, kind='DENY', mode='EMPLOYEE', payload={'issue_id': issue.id},
        issue_id=issue.id, reason='Từ chối bổ sung; giữ nguyên quyết định gốc.'))
    after = repo._read('SELECT COUNT(*) AS n FROM decisions WHERE case_id = ?', (case.id,))[0]['n']
    assert after == before  # DENY never deletes the original decision
