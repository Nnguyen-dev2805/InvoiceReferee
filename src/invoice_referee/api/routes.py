"""Demo API routes (plan T2).

Delegates every command to CaseWorkflow; no SQL and no money math here. Session,
tenant and version scoping are enforced server-side, never from the client body.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from invoice_referee.api import views
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AnswerIssue,
    AttachSources,
    CommandResult,
    ConfirmCoverage,
    ConfirmMoneyHistory,
    CorrectDeclaration,
    RecheckDossierHistory,
    Control,
    CreateDraft,
    Decide,
    Declaration,
    DigitalExpenseLine,
    MarkExecution,
    Override,
    RecordActual,
    RefuseException,
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
    """Redacted health/versions for the launcher; never exposes a secret.

    `langsmith_ready` is only the CONFIG flag; `langsmith_export_errors` is the
    observed export state (0 = no failed sends so far). The two are distinct so a
    green config never hides a broken export.
    """
    import platform
    import sys

    settings = getattr(request.app.state, "settings", None)
    workflow = getattr(request.app.state, "workflow", None)
    recorder = getattr(workflow, "trace", None)
    export_errors = list(getattr(recorder, "export_errors", []) or [])
    return {
        "status": "ok",
        "mode": request.app.state.mode,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.system(),
        "live_ready": bool(getattr(settings, "live_ready", False))
        if settings
        else False,
        "langsmith_ready": bool(getattr(settings, "langsmith_ready", False))
        if settings
        else False,
        "langsmith_enabled": bool(getattr(recorder, "enabled", False)),
        "langsmith_export_errors": len(export_errors),
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
        raise HTTPException(
            status_code=404, detail="Tệp chứng từ không tồn tại trên máy chủ."
        )

    media_type = (
        "application/pdf"
        if matching.media == "PDF"
        else (
            "image/png"
            if matching.media == "PNG"
            else (
                "image/jpeg"
                if matching.media == "JPEG"
                else (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    if matching.media == "DOCX"
                    else "application/msword"
                )
            )
        )
    )
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=matching.filename or "document.pdf",
        content_disposition_type="inline",
    )


@router.post("/cases/{root_id}/sources")
async def attach_sources(
    request: Request,
    root_id: str,
    files: list[UploadFile] = File(...),
    upload_role: str | None = Form(None),
) -> CommandResult:
    """Attach uploaded files; one optional role applies to the whole call.

    New UI calls once per box (paper box → role=paper, evidence box →
    role=evidence). Legacy callers omit the role (None = legacy, never guessed).
    """
    session = _require_session(request)
    workflow = _workflow(request)
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn tệp chứng từ nào.")
    role: str | None = None
    if upload_role is not None and upload_role != "":
        if upload_role not in ("paper", "evidence"):
            raise HTTPException(
                status_code=422, detail="upload_role phải là 'paper' hoặc 'evidence'."
            )
        role = upload_role

    prepared: list[tuple[str, Media, bytes]] = []
    for upload in files:
        data = await upload.read()
        media = _sniff_media(data, upload.filename)
        if media is None:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Định dạng tệp '{upload.filename or 'không tên'}' không hỗ trợ. "
                    "Chỉ nhận PDF, DOC, DOCX, PNG hoặc JPEG."
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
                upload_role=role,  # type: ignore[arg-type]
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
async def run_verify(
    request: Request, payload: views.VerifyRequest
) -> dict[str, object]:
    """Run a suite through an isolated workflow instance and score with independent gold (§8)."""
    from invoice_referee.evaluation.service import run_isolated_verify

    settings = getattr(request.app.state, "settings", None)
    try:
        return await run_isolated_verify(suite=payload.suite, mode=payload.mode, settings=settings)
    except ValueError as error:
        raise HTTPException(status_code=409 if "VERIFY_BUSY" in str(error) else 422, detail=str(error)) from error


@router.get("/verify/last")
async def get_last_verify() -> dict[str, object] | None:
    """Retrieve the last recorded verify report if present."""
    from invoice_referee.evaluation.service import get_last_verify_report

    return get_last_verify_report()


def _sniff_media(data: bytes, filename: str | None = None) -> Media | None:
    if data.startswith(b"%PDF"):
        return "PDF"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    # Word documents (17/10/2026): content-sniffed, never by extension alone.
    from invoice_referee.evidence.office import sniff_office

    office = sniff_office(data)
    if office is not None:
        return office  # type: ignore[return-value]
    _ = filename
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
                confirmed_activity_id=payload.confirmed_activity_id,
                declared_purpose=payload.declared_purpose,
                notes=payload.notes,
                declared_name=payload.declared_name,
                destination=payload.destination,
                trip_start=payload.trip_start,
                trip_end=payload.trip_end,
                declared_advance=payload.declared_advance,
                incurred_total=payload.incurred_total,
                original_declared_advance=payload.original_declared_advance,
                settlement_type=payload.settlement_type,
                submission_source=payload.submission_source,
                digital_lines=tuple(
                    DigitalExpenseLine(
                        item_id=line.item_id,
                        description=line.description,
                        category=line.category,
                        expense_date=line.expense_date,
                        amount=line.amount,
                        evidence_status=line.evidence_status,  # type: ignore[arg-type]
                        alternative_type=line.alternative_type,  # type: ignore[arg-type]
                        exception_reason=line.exception_reason,
                        note=line.note,
                        source_ids=tuple(line.source_ids),
                    )
                    for line in payload.digital_lines
                ),
                no_advance_asserted=payload.no_advance_asserted,
                no_advance_reason=payload.no_advance_reason,
            ),
            employee_paid_claims=claims,
        ),
    )


@router.get("/cases/{root_id}/issues/{issue_id}/card")
async def get_question_card(request: Request,root_id: str,issue_id: str):
    session=_require_session(request)
    return _workflow(request).question_card(session,root_id,issue_id)


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


@router.post("/cases/{root_id}/issues/{issue_id}/corrections")
async def correct_declaration(request: Request,root_id: str,issue_id: str,payload: views.CorrectDeclarationRequest):
    session=_require_session(request)
    context=_command_context(request,session,require_version=True)
    return await _workflow(request).execute(context,CorrectDeclaration(root_id=root_id,issue_id=issue_id,basis_id=payload.basis_id,correction_id=payload.correction_id,reason=payload.reason))


@router.post("/cases/{root_id}/decisions")
async def decide_case(
    request: Request, root_id: str, payload: views.DecisionRequest
) -> CommandResult:
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=True)
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
    money = payload.money
    if money.claimed_kind in ("REIMBURSEMENT_RECEIVED", "EMPLOYEE_RETURN"):
        if session.persona != "accountant":
            raise HTTPException(
                status_code=403,
                detail="Chỉ kế toán được xác nhận giao dịch theo lệnh chi/thu.",
            )
        if (
            money.claimed_kind == "EMPLOYEE_RETURN"
            and not money.money_movement_draft_id
        ):
            raise HTTPException(
                status_code=422, detail="Cần xác nhận từ chứng từ hoàn trả đã lưu."
            )
    if money.claimed_kind == "ADVANCE_RECEIVED":
        if session.persona != "accountant":
            raise HTTPException(
                status_code=403, detail="Chỉ kế toán được xác nhận chứng từ ứng."
            )
        if not money.advance_draft_id:
            raise HTTPException(
                status_code=422,
                detail="Cần xác nhận từ bản nháp chứng từ đã lưu trong hồ sơ.",
            )
    context = _command_context(request, session, require_version=True)
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
                advance_draft_id=money.advance_draft_id,
                instruction_id=money.instruction_id,
                money_movement_draft_id=money.money_movement_draft_id,
                activity_link_confirmed=money.activity_link_confirmed,
                activity_link_reason=money.activity_link_reason,
                refs=tuple(money.refs),
            ),
        ),
    )


@router.post("/cases/{root_id}/coverage")
async def confirm_coverage(
    request: Request, root_id: str, payload: views.ConfirmCoverageRequest
) -> CommandResult:
    session = _require_session(request)
    if session.persona != "accountant":
        raise HTTPException(
            status_code=403,
            detail="Chỉ kế toán được xác nhận đã đối chiếu lịch sử tiền.",
        )
    context = _command_context(request, session, require_version=True)
    return await _workflow(request).execute(
        context,
        ConfirmCoverage(
            root_id=root_id,
            start=payload.start,
            funds=tuple(payload.funds),
            flow_kinds=tuple(payload.flow_kinds),
            opening_balance=payload.opening_balance,
            unallocated_event_ids=tuple(payload.unallocated_event_ids),
            witness_refs=tuple(payload.witness_refs),
            reason=payload.reason,
        ),
    )


@router.post("/cases/{root_id}/money-history/confirm")
async def confirm_money_history(
    request: Request, root_id: str, payload: views.ConfirmMoneyHistoryRequest
) -> CommandResult:
    session = _require_session(request)
    if session.persona != "accountant":
        raise HTTPException(
            status_code=403, detail="Chỉ kế toán được xác nhận lịch sử tiền ban đầu."
        )
    return await _workflow(request).execute(
        _command_context(request, session, require_version=True),
        ConfirmMoneyHistory(
            root_id=root_id, all_prior_money_recorded=payload.all_prior_money_recorded
        ),
    )


@router.get("/cases/{root_id}/advance/draft")
async def get_advance_draft(
    request: Request, root_id: str, draft_id: str | None = None
):
    session = _require_session(request)
    if session.persona != "accountant":
        raise HTTPException(
            status_code=403, detail="Chỉ kế toán được mở bản nháp chứng từ ứng."
        )
    return _workflow(request).get_advance_draft(session, root_id, draft_id)


@router.post("/cases/{root_id}/advance/draft")
async def advance_draft(
    request: Request,
    root_id: str,
    files: list[UploadFile] = File(...),
    method: str | None = None,
) -> dict[str, object]:
    """Persist the voucher on this root, then return its source-bound draft.

    Uploading/reading never records money. The accountant reviews and confirms
    through the actuals endpoint. File persistence and source attachment finish
    before provider I/O; a failed read still leaves the uploaded source retrievable.
    """
    session = _require_session(request)
    workflow = _workflow(request)
    if session.persona != "accountant":
        raise HTTPException(
            status_code=403, detail="Chỉ kế toán được bổ sung chứng từ ứng."
        )
    if not files:
        raise HTTPException(status_code=400, detail="Chưa chọn chứng từ ứng.")
    uploads: list[tuple[str, str, bytes]] = []
    for upload in files:
        data = await upload.read()
        media = _sniff_media(data, upload.filename)
        if media is None:
            raise HTTPException(
                status_code=415, detail="Chỉ nhận PDF, DOC, DOCX, PNG hoặc JPEG."
            )
        if len(data) > workflow.max_source_bytes:
            raise HTTPException(status_code=413, detail="Tệp vượt giới hạn dung lượng.")
        uploads.append((upload.filename or "tep", media, data))

    attach_uploads: list[SourceUpload] = []
    written: list[str] = []
    for filename, media, data in uploads:
        digest = hashlib.sha256(data).hexdigest()
        connection = workflow.db.connect()
        try:
            stored = connection.execute(
                "SELECT 1 FROM case_sources WHERE tenant = ? AND root_id = ? "
                "AND digest = ? LIMIT 1",
                (session.tenant, root_id, digest),
            ).fetchone()
        finally:
            connection.close()
        if stored is not None:
            continue
        source_id = f"source:{uuid.uuid4().hex}"
        storage_key = f"{session.tenant}/{root_id}/{source_id}"
        destination = workflow.uploads_dir / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        written.append(storage_key)
        attach_uploads.append(
            SourceUpload(
                filename=filename,
                media=media,
                digest=digest,
                storage_key=storage_key,
            )
        )

    case_view = None
    if attach_uploads:
        command_context = _command_context(request, session, require_version=True)
        command_context = command_context.model_copy(
            update={"command_id": f"{command_context.command_id}:advance-source"}
        )
        try:
            attached = await workflow.execute(
                command_context,
                AttachSources(root_id=root_id, uploads=tuple(attach_uploads)),
            )
            case_view = attached.case_view
        except Exception:
            for storage_key in written:
                (workflow.uploads_dir / storage_key).unlink(missing_ok=True)
            _prune_empty_upload_dirs(workflow.uploads_dir, session.tenant, root_id)
            raise

    draft = await workflow.read_advance_draft(
        session, root_id, tuple(uploads), method_hint=method
    )
    if case_view is None:
        case_view = workflow.view(_read_context(session), root_id)
    return {
        "draft": draft._asdict(),
        "case_view": case_view.model_dump(mode="json"),
    }


@router.post("/cases/{root_id}/return-draft")
async def employee_return_draft(
    request: Request, root_id: str, payload: views.EmployeeReturnDraftRequest
) -> dict[str, object]:
    """Read an employee's return proof; money awaits accountant confirmation."""
    session = _require_session(request)
    if session.persona != "employee":
        raise HTTPException(
            status_code=403,
            detail="Chỉ nhân viên của hồ sơ được tải chứng từ hoàn trả.",
        )
    context = _command_context(request, session, require_version=True)
    return await _workflow(request).read_employee_return_draft(
        session,
        root_id,
        payload.source_id,
        payload.instruction_id,
        method_hint=payload.instrument_method,
        expected_case_version=context.expected_case_version,
    )


