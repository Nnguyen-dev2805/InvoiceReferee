"""T08 integration — human closure and atomic action through CaseService.

RED first: fails to collect until ``invoice_referee.application.service`` exists.
Drives the T07 action sequences through the real service (validate -> persist ->
auto-reevaluate) and asserts ACTUAL current/history request counts. Fake
providers only; NO network. Does NOT prove live provider quality.
"""
from __future__ import annotations

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.storage.repository import Repository
from tests.builders import human_action
from tests.integration.conftest import build_runtime


def _current(runtime):
    """The current run's (bundle, decision) — the basis a human acts on."""
    run = runtime.repo.get_run(runtime.repo.get_case(runtime.case_id).current_run_id)
    return run.result.bundle, run.result.decision


def _drive(runtime, run):
    """Release the OCR barrier and wait for the run (object or id) to end."""
    runtime.release.set()
    run_id = run.id if hasattr(run, 'id') else run
    return runtime.service.wait(run_id, timeout_seconds=5)


# --- DENY: persists a REJECT decision without calling providers -----------------

def test_deny_persists_reject_without_providers(tmp_path):
    rt = build_runtime(tmp_path, amount=2_000_001)
    try:
        run = rt.service.start_run(rt.case_id)
        ended = _drive(rt, run)
        assert ended.result.decision.action == 'ESCALATE'
        calls_before = len(rt.providers.calls)

        _bundle, decision = _current(rt)
        issue = next(i for i in decision.issues if i.blockers == ['AUTH-01'])
        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(
            snapshot, kind='DENY', mode=issue.owner_mode,
            payload={'issue_id': issue.id}, issue_id=issue.id, reason='Không hợp lệ',
        )
        case = rt.service.act(action)
        denied = rt.service.wait(case.current_run_id, timeout_seconds=5)

        assert denied.result.decision.action == 'REJECT'
        assert any('Không hợp lệ' in r for r in denied.result.decision.reasons)
        assert len(rt.providers.calls) == calls_before  # no providers on DENY
        assert rt.repo.get_payment_request(rt.case_id) is None
        assert rt.repo.get_case(rt.case_id).workflow_state == 'REJECTED'
    finally:
        rt.close()


def test_deny_releases_the_run_slot(tmp_path):
    # CRITICAL regression: DENY finalizes synchronously with NO worker, so it must
    # not leak the single run slot. A later run/mutation must still be accepted.
    rt = build_runtime(tmp_path, amount=2_000_001)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        _bundle, decision = _current(rt)
        issue = next(i for i in decision.issues if i.blockers == ['AUTH-01'])
        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        deny = human_action(snapshot, kind='DENY', mode=issue.owner_mode,
                            payload={'issue_id': issue.id}, reason='Không hợp lệ')
        denied = rt.service.act(deny)
        assert rt.repo.get_case(rt.case_id).workflow_state == 'REJECTED'

        # The slot must be free: a fresh run on the same case is accepted.
        again = rt.service.start_run(rt.case_id)
        assert rt.entered.wait(timeout=2)
        rt.release.set()
        assert rt.service.wait(again.id, timeout_seconds=5).status in {'SUCCEEDED', 'FAILED'}
    finally:
        rt.close()


def test_override_deny_releases_the_run_slot(tmp_path):
    rt = build_runtime(tmp_path, amount=2_000_001)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        _bundle, decision = _current(rt)
        issue = next(i for i in decision.issues if i.blockers == ['AUTH-01'])
        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(
            snapshot, kind='OVERRIDE', mode=issue.owner_mode,
            payload={'operation': 'DENY', 'values': {'issue_id': issue.id}},
            reason='Override từ chối có căn cứ')
        rt.service.act(action)
        assert rt.repo.get_case(rt.case_id).workflow_state == 'REJECTED'
        # Slot free again.
        again = rt.service.start_run(rt.case_id)
        assert rt.entered.wait(timeout=2)
        rt.release.set()
        rt.service.wait(again.id, timeout_seconds=5)
    finally:
        rt.close()


