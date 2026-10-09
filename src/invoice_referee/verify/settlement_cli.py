"""Settlement Verify CLI (W06): baseline measurement over the real Service.

Runs the development corpus sequentially through the same settlement
``Service`` the UI uses, compares against the packet's independent expected
files, and writes a frozen baseline artifact (SuiteReport JSON) under the
given output directory (default ``data/settlement/verify/``, Git-ignored).

Honesty rules:

- Exit code reflects whether the **measurement ran**, not whether cases PASS:
  a weak-but-truthful baseline is a successful measurement. Dataset/gate
  errors (hash mismatch, expected-as-input, live-mode author hints) exit 2.
- The mode is explicit: default fake reader proves the harness only; live
  provider runs need keys plus an author-hints-free dataset version.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from invoice_referee.api.settlement import DEMO_AUTHORITY, _reader_from_env
from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.evaluation import run_suite
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

DEFAULT_CORPUS = Path("docs/discovery/eval_development")
DEFAULT_OUT_DIR = Path("data/settlement/verify")


def build_service(db_path: Path, artifact_root: Path) -> Service:
    store = Store(db_path, artifact_root)
    reader = _reader_from_env(store.artifact_root)
    return Service(store, reader,
                   config=ServiceConfig(authority=DEMO_AUTHORITY))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m invoice_referee.verify.settlement_cli",
        description="Chạy settlement evaluation suite tuần tự qua Service thật.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS,
                        help="Thư mục corpus packets (mặc định development 20).")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="Nơi ghi artifact SuiteReport JSON.")
    parser.add_argument("--packets", type=str, default=None,
                        help="Danh sách case id phân cách phẩy (mặc định: tất cả).")
    parser.add_argument("--db-path", type=Path, default=None,
                        help="SQLite riêng của verify (mặc định trong out-dir).")
    parser.add_argument("--artifact-root", type=Path, default=None,
                        help="Artifact root riêng của verify.")
    args = parser.parse_args(argv)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.db_path or (out_dir / "verify.sqlite")
    artifact_root = args.artifact_root or (out_dir / "artifacts")
    packet_ids = ([part.strip() for part in args.packets.split(",") if part.strip()]
                  if args.packets else None)

    try:
        service = build_service(db_path, artifact_root)
        report = run_suite(args.corpus, service, packet_ids)
    except DomainError as error:
        print(f"DATASET_ERROR {error.code}: {error.message}", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = out_dir / f"settlement-verify-{stamp}.json"
    artifact.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1),
        encoding="utf-8")
    (out_dir / "latest.json").write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=1),
        encoding="utf-8")

    print(f"suite={report.suite} mode={report.mode}")
    print(f"source_hash={report.source_hash}")
    print(f"config_hash={report.config_hash}")
    for result in report.results:
        failed_axes = [c.axis for c in result.checks if not c.ok]
        print(f"{result.case_id} {result.job} {result.phase} "
              f"{result.verdict} run={result.run_status}"
              + (f" sai_axis={','.join(failed_axes)}" if failed_axes else ""))
    metrics = report.metrics
    print(f"metrics: n_routine={metrics['n_routine']} n_needs={metrics['n_needs']} "
          f"fn={metrics['fn']} fp={metrics['fp']} "
          f"u_routine={metrics['u_routine']} u_needs={metrics['u_needs']} "
          f"fn_interval={metrics['fn_interval']} "
          f"fp_interval={metrics['fp_interval']} "
          f"routine_completion={metrics['routine_completion']}")
    for note in report.notes:
        print(f"note: {note}")
    print(f"artifact: {artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
