"""Named evaluation suites over the development dataset (contracts §7; plan T9).

`core` and `escalation` are fixed, small selections the plan names; `development`
is the whole development split. Selecting a suite picks the packet directories;
it never changes how a packet is run or scored.
"""

from __future__ import annotations

from pathlib import Path

# Core4: varied routine roots (CHI, THU, a balanced zero, and a personal/no-
# advance rejection) that exercise the whole money model without human input.
CORE: tuple[str, ...] = (
    "dev-clean-chi",
    "dev-clean-thu",
    "dev-balanced",
    "dev-personal",
)

# Escalation5: 3 auto + 2 human-required, covering the three escalation routes.
ESCALATION: tuple[str, ...] = (
    "dev-supplementary",   # auto, multi-source
    "dev-mixed-pdf",       # auto, scanned source
    "dev-clean-thu",       # auto, COLLECT direction
    "dev-payer-unknown",   # FACT
    "dev-over-budget",     # POLICY
)

SUITE_MEMBERS: dict[str, tuple[str, ...]] = {
    "core": CORE,
    "escalation": ESCALATION,
}


def select_suite(suite: str, dataset_dir: Path) -> list[Path]:
    """The packet directories for `suite` under `dataset_dir`.

    `development` is every packet directory; `core`/`escalation` are the fixed
    members above (a member missing on disk is skipped, never silently swapped).
    """
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        return []
    if suite == "development":
        return sorted(p for p in dataset_dir.iterdir() if p.is_dir())
    members = SUITE_MEMBERS.get(suite)
    if members is None:
        raise ValueError(f"unknown suite: {suite}")
    return [dataset_dir / name for name in members if (dataset_dir / name).is_dir()]
