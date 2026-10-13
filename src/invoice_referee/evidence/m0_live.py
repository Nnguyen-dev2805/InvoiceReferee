"""M0 LIVE runner: measure the real reader over 4 packet types (plan T5, §5/§8/§9).

Runs text / clear-scan / unclear-scan / non-document once each with finite
ceilings, records every attempt/error/usage/time, and emits a LangSmith span
per attempt (payload filtered). No business decision is made here; this only
measures the provider so the baseline model/ceilings are real numbers, not
guesses.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.evidence.mistral import MistralError, MistralOcrClient
from invoice_referee.evidence.pdf import native_text, render_page_png
from invoice_referee.evidence.trace import RunBudget, RunManifest, TraceSpan, build_trace

M0_CASES = ("text", "clear_scan", "unclear_scan", "non_document")


@dataclass
class LiveAttempt:
    kind: str
    source: str
    ok: bool
    used_ocr: bool
    error: str | None = None
    chars: int = 0
    elapsed_ms: float = 0.0
    ocr_model: str | None = None


@dataclass
class LiveReport:
    mode: str
    manifest: dict[str, object]
    attempts: list[LiveAttempt] = field(default_factory=list)
    budget: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "manifest": self.manifest,
                "budget": self.budget,
                "attempts": [asdict(a) for a in self.attempts],
            },
            ensure_ascii=False,
            indent=2,
        )


def _run_case(
    kind: str, path: Path, settings: Settings, budget: RunBudget
) -> tuple[LiveAttempt, str]:
    """Read one M0 input; native text for PDFs, Mistral OCR for scans/images."""
    start = time.monotonic()
    used_ocr = False
    text = ""
    error: str | None = None
    try:
        if path.suffix.lower() == ".pdf":
            pages = native_text(path)
            text = "\n".join(pages.values())
        if not text.strip():
            # No native text (scan/hybrid) or a non-PDF image: OCR is needed.
            if not budget.can_call_ocr():
                raise MistralError("OCR budget exhausted")
            client = MistralOcrClient(
                api_key=settings.mistral_api_key or "",
                model=settings.mistral_ocr_model or "",
                timeout_s=budget.http_timeout_s,
            )
            if path.suffix.lower() == ".pdf":
                image_bytes = render_page_png(path, 1)
            else:
                image_bytes = path.read_bytes()
            text = await_ocr(client, image_bytes, budget)
            used_ocr = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = (time.monotonic() - start) * 1000
    attempt = LiveAttempt(
        kind=kind,
        source=str(path),
        ok=error is None,
        used_ocr=used_ocr,
        error=error,
        chars=len(text),
        elapsed_ms=elapsed,
        ocr_model=settings.mistral_ocr_model if used_ocr else None,
    )
    return attempt, text


def await_ocr(client: MistralOcrClient, image_bytes: bytes, budget: RunBudget) -> str:
    import asyncio

    return asyncio.run(client.ocr_image(image_bytes, budget=budget))


def _resolve_m0_inputs(input_dir: Path) -> dict[str, Path | None]:
    """Map each M0 kind to its probe file, via the technical manifest if present.

    The R1 generator writes ky-thuat/manifest.json mapping folders to kinds; the
    M0 CLI reads it instead of a hardcoded root layout (plan R8). A legacy flat
    root (text.pdf/clear_scan.pdf/...) is still accepted.
    """
    manifest_path = input_dir / "manifest.json"
    files: dict[str, Path | None] = {kind: None for kind in M0_CASES}
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for probe in data.get("probes", []):
            kind = str(probe.get("kind"))
            folder = input_dir / str(probe.get("folder"))
            candidate = next(
                (p for p in sorted(folder.glob("*")) if p.is_file()),
                None,
            ) if folder.is_dir() else None
            if kind in files:
                files[kind] = candidate
        return files
    files["text"] = input_dir / "text.pdf"
    files["clear_scan"] = input_dir / "clear_scan.pdf"
    files["unclear_scan"] = input_dir / "unclear_scan.pdf"
    files["non_document"] = input_dir / "non_document.png"
    return files


def run_m0_live(input_dir: Path, settings: Settings) -> LiveReport:
    budget = RunBudget()
    trace = build_trace(settings)
    manifest = RunManifest(
        mode="LIVE",
        requested_model=settings.mistral_ocr_model,
        returned_model=None,
        resolved_model=settings.mistral_ocr_model,
        usage_unknown=True,
        notes="M0 LIVE baseline; no business decision.",
    )
    report = LiveReport(
        mode="LIVE",
        manifest=json.loads(manifest.model_dump_json()),
        budget={
            "max_ocr_attempts": budget.max_ocr_attempts,
            "http_timeout_s": budget.http_timeout_s,
            "processing_deadline_s": budget.processing_deadline_s,
        },
    )

    files = _resolve_m0_inputs(input_dir)
    for kind in M0_CASES:
        path = files.get(kind)
        if path is None or not path.is_file():
            report.attempts.append(
                LiveAttempt(kind=kind, source=str(path), ok=False, used_ocr=False,
                            error="missing input file")
            )
            continue
        attempt, text = _run_case(kind, path, settings, budget)
        report.attempts.append(attempt)
        trace.record(
            TraceSpan(
                name=f"m0-live:{kind}",
                run_id=f"m0-live:{kind}:{int(time.time() * 1000)}",
                model=settings.mistral_ocr_model,
                basis=str(path),
                detail=attempt.error or "ok",
            ),
            payload={
                "kind": kind,
                "ok": attempt.ok,
                "used_ocr": attempt.used_ocr,
                "chars": attempt.chars,
                "error": attempt.error,
            },
        )
    return report
