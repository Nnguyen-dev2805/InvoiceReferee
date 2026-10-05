"""T08 integration — one-process executor, Stop guard and execution controls.

RED first: this file fails to collect until ``invoice_referee.application.service``
(and ``executor``) exist. Values come from ``seed_case`` + ``FakeProviders``; the
OCR barrier makes the Stop/finalize orderings deterministic. NO network.

These are FAKE-provider proofs of wiring (slot, Stop ordering, idempotency, busy
and stale semantics). They do NOT prove a remote provider cancelled inference.
"""
from __future__ import annotations

import threading

import pytest

from invoice_referee.application.service import CaseService
from invoice_referee.config import activate_demo_policy
from invoice_referee.domain.models import DomainError
from invoice_referee.storage.repository import Repository
from tests.builders import demo_policy, human_action
from tests.integration.conftest import BarrierProviders
from tests.integration.support import seed_case


# --- Brief step 1: persisted Stop vs a late provider result ---------------------

def test_acknowledged_stop_blocks_late_payment(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    reply = runtime.service.stop(run.id)
    assert reply.status == 'STOP_REQUESTED'
    assert runtime.repo.get_run(run.id).stop_requested is True
    runtime.release.set()
    ended = runtime.service.wait(run.id, timeout_seconds=5)
    assert ended.status == 'STOPPED'
    assert runtime.repo.get_payment_request(runtime.case_id) is None
    assert any(e.kind == 'STOP_REQUESTED' for e in runtime.repo.history(runtime.case_id))


# --- Busy semantics: human input during RUNNING is refused ----------------------

def test_act_during_running_is_run_busy(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    snapshot = runtime.repo.snapshot(runtime.case_id, runtime.service.policy)
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Đã bổ sung mô tả'}})
    with pytest.raises(DomainError) as exc:
        runtime.service.act(action)
    assert exc.value.code == 'RUN_BUSY'
    # The stop control is still accepted while busy.
    assert runtime.service.stop(run.id).status == 'STOP_REQUESTED'
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


def test_start_run_while_busy_is_run_busy(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    with pytest.raises(DomainError) as exc:
        runtime.service.start_run(runtime.case_id)
    assert exc.value.code == 'RUN_BUSY'
    runtime.service.stop(run.id)
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


# --- Stop idempotency and already-completed ------------------------------------

def test_repeated_stop_is_idempotent(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    first = runtime.service.stop(run.id)
    second = runtime.service.stop(run.id)
    assert first.status == 'STOP_REQUESTED'
    assert second.status == 'STOP_REQUESTED'
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


def test_stop_after_completion_is_already_completed(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    runtime.release.set()
    ended = runtime.service.wait(run.id, timeout_seconds=5)
    assert ended.status == 'SUCCEEDED'
    assert runtime.service.stop(run.id).status == 'ALREADY_COMPLETED'
    # The completed request is untouched by the late stop.
    assert runtime.repo.get_payment_request(runtime.case_id) is not None


def test_stop_acknowledged_blocks_late_human_action(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    runtime.service.stop(run.id)
    snapshot = runtime.repo.snapshot(runtime.case_id, runtime.service.policy)
    action = human_action(snapshot, kind='SUPPLY_DECLARATION', mode='EMPLOYEE',
                          payload={'changes': {'purpose': 'Sửa muộn'}})
    with pytest.raises(DomainError) as exc:
        runtime.service.act(action)
    assert exc.value.code == 'RUN_BUSY'
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


def test_finalize_technical_honors_acknowledged_stop(tmp_path):
    # A technical error that surfaces AFTER an acknowledged Stop must still end
    # STOPPED: the persisted stop guard is never bypassed by an infra failure.
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _ = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    repo.request_stop(run.id)
    ended = repo.finalize_technical(run.id, code='EXECUTION_FAILED', reason='boom')
    assert ended.status == 'STOPPED'
    assert repo.get_payment_request(case.id) is None


# --- wait(): a timeout must NOT flip execution status to SUCCEEDED --------------

def test_wait_timeout_does_not_report_success(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    timed_out = runtime.service.wait(run.id, timeout_seconds=0.2)
    assert timed_out.status in {'RUNNING', 'STOP_REQUESTED'}
    assert timed_out.status != 'SUCCEEDED'
    # Cleanup: let the worker finish so the slot is released.
    runtime.service.stop(run.id)
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)


# --- Slot is released only after the worker ends -------------------------------

def test_slot_released_after_stopped_worker(runtime):
    run = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    runtime.service.stop(run.id)
    runtime.release.set()
    runtime.service.wait(run.id, timeout_seconds=5)
    # A new run on the same case is accepted once the slot is free.
    again = runtime.service.start_run(runtime.case_id)
    assert runtime.entered.wait(timeout=2)
    runtime.service.stop(again.id)
    runtime.release.set()
    runtime.service.wait(again.id, timeout_seconds=5)


# --- Startup: an interrupted in-flight run is marked, never auto-rerun ----------

def test_startup_marks_interrupted_run(tmp_path):
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, bundle = seed_case(repo)
    snapshot = repo.snapshot(case.id, demo_policy())
    run = repo.create_run(snapshot)
    entered, release = threading.Event(), threading.Event()
    providers = BarrierProviders(
        entered, release,
        documents={d.evidence_id: d for d in bundle.documents},
        registries={ev.id: __import__('tests.builders', fromlist=['text_registry']).text_registry(
            evidence_id=ev.id, amount='1200000') for ev in case.evidence},
    )
    service = CaseService(repo, providers,
                          activate_demo_policy(demo_policy(active=False), 'fixture'))
    try:
        # The run created before startup is presented as technical failed.
        assert repo.get_run(run.id).status == 'FAILED'
        assert repo.get_run(run.id).stage == 'interrupted'
        assert repo.get_payment_request(case.id) is None
    finally:
        release.set()
        service.close()


# --- Provider exception becomes FAILED, not a fabricated business result -------

def test_provider_exception_run_is_failed(tmp_path):
    from invoice_referee.extraction.providers import FakeProviders

    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _bundle = seed_case(repo)

    class BoomProviders(FakeProviders):
        def ocr(self, evidence):
            raise DomainError('PROVIDER_FAILED', 'transport lỗi')

    providers = BoomProviders(documents={}, registries={})
    service = CaseService(repo, providers,
                          activate_demo_policy(demo_policy(active=False), 'fixture'))
    try:
        run = service.start_run(case.id)
        ended = service.wait(run.id, timeout_seconds=5)
        assert ended.status == 'FAILED'
        assert ended.result.decision.technical_code == 'PROVIDER_FAILED'
        assert repo.get_payment_request(case.id) is None
    finally:
        service.close()
