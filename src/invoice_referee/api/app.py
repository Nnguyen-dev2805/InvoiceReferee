"""T09 FastAPI composition root, routes and contract/error mapping.

Ledger §3.2:

- ``create_app(service: CaseService) -> FastAPI`` — builds the routes around an
  injected service (tests inject a real ``CaseService`` + ``FakeProviders``).
- ``create_runtime_app() -> FastAPI`` — composition root used by the ASGI
  factory ``invoice_referee.api.app:create_runtime_app``: it builds the
  repository, providers, policy and service ONCE at startup.

Design rulings (recorded at T09):

- **No decision logic here.** Every route delegates to ``CaseService`` (T08);
  the API only maps HTTP <-> records, validates the transport shape and maps
  ``DomainError`` codes to an ``{code, message}`` envelope.
- **Explicit provider mode.** ``PROVIDER_MODE`` must be ``fake`` or ``live``.
  A missing/invalid value is a clear startup error; there is NO live->fake
  fallback (a live deployment that cannot reach its provider must fail loudly,
  never silently serve fake results).
- **Runtime starts INACTIVE.** ``create_runtime_app`` loads the proposed demo
  policy file (``active=false``); activation is an explicit POLICY_OWNER action
  through ``POST /policy/activate`` (System §8, Global Constraints).
- **No secrets / no absolute artifact paths.** Evidence DTOs omit
  ``stored_path``; run artifacts are reduced to basenames. Health never echoes
  credentials.
- **Stop is a real record.** ``POST /runs/{id}/stop`` returns the persisted
  ``StopReply`` (requested/stopped/already-completed), not a canned message.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from invoice_referee.application.service import CaseService
from invoice_referee.config import activate_demo_policy, load_policy
from invoice_referee.domain.models import (
    AuditEvent,
    CaseRecord,
    Claim,
    DomainError,
    Evidence,
    HumanAction,
    PaymentRequest,
    PolicyConfig,
    RunRecord,
    StopReply,
    Upload,
)
from invoice_referee.extraction.providers import FakeProviders, LiveProviders, Providers
from invoice_referee.storage.repository import Repository
from invoice_referee.verify.jobs import VerifyJobs
from invoice_referee.verify.manifest import load_manifest

# DomainError.code -> HTTP status (brief step 2). A code outside this set is a
# server-side contract gap, not a client error; default to 422 (input-shaped).
HTTP_CODES = {
    'INVALID_INPUT': 422,
    'NOT_FOUND': 404,
    'RUN_BUSY': 409,
    'STALE_VERSION': 409,
    'INVALID_ACTION': 422,
    'CONFIG_NOT_ACTIVE': 503,
    'PROVIDER_FAILED': 503,
    'INVALID_ANALYSIS': 422,
    'OUT_OF_DOMAIN': 422,
}

_POLICY_PATH = Path(__file__).resolve().parents[3] / 'config' / 'demo-policy.json'
_VALID_MODES = {'fake', 'live'}


# --- Request bodies ------------------------------------------------------------

class ActionBody(BaseModel):
    """Non-file human action transport body (strict: extra keys rejected)."""

    model_config = ConfigDict(extra='forbid')

    mode: str
    kind: str
    payload: dict = Field(default_factory=dict)
    reason: str
    issue_id: str | None = None
    case_version: int | None = None


class PolicyActivationBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    mode: str
    reason: str


class VerifyRunBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    suite: str  # core | escalation | all
    mode: str = 'replay'  # replay | live
    manifest: str | None = None  # path to a manifest; default = dev corpus


# --- DTO mapping ---------------------------------------------------------------

def _display_name(name: str) -> str:
    """Reduce a client-supplied filename to a safe basename for echoing.

    The backend already sanitizes the stored path; the echoed display name must
    be sanitized too so a traversal-ish client name is never reflected back.
    """
    base = name.replace('\\', '/').rsplit('/', 1)[-1]
    return base if base not in ('', '.', '..') else 'unnamed'


def _evidence_dto(evidence: Evidence) -> dict:
    """Evidence as seen by a client: never the backend ``stored_path``."""
    return {
        'id': evidence.id,
        'case_id': evidence.case_id,
        'role': evidence.role,
        'original_name': _display_name(evidence.original_name),
        'sha256': evidence.sha256,
        'mime': evidence.mime,
        'size': evidence.size,
    }


def _case_dto(case: CaseRecord) -> dict:
    return {
        'id': case.id,
        'case_version': case.case_version,
        'claim': case.claim.model_dump(mode='json'),
        'current_run_id': case.current_run_id,
        'workflow_state': case.workflow_state,
        'evidence': [_evidence_dto(e) for e in case.evidence],
    }


def _result_dto(result) -> dict:
    payload = result.model_dump(mode='json')
    # Artifacts are backend-owned absolute paths; expose basenames only so the
    # filesystem layout never leaks through the API (System §10).
    payload['artifacts'] = [Path(name).name for name in payload.get('artifacts', [])]
    return payload


def _run_dto(run: RunRecord) -> dict:
    return {
        'id': run.id,
        'case_id': run.case_id,
        'input_hash': run.input_hash,
        'case_version': run.case_version,
        'status': run.status,
        'stop_requested': run.stop_requested,
        'stage': run.stage,
        'started_at': run.started_at.isoformat(),
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'policy_version': run.policy_version,
        'threshold_version': run.threshold_version,
        'identities': [i.model_dump(mode='json') for i in run.identities],
        'result': _result_dto(run.result) if run.result is not None else None,
    }


def _payment_dto(request: PaymentRequest) -> dict:
    return request.model_dump(mode='json')


def _event_dto(event: AuditEvent) -> dict:
    return event.model_dump(mode='json')


def _policy_dto(policy: PolicyConfig) -> dict:
    return {
        'version': policy.version,
        'origin': policy.origin,
        'activation_id': policy.activation_id,
        'active': policy.active,
        'currency': policy.currency,
        'auto_approval_max': policy.auto_approval_max,
        'standard_policy_max': policy.standard_policy_max,
        'inventory_date_gap_days': policy.inventory_date_gap_days,
        'comparison_money_tolerance': policy.comparison_money_tolerance,
        'normalized_unit_price_tolerance': policy.normalized_unit_price_tolerance,
        'word_review_threshold': policy.word_review_threshold,
        'threshold_version': policy.threshold_version,
    }


def _stop_dto(reply: StopReply) -> dict:
    return {'status': reply.status, 'run_id': reply.run_id}


def _error(code: str, message: str) -> JSONResponse:
    status = HTTP_CODES.get(code, 422)
    return JSONResponse(status_code=status, content={'code': code, 'message': message})


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_INPUT', message)


# --- Multipart parsing helpers -------------------------------------------------

def _parse_roles(roles_raw: str | None, files: list[UploadFile]) -> list[str]:
    """Parse the ``roles`` JSON list and require it to match ``files`` one-to-one."""
    if not files:
        if roles_raw not in (None, '', '[]'):
            raise _invalid('Có roles nhưng không có tệp đính kèm.')
        return []
    if not roles_raw:
        raise _invalid('Thiếu danh sách roles cho các tệp đã tải lên.')
    try:
        roles = json.loads(roles_raw)
    except (TypeError, ValueError):
        raise _invalid('roles phải là JSON list các role.')
    if not isinstance(roles, list) or len(roles) != len(files):
        raise _invalid('Số role phải khớp số tệp tải lên.')
    if not all(isinstance(role, str) for role in roles):
        raise _invalid('Mỗi role phải là chuỗi.')
    return roles


async def _build_uploads(files: list[UploadFile], roles: list[str]) -> list[Upload]:
    uploads: list[Upload] = []
    for file, role in zip(files, roles):
        if not file.filename or not file.content_type:
            raise _invalid('Tệp tải lên thiếu tên hoặc MIME type.')
        content = await file.read()
        try:
            uploads.append(Upload(
                original_name=file.filename, mime=file.content_type,
                content=content, role=role,
            ))
        except ValidationError:
            raise _invalid(f'Role không hợp lệ: {role!r}.')
    return uploads


def _parse_claim(claim_json: str | None) -> Claim:
    if not claim_json:
        raise _invalid('Thiếu claim_json cho hồ sơ.')
    try:
        return Claim.model_validate_json(claim_json)
    except ValidationError as exc:
        raise _invalid(f'Claim không hợp lệ ({exc.error_count()} lỗi).')


# --- App factory ---------------------------------------------------------------

def create_app(service: CaseService, *, provider_mode: str = 'fake') -> FastAPI:
    """Build the FastAPI app around an injected ``CaseService`` (no decision logic)."""
    app = FastAPI(title='InvoiceReferee API', version='0.1.0')
    app.state.service = service
    app.state.provider_mode = provider_mode

    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return _error(exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error('INVALID_INPUT', 'Dữ liệu yêu cầu không hợp lệ.')

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Preserve the framework status instead of mislabeling 405/5xx as 422.
        # Only 404 (a missing resource) maps onto the domain NOT_FOUND code; any
        # other status keeps its own code so the envelope never lies about it.
        if exc.status_code == 404:
            code = 'NOT_FOUND'
        elif exc.status_code >= 500:
            code = 'INTERNAL_ERROR'
        else:
            code = 'HTTP_ERROR'
        return JSONResponse(
            status_code=exc.status_code,
            content={'code': code, 'message': str(exc.detail)},
        )

    # --- health ---

    @app.get('/api/health')
    async def health() -> dict:
        policy = service.policy
        return {
            'status': 'ok',
            'live': True,
            'ready': bool(policy.active),
            'provider_mode': provider_mode,
        }

    # --- cases ---

    @app.post('/api/cases', status_code=201)
    async def create_case(
        claim_json: str | None = Form(default=None),
        roles: str | None = Form(default=None),
        files: list[UploadFile] = Form(default=[]),
    ) -> dict:
        claim = _parse_claim(claim_json)
        role_list = _parse_roles(roles, files)
        uploads = await _build_uploads(files, role_list)
        try:
            case = service.submit(claim, uploads)
        except ValueError as exc:  # bad filename/path -> invalid input, not 500
            raise _invalid(str(exc))
        return _case_dto(case)

    @app.get('/api/cases')
    async def list_cases() -> list[dict]:
        return [_case_dto(case) for case in service.list_cases()]

    @app.get('/api/cases/{case_id}')
    async def get_case(case_id: str) -> dict:
        return _case_dto(service.get_case(case_id))

    # --- runs ---

    @app.post('/api/cases/{case_id}/runs', status_code=202)
    async def start_run(case_id: str) -> dict:
        return _run_dto(service.start_run(case_id))

    @app.get('/api/runs/{run_id}')
    async def get_run(run_id: str) -> dict:
        return _run_dto(service.get_run(run_id))

    @app.post('/api/runs/{run_id}/stop')
    async def stop_run(run_id: str) -> dict:
        return _stop_dto(service.stop(run_id))

    # --- human actions ---

    @app.post('/api/cases/{case_id}/actions')
    async def case_action(case_id: str, request: Request) -> dict:
        content_type = request.headers.get('content-type', '')
        if content_type.startswith('multipart/form-data'):
            return await _add_evidence_action(service, case_id, request)
        return await _human_action(service, case_id, request)

    # --- history / payment request ---

    @app.get('/api/cases/{case_id}/history')
    async def history(case_id: str) -> list[dict]:
        return [_event_dto(event) for event in service.case_history(case_id)]

    @app.get('/api/cases/{case_id}/payment-request')
    async def payment_request(case_id: str) -> dict | None:
        request_record = service.payment_request(case_id)
        return _payment_dto(request_record) if request_record is not None else None

    # --- evidence (owned only) ---

    @app.get('/api/cases/{case_id}/evidence/{evidence_id}')
    async def evidence(case_id: str, evidence_id: str) -> dict:
        case = service.get_case(case_id)
        owned = next((e for e in case.evidence if e.id == evidence_id), None)
        if owned is None:
            raise DomainError('NOT_FOUND', f'Không tìm thấy chứng từ {evidence_id} trong hồ sơ.')
        return _evidence_dto(owned)

    # --- policy ---

    @app.get('/api/policy')
    async def get_policy() -> dict:
        return _policy_dto(service.policy)

    @app.post('/api/policy/activate')
    async def activate_policy(body: PolicyActivationBody) -> dict:
        if body.mode != 'POLICY_OWNER':
            raise DomainError('INVALID_ACTION', 'Chỉ POLICY_OWNER được kích hoạt policy demo.')
        if not body.reason or not body.reason.strip():
            raise _invalid('Cần lý do để kích hoạt policy demo.')
        policy = activate_demo_policy(service.policy, body.reason)
        service.set_policy(policy, actor_mode='POLICY_OWNER', reason=body.reason)
        return _policy_dto(service.policy)

    # --- verify (T11) ---------------------------------------------------------
    # The suite runs in a background thread that drives the same CaseService; the
    # provider execution stays on the service's single executor. A report is only
    # returned once the run actually finished — never fabricated.

    jobs = VerifyJobs(service, Path(os.environ.get('DATA_ROOT', 'data')) / 'verify')

    @app.post('/api/verify-runs', status_code=202)
    async def start_verify(body: VerifyRunBody) -> dict:
        if body.suite not in ('core', 'escalation', 'all'):
            raise _invalid("suite phải là 'core', 'escalation' hoặc 'all'.")
        if body.mode not in ('replay', 'live'):
            raise _invalid("mode phải là 'replay' hoặc 'live'.")
        manifest = _load_suite(body)
        job = jobs.start(manifest)
        return job.model_dump(mode='json')

    @app.get('/api/verify-runs/{job_id}')
    async def get_verify(job_id: str) -> dict:
        return jobs.get(job_id).model_dump(mode='json')

    return app


def _load_suite(body: VerifyRunBody):
    """Load + select the manifest for a verify request (no outcome by filename)."""
    root = Path(__file__).resolve().parents[3]
    default = root / 'tests' / 'fixtures' / 'development' / 'manifest.json'
    manifest = load_manifest(Path(body.manifest) if body.manifest else default)
    from invoice_referee.verify.__main__ import SUITES

    ids = SUITES[body.suite]
    cases = manifest.cases if ids is None else [c for c in manifest.cases if c.id in ids]
    selected = manifest.model_copy(update={'cases': cases, 'suite': body.suite})
    if body.mode == 'live':
        selected = selected.model_copy(update={'mode': 'LIVE_END_TO_END'})
    return selected.model_copy(update={'sha256': selected.content_hash()})


async def _human_action(service: CaseService, case_id: str, request: Request) -> dict:
    try:
        raw = await request.json()
    except (ValueError, UnicodeDecodeError):
        # Malformed JSON (or a non-JSON/form-encoded body) is invalid input, not
        # a server error: surface the {code, message} 422 envelope.
        raise DomainError('INVALID_INPUT', 'Body action phải là JSON hợp lệ.')
    if not isinstance(raw, dict):
        raise DomainError('INVALID_INPUT', 'Body action phải là JSON object.')
    try:
        body = ActionBody.model_validate(raw)
    except ValidationError:
        raise DomainError('INVALID_INPUT', 'Body action không hợp lệ.')
    case = service.get_case(case_id)
    try:
        action = HumanAction(
            id=f'ha-{uuid.uuid4().hex}', case_id=case_id,
            case_version=body.case_version if body.case_version is not None else case.case_version,
            issue_id=body.issue_id, mode=body.mode, kind=body.kind, payload=body.payload,
            reason=body.reason, created_at=datetime.now(timezone.utc),
        )
    except ValidationError as exc:
        raise DomainError('INVALID_ACTION', f'Hành động không hợp lệ ({exc.error_count()} lỗi).')
    updated = service.act(action)
    return _case_dto(updated)


async def _add_evidence_action(service: CaseService, case_id: str, request: Request) -> dict:
    form = await request.form()
    action_raw = form.get('action_json')
    if not action_raw or not isinstance(action_raw, str):
        raise _invalid('ADD_EVIDENCE cần action_json.')
    try:
        meta = json.loads(action_raw)
    except (TypeError, ValueError):
        raise _invalid('action_json phải là JSON object.')
    if not isinstance(meta, dict):
        raise _invalid('action_json phải là JSON object.')
    extra = set(meta) - {'mode', 'reason', 'issue_id'}
    if extra:
        raise _invalid(f'action_json có trường không hợp lệ: {sorted(extra)}.')
    mode = meta.get('mode')
    reason = meta.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        raise _invalid('ADD_EVIDENCE cần reason.')
    files = [value for value in form.getlist('files') if isinstance(value, StarletteUploadFile)]
    roles_raw = form.get('roles')
    roles = _parse_roles(roles_raw if isinstance(roles_raw, str) else None, files)
    uploads = await _build_uploads(files, roles)
    try:
        case = service.add_evidence(
            case_id=case_id, mode=mode, uploads=uploads, reason=reason,
            issue_id=meta.get('issue_id'),
        )
    except ValueError as exc:
        raise _invalid(str(exc))
    return _case_dto(case)


# --- Composition root ----------------------------------------------------------

def _provider_mode() -> str:
    """Read PROVIDER_MODE explicitly; missing/invalid is a startup error."""
    value = os.environ.get('PROVIDER_MODE')
    if value is None or value.strip().lower() not in _VALID_MODES:
        raise RuntimeError(
            "PROVIDER_MODE phải là 'fake' hoặc 'live'; không có fallback ngầm "
            f"(nhận {value!r})."
        )
    return value.strip().lower()


def _build_providers(mode: str) -> Providers:
    if mode == 'fake':
        # Deterministic wiring with no fixtures: a fake runtime proves the
        # composition path, never live OCR/Kimi quality.
        return FakeProviders(documents={}, registries={})
    return LiveProviders()


def create_runtime_app() -> FastAPI:
    """ASGI factory: build repo/providers/policy/service ONCE (System §8).

    ``PROVIDER_MODE=fake`` wires an EMPTY ``FakeProviders`` (no fixtures): it
    proves the composition path only and is NOT an evaluable runtime.
    """
    mode = _provider_mode()
    data_root = Path(os.environ.get('DATA_ROOT', 'data'))
    repo = Repository(data_root / 'cases.sqlite', data_root / 'artifacts')
    providers = _build_providers(mode)
    policy = load_policy(_POLICY_PATH)  # proposed/inactive; explicit activation later
    service = CaseService(repo, providers, policy)
    return create_app(service, provider_mode=mode)


__all__ = ['HTTP_CODES', 'create_app', 'create_runtime_app']
