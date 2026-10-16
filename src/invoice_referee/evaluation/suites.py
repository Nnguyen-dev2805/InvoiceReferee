"""Named evaluation suites over the corpus (contracts §7; plan T9/R7).

`core` and `escalation` are the fixed selections the plan names; `development`
is every case. Selection picks the case directories from the dataset manifest
(case_id -> slug), so it works with both the R1 corpus layout and the locked
data/verify benchmark layout.
"""

from __future__ import annotations

import json
from pathlib import Path

# Legacy corpus suites (for backward compatibility with legacy tests and R1 corpus)
CORE: tuple[str, ...] = ("D01", "D02", "D03", "D11")
ESCALATION: tuple[str, ...] = ("D01", "D02", "D03", "D04", "D07")

# Locked benchmark suites (VERIFY_SCORER_AGENT_PROMPT.md §3):
# Core4: 4 cases sequential (TC01, TC02, VFY-BAL-01, TC06)
VERIFY_CORE: tuple[str, ...] = ("TC01", "TC02", "VFY-BAL-01", "TC06")
# Escalation5: 5 cases, 3 routine + 2 human-required (TC01, TC02, VFY-BAL-01, TC06, TC04)
VERIFY_ESCALATION: tuple[str, ...] = ("TC01", "TC02", "VFY-BAL-01", "TC06", "TC04")

SUITE_MEMBERS: dict[str, tuple[str, ...]] = {
    "core": CORE,
    "escalation": ESCALATION,
    "verify_core": VERIFY_CORE,
    "verify_escalation": VERIFY_ESCALATION,
}


def _manifest_map(dataset_dir: Path) -> dict[str, str]:
    """case_id -> slug from the dataset manifest (empty when absent)."""
    manifest = dataset_dir / "manifest.json"
    if not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return {entry["root_id"]: _slug_for(dataset_dir, entry) for entry in data.get("entries", [])}


def _slug_for(dataset_dir: Path, entry: dict[str, object]) -> str:
    root_id = str(entry.get("root_id"))
    base = dataset_dir / "cases" if (dataset_dir / "cases").is_dir() else dataset_dir
    for path in base.iterdir():
        if not path.is_dir():
            continue
        case_file = path / "cau-hinh" / "kich-ban.json"
        if case_file.is_file():
            kich_ban = json.loads(case_file.read_text(encoding="utf-8"))
            if kich_ban.get("case_id") == root_id:
                return path.name
    return root_id


def select_suite(suite: str, dataset_dir: Path) -> list[Path]:
    """The case directories for `suite` under `dataset_dir`.

    `development` is every case directory; `core`/`escalation` are the fixed
    members (a member missing on disk is skipped, never silently swapped).
    """
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        return []
    base_dirs = dataset_dir / "cases" if (dataset_dir / "cases").is_dir() else dataset_dir
    case_dirs = sorted(
        p for p in base_dirs.iterdir() if p.is_dir() and (p / "cau-hinh").is_dir()
    )
    if suite == "development":
        return case_dirs

    by_id = {cid: path for path in case_dirs for cid in _case_ids(path)}
    # Choose mapping based on dataset membership
    if any(k in by_id for k in VERIFY_CORE):
        members_map = {"core": VERIFY_CORE, "escalation": VERIFY_ESCALATION}
    else:
        members_map = {"core": CORE, "escalation": ESCALATION}

    members = members_map.get(suite, SUITE_MEMBERS.get(suite))
    if members is None:
        raise ValueError(f"unknown suite: {suite}")
    return [by_id[cid] for cid in members if cid in by_id]


def _case_ids(case_dir: Path) -> tuple[str, ...]:
    kich_ban = case_dir / "cau-hinh" / "kich-ban.json"
    if kich_ban.is_file():
        cid = json.loads(kich_ban.read_text(encoding="utf-8")).get("case_id")
        return (cid,) if cid else ()
    return ()