# --- APPROVE_AMOUNT: reevaluates to a HUMAN_AUTHORIZED request ------------------

def test_approval_reevaluates_to_human_authorized_request(tmp_path):
    rt = build_runtime(tmp_path, amount=2_000_001)
    try:
        run = rt.service.start_run(rt.case_id)
        ended = _drive(rt, run)
        assert ended.result.decision.action == 'ESCALATE'
        original_run = rt.repo.get_run(run.id)

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='APPROVE_AMOUNT', mode='APPROVER', payload={
            'amount_vnd': 2_000_001, 'profile': 'TRAVEL',
            'purpose': snapshot.claim.purpose, 'policy_version': snapshot.policy.version,
        })
        case = rt.service.act(action)
        final = _drive(rt, case.current_run_id)

        assert final.result.decision.action == 'CREATE_PAYMENT_REQUEST'
        request = rt.repo.get_payment_request(rt.case_id)
        assert request.amount_vnd == 2_000_001
        assert request.completion_basis == 'HUMAN_AUTHORIZED'
        # The approval did NOT change the data version; the original run/decision
        # are preserved in history.
        assert rt.repo.get_case(rt.case_id).case_version == original_run.case_version
        assert rt.repo.get_run(original_run.id).result.decision.action == 'ESCALATE'
    finally:
        rt.close()


# --- CONFIRM_FIELD deep path: a valid confirmation makes a fact USABLE ----------

def test_confirm_field_makes_low_score_fact_usable(tmp_path):
    rt = build_runtime(tmp_path, score=None)
    try:
        run = rt.service.start_run(rt.case_id)
        ended = _drive(rt, run)
        assert ended.result.decision.action == 'REQUEST_INFO'
        bundle, _decision = _current(rt)
        doc = next(d for d in bundle.documents if d.kind == 'BILL')
        ref = doc.fields['total'].refs[0]
        field = f'{doc.evidence_id}.fields.total'

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
            'field': field, 'value': '1200000', 'refs': [ref.model_dump(mode='json')],
        })
        case = rt.service.act(action)
        assert case.current_run_id is not None and case.current_run_id != run.id
        final = _drive(rt, case.current_run_id)

        assert final.result.decision.action == 'CREATE_PAYMENT_REQUEST'
        assert rt.repo.get_payment_request(rt.case_id).amount_vnd == 1_200_000
    finally:
        rt.close()


def test_confirm_field_with_unresolvable_ref_is_rejected(tmp_path):
    rt = build_runtime(tmp_path, score=None)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        bundle, _decision = _current(rt)
        doc = next(d for d in bundle.documents if d.kind == 'BILL')
        bad_ref = doc.fields['total'].refs[0].model_copy(update={'locator': 'no-such-locator'})

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
            'field': f'{doc.evidence_id}.fields.total', 'value': '1200000',
            'refs': [bad_ref.model_dump(mode='json')],
        })
        with pytest.raises(DomainError) as exc:
            rt.service.act(action)
        assert exc.value.code == 'INVALID_ACTION'
        # No version bump, no new run.
        assert rt.repo.get_case(rt.case_id).current_run_id == run.id
    finally:
        rt.close()


def test_confirm_field_naming_unknown_evidence_is_rejected(tmp_path):
    rt = build_runtime(tmp_path, score=None)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='CONFIRM_FIELD', mode='REVIEWER', payload={
            'field': 'ev-not-in-bundle.fields.total', 'value': '1200000',
            'refs': [{'evidence_id': rt.repo.get_case(rt.case_id).evidence[0].id,
                      'page_index': 0, 'block_id': 'b-1', 'locator': 'total',
                      'raw_value': '1200000'}],
        })
        # T07 rejects an evidence id that is not owned by the case.
        with pytest.raises(DomainError) as exc:
            rt.service.act(action)
        assert exc.value.code == 'INVALID_ACTION'
    finally:
        rt.close()


