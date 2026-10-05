"""Verify harness integration tests (T11).

Drives the REAL ``CaseService`` with a ``ReplayProviders`` (no network). The
expected labels come only from the manifest; the runner compares them to the
actual decision produced by the same production path the UI uses.
"""
from __future__ import annotations

from pathlib import Path
import time

import pytest

from invoice_referee.application.service import CaseService
from invoice_referee.config import activate_demo_policy
from invoice_referee.storage.repository import Repository
from invoice_referee.verify.manifest import load_manifest
from invoice_referee.verify.replay import ReplayProviders
from invoice_referee.verify.runner import VerifyRunner

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'tests' / 'fixtures' / 'development' / 'manifest.json'


@pytest.fixture
def verify_service(tmp_path):
    repo = Repository(tmp_path / 'verify.sqlite', tmp_path / 'artifacts')
    service = CaseService(repo, ReplayProviders(), repo.get_active_policy() or _policy())
    service.set_policy(activate_demo_policy(service.policy, 'test'), actor_mode='POLICY_OWNER', reason='test')
    yield service
    service.close()


def _policy():
    from invoice_referee.config import load_policy

    return load_policy(ROOT / 'config' / 'demo-policy.json')


@pytest.fixture
def core_manifest():
    manifest = load_manifest(MANIFEST)
    cases = [c for c in manifest.cases if c.id in ('TC01', 'TC03', 'TC04', 'TC11')]
    selected = manifest.model_copy(update={'cases': cases, 'suite': 'core'})
    return selected.model_copy(update={'sha256': selected.content_hash()})


def test_core_correct_human_case_is_test_pass(verify_service, core_manifest, tmp_path):
    report = VerifyRunner(verify_service, tmp_path).run(core_manifest)
    assert len(report.results) == 4
    row = next(r for r in report.results if r.case_id == 'TC04')
    assert row.actual['action'] == 'REQUEST_INFO'
    assert row.actual['request_count'] == 0
    assert row.verdict == 'PASS'
    assert row.timestamp and row.run_id and row.trace_path


def test_full_development_suite_matches_gold(verify_service, tmp_path):
    manifest = load_manifest(MANIFEST)
    report = VerifyRunner(verify_service, tmp_path).run(manifest)
    assert len(report.results) == 15
    failures = [r for r in report.results if r.verdict == 'FAIL']
    assert not failures, [(r.case_id, r.expected.action, r.actual.get('action')) for r in failures]
    assert report.metrics['wrong_routine_automation']['numerator'] == 0


def test_verify_api_uses_the_same_case_service(verify_service, core_manifest, tmp_path, monkeypatch):
    """The API and the runner must drive the SAME CaseService, not a parallel one."""
    from fastapi.testclient import TestClient

    from invoice_referee.api.app import create_app

    client = TestClient(create_app(verify_service))
    started = client.post('/api/verify-runs', json={'suite': 'core', 'mode': 'replay'})
    assert started.status_code == 202
    job_id = started.json()['id']
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        body = client.get(f'/api/verify-runs/{job_id}').json()
        if body['status'] in ('SUCCEEDED', 'FAILED'):
            break
        time.sleep(0.01)  # Yield to the background worker; don't assume a poll count is elapsed time.
    assert body['status'] == 'SUCCEEDED'
    assert body['completed_count'] == 4
    assert body['report']['metrics']['verdicts']['pass'] == 4


def test_verify_live_mode_is_inconclusive(verify_service, tmp_path):
    manifest = load_manifest(MANIFEST)
    cases = [c.model_copy(update={'mode': 'LIVE_END_TO_END'}) for c in manifest.cases[:2]]
    selected = manifest.model_copy(update={'cases': cases, 'mode': 'LIVE_END_TO_END'})
    report = VerifyRunner(verify_service, tmp_path).run(selected)
    assert all(r.verdict == 'INCONCLUSIVE' for r in report.results)
