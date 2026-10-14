"""Demo API routes (plan T2).

Delegates every command to CaseWorkflow; no SQL and no money math here. Session,
tenant and version scoping are enforced server-side, never from the client body.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from invoice_referee.api import views
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AnswerIssue,
    AttachSources,
    CommandResult,
    Control,
    CreateDraft,
    Decide,
    Declaration,
    Override,
    RecordActual,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.domain.issues import Answer, DecisionCommand
from invoice_referee.domain.evidence import Media
from invoice_referee.workflow.service import (
    PROPOSED_ACTIVITY_PREFIX,
    CaseWorkflow,
    DemoSession,
    UnknownSessionError,
)

SESSION_COOKIE = "invoice_referee_session"

router = APIRouter(prefix="/api")

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _workflow(request: Request) -> CaseWorkflow:
    return request.app.state.workflow


def _resolve_session(request: Request, response: Response | None = None) -> DemoSession:
    """The session for this request; a missing/stale cookie starts a fresh one."""
    workflow = _workflow(request)
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        try:
            return workflow.session(session_id)
        except UnknownSessionError:
            pass
    session = workflow.start_session()
    if response is not None:
        _set_session_cookie(response, session)
    return session


def _require_session(request: Request) -> DemoSession:
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(
            status_code=401, detail="Chưa có phiên demo; hãy tải lại trang để bắt đầu."
        )
    return _workflow(request).session(session_id)


def _set_session_cookie(response: Response, session: DemoSession) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session.session_id,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _command_context(
    request: Request, session: DemoSession, *, require_version: bool
) -> CommandContext:
    command_id = request.headers.get("X-Command-Id")
    if not command_id:
        raise HTTPException(
            status_code=400, detail="Thiếu header X-Command-Id cho thao tác ghi."
        )
    raw_version = request.headers.get("X-Expected-Version")
    if require_version and raw_version is None:
        raise HTTPException(
            status_code=400,
            detail="Thiếu header X-Expected-Version để kiểm phiên bản hồ sơ.",
        )
    try:
        expected = int(raw_version) if raw_version is not None else 0
    except ValueError as error:
        raise HTTPException(
            status_code=400, detail="X-Expected-Version phải là số nguyên."
        ) from error
    return CommandContext(
        session_id=session.session_id,
        actor_id=session.actor_id,
        command_id=command_id,
        expected_case_version=expected,
    )


def _read_context(session: DemoSession) -> CommandContext:
    return CommandContext(
        session_id=session.session_id,
        actor_id=session.actor_id,
        command_id=f"read:{uuid.uuid4().hex}",
        expected_case_version=0,
    )


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    """Redacted health/versions for the launcher; never exposes a secret."""
    import platform
    import sys

    settings = getattr(request.app.state, "settings", None)
    return {
        "status": "ok",
        "mode": request.app.state.mode,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.system(),
        "live_ready": bool(getattr(settings, "live_ready", False)) if settings else False,
        "langsmith_ready": bool(getattr(settings, "langsmith_ready", False))
        if settings
        else False,
    }


@router.get("/demo/session")
def demo_session(request: Request, response: Response) -> dict[str, object]:
    session = _resolve_session(request, response)
    return views.session_payload(
        _workflow(request),
        session,
        mode=request.app.state.mode,
        settings=request.app.state.settings,
        frontend_dir=request.app.state.frontend_dir,
    )


@router.post("/demo/persona")
def demo_persona(
    request: Request, payload: views.PersonaSwitchRequest, response: Response
) -> dict[str, object]:
    session = _require_session(request)
    switched = _workflow(request).switch_persona(session.session_id, payload.persona)
    _set_session_cookie(response, switched)
    return views.session_payload(
        _workflow(request),
        switched,
        mode=request.app.state.mode,
        settings=request.app.state.settings,
        frontend_dir=request.app.state.frontend_dir,
    )


@router.get("/cases")
def list_cases(request: Request) -> dict[str, object]:
    session = _require_session(request)
    cases = _workflow(request).list_cases(_read_context(session))
    return {"cases": [case.model_dump(mode="json") for case in cases]}


@router.post("/cases")
async def create_case(
    request: Request, payload: views.CreateCaseRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    choice = payload.activity
    if isinstance(choice, views.NewActivity):
        # Server-generated activity id: the client never mints authority (§10.4).
        activity_id = f"{PROPOSED_ACTIVITY_PREFIX}{uuid.uuid4().hex}"
        activity = ActivityData(
            activity_id=activity_id,
            name=choice.name,
            occurred_at=choice.occurred_at,
            declared_purpose=choice.declared_purpose,
        )
    else:
        entry = workflow.catalog_entry(session.tenant, choice.activity_id)
        if entry is None or entry.status != "AUTHORIZED":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Hoạt động không có trong danh mục demo; hãy chọn hoạt động "
                    "có sẵn hoặc tạo hoạt động mới."
                ),
            )
        activity = ActivityData(
            activity_id=entry.activity_id,
            name=entry.name,
            occurred_at=entry.occurred_at or datetime.now(UTC),
            declared_purpose=entry.purpose,
        )
    context = _command_context(request, session, require_version=False)
    return await workflow.execute(context, CreateDraft(activity_data=activity))


@router.get("/cases/{root_id}")
def get_case(request: Request, root_id: str) -> dict[str, object]:
    session = _require_session(request)
    case = _workflow(request).view(_read_context(session), root_id)
    return case.model_dump(mode="json")


@router.get("/cases/{root_id}/sources/{source_id}")
def get_source_content(request: Request, root_id: str, source_id: str) -> FileResponse:
    session = _require_session(request)
    workflow = _workflow(request)
    case = workflow.view(_read_context(session), root_id)
    matching = next((s for s in case.sources if s.id == source_id), None)
    if matching is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy chứng từ.")
    file_path = workflow.uploads_dir / matching.storage_key
    if not file_path.exists() and matching.filename:
        for candidate in (PROJECT_ROOT / "data").glob(f"**/{matching.filename}"):
            if candidate.is_file():
                file_path = candidate
                break
    if not file_path.exists() and matching.filename:
        for candidate in (PROJECT_ROOT / ".runtime").glob(f"**/{matching.filename}"):
            if candidate.is_file():
                file_path = candidate
                break
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Tệp chứng từ không tồn tại trên máy chủ.")

    media_type = (
        "application/pdf"
        if matching.media == "PDF"
        else ("image/png" if matching.media == "PNG" else "image/jpeg")
    )
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=matching.filename or "document.pdf",
        content_disposition_type="inline",
    )



@router.post("/cases/{root_id}/sources")
async def attach_sources(
    request: Request, root_id: str, files: list[UploadFile] = File(...)
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn tệp chứng từ nào.")

    prepared: list[tuple[str, Media, bytes]] = []
    for upload in files:
        data = await upload.read()
        media = _sniff_media(data)
        if media is None:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Định dạng tệp '{upload.filename or 'không tên'}' không hỗ trợ. "
                    "Chỉ nhận PDF, PNG hoặc JPEG."
                ),
            )
        if len(data) > workflow.max_source_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Tệp '{upload.filename or 'không tên'}' quá lớn "
                    f"({len(data)} bytes > {workflow.max_source_bytes} bytes)."
                ),
            )
        prepared.append((upload.filename or "tep", media, data))

    uploads: list[SourceUpload] = []
    written: list[str] = []
    for filename, media, data in prepared:
        source_id = f"source:{uuid.uuid4().hex}"
        storage_key = f"{session.tenant}/{root_id}/{source_id}"
        destination = workflow.uploads_dir / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        written.append(storage_key)
        uploads.append(
            SourceUpload(
                filename=filename,
                media=media,
                digest=hashlib.sha256(data).hexdigest(),
                storage_key=storage_key,
            )
        )

    context = _command_context(request, session, require_version=True)
    try:
        return await workflow.execute(
            context, AttachSources(root_id=root_id, uploads=tuple(uploads))
        )
    except Exception:
        for storage_key in written:
            (workflow.uploads_dir / storage_key).unlink(missing_ok=True)
        _prune_empty_upload_dirs(workflow.uploads_dir, session.tenant, root_id)
        raise


def _prune_empty_upload_dirs(uploads_dir: Path, tenant: str, root_id: str) -> None:
    """Remove the per-root (and per-tenant) upload dirs once they are empty."""
    for directory in (
        uploads_dir / tenant / root_id,
        uploads_dir / tenant,
    ):
        try:
            directory.rmdir()
        except OSError:
            break


@router.post("/verify")
async def run_verify(request: Request, payload: views.VerifyRequest) -> dict[str, object]:
    """Run a suite through the workflow and score with independent gold (§8)."""
    from invoice_referee.evaluation.packets import load_gold, load_input, load_stub_readings
    from invoice_referee.evaluation.runner import EvaluationRunner
    from invoice_referee.evaluation.scorer import IndependentScorer
    from invoice_referee.evaluation.suites import select_suite

    workflow = _workflow(request)
    dataset = PROJECT_ROOT / "data" / "kiem-thu"
    packets = select_suite(payload.suite, dataset)
    runner = EvaluationRunner(workflow=workflow)
    scorer = IndependentScorer()
    rows = []
    for packet_dir in packets:
        packet_input = load_input(packet_dir, stage_id="ban-dau")
        if payload.mode == "STUB":
            packet_input = packet_input.model_copy(
                update={"transcription": load_stub_readings(packet_dir, stage_id="ban-dau")}
            )
        actual = await runner.run(packet_input, payload.mode)
        gold = load_gold(packet_dir, stage_id="ban-dau")
        rows.append(scorer.score(actual, gold))
    report = scorer.release_gate(
        rows,
        total_human=sum(
            1 for row in rows if row.expected_route in ("FACT", "POLICY", "AUTHORITY")
        ),
    )
    return {
        "suite": payload.suite,
        "mode": payload.mode,
        "total": len(rows),
        "union_dangerous_miss": report.union_dangerous_miss,
        "release": report.release,
        "rows": [row.model_dump(mode="json") for row in rows],
    }


def _sniff_media(data: bytes) -> Media | None:
    if data.startswith(b"%PDF"):
        return "PDF"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    return None


@router.post("/cases/{root_id}/submit")
async def submit_case(
    request: Request, root_id: str, payload: views.SubmitRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=True)
    from invoice_referee.domain.commands import EmployeePaidClaim

    claims = tuple(
        EmployeePaidClaim(
            invoice_reference=claim.invoice_reference,
            amount=claim.amount,
            refs=tuple(claim.refs),
            reason=claim.reason,
        )
        for claim in payload.employee_paid_claims
    )
    return await workflow.execute(
        context,
        Submit(
            root_id=root_id,
            declaration=Declaration(
                activity_id=payload.activity_id,
                declared_purpose=payload.declared_purpose,
                notes=payload.notes,
                declared_name=payload.declared_name,
                destination=payload.destination,
                trip_start=payload.trip_start,
                trip_end=payload.trip_end,
                declared_advance=payload.declared_advance,
                incurred_total=payload.incurred_total,
                original_declared_advance=payload.original_declared_advance,
            ),
            employee_paid_claims=claims,
        ),
    )


@router.post("/cases/{root_id}/answers")
async def answer_issue(
    request: Request, root_id: str, payload: views.AnswerRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=True)
    return await workflow.execute(
        context,
        AnswerIssue(
            root_id=root_id,
            answer=Answer(
                issue_id=payload.issue_id,
                basis_id=payload.basis_id,
                answer_kind=payload.answer_kind,
                value=payload.value,
                reason=payload.reason,
            ),
        ),
    )


@router.post("/cases/{root_id}/decisions")
async def decide_case(
    request: Request, root_id: str, payload: views.DecisionRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=False)
    return await workflow.execute(
        context,
        Decide(
            root_id=root_id,
            decision=DecisionCommand(
                issue_ids=tuple(payload.issue_ids),
                basis_id=payload.basis_id,
                actions=tuple(payload.actions),
                effect_scope=payload.effect_scope,
                amount=payload.amount,
                reason=payload.reason,
            ),
        ),
    )


@router.post("/cases/{root_id}/actuals")
async def record_actual(
    request: Request, root_id: str, payload: views.RecordActualRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=False)
    money = payload.money
    return await workflow.execute(
        context,
        RecordActual(
            root_id=root_id,
            money=RecordMoneyInput(
                external_key=money.external_key,
                claimed_kind=money.claimed_kind,
                claimed_scope=money.claimed_scope,
                payer=money.payer,
                payee=money.payee,
                amount=money.amount,
                event_at=money.event_at,
                completion_claim=money.completion_claim,
                reverses_event_id=money.reverses_event_id,
                reason=money.reason,
                instrument_method=money.instrument_method,
                instrument_status=money.instrument_status,
                instrument_reference=money.instrument_reference,
            ),
        ),
    )


@router.post("/cases/{root_id}/advance/draft")
async def advance_draft(
    request: Request,
    root_id: str,
    files: list[UploadFile] = File(...),
    method: str | None = None,
) -> dict[str, object]:
    """Read an uploaded advance document and return a prefilled DRAFT (plan D).

    This is a READ: it never records money. The accountant reviews/edits the
    draft and then records it through the existing actuals endpoint. Provider
    I/O runs outside any transaction.
    """
    session = _require_session(request)
    workflow = _workflow(request)
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn chứng từ ứng.")
    uploads: list[tuple[str, str, bytes]] = []
    for upload in files:
        data = await upload.read()
        media = _sniff_media(data)
        if media is None:
            raise HTTPException(status_code=415, detail="Chỉ nhận PDF, PNG hoặc JPEG.")
        if len(data) > workflow.max_source_bytes:
            raise HTTPException(status_code=413, detail="Tệp vượt giới hạn dung lượng.")
        uploads.append((upload.filename or "tep", media, data))
    draft = await workflow.read_advance_draft(
        session, root_id, tuple(uploads), method_hint=method
    )
    return draft._asdict()


@router.post("/cases/{root_id}/settlement/draft")
async def settlement_draft(
    request: Request,
    root_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    """Read uploaded settlement documents and return a prefilled draft for review."""
    session = _require_session(request)
    workflow = _workflow(request)
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn chứng từ.")
    uploads: list[tuple[str, str, bytes]] = []
    for upload in files:
        data = await upload.read()
        media = _sniff_media(data)
        if media is None:
            raise HTTPException(status_code=415, detail="Chỉ nhận PDF, PNG hoặc JPEG.")
        if len(data) > workflow.max_source_bytes:
            raise HTTPException(status_code=413, detail="Tệp vượt giới hạn dung lượng.")
        uploads.append((upload.filename or "tep", media, data))
    draft = await workflow.read_settlement_draft(session, root_id, tuple(uploads))
    return draft


@router.post("/cases/{root_id}/control")
async def control_case(
    request: Request, root_id: str, payload: views.ControlRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    # STOP is a control signal: it is not guarded by expected_case_version.
    context = _command_context(request, session, require_version=False)
    return await workflow.execute(
        context, Control(root_id=root_id, action=payload.action, reason=payload.reason)
    )


@router.post("/cases/{root_id}/override")
async def override_case(
    request: Request, root_id: str, payload: views.OverrideRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=False)
    return await workflow.execute(
        context,
        Override(
            root_id=root_id,
            supersedes_decision_id=payload.supersedes_decision_id,
            decision=DecisionCommand(
                issue_ids=tuple(payload.issue_ids),
                basis_id=payload.basis_id,
                actions=tuple(payload.actions),
                effect_scope=payload.effect_scope,
                amount=payload.amount,
                reason=payload.reason,
            ),
        ),
    )

