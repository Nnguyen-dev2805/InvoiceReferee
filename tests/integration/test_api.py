"""T09 integration — FastAPI composition root and contract responses.

RED first: this file fails to collect until ``invoice_referee.api.app`` exists.
The ``runtime`` fixture (T08, ``tests/integration/conftest.py``) is reused
as-is — providers are NOT re-declared here.

These tests prove API WIRING and contract/error mapping over the real
``CaseService`` + SQLite repository with fake providers. They do NOT prove live
OCR/Kimi quality (see T05/T06 evidence).
"""
from __future__ import annotations

import hashlib
import json

from fastapi.testclient import TestClient

from invoice_referee.api.app import create_app, create_runtime_app
from invoice_referee.application.service import CaseService
from invoice_referee.domain.models import DomainError
from invoice_referee.extraction.providers import FakeProviders
from invoice_referee.storage.repository import Repository
from tests.builders import demo_policy
from tests.integration.support import seed_case

import pytest


# --- helpers -------------------------------------------------------------------

def _pdf(tag: str) -> bytes:
    return f'%PDF-1.4\n% {tag}\n%%EOF\n'.encode('utf-8')


def _claim(**overrides) -> dict:
    claim = {
        'employee_id': 'emp-demo',
        'profile': 'TRAVEL',
        'purpose_type': 'BUSINESS',
        'purpose': 'Công tác demo',
        'trip': 'Chuyến demo',
        'payer_type': 'PERSONAL',
        'requested_amount_vnd': 1_200_000,
    }
    claim.update(overrides)
    return claim


def _fresh_service(tmp_path, *, active: bool = False) -> tuple[Repository, CaseService]:
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    providers = FakeProviders(documents={}, registries={})
    service = CaseService(repo, providers, demo_policy(active=active))
    return repo, service


# --- Brief step 1: end-to-end business vs execution status ---------------------

def test_api_preserves_business_and_execution_status(runtime):
    client = TestClient(create_app(runtime.service))
    started = client.post(f'/api/cases/{runtime.case_id}/runs')
    assert started.status_code == 202
    runtime.release.set()
    runtime.service.wait(started.json()['id'], timeout_seconds=5)
    response = client.get(f"/api/runs/{started.json()['id']}")
    assert response.json()['status'] == 'SUCCEEDED'
    assert response.json()['result']['decision']['action'] == 'CREATE_PAYMENT_REQUEST'


def test_run_and_stop_contract(runtime):
    client = TestClient(create_app(runtime.service))
    started = client.post(f'/api/cases/{runtime.case_id}/runs')
    assert started.status_code == 202
    run_id = started.json()['id']
    stopped = client.post(f'/api/runs/{run_id}/stop')
    assert stopped.status_code == 200
    assert stopped.json() == {'status': 'STOP_REQUESTED', 'run_id': run_id}
    runtime.release.set()
    runtime.service.wait(run_id, timeout_seconds=5)
    again = client.post(f'/api/runs/{run_id}/stop')
    assert again.json()['status'] == 'ALREADY_COMPLETED'