# --- OVERRIDE: keeps the original run/decision, runs a fresh evaluation ---------

def test_override_keeps_original_run_and_decision(tmp_path):
    rt = build_runtime(tmp_path, score=None)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        bundle, _decision = _current(rt)
        doc = next(d for d in bundle.documents if d.kind == 'BILL')
        ref = doc.fields['total'].refs[0]

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='OVERRIDE', mode='REVIEWER', payload={
            'operation': 'CONFIRM_FIELD',
            'values': {'field': f'{doc.evidence_id}.fields.total', 'value': '1200000',
                       'refs': [ref.model_dump(mode='json')]},
        }, reason='Reviewer xác nhận số tiền trên chứng từ gốc')
        case = rt.service.act(action)
        final = _drive(rt, case.current_run_id)

        assert final.result.decision.action == 'CREATE_PAYMENT_REQUEST'
        # The original run/decision are preserved, never overwritten.
        original = rt.repo.get_run(run.id)
        assert original.result.decision.action == 'REQUEST_INFO'
        assert original.status == 'SUCCEEDED'
        assert rt.repo.get_payment_request(rt.case_id) is not None
    finally:
        rt.close()


def test_override_confirm_field_with_unresolvable_ref_is_rejected(tmp_path):
    rt = build_runtime(tmp_path, score=None)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        bundle, _decision = _current(rt)
        doc = next(d for d in bundle.documents if d.kind == 'BILL')
        bad_ref = doc.fields['total'].refs[0].model_copy(update={'locator': 'nope'})

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='OVERRIDE', mode='REVIEWER', payload={
            'operation': 'CONFIRM_FIELD',
            'values': {'field': f'{doc.evidence_id}.fields.total', 'value': '1200000',
                       'refs': [bad_ref.model_dump(mode='json')]},
        })
        with pytest.raises(DomainError) as exc:
            rt.service.act(action)
        assert exc.value.code == 'INVALID_ACTION'
        assert rt.repo.get_case(rt.case_id).current_run_id == run.id
    finally:
        rt.close()


# --- CONFIRM_MAPPING deep checks: resolution, coverage, units -------------------

def test_confirm_mapping_rejects_unresolvable_item_id(tmp_path):
    rt = build_runtime(tmp_path, profile='WORK_PURCHASE', amount=900_000)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        bundle, _decision = _current(rt)
        ref = next(d for d in bundle.documents if d.kind == 'BILL').fields['total'].refs[0]

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='CONFIRM_MAPPING', mode='REVIEWER', payload={
            'pairs': [['i-primary-1', 'i-receipt-999']],
            'refs': [ref.model_dump(mode='json')],
        })
        with pytest.raises(DomainError) as exc:
            rt.service.act(action)
        assert exc.value.code == 'INVALID_ACTION'
    finally:
        rt.close()


def test_confirm_mapping_rejects_incomplete_coverage(tmp_path):
    # A receipt with TWO items and a mapping that covers only one must be refused:
    # no unmatched line may be silently dropped.
    from invoice_referee.application.service import CaseService
    from invoice_referee.config import activate_demo_policy
    from invoice_referee.extraction.providers import FakeProviders
    from tests.builders import demo_policy
    from tests.integration.support import seed_case

    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo, amount=900_000, profile='WORK_PURCHASE')
    receipt = next(d for d in bundle.documents if d.kind == 'GOODS_RECEIPT')
    extra = receipt.items[0].model_copy(update={'id': receipt.items[0].id + '-x'})
    receipt2 = receipt.model_copy(update={'items': [*receipt.items, extra]})
    docs = {d.evidence_id: d for d in bundle.documents}
    docs[receipt.evidence_id] = receipt2
    providers = FakeProviders(documents=docs, registries=bundle.registries,
                              mapping=bundle.mapping)
    policy = activate_demo_policy(demo_policy(active=False), 'fixture')
    service = CaseService(repo, providers, policy)
    try:
        run = service.start_run(case.id)
        ended = service.wait(run.id, timeout_seconds=5)
        assert ended.result.decision.action == 'REQUEST_INFO'
        ref = next(d for d in bundle.documents if d.kind == 'BILL').fields['total'].refs[0]
        snapshot = repo.snapshot(case.id, policy)
        action = human_action(snapshot, kind='CONFIRM_MAPPING', mode='REVIEWER', payload={
            'pairs': [['i-primary-1', 'i-receipt-1']],
            'refs': [ref.model_dump(mode='json')],
        })
        with pytest.raises(DomainError) as exc:
            service.act(action)
        assert exc.value.code == 'INVALID_ACTION'
    finally:
        service.close()


