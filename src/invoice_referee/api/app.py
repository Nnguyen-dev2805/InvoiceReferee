"""create_app(workflow: CaseWorkflow) -> FastAPI (contracts §9).

Wires the demo routes, maps workflow errors to explicit HTTP codes and serves
the built frontend when present. Delegation only; behaviour lives in the
workflow.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from invoice_referee.api.routes import router
from invoice_referee.workflow.service import (
    CaseWorkflow,
    CommandConflictError,
    NotFoundError,
    StaleCommandError,
    UnknownSessionError,
    UnsupportedCommandError,
)


def create_app(
    workflow: CaseWorkflow,
    *,
    mode: str = "STUB",
    settings: object | None = None,
    frontend_dir: str | Path | None = None,
    evidence_worker: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        stop = asyncio.Event()
        task: asyncio.Task | None = None
        if evidence_worker and getattr(workflow, "_evidence_reader", None) is not None:
            from invoice_referee.workflow.evidence_jobs import drain_evidence_jobs

            task = asyncio.create_task(drain_evidence_jobs(workflow, stop))
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    app = FastAPI(title="InvoiceReferee", docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.state.workflow = workflow
    app.state.mode = mode
    app.state.settings = settings
    app.state.frontend_dir = Path(frontend_dir) if frontend_dir is not None else None
    app.include_router(router)

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc), "code": "NOT_FOUND"})

    @app.exception_handler(StaleCommandError)
    async def _stale(request: Request, exc: StaleCommandError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": str(exc), "code": "STALE_VERSION"}
        )

    @app.exception_handler(CommandConflictError)
    async def _conflict(request: Request, exc: CommandConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": str(exc), "code": "IDEMPOTENCY_CONFLICT"}
        )

    @app.exception_handler(UnknownSessionError)
    async def _unknown_session(request: Request, exc: UnknownSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=401, content={"detail": str(exc), "code": "UNKNOWN_SESSION"}
        )

    @app.exception_handler(UnsupportedCommandError)
    async def _unsupported(request: Request, exc: UnsupportedCommandError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content={"detail": str(exc), "code": "UNSUPPORTED_COMMAND"}
        )

    if app.state.frontend_dir is not None and app.state.frontend_dir.is_dir():
        app.mount(
            "/", StaticFiles(directory=str(app.state.frontend_dir), html=True), name="frontend"
        )
    return app
