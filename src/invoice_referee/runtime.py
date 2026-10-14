"""Runtime composition: build a CaseWorkflow with the reader wired per mode.

`build_workflow(settings, mode, ...)` is the single entry the dev server, the
CLI and Verify use, so every mode (STUB / RECORDED_REPLAY / LIVE) composes the
same workflow and only the reader differs (plan R4). A LIVE submit reads the
uploaded sources; STUB assesses a seeded hand-transcription; replay serves a
matching recording. Provider I/O never runs inside a mutation transaction.
"""

from __future__ import annotations

from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.evidence.trace import ProviderMode
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow


def build_llm_client(settings: Settings):
    """Build the configured X-Kiro LLM client, or fail loudly (plan E4 Step 5).

    A missing provider credential is reported with the setting name; LIVE is
    never silently downgraded to STUB.
    """
    from invoice_referee.evidence.xkiro import XkiroClient

    missing = [
        name
        for name in ("XKIRO_API_KEY", "XKIRO_BASE_URL", "INVOICE_REFEREE_LLM_MODEL")
        if not getattr(settings, name.lower(), None)
    ]
    if missing:
        raise ValueError(f"LLM provider not configured: missing {', '.join(missing)}")
    return XkiroClient(
        api_key=settings.xkiro_api_key or "",
        model=settings.invoice_referee_llm_model or "",
        base_url=settings.xkiro_base_url or "",
    )


def build_workflow(
    settings: Settings,
    mode: ProviderMode,
    *,
    db: Database,
    uploads_dir: str | Path,
    context_path: str | Path,
    clock=None,
) -> CaseWorkflow:
    """Build the workflow for one mode and import the demo context.

    `clock` is an optional server/harness clock. The web entry leaves it None
    (real UTC); a historical-fixture harness injects a controlled clock so the
    assessment time is explicit and reproducible. It is never a client value.
    """
    db.migrate()
    workflow = CaseWorkflow(db, uploads_dir=uploads_dir, clock=clock)
    workflow.import_demo_context(context_path, origin="SIMULATED")
    workflow.provider_mode = mode
    # Compose the trace sink here (the single entry point) and pass it to the
    # real consumers. Tracing is opt-in from Settings; when off the recorder is a
    # local no-op sink, so the workflow traces nothing and never calls the cloud.
    _wire_trace(workflow, settings)

    if mode == "LIVE":
        _wire_live(workflow, uploads_dir=uploads_dir, settings=settings)
    elif mode == "RECORDED_REPLAY":
        _wire_replay(workflow, settings=settings)
    return workflow


def _wire_trace(workflow: CaseWorkflow, settings: Settings) -> None:
    """Compose the operation/step trace recorder from Settings.

    `build_trace` returns a LangSmithTrace that is a local no-op when tracing is
    disabled or unkeyed; the recorder always exists so the workflow can open an
    operation root without a None check. Never a separate pipeline: the recorder
    wraps the SAME business workflow and only observes it.
    """
    from invoice_referee.evidence.telemetry import TraceRecorder
    from invoice_referee.evidence.trace import build_trace

    workflow.enable_trace(TraceRecorder(build_trace(settings)))


def _wire_live(workflow: CaseWorkflow, *, uploads_dir: str | Path, settings: Settings) -> None:
    """Compose the §12 evidence pipeline for LIVE (plan E7).

    The LIVE runtime uses the file-level OCR reader + the configured X-Kiro
    classifier; the legacy native-text transcriber is not used. Provider I/O
    runs in the durable evidence worker, outside any SQLite transaction.
    """
    from invoice_referee.evidence.live_reader import build_file_ocr_provider
    from invoice_referee.evidence.reader import FileOcrReader

    llm = build_llm_client(settings)
    reader = FileOcrReader(provider=build_file_ocr_provider(settings=settings))
    workflow.enable_evidence_read(
        reader=reader,
        classifier=llm,
        artifacts_root=Path(uploads_dir).parent / "artifacts",
        provider_mode="LIVE",
    )


def _wire_replay(workflow: CaseWorkflow, *, settings: Settings) -> None:
    """Compose the evidence pipeline for RECORDED_REPLAY (plan E7).

    Replay needs a captured recording; without one the read is a miss (never a
    fabricated page), so the case stays unresolved.
    """
    from invoice_referee.evidence.reader import FileOcrReader
    from invoice_referee.evidence.replay import ReplayReader

    recording = getattr(settings, "replay_recording", None)
    provider = ReplayReader(Path(recording)) if recording else ReplayReader(Path("/nonexistent"))
    llm = build_llm_client(settings)
    workflow.enable_evidence_read(
        reader=FileOcrReader(provider=provider),
        classifier=llm,
        artifacts_root=Path(getattr(settings, "uploads_dir", ".")).parent / "artifacts",
        provider_mode="RECORDED_REPLAY",
    )