def test_missing_run_is_404_envelope(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.get('/api/runs/run-does-not-exist')
    assert response.status_code == 404
    assert response.json()['code'] == 'NOT_FOUND'
    assert set(response.json()) == {'code', 'message'}


# --- Case intake ---------------------------------------------------------------

def test_create_case_multipart_and_redacts_stored_path(runtime):
    client = TestClient(create_app(runtime.service))
    data = {'claim_json': json.dumps(_claim()), 'roles': json.dumps(['PRIMARY_BILL'])}
    files = [('files', ('bill.pdf', _pdf('bill'), 'application/pdf'))]
    created = client.post('/api/cases', data=data, files=files)
    assert created.status_code == 201
    body = created.json()
    assert body['workflow_state'] == 'DRAFT'
    assert len(body['evidence']) == 1
    assert 'stored_path' not in body['evidence'][0]

    listed = client.get('/api/cases')
    assert listed.status_code == 200
    assert any(case['id'] == body['id'] for case in listed.json())
    assert all('stored_path' not in ev for case in listed.json() for ev in case['evidence'])


def test_empty_form_does_not_create_case(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.post('/api/cases')
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'


def test_strict_claim_rejects_unknown_field(runtime):
    client = TestClient(create_app(runtime.service))
    data = {
        'claim_json': json.dumps(_claim(stored_path='/etc/passwd')),
        'roles': '[]',
    }
    response = client.post('/api/cases', data=data)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'


def test_upload_count_limit_is_422(runtime):
    client = TestClient(create_app(runtime.service))
    files = [
        ('files', (f'bill-{i}.pdf', _pdf(f'bill-{i}'), 'application/pdf'))
        for i in range(13)
    ]
    data = {'claim_json': json.dumps(_claim()), 'roles': json.dumps(['PRIMARY_BILL'] * 13)}
    response = client.post('/api/cases', data=data, files=files)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'


def test_roles_must_match_files(runtime):
    client = TestClient(create_app(runtime.service))
    data = {'claim_json': json.dumps(_claim()), 'roles': '[]'}
    files = [('files', ('bill.pdf', _pdf('bill'), 'application/pdf'))]
    response = client.post('/api/cases', data=data, files=files)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'


# --- Human actions -------------------------------------------------------------

def test_action_wrong_role_is_422_invalid_action(runtime):
    client = TestClient(create_app(runtime.service))
    payload = {
        'mode': 'EMPLOYEE',
        'kind': 'APPROVE_AMOUNT',
        'reason': 'duyệt',
        'payload': {
            'amount_vnd': 1_200_000,
            'profile': 'TRAVEL',
            'purpose': 'Công tác demo',
            'policy_version': runtime.service.policy.version,
        },
    }
    response = client.post(f'/api/cases/{runtime.case_id}/actions', json=payload)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_ACTION'


def test_action_stop_kind_rejected(runtime):
    client = TestClient(create_app(runtime.service))
    payload = {'mode': 'EMPLOYEE', 'kind': 'STOP', 'reason': 'stop', 'payload': {'run_id': 'x'}}
    response = client.post(f'/api/cases/{runtime.case_id}/actions', json=payload)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_ACTION'


def test_add_evidence_multipart_wires_service(runtime):
    client = TestClient(create_app(runtime.service))
    before = client.get(f'/api/cases/{runtime.case_id}').json()
    data = {
        'action_json': json.dumps({'mode': 'EMPLOYEE', 'reason': 'Bổ sung hoá đơn'}),
        'roles': json.dumps(['CONTEXT']),
    }
    files = [('files', ('extra.pdf', _pdf('extra'), 'application/pdf'))]
    response = client.post(f'/api/cases/{runtime.case_id}/actions', data=data, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body['case_version'] == before['case_version'] + 1
    assert len(body['evidence']) == len(before['evidence']) + 1
    run_id = body['current_run_id']
    assert run_id is not None
    # Cleanup: stop the reevaluation started by the action.
    client.post(f'/api/runs/{run_id}/stop')
    runtime.release.set()
    runtime.service.wait(run_id, timeout_seconds=5)


# --- Evidence ownership --------------------------------------------------------

def test_evidence_endpoint_is_owned_only_and_path_free(runtime):
    client = TestClient(create_app(runtime.service))
    owned = runtime.repo.get_case(runtime.case_id).evidence[0].id
    response = client.get(f'/api/cases/{runtime.case_id}/evidence/{owned}')
    assert response.status_code == 200
    assert response.json()['id'] == owned
    assert 'stored_path' not in response.json()

    missing = client.get(f'/api/cases/{runtime.case_id}/evidence/ev-not-mine')
    assert missing.status_code == 404
    assert missing.json()['code'] == 'NOT_FOUND'


# --- History and payment request ----------------------------------------------

def test_history_route_returns_timeline(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.get(f'/api/cases/{runtime.case_id}/history')
    assert response.status_code == 200
    assert any(event['kind'] == 'CASE_CREATED' for event in response.json())


def test_payment_request_route_null_when_absent(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.get(f'/api/cases/{runtime.case_id}/payment-request')
    assert response.status_code == 200
    assert response.json() is None


# --- Policy activation ---------------------------------------------------------

def test_policy_activation_requires_owner_and_persists(tmp_path):
    repo, service = _fresh_service(tmp_path, active=False)
    client = TestClient(create_app(service))
    assert client.get('/api/policy').json()['active'] is False
    assert client.get('/api/health').json()['ready'] is False

    wrong = client.post('/api/policy/activate', json={'mode': 'SYSTEM', 'reason': 'x'})
    assert wrong.status_code == 422
    assert wrong.json()['code'] == 'INVALID_ACTION'

    blank = client.post('/api/policy/activate', json={'mode': 'POLICY_OWNER', 'reason': '  '})
    assert blank.status_code == 422

    ok = client.post(
        '/api/policy/activate',
        json={'mode': 'POLICY_OWNER', 'reason': 'Kích hoạt demo policy'},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body['active'] is True
    assert body['origin'] == 'developer_activated_demo'
    assert body['activation_id']
    assert body['auto_approval_max'] == 2_000_000
    assert client.get('/api/health').json()['ready'] is True
    assert repo.get_active_policy() is not None
    service.close()


def test_health_reports_mode_without_secrets(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.get('/api/health')
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'ok'
    assert body['live'] is True
    assert body['provider_mode'] == 'fake'
    text = json.dumps(body).lower()
    assert 'api_key' not in text and 'secret' not in text and 'token' not in text


# --- Composition root ----------------------------------------------------------

def test_runtime_app_requires_explicit_provider_mode(monkeypatch):
    # Isolate from the developer's real `.env` so the test exercises "no mode set".
    monkeypatch.setattr('invoice_referee.api.app.load_repo_env', lambda *a, **k: {})
    monkeypatch.delenv('PROVIDER_MODE', raising=False)
    with pytest.raises(RuntimeError):
        create_runtime_app()
    monkeypatch.setenv('PROVIDER_MODE', 'not-a-mode')
    with pytest.raises(RuntimeError):
        create_runtime_app()


def test_busy_run_is_409(runtime):
    client = TestClient(create_app(runtime.service))
    first = client.post(f'/api/cases/{runtime.case_id}/runs')
    assert first.status_code == 202
    assert runtime.entered.wait(timeout=2)
    second = client.post(f'/api/cases/{runtime.case_id}/runs')
    assert second.status_code == 409
    assert second.json()['code'] == 'RUN_BUSY'
    client.post(f"/api/runs/{first.json()['id']}/stop")
    runtime.release.set()
    runtime.service.wait(first.json()['id'], timeout_seconds=5)


def test_provider_failure_lives_in_run_record_not_http(tmp_path):
    # The run was accepted (202); a later provider failure is a RunRecord FAILED
    # with a technical code, never a 5xx on the accepted request.
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _bundle = seed_case(repo)

    class BoomProviders(FakeProviders):
        def ocr(self, evidence):
            raise DomainError('PROVIDER_FAILED', 'transport lỗi')

    service = CaseService(repo, BoomProviders(documents={}, registries={}),
                          demo_policy(active=True))
    try:
        client = TestClient(create_app(service))
        started = client.post(f'/api/cases/{case.id}/runs')
        assert started.status_code == 202
        run_id = started.json()['id']
        service.wait(run_id, timeout_seconds=5)
        run = client.get(f'/api/runs/{run_id}')
        assert run.status_code == 200
        assert run.json()['status'] == 'FAILED'
        assert run.json()['result']['decision']['technical_code'] == 'PROVIDER_FAILED'
        assert client.get(f'/api/cases/{case.id}/payment-request').json() is None
    finally:
        service.close()


def test_inactive_policy_run_is_technical_failure_not_http(tmp_path):
    # An INACTIVE policy is a legitimate business/config state for a run: the
    # request is accepted, the run ends FAILED with CONFIG_NOT_ACTIVE, and the
    # failure is NOT an HTTP error on the accepted request.
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    case, _bundle = seed_case(repo)
    service = CaseService(repo, FakeProviders(documents={}, registries={}),
                          demo_policy(active=False))
    try:
        client = TestClient(create_app(service))
        assert client.get('/api/health').json()['ready'] is False
        started = client.post(f'/api/cases/{case.id}/runs')
        assert started.status_code == 202
        run_id = started.json()['id']
        service.wait(run_id, timeout_seconds=5)
        run = client.get(f'/api/runs/{run_id}').json()
        assert run['status'] == 'FAILED'
        assert run['result']['decision']['technical_code'] == 'CONFIG_NOT_ACTIVE'
    finally:
        service.close()


def test_business_request_info_is_not_http_error(tmp_path):
    # A missing primary bill is a BUSINESS result (REQUEST_INFO), returned as a
    # 200 run record, NOT a 4xx/5xx on the accepted run request.
    repo = Repository(tmp_path / 'cases.sqlite', tmp_path / 'artifacts')
    service = CaseService(repo, FakeProviders(documents={}, registries={}),
                          demo_policy(active=True))
    try:
        client = TestClient(create_app(service))
        data = {'claim_json': json.dumps(_claim()), 'roles': json.dumps(['CONTEXT'])}
        files = [('files', ('ctx.pdf', _pdf('ctx'), 'application/pdf'))]
        created = client.post('/api/cases', data=data, files=files)
        assert created.status_code == 201
        started = client.post(f"/api/cases/{created.json()['id']}/runs")
        assert started.status_code == 202
        run_id = started.json()['id']
        service.wait(run_id, timeout_seconds=5)
        run = client.get(f'/api/runs/{run_id}')
        assert run.status_code == 200
        assert run.json()['status'] == 'SUCCEEDED'
        assert run.json()['result']['decision']['action'] == 'REQUEST_INFO'
    finally:
        service.close()


def test_invalid_amount_is_422(runtime):
    client = TestClient(create_app(runtime.service))
    data = {'claim_json': json.dumps(_claim(requested_amount_vnd=0)), 'roles': '[]'}
    response = client.post('/api/cases', data=data)
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'


def test_malformed_json_action_body_is_422_envelope(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.post(
        f'/api/cases/{runtime.case_id}/actions',
        content='{not json',
        headers={'content-type': 'application/json'},
    )
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'
    assert set(response.json()) == {'code', 'message'}


def test_non_json_action_body_is_422_envelope(runtime):
    # A form-encoded (or otherwise non-JSON) body to the JSON action route must
    # not 500: it is invalid input.
    client = TestClient(create_app(runtime.service))
    response = client.post(
        f'/api/cases/{runtime.case_id}/actions',
        data={'mode': 'EMPLOYEE', 'kind': 'SUPPLY_DECLARATION'},
        headers={'content-type': 'application/x-www-form-urlencoded'},
    )
    assert response.status_code == 422
    assert response.json()['code'] == 'INVALID_INPUT'
    assert set(response.json()) == {'code', 'message'}


def test_method_not_allowed_keeps_status(runtime):
    client = TestClient(create_app(runtime.service))
    response = client.put(f'/api/cases/{runtime.case_id}/history')
    assert response.status_code == 405
    assert set(response.json()) == {'code', 'message'}


def test_evidence_original_name_is_sanitized(runtime):
    client = TestClient(create_app(runtime.service))
    data = {'claim_json': json.dumps(_claim()), 'roles': json.dumps(['PRIMARY_BILL'])}
    files = [('files', ('../../etc/evil.pdf', _pdf('evil'), 'application/pdf'))]
    created = client.post('/api/cases', data=data, files=files)
    assert created.status_code == 201
    name = created.json()['evidence'][0]['original_name']
    assert '/' not in name and '\\' not in name and name == 'evil.pdf'


def test_openapi_exposes_required_paths(runtime):
    client = TestClient(create_app(runtime.service))
    schema = client.get('/openapi.json').json()
    paths = schema['paths']
    for path in (
        '/api/cases', '/api/cases/{case_id}', '/api/cases/{case_id}/runs',
        '/api/runs/{run_id}', '/api/cases/{case_id}/actions', '/api/runs/{run_id}/stop',
        '/api/cases/{case_id}/history', '/api/cases/{case_id}/payment-request',
        '/api/cases/{case_id}/evidence/{evidence_id}', '/api/policy',
        '/api/policy/activate', '/api/health',
    ):
        assert path in paths, path
    # Deterministic schema hash is recorded in the T09 evidence doc.
    canonical = json.dumps(schema, sort_keys=True, separators=(',', ':')).encode('utf-8')
    assert len(hashlib.sha256(canonical).hexdigest()) == 64
