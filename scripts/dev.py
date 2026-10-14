"""Single dev/pilot entry (plan T2; extended for Docker/public pilot at T10).

Usage:
    uv run python scripts/dev.py [--mode live|replay|stub] [--port 8000]

Default mode is LIVE: the server reads the documents you upload (Mistral OCR +
model). Pass --mode stub for the offline demo path (a seeded hand-transcription,
no provider calls). A missing live credential fails with the missing names
instead of silently degrading (design §10).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from invoice_referee.api.app import create_app
from invoice_referee.config import Settings
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / ".runtime" / "invoice-referee.sqlite"
DEFAULT_UPLOADS = PROJECT_ROOT / ".runtime" / "uploads"
DEFAULT_CONTEXT = PROJECT_ROOT / "data" / "demo" / "company-context.json"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def build_workflow(
    db_path: str, uploads_dir: str, context_path: str, *, mode: str = "STUB", settings: Settings | None = None
) -> tuple[CaseWorkflow, str]:
    from invoice_referee.runtime import build_workflow as compose_workflow

    database = Database(db_path)
    workflow = compose_workflow(
        settings or Settings(),
        mode,  # type: ignore[arg-type]
        db=database,
        uploads_dir=uploads_dir,
        context_path=context_path,
    )
    digest = workflow.last_context_import("tenant:demo")["digest"]
    return workflow, digest


def format_diagnostics(
    *,
    mode: str,
    db_path: str,
    uploads_dir: str,
    context_path: str,
    context_digest: str,
    settings: Settings,
    host: str,
    port: int,
) -> str:
    frontend_note = (
        f"{FRONTEND_DIST} (đã build)"
        if FRONTEND_DIST.is_dir()
        else "CHƯA build — chạy: npm --prefix frontend run build"
    )
    missing = settings.missing_for_live()
    keys_note = ", ".join(missing) if missing else "đủ cho LIVE"
    if mode != "LIVE":
        keys_note = f"(mode {mode} không cần provider) thiếu: {keys_note}"
    return "\n".join(
        (
            "InvoiceReferee demo server",
            f"  mode      : {mode}",
            f"  db        : {db_path}",
            f"  uploads   : {uploads_dir}",
            f"  context   : {context_path} · sha256 {context_digest[:12]}… · origin SIMULATED",
            f"  frontend  : {frontend_note}",
            f"  live keys : {keys_note}",
            f"  url       : http://{host}:{port}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InvoiceReferee demo server")
    parser.add_argument("--mode", choices=("stub", "replay", "live"), default="live")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--uploads", default=str(DEFAULT_UPLOADS))
    parser.add_argument("--context", default=str(DEFAULT_CONTEXT))
    args = parser.parse_args(argv)

    mode = args.mode.upper()
    settings = Settings()
    if mode == "LIVE" and settings.missing_for_live():
        print(
            "LIVE mode thiếu cấu hình: "
            + ", ".join(settings.missing_for_live())
            + "\nĐặt biến trong .env (xem .env.example) rồi chạy lại; "
            "không có chế độ giả lập ngầm.",
        )
        return 2
    if mode == "RECORDED_REPLAY":
        print(
            "RECORDED_REPLAY chưa có read recording (đến ở T5). "
            "UI hiện chưa thực hiện đọc chứng từ; tiếp tục với server STUB nhãn REPLAY.",
        )

    workflow, digest = build_workflow(
        args.db, args.uploads, args.context, mode=mode, settings=settings
    )
    app = create_app(
        workflow,
        mode=mode,
        settings=settings,
        frontend_dir=FRONTEND_DIST,
        evidence_worker=(mode in ("LIVE", "RECORDED_REPLAY")),
    )
    print(
        format_diagnostics(
            mode=mode,
            db_path=args.db,
            uploads_dir=args.uploads,
            context_path=args.context,
            context_digest=digest,
            settings=settings,
            host=args.host,
            port=args.port,
        )
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
