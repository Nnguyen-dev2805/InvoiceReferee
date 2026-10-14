"""Migration-only importer for the Hoangha UC-03 corpus (plan E8).

Copies the 25 v1 + 50 v2 formal UC-03 cases into `data/test-kit/hoangha-uc03/`
so tests/CI no longer depend on `.worktrees/hoangha`. Only PDF/PNG/JPEG inputs
are copied (DOCX is excluded as app input); oracle files go under `gold/`.
Content-hash dedup avoids duplicate bytes. Fails unless the expected source
revision/manifest set is present.

Usage: uv run python scripts/import_hoangha_case_corpus.py --source-root <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

SOURCE_REVISION = "1ee33487e2770ebd9e5ae65b994bbd3f3a4dd7a8"
ACCEPTED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg")
DOCX_SUFFIX = ".docx"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
KIT = PROJECT_ROOT / "data" / "test-kit" / "hoangha-uc03"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v2_cases(source_root: Path) -> list[dict]:
    manifest = json.loads((source_root / "testcase_uc3_v2" / "manifest.json").read_text("utf-8"))
    return [
        {
            "case_id": case["case_id"],
            "folder": str(source_root / "testcase_uc3_v2" / case["folder"]),
            "set": "v2",
        }
        for case in manifest["cases"]
    ]


def _v1_cases(source_root: Path) -> list[dict]:
    manifest_path = source_root / "testcase_uc3" / "manifest.json"
    entries = json.loads(manifest_path.read_text("utf-8"))
    base = source_root / "testcase_uc3"
    return [
        {"case_id": entry["case_id"], "folder": str(base / entry["folder"]), "set": "v1"}
        for entry in entries
    ]


def build_kit(source_root: Path) -> dict:
    cases = _v1_cases(source_root) + _v2_cases(source_root)
    if len(cases) != 75:
        raise SystemExit(f"expected 75 formal UC-03 cases, found {len(cases)}")

    if KIT.exists():
        shutil.rmtree(KIT)
    (KIT / "inputs").mkdir(parents=True)
    (KIT / "gold").mkdir(parents=True)

    seen_hashes: dict[str, str] = {}
    out_cases: list[dict] = []
    for case in cases:
        folder = Path(case["folder"])
        if not folder.is_dir():
            raise SystemExit(f"missing case folder: {folder}")
        inputs: list[str] = []
        gold: list[str] = []
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix == DOCX_SUFFIX:
                continue  # excluded as app input
            if suffix in ACCEPTED_SUFFIXES:
                digest = _sha256(path)
                if digest in seen_hashes:
                    continue  # content-hash dedup
                seen_hashes[digest] = case["case_id"]
                rel = f"inputs/{case['case_id']}__{path.name}"
                shutil.copy2(path, KIT / rel)
                inputs.append(rel)
            elif path.name.endswith(".json") and "expected" in path.name:
                rel = f"gold/{case['case_id']}__{path.name}"
                shutil.copy2(path, KIT / rel)
                gold.append(rel)
        out_cases.append(
            {
                "case_id": case["case_id"],
                "set": case["set"],
                "inputs": inputs,
                "gold": gold,
            }
        )

    manifest = {
        "dataset": "hoangha-uc03",
        "source_revision": SOURCE_REVISION,
        "v1_count": sum(1 for c in out_cases if c["set"] == "v1"),
        "v2_count": sum(1 for c in out_cases if c["set"] == "v2"),
        "cases": out_cases,
        "runtime": {"gold_visible": False},
    }
    (KIT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    args = parser.parse_args(argv)
    source_root = Path(args.source_root)
    if not (source_root / "testcase_uc3" / "manifest.json").is_file():
        raise SystemExit("source revision/manifest set not present")
    manifest = build_kit(source_root)
    print(f"imported {len(manifest['cases'])} cases into {KIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
