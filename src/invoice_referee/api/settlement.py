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
from typing import Any

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    AuthorityGrant,
    CaseSummary,
    CaseView,
    Command,
    DemoRole,
    Report,
    RunView,
    SourceRecord,
    SourceView,
    Submission,
    Upload,
)
from invoice_referee.settlement.pipeline import StructuredLedgerReader
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
    "STALE_VERSION": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "RUN_ACTIVE": 409,
    "STOP_ACTIVE": 409,
    "TOO_MANY_RUNS": 409,
    "REPORT_NOT_READY": 409,
    "FILE_TOO_LARGE": 413,
    "SOURCE_LIMIT_REACHED": 413,
    "UNSUPPORTED_FORMAT": 415,
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


def create_runtime_app(*, db_path: Path | None = None,
                       artifact_root: Path | None = None,
                       service: Service | None = None) -> FastAPI:
    """Build the settlement app; pilot defaults under ``data/settlement``."""
    if service is None:
        db = Path(db_path or os.environ.get(
            "SETTLEMENT_DB_PATH", DEFAULT_DATA_DIR / "settlement.sqlite"))
        root = Path(artifact_root or os.environ.get(
            "SETTLEMENT_ARTIFACT_ROOT", DEFAULT_DATA_DIR / "artifacts"))
        store = Store(db, root)
        reader = StructuredLedgerReader(store.artifact_root)
        service = Service(store, reader,
                          config=ServiceConfig(authority=DEMO_AUTHORITY))
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