def test_confirm_mapping_accepts_full_valid_mapping(tmp_path):
    rt = build_runtime(tmp_path, profile='WORK_PURCHASE', amount=900_000)
    try:
        run = rt.service.start_run(rt.case_id)
        _drive(rt, run)
        bundle, _decision = _current(rt)
        ref = next(d for d in bundle.documents if d.kind == 'BILL').fields['total'].refs[0]

        snapshot = rt.repo.snapshot(rt.case_id, rt.service.policy)
        action = human_action(snapshot, kind='CONFIRM_MAPPING', mode='REVIEWER', payload={
            'pairs': [['i-primary-1', 'i-receipt-1']],
            'refs': [ref.model_dump(mode='json')],
        })
        case = rt.service.act(action)
        final = _drive(rt, case.current_run_id)
        assert final.result.decision.action == 'CREATE_PAYMENT_REQUEST'
    finally:
        rt.close()


# --- set_policy: idle-only, SYSTEM vs human, audit -----------------------------

def test_set_policy_only_when_idle(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    new = runtime.service.policy.model_copy(update={'word_review_threshold': '0.75'})
    with pytest.raises(DomainError) as exc:
        runtime.service.set_policy(new, actor_mode='SYSTEM', reason='auto')
    assert exc.value.code == 'RUN_BUSY'
    runtime.service.stop(run.id)
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


def test_set_policy_system_changes_only_threshold(runtime):
    base = runtime.service.policy
    runtime.service.set_policy(
        base.model_copy(update={'word_review_threshold': '0.75', 'threshold_version': 'tv-2'}),
        actor_mode='SYSTEM', reason='auto adapt from calibration',
    )
    active = runtime.repo.get_active_policy()
    assert active.word_review_threshold == '0.75'
    assert active.threshold_version == 'tv-2'
    assert active.activation_id == base.activation_id
    assert active.version == base.version
    assert active.auto_approval_max == base.auto_approval_max
    assert active.standard_policy_max == base.standard_policy_max
    assert runtime.service.policy.word_review_threshold == '0.75'
    event = [e for e in runtime.repo.history(runtime.case_id) or [] if e.kind == 'POLICY_CHANGE']
    # Policy events are case-global (case_id None); assert via a full read.
    globals_ = runtime.repo._read("SELECT payload_json FROM events WHERE kind='POLICY_CHANGE'")
    assert globals_ and 'SYSTEM' in globals_[-1]['payload_json']


def test_set_policy_system_cannot_change_limits(runtime):
    base = runtime.service.policy
    with pytest.raises(DomainError) as exc:
        runtime.service.set_policy(
            base.model_copy(update={'auto_approval_max': 9_000_000}),
            actor_mode='SYSTEM', reason='auto',
        )
    assert exc.value.code == 'INVALID_INPUT'
    assert runtime.repo.get_active_policy().auto_approval_max == base.auto_approval_max


def test_set_policy_policy_owner_activation(runtime):
    base = runtime.service.policy
    new = base.model_copy(update={'activation_id': 'act-owner-2', 'origin': 'developer_activated_demo'})
    runtime.service.set_policy(new, actor_mode='POLICY_OWNER', reason='Kích hoạt lại demo')
    assert runtime.repo.get_active_policy().activation_id == 'act-owner-2'
    assert runtime.service.policy.activation_id == 'act-owner-2'
    row = runtime.repo._read("SELECT payload_json FROM events WHERE kind='POLICY_CHANGE' ORDER BY rowid DESC LIMIT 1")
    assert 'POLICY_OWNER' in row[0]['payload_json']
    assert '"automatic": false' in row[0]['payload_json']


# --- ADD_EVIDENCE: atomic linkage + consistent version bump ---------------------

def test_add_evidence_bumps_version_atomically(runtime):
    before = runtime.repo.get_case(runtime.case_id)
    snapshot = runtime.repo.snapshot(runtime.case_id, runtime.service.policy)
    owned_id = before.evidence[0].id
    action = human_action(snapshot, kind='ADD_EVIDENCE', mode='EMPLOYEE',
                          payload={'evidence_ids': [owned_id]})
    case = runtime.service.act(action)
    assert case.case_version == before.case_version + 1
    runtime.release.set()
    runtime.service.wait(case.current_run_id, timeout_seconds=5)


def test_add_evidence_with_foreign_id_is_rejected_atomically(runtime):
    before = runtime.repo.get_case(runtime.case_id)
    snapshot = runtime.repo.snapshot(runtime.case_id, runtime.service.policy)
    action = human_action(snapshot, kind='ADD_EVIDENCE', mode='EMPLOYEE',
                          payload={'evidence_ids': ['ev-foreign']})
    with pytest.raises(DomainError) as exc:
        runtime.service.act(action)
    assert exc.value.code == 'INVALID_ACTION'
    # All-or-nothing: no version bump, no action row, no new run.
    assert runtime.repo.get_case(runtime.case_id).case_version == before.case_version
    assert runtime.repo.get_case(runtime.case_id).current_run_id is None


def test_add_evidence_links_uploads_and_bumps_version(tmp_path):
    from invoice_referee.domain.models import Upload

    rt = build_runtime(tmp_path)
    try:
        before = rt.repo.get_case(rt.case_id)
        upload = Upload(original_name='extra.pdf', mime='application/pdf',
                        content=b'%PDF-1.4\n% extra evidence\n%%EOF\n', role='CONTEXT')
        case = rt.service.add_evidence(
            case_id=rt.case_id, mode='EMPLOYEE', uploads=[upload], reason='Bổ sung chứng từ')
        assert case.case_version == before.case_version + 1
        assert len(case.evidence) == len(before.evidence) + 1
        assert case.current_run_id is not None
        _drive(rt, case.current_run_id)
    finally:
        rt.close()


def test_add_evidence_invalid_batch_is_all_or_nothing(tmp_path):
    from invoice_referee.domain.models import Upload

    rt = build_runtime(tmp_path)
    try:
        before = rt.repo.get_case(rt.case_id)
        # One valid upload + one EMPTY file: the batch must not partially link.
        bad_batch = [
            Upload(original_name='ok.pdf', mime='application/pdf',
                   content=b'%PDF-1.4 ok\n%%EOF\n', role='CONTEXT'),
            Upload(original_name='empty.pdf', mime='application/pdf',
                   content=b'', role='CONTEXT'),
        ]
        with pytest.raises(DomainError) as exc:
            rt.service.add_evidence(
                case_id=rt.case_id, mode='EMPLOYEE', uploads=bad_batch, reason='Bổ sung')
        assert exc.value.code == 'INVALID_INPUT'
        after = rt.repo.get_case(rt.case_id)
        assert after.case_version == before.case_version
        assert len(after.evidence) == len(before.evidence)
        assert after.current_run_id is None
    finally:
        rt.close()


# --- Stale action version -------------------------------------------------------

def test_stale_action_version_is_rejected(runtime):
    snapshot = runtime.repo.snapshot(runtime.case_id, runtime.service.policy)
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Đã sửa'}})
    stale = action.model_copy(update={'case_version': snapshot.case_version - 1})
    with pytest.raises(DomainError) as exc:
        runtime.service.act(stale)
    assert exc.value.code == 'INVALID_ACTION'
