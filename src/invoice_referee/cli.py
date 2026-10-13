"""Package entry point (contracts §9): main(argv: list[str]) -> int.

Subcommands:
  m0 --input <packet-dir> --output <dir> [--mode stub|replay|live]

`m0` measures the reader over four packet types and writes a manifest. It is a
technical baseline, not a business decision; missing credentials fail with the
named gap instead of silently degrading.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.evidence.m0 import M0Report, measure_call, write_m0_report
from invoice_referee.evidence.trace import (
    ProviderMode,
    RunBudget,
    RunManifest,
    TraceSpan,
    build_trace,
)


def _run_m0(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="invoice-referee m0")
    parser.add_argument("--input", required=True, help="packet or dataset directory")
    parser.add_argument("--output", required=True, help="where to write the manifest")
    parser.add_argument("--mode", choices=("stub", "replay", "live"), default="stub")
    args = parser.parse_args(argv)

    mode: ProviderMode = args.mode.upper()  # type: ignore[assignment]
    settings = Settings()
    if mode == "LIVE" and settings.missing_for_live():
        print(
            "M0 LIVE thiếu cấu hình: " + ", ".join(settings.missing_for_live()),
            file=sys.stderr,
        )
        return 2

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"input không tồn tại: {input_dir}", file=sys.stderr)
        return 2

    if mode == "LIVE":
        # Real provider run: measure the reader over the 4 M0 inputs.
        from invoice_referee.evidence.m0_live import run_m0_live

        live = run_m0_live(input_dir, settings)
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "m0-manifest.json"
        path.write_text(live.to_json(), encoding="utf-8")
        print(f"M0 LIVE report written: {path}")
        return 0

    budget = RunBudget()
    manifest = RunManifest(
        mode=mode,
        requested_model=settings.mistral_ocr_model,
        returned_model=None,
        resolved_model=None if mode == "LIVE" else settings.mistral_ocr_model,
        usage_unknown=mode == "LIVE",
        notes="M0 baseline; no business decision.",
    )
    report = M0Report(mode=mode, budget=budget, manifest=manifest)
    trace = build_trace(settings)

    # Non-LIVE modes make no provider call; record that honestly rather than a
    # fake attempt. Spans carry run/basis/prompt/model; the payload is filtered
    # before send and the local audit never depends on telemetry (§9).
    for kind in ("text", "clear_scan", "unclear_scan", "non_document"):
        attempt = measure_call(kind, source=str(input_dir), page=1, call=lambda: None)
        report.attempts.append(attempt)
        trace.record(
            TraceSpan(
                name=f"m0:{kind}",
                run_id=f"m0:{mode}:{kind}",
                model=settings.mistral_ocr_model,
                basis=str(input_dir),
                detail=attempt.error or "ok",
            ),
            payload={"kind": kind, "ok": attempt.ok, "error": attempt.error},
        )

    path = write_m0_report(report, Path(args.output))
    print(f"M0 report written: {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Returns a process exit status.

    `argv` defaults to the process arguments so the console entry point
    (`invoice-referee`) works when invoked with no explicit list.
    """
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "m0":
        return _run_m0(argv[1:])
    if not argv:
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 2
