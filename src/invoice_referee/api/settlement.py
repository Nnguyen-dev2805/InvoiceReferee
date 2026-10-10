"""Settlement API factory (W01+W02): intake and run/report routes.

``create_runtime_app`` is the composition root used by the ASGI factory
``invoice_referee.api.settlement:create_runtime_app`` (uvicorn ``--factory``).
It builds the Store, the reader and the Service ONCE at startup; routes only
map HTTP <-> records and DomainError codes to the S6 error envelope. The
historical contract in ``api/app`` stays untouched and is never mounted on
the same paths.

The demo authority grant below is explicit composition config (documented,
version-tagged), not a runtime policy default.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt

from invoice_referee.domain.models import DomainError
from invoice_referee.env import load_repo_env
from invoice_referee.settlement.b3 import B3Intake, load_b3_context
from invoice_referee.settlement.models import (
    AuthorityGrant,
    CaseSummary,
    CaseView,
    ClosureView,
    Command,
    DecisionView,
    DemoRole,
    MoneyEventView,
    QuestionView,
    Report,
    ResponsePayload,
    ResponseView,
    ReviewView,
    RunView,
    SourceRecord,
    SourceView,
    Submission,
    Upload,
)
from invoice_referee.settlement.evaluation import run_suite
from invoice_referee.settlement.reader import (
    MISTRAL_OCR_BASE_URL,
    MISTRAL_OCR_MODEL,
    XKIRO_BASE_URL,
    XKIRO_MODEL,
    MistralOCRClient,
    SettlementReader,
    StructuredLedgerReader,
    XkiroClient,
)
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

DEFAULT_DATA_DIR = Path("data") / "settlement"

DEMO_AUTHORITY = [
    AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                   max_settlement_vnd=100_000_000),
]

_STATUS_BY_CODE = {
    "CASE_NOT_FOUND": 404,
    "SOURCE_NOT_FOUND": 404,
    "RUN_NOT_FOUND": 404,
    "QUESTION_NOT_FOUND": 404,
    "DECISION_NOT_FOUND": 404,
    "STALE_VERSION": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "RUN_ACTIVE": 409,
    "STOP_ACTIVE": 409,
    "TOO_MANY_RUNS": 409,
    "REPORT_NOT_READY": 409,
    "BASIS_STALE": 409,
    "CLOSURE_BLOCKED": 409,
    "CASE_CLOSED": 409,
    "DUPLICATE_EVENT_REF": 409,
    "BEYOND_AUTHORITY": 403,
    "PERSONA_MISMATCH": 403,
    "B3_REPORT_ONLY": 409,
    "FILE_TOO_LARGE": 413,
    "SOURCE_LIMIT_REACHED": 413,
    "UNSUPPORTED_FORMAT": 415,
    "REVIEW_NOT_APPROVAL": 400,
    "INVALID_PAYLOAD": 400,
    "CONTROL_INVALID": 400,
}


class CreateCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission: Submission
    actor_id: str
    demo_role: DemoRole
    body: dict[str, Any] = {}


class ReviseSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission: Submission
    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    reason: str = ""


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt


class RespondRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    content: str
    source_ids: list[str] = []


class DecisionRequest(BaseModel):
    """DECIDE over HTTP: authority-checked approval/refusal (S6)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    kind: Literal["SETTLEMENT"]
    amount_vnd: StrictInt | None = None
    direction: Literal["PAY_EMPLOYEE", "COLLECT_FROM_EMPLOYEE", "REFUSE"]
    reason: str
    basis_report_id: str
    conditions: list[str] = []
    exception_of: str | None = None


