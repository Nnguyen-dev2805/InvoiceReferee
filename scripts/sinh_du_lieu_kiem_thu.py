"""R1 entry: generate the 15-case test corpus (plan R1/D).

Usage:
    uv run python scripts/sinh_du_lieu_kiem_thu.py --output data/kiem-thu --cases all --replace-generated
    uv run python scripts/sinh_du_lieu_kiem_thu.py --output data/kiem-thu --check

Four behaviours, kept explicit: --output, --cases all|01,02,..., --check
(read-only validation), --replace-generated. No provider/model calls. The
output must be a dedicated directory (refuses /, repo root, data root, symlink
targets, and non-empty unmanaged targets).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from du_lieu_kiem_thu import dap_an  # noqa: E402
from du_lieu_kiem_thu.ho_so import (  # noqa: E402
    CASE_IDS,
    CASES,
    CaseSpec,
    build_case,
)

MANAGED_MARKER = ".invoice-referee-managed"


def _select(cases: str) -> list[CaseSpec]:
    if cases == "all":
        return list(CASES)
    wanted = {f"D{part.strip().zfill(2)}" for part in cases.split(",") if part.strip()}
    chosen = [c for c in CASES if c.case_id in wanted]
    missing = wanted - {c.case_id for c in chosen}
    if missing:
        raise SystemExit(f"unknown case ids: {sorted(missing)}")
    return chosen


def _guard_output(output: Path) -> None:
    resolved = output.resolve()
    forbidden = {Path("/").resolve(), PROJECT_ROOT.resolve(), (PROJECT_ROOT / "data").resolve()}
    if resolved in forbidden:
        raise SystemExit(f"refusing to write the corpus into {resolved}")
    if output.is_symlink():
        raise SystemExit(f"output must not be a symlink: {output}")
    if output.exists() and any(output.iterdir()):
        if not (output / MANAGED_MARKER).is_file():
            raise SystemExit(
                f"{output} is non-empty and not managed by this generator; refusing to overwrite"
            )


def _generate(output: Path, specs: list[CaseSpec]) -> None:
    _guard_output(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / MANAGED_MARKER).write_text("managed by sinh_du_lieu_kiem_thu.py\n", encoding="utf-8")
    entries = []
    for spec in specs:
        entry = build_case(spec, output)
        entries.append(json.loads(entry.model_dump_json()))
    manifest = {
        "dataset": "invoice-referee-kiem-thu",
        "schema_version": 1,
        "data_version": 1,
        "count": len(entries),
        "entries": entries,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"generated {len(entries)} cases -> {output}")


def _check(output: Path) -> int:
    """Read-only validation; nonzero on invalid/missing/stale."""
    if not (output / MANAGED_MARKER).is_file():
        print(f"not a managed dataset: {output}", file=sys.stderr)
        return 2
    problems: list[str] = []
    for spec in CASES:
        case_dir = output / spec.slug
        if not case_dir.is_dir():
            problems.append(f"missing case dir: {spec.slug}")
            continue
        if not (case_dir / "dap-an" / "ket-qua-hop-le.json").is_file():
            problems.append(f"missing gold: {spec.slug}")
        if not any((case_dir / "dau-vao" / "01-nop-ban-dau").glob("*.pdf")):
            problems.append(f"missing initial source: {spec.slug}")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"ok: {len(CASES)} cases valid in {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the InvoiceReferee test corpus")
    parser.add_argument("--output", required=True)
    parser.add_argument("--cases", default="all")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output)
    if args.check:
        return _check(output)

    specs = _select(args.cases)
    if output.exists() and any(output.iterdir()) and not args.replace_generated:
        raise SystemExit(
            f"{output} already exists; pass --replace-generated to overwrite"
        )
    if args.replace_generated and output.exists() and (output / MANAGED_MARKER).is_file():
        shutil.rmtree(output)
    _generate(output, specs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
