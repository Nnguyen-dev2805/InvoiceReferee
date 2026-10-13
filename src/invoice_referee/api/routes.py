"""Demo API routes (plan T2).

Delegates every command to CaseWorkflow; no SQL and no money math here. Session,
tenant and version scoping are enforced server-side, never from the client body.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from invoice_referee.api import views
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CommandResult,
    CreateDraft,
    SourceUpload,
)
from invoice_referee.domain.evidence import Media
from invoice_referee.workflow.service import (
    CaseWorkflow,
    DemoSession,
    UnknownSessionError,
)

SESSION_COOKIE = "invoice_referee_session"

router = APIRouter(prefix="/api")


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
        activity_id = f"activity:proposed:{uuid.uuid4().hex}"
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
        raise


def _sniff_media(data: bytes) -> Media | None:
    if data.startswith(b"%PDF"):
        return "PDF"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    return None