class ReviewRequest(BaseModel):
    """Accountant review; amount_vnd is surfaced so the semantic error fires."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    report_id: str
    note: str
    refs: list[str] = []
    amount_vnd: StrictInt | None = None


class MoneyEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    event_ref: str
    kind: Literal["PAYMENT_TO_EMPLOYEE", "PAYMENT_FROM_EMPLOYEE"]
    gross_vnd: StrictInt
    decision_id: str | None = None
    payee_ref: str
    event_at: str
    reported_status: Literal["RECEIVED", "PENDING"]
    refs: list[str] = []


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    action: Literal["STOP", "RESUME"]
    reason: str = ""


class HandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    decision_id: str


class ClosureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    demo_role: DemoRole
    expected_case_version: StrictInt
    kind: Literal["SETTLEMENT_COMPLETE", "REJECTED_REQUEST_ENDED"]
    basis: str


class VerifyRunRequest(BaseModel):
    """Run the settlement evaluation suite sequentially (same Service path)."""

    model_config = ConfigDict(extra="forbid")

    packets: list[str] | None = None


class CreateB3CaseRequest(BaseModel):
    """B3 v1 intake: chỉ actor + lời khai; context/quyền/clock do backend."""

    model_config = ConfigDict(extra="forbid")

    actor_id: str
    intake: dict[str, Any]


DEFAULT_EVAL_CORPUS = Path("docs/discovery/eval_development")
DEFAULT_VERIFY_DIR = DEFAULT_DATA_DIR / "verify"
_verify_service: dict[str, Service] = {}


def _evaluation_service() -> Service:
    """Isolated store for evaluation runs; same Service/reader wiring."""
    if "service" not in _verify_service:
        out_dir = Path(os.environ.get("SETTLEMENT_VERIFY_DIR", DEFAULT_VERIFY_DIR))
        out_dir.mkdir(parents=True, exist_ok=True)
        store = Store(out_dir / "verify.sqlite", out_dir / "artifacts")
        reader = _reader_from_env(store.artifact_root)
        _verify_service["service"] = Service(
            store, reader, config=ServiceConfig(authority=DEMO_AUTHORITY))
    return _verify_service["service"]


def _reader_from_env(artifact_root: Path):
    """Explicit provider mode: fake offline default; live fails loudly.

    There is NO live→fake fallback: ``SETTLEMENT_PROVIDER_MODE=live`` without
    the required keys raises CONFIG_NOT_ACTIVE at startup.
    """
    mode = os.environ.get("SETTLEMENT_PROVIDER_MODE", "fake").strip().lower()
    if mode not in {"fake", "live"}:
        raise DomainError(
            "CONFIG_NOT_ACTIVE",
            f"SETTLEMENT_PROVIDER_MODE phải là fake hoặc live, nhận {mode!r}.",
        )
    if mode == "live":
        ocr = MistralOCRClient(
            api_key=os.environ.get("MISTRAL_API_KEY", ""),
            base_url=os.environ.get("MISTRAL_BASE_URL", MISTRAL_OCR_BASE_URL),
            model=os.environ.get("MISTRAL_OCR_MODEL", MISTRAL_OCR_MODEL),
        )
        xkiro = XkiroClient(
            api_key=os.environ.get("XKIRO_API_KEY", ""),
            base_url=os.environ.get("XKIRO_BASE_URL", XKIRO_BASE_URL),
            model=os.environ.get("XKIRO_MODEL", XKIRO_MODEL),
        )
        return SettlementReader(artifact_root, ocr, xkiro)
    return StructuredLedgerReader(artifact_root)


def create_runtime_app(*, db_path: Path | None = None,
                       artifact_root: Path | None = None,
                       service: Service | None = None) -> FastAPI:
    """Build the settlement app; pilot defaults under ``data/settlement``."""
    if service is None:
        # Repo-root .env (Git-ignored) được nạp như app cũ: biến đã export
        # trong môi trường luôn thắng (setdefault semantics).
        load_repo_env()
        db = Path(db_path or os.environ.get(
            "SETTLEMENT_DB_PATH", DEFAULT_DATA_DIR / "settlement.sqlite"))
        root = Path(artifact_root or os.environ.get(
            "SETTLEMENT_ARTIFACT_ROOT", DEFAULT_DATA_DIR / "artifacts"))
        store = Store(db, root)
        reader = _reader_from_env(store.artifact_root)
        b3_context = None
        context_path = os.environ.get(
            "SETTLEMENT_B3_CONTEXT_PATH", "").strip()
        if context_path:
            # File cấu hình sai dạng phải lỗi startup rõ, không fallback quyền.
            b3_context = load_b3_context(context_path)
        service = Service(store, reader,
                          config=ServiceConfig(authority=DEMO_AUTHORITY,
                                               b3_context=b3_context))
    app = FastAPI(title="InvoiceReferee Settlement", version="0.2.0")

    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        payload: dict[str, Any] = {"code": exc.code, "message": exc.message}
        case_id = request.path_params.get("case_id")
        if case_id:
            try:
                payload["current_case_version"] = service.get_case(
                    case_id).case_version
            except DomainError:
                payload["current_case_version"] = None
        return JSONResponse(status_code=_STATUS_BY_CODE.get(exc.code, 400),
                            content=payload)

    def _command(key: str, actor_id: str, demo_role: str,
                 expected_case_version: int | None,
                 body: dict[str, Any]) -> Command:
        return Command(key=key, actor_id=actor_id, demo_role=demo_role,  # type: ignore[arg-type]
                       expected_case_version=expected_case_version, body=body)

    @app.post("/api/cases", response_model=None, status_code=201)
    async def create_case(
        request: CreateCaseRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | CaseView:
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                           None, request.body)
        view = service.submit(request.submission, command)
        if view.idempotent_replay:
            return JSONResponse(status_code=200, content=view.model_dump(mode="json"))
        return view

    @app.get("/api/cases", response_model=list[CaseSummary])
    async def list_cases() -> list[CaseSummary]:
        return service.store.list_cases()

    @app.get("/api/demo-context", response_model=None)
    async def demo_context() -> JSONResponse:
        """Profile demo đã cấu hình; không cấp quyền do client nhập."""
        context = service.config.b3_context
        if context is None or not context.activated:
            raise DomainError(
                "CONFIG_NOT_ACTIVE",
                "Chưa cấu hình SETTLEMENT_B3_CONTEXT_PATH trỏ tới company "
                "fixture B3; không generate profile/quyền giả.",
            )
        return JSONResponse({
            "version": context.version,
            "synthetic": context.synthetic,
            "demo_clock": (context.demo_clock.isoformat()
                           if context.demo_clock else None),
            "people": [p.model_dump(mode="json") for p in context.people],
            "routes": [r.model_dump(mode="json") for r in context.routes],
        })

    @app.post("/api/b3-cases", response_model=None, status_code=201)
    async def create_b3_case(
        request: CreateB3CaseRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | CaseView:
        from pydantic import ValidationError

        try:
            intake = B3Intake.model_validate(request.intake)
        except ValidationError as error:
            raise DomainError(
                "INVALID_PAYLOAD",
                f"Lời khai B3 không hợp lệ (không nhận context/quyền do "
                f"client nhập): {error}",
            ) from error
        command = _command(idempotency_key, request.actor_id, "EMPLOYEE",
                           None, {})
        view = service.submit_b3(request.actor_id, intake, command)
        if view.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=view.model_dump(mode="json"))
        return view

    @app.get("/api/cases/{case_id}", response_model=CaseView)
    async def get_case(case_id: str) -> CaseView:
        return service.get_case(case_id)

    @app.patch("/api/cases/{case_id}/submission", response_model=CaseView)
    async def revise_submission(
        case_id: str,
        request: ReviseSubmissionRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> CaseView:
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                           request.expected_case_version,
                           {"reason": request.reason})
        return service.revise(case_id, request.submission, command)

    @app.post("/api/cases/{case_id}/sources", response_model=SourceView, status_code=201)
    async def add_source(
        case_id: str,
        file: UploadFile = File(...),
        actor_id: str = Form(...),
        demo_role: str = Form(...),
        expected_case_version: int = Form(...),
        note: str = Form(""),
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | SourceView:
        content = await file.read()
        upload = Upload(filename=file.filename or "source",
                        content=content,
                        provenance={"note": note} if note else {})
        command = _command(idempotency_key, actor_id, demo_role,
                           expected_case_version, {})
        record: SourceRecord = service.add_source(case_id, upload, command)
        if record.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=_source_view(record).model_dump(mode="json"))
        return _source_view(record)

    @app.get("/api/sources/{source_id}/content")
    async def source_content(source_id: str, download: bool = False) -> FileResponse:
        record = service.store.get_source(source_id)
        path = service.store.artifact_root / record.original_path
        return FileResponse(
            path,
            media_type=record.media_type,
            filename=record.filename if download else None,
        )

    @app.post("/api/cases/{case_id}/runs", response_model=RunView, status_code=202)
    async def start_run(
        case_id: str,
        request: StartRunRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | RunView:
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                           request.expected_case_version, {})
        run = service.start(case_id, command)
        if run.idempotent_replay:
            return JSONResponse(status_code=200, content=run.model_dump(mode="json"))
        return run

    @app.get("/api/runs/{run_id}", response_model=RunView)
    async def get_run(run_id: str) -> RunView:
        return service.get_run(run_id)

    @app.get("/api/runs/{run_id}/report", response_model=Report)
    async def get_report(run_id: str) -> Report:
        return service.report(run_id)

    @app.get("/api/runs/{run_id}/b3-context", response_model=None)
    async def b3_run_context(run_id: str) -> JSONResponse:
        """Snapshot context của run đó (immutable); refs company:<...> mở tới
        record tương ứng trong response này."""
        run_input = service.store.get_run_input(run_id)
        context = run_input.b3_context
        if context is None:
            raise DomainError(
                "CONFIG_NOT_ACTIVE",
                f"Run {run_id} không mang company context trong snapshot.",
            )
        return JSONResponse({
            "version": context.version,
            "synthetic": context.synthetic,
            "demo_clock": (context.demo_clock.isoformat()
                           if context.demo_clock else None),
            "grants": [g.model_dump(mode="json") for g in context.grants],
            "coverage": [c.model_dump(by_alias=True, mode="json")
                         for c in context.coverage],
            "history": [h.model_dump(mode="json") for h in context.history],
        })

    @app.get("/api/cases/{case_id}/questions", response_model=list[QuestionView])
    async def list_questions(case_id: str) -> list[QuestionView]:
        return service.questions(case_id)

    @app.post("/api/questions/{question_id}/responses",
              response_model=ResponseView, status_code=201)
    async def respond_question(
        question_id: str,
        request: RespondRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | ResponseView:
        payload = ResponsePayload(content=request.content,
                                  source_ids=request.source_ids)
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        response = service.respond(question_id, payload, command)
        if response.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=response.model_dump(mode="json"))
        return response

    @app.post("/api/cases/{case_id}/decisions",
              response_model=DecisionView, status_code=201)
    async def decide(
        case_id: str,
        request: DecisionRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | DecisionView:
        payload = {
            "kind": request.kind, "amount_vnd": request.amount_vnd,
            "direction": request.direction, "reason": request.reason,
            "basis_report_id": request.basis_report_id,
            "conditions": request.conditions, "exception_of": request.exception_of,
        }
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        decision = service.decide(case_id, payload, command)
        if decision.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=decision.model_dump(mode="json"))
        return decision

    @app.post("/api/cases/{case_id}/reviews",
              response_model=ReviewView, status_code=201)
    async def review(
        case_id: str,
        request: ReviewRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | ReviewView:
        payload: dict[str, Any] = {
            "report_id": request.report_id, "note": request.note,
            "refs": request.refs,
        }
        if request.amount_vnd is not None:
            payload["amount_vnd"] = request.amount_vnd  # → REVIEW_NOT_APPROVAL
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        review = service.review(case_id, payload, command)
        if review.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=review.model_dump(mode="json"))
        return review

    @app.post("/api/cases/{case_id}/money-events",
              response_model=MoneyEventView, status_code=201)
    async def record_money(
        case_id: str,
        request: MoneyEventRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | MoneyEventView:
        payload = {
            "event_ref": request.event_ref, "kind": request.kind,
            "gross_vnd": request.gross_vnd, "decision_id": request.decision_id,
            "payee_ref": request.payee_ref, "event_at": request.event_at,
            "reported_status": request.reported_status, "refs": request.refs,
        }
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        event = service.record_money(case_id, payload, command)
        if event.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=event.model_dump(mode="json"))
        return event

    @app.post("/api/cases/{case_id}/control", response_model=None, status_code=201)
    async def control(
        case_id: str,
        request: ControlRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | dict[str, Any]:
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version,
                          {"reason": request.reason})
        result = service.control(case_id, request.action, command)
        status = 200 if result.get("idempotent_replay") else 201
        return JSONResponse(status_code=status, content=result)

    @app.post("/api/cases/{case_id}/handoffs", response_model=None, status_code=201)
    async def handoff(
        case_id: str,
        request: HandoffRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse:
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        result = service.handoff(case_id, {"decision_id": request.decision_id},
                                 command)
        status = 200 if result.get("idempotent_replay") else 201
        return JSONResponse(status_code=status, content=result)

    @app.post("/api/cases/{case_id}/closures",
              response_model=ClosureView, status_code=201)
    async def close_case(
        case_id: str,
        request: ClosureRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
    ) -> JSONResponse | ClosureView:
        payload = {"kind": request.kind, "basis": request.basis}
        command = _command(idempotency_key, request.actor_id, request.demo_role,
                          request.expected_case_version, {})
        closure = service.close_case(case_id, payload, command)
        if closure.idempotent_replay:
            return JSONResponse(status_code=200,
                                content=closure.model_dump(mode="json"))
        return closure

    @app.post("/api/verify/settlement/run", response_model=None, status_code=200)
    async def run_settlement_verify(
        request: VerifyRunRequest,
    ) -> JSONResponse:
        corpus = Path(os.environ.get("SETTLEMENT_EVAL_CORPUS",
                                     DEFAULT_EVAL_CORPUS))
        report = run_suite(corpus, _evaluation_service(), request.packets)
        return JSONResponse(report.model_dump(mode="json"))

    @app.get("/api/cases/{case_id}/history", response_model=None)
    async def case_history(case_id: str) -> list[dict[str, Any]]:
        service.get_case(case_id)  # 404 for unknown cases before an empty history
        return [entry.model_dump(mode="json")
                for entry in service.store.history(case_id)]

    return app


def _source_view(record: SourceRecord) -> SourceView:
    return SourceView(
        id=record.id, filename=record.filename, media_type=record.media_type,
        sha256=record.sha256, size_bytes=record.size_bytes, status=record.status,
        uploader_actor_id=record.uploader_actor_id,
        received_at=record.received_at,
        supersedes_source_id=record.supersedes_source_id,
        provenance=record.provenance,
    )
