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
from invoice_referee.evidence.trace import ProviderMode, RunBudget, RunManifest


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

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"input không tồn tại: {input_dir}", file=sys.stderr)
        return 2

    # In non-LIVE modes there is no provider call; record that honestly rather
    # than a fake attempt.
    for kind in ("text", "clear_scan", "unclear_scan", "non_document"):
        report.attempts.append(
            measure_call(
                kind,
                source=str(input_dir),
                page=1,
                call=lambda: None if mode != "LIVE" else _require_provider(),
            )
        )

    path = write_m0_report(report, Path(args.output))
    print(f"M0 report written: {path}")
    return 0


def _require_provider() -> None:
    raise RuntimeError("LIVE provider not wired in this build step")


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
