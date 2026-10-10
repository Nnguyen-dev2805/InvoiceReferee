"""FastAPI entrypoint for InvoiceReferee."""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app.web.routes import build_router
from app.web.runtime import build_runtime
from invoice_referee.config import AppSettings


def create_app() -> FastAPI:
    settings = AppSettings.from_environment(PROJECT_ROOT)
    runtime = build_runtime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def worker_loop() -> None:
            while True:
                processed = await asyncio.to_thread(runtime.processor.run_once)
                await asyncio.sleep(0.25 if processed else 1.5)

        worker_task = None
        if os.getenv("INVOICE_REFEREE_DISABLE_WORKER", "0") != "1":
            worker_task = asyncio.create_task(worker_loop())
        yield
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task

    app = FastAPI(
        title="InvoiceReferee",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.runtime = runtime
    app.mount(
        "/static",
        StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
        name="static",
    )
    app.include_router(build_router(PROJECT_ROOT / "app" / "templates"))
    return app


app = create_app()