@router.get("/cases/{root_id}/settlement/draft")
async def get_settlement_draft(
    request: Request,
    root_id: str,
) -> dict[str, object]:
    """Return prefilled draft for an existing case (reusing persisted report)."""
    session = _require_session(request)
    workflow = _workflow(request)
    return await workflow.get_settlement_draft(session, root_id)


@router.post("/cases/{root_id}/settlement/draft")
async def settlement_draft(
    request: Request,
    root_id: str,
    files: list[UploadFile] = File(default=[]),
    paper: list[UploadFile] = File(default=[]),
    evidence: list[UploadFile] = File(default=[]),
) -> dict[str, object]:
    """Read uploaded settlement documents and return a prefilled draft for review.

    New UI posts the paper box as ``paper`` (exactly one settlement form) and
    the evidence box as ``evidence`` (many). Legacy callers post ``files``
    without roles and keep the legacy classify-then-extract path.
    """
    session = _require_session(request)
    workflow = _workflow(request)
    if not files and not paper and not evidence:
        return await workflow.get_settlement_draft(session, root_id)

    async def _read_part(
        uploads: list[UploadFile], role: str | None
    ) -> list[tuple[str, str, bytes, str | None]]:
        out: list[tuple[str, str, bytes, str | None]] = []
        for upload in uploads:
            data = await upload.read()
            media = _sniff_media(data, upload.filename)
            if media is None:
                raise HTTPException(
                    status_code=415, detail="Chỉ nhận PDF, DOC, DOCX, PNG hoặc JPEG."
                )
            if len(data) > workflow.max_source_bytes:
                raise HTTPException(
                    status_code=413, detail="Tệp vượt giới hạn dung lượng."
                )
            out.append((upload.filename or "tep", media, data, role))
        return out

    uploads: list[tuple[str, str, bytes, str | None]] = []
    uploads.extend(await _read_part(files, None))
    uploads.extend(await _read_part(paper, "paper"))
    uploads.extend(await _read_part(evidence, "evidence"))
    draft = await workflow.read_settlement_draft(session, root_id, tuple(uploads))  # type: ignore[arg-type]
    return draft


