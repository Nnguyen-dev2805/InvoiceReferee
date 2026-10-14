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
) -> CaseWorkflow:
    """Build the workflow for one mode and import the demo context."""
    db.migrate()
    workflow = CaseWorkflow(db, uploads_dir=uploads_dir)
    workflow.import_demo_context(context_path, origin="SIMULATED")
    workflow.provider_mode = mode

    if mode == "LIVE":
        _wire_live(workflow, uploads_dir=uploads_dir, settings=settings)
    elif mode == "RECORDED_REPLAY":
        _wire_replay(workflow, settings=settings)
    return workflow


def _wire_live(workflow: CaseWorkflow, *, uploads_dir: str | Path, settings: Settings) -> None:
    from invoice_referee.evidence.live_reader import MistralPageReader
    from invoice_referee.evidence.pipeline import transcribe_root
    from invoice_referee.evidence.trace import RunBudget

    async def transcriber(*, sources, budget=None, provider_mode="LIVE"):
        return await transcribe_root(
            reader=MistralPageReader(
                uploads_dir=uploads_dir, settings=settings, budget=budget or RunBudget()
            ),
            sources=sources,
            budget=budget or RunBudget(),
            provider_mode=provider_mode,
        )

    workflow.enable_live_read(transcriber, provider_mode="LIVE")


def _wire_replay(workflow: CaseWorkflow, *, settings: Settings) -> None:
    from invoice_referee.evidence.pipeline import transcribe_root
    from invoice_referee.evidence.replay import ReplayReader
    from invoice_referee.evidence.trace import RunBudget

    recording = getattr(settings, "replay_recording", None)
    reader = ReplayReader(Path(recording)) if recording else ReplayReader(Path("/nonexistent"))

    async def transcriber(*, sources, budget=None, provider_mode="RECORDED_REPLAY"):
        return await transcribe_root(
            reader=reader, sources=sources, budget=budget or RunBudget(),
            provider_mode=provider_mode,
        )

    workflow.enable_live_read(transcriber, provider_mode="RECORDED_REPLAY")