@router.post("/cases/{root_id}/declaration/digital")
async def save_digital_declaration(
    request: Request, root_id: str, payload: views.DigitalDeclarationRequest
) -> dict[str, object]:
    """Validate + persist a DIGITAL_FORM declaration (S6).

    The server re-validates every row against attached case sources; files are
    referenced by source id, never bare filename.
    """
    from invoice_referee.domain.commands import Declaration, DigitalExpenseLine

    session = _require_session(request)
    workflow = _workflow(request)
    return workflow.save_digital_declaration(
        session,
        root_id,
        Declaration(
            declared_purpose=payload.declared_purpose,
            settlement_type=payload.settlement_type,
            submission_source="DIGITAL_FORM",
            digital_lines=tuple(
                DigitalExpenseLine(
                    item_id=line.item_id,
                    description=line.description,
                    category=line.category,
                    expense_date=line.expense_date,
                    amount=line.amount,
                    evidence_status=line.evidence_status,  # type: ignore[arg-type]
                    alternative_type=line.alternative_type,  # type: ignore[arg-type]
                    exception_reason=line.exception_reason,
                    note=line.note,
                    source_ids=tuple(line.source_ids),
                )
                for line in payload.digital_lines
            ),
            no_advance_asserted=payload.no_advance_asserted,
            no_advance_reason=payload.no_advance_reason,
        ).model_dump(mode="json"),
    )


@router.post("/cases/{root_id}/digital/draft")
async def read_digital_draft(request: Request, root_id: str) -> dict[str, object]:
    """Read attached evidence + the saved web declaration into a shared draft."""
    session = _require_session(request)
    workflow = _workflow(request)
    try:
        return await workflow.read_digital_draft(session, root_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/cases/{root_id}/decisions/refuse")
async def refuse_exception(
    request: Request, root_id: str, payload: views.RefuseRequest
) -> CommandResult:
    """Record an exception refusal: audit + REFUSED row, issues stay OPEN."""
    session = _require_session(request)
    workflow = _workflow(request)
    context = _command_context(request, session, require_version=True)
    return await workflow.execute(
        context,
        RefuseException(
            root_id=root_id,
            issue_ids=tuple(payload.issue_ids),
            reason=payload.reason,
        ),
    )


@router.get("/cases/{root_id}/exceptions/preview")
async def exception_preview(
    request: Request, root_id: str, issue_id: str
) -> dict[str, object]:
    """Grant coverage for one exception decision by the current actor (S6).

    Read-only: tells the accountant UI whether an accept would be authorized,
    which grants cover it and the ceiling — never a grant itself.
    """
    session = _require_session(request)
    workflow = _workflow(request)
    return workflow.exception_grant_preview(session, root_id, issue_id)


@router.get("/cases/{root_id}/sources/{source_id}/ocr-preview")
async def ocr_preview(
    request: Request,
    root_id: str,
    source_id: str,
    page: int = 1,
    x0: float = 0,
    y0: float = 0,
    x1: float = 0,
    y1: float = 0,
    ocr_width: float = 1000,
    ocr_height: float = 1400,
):
    """Render one source page PNG with the review box (S6, accountant region view).

    The box must come from a real source ref (bbox); without one the endpoint
    refuses (409) and the UI falls back to file/page/quote + original link —
    never an invented box.
    """
    from fastapi.responses import Response

    from invoice_referee.evidence.ocr_preview import render_ocr_block_preview

    session = _require_session(request)
    workflow = _workflow(request)
    if not (x1 > x0 and y1 > y0 and ocr_width > 0 and ocr_height > 0):
        raise HTTPException(
            status_code=409,
            detail="Vùng OCR chưa có bbox nguồn; xem file/trang/trích dẫn gốc.",
        )
    case = workflow.view(_read_context(session), root_id)
    matching = next((s for s in case.sources if s.id == source_id), None)
    if matching is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn trong hồ sơ.")
    file_path = workflow.uploads_dir / matching.storage_key
    if not file_path.exists():
        raise HTTPException(
            status_code=404, detail="Tệp chứng từ không tồn tại trên máy chủ."
        )
    try:
        image = render_ocr_block_preview(
            file_path,
            page_index=page - 1,
            bounding_box={
                "top_left_x": x0,
                "top_left_y": y0,
                "bottom_right_x": x1,
                "bottom_right_y": y1,
            },
            ocr_width=ocr_width,
            ocr_height=ocr_height,
            media=matching.media,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png")


@router.post("/cases/{root_id}/money-history/recheck")
async def recheck_dossier_history(request: Request, root_id: str, payload: views.RecheckDossierHistoryRequest) -> CommandResult:
    session = _require_session(request)
    context = _command_context(request, session, require_version=True)
    return await _workflow(request).execute(context, RecheckDossierHistory(root_id=root_id, reason=payload.reason))


@router.post("/cases/{root_id}/mark-execution")
async def mark_execution(request: Request, root_id: str, payload: views.MarkExecutionRequest) -> CommandResult:
    session = _require_session(request)
    context = _command_context(request, session, require_version=True)
    return await _workflow(request).execute(context, MarkExecution(
        root_id=root_id, instruction_id=payload.instruction_id,
        execution_state=payload.execution_state, refs=tuple(payload.refs), reason=payload.reason,
    ))


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
