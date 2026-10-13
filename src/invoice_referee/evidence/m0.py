"""M0 baseline harness (contracts §5, §8, §9; plan T5).

Runs four packet types — text PDF, clear scan, unclear scan, non-document —
against the available reader with finite ceilings, and writes a manifest of
every attempt, error, source-support verdict, usage and timing. A model alias
that cannot be resolved is disclosed, never faked. This harness makes no
business decision; it measures the reader.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from invoice_referee.domain.common import UtcDatetime
from invoice_referee.evidence.trace import ProviderMode, RunBudget, RunManifest

M0_KINDS = ("text", "clear_scan", "unclear_scan", "non_document")


@dataclass
class M0Attempt:
    kind: str
    source: str
    page: int
    ok: bool
    error: str | None = None
    elapsed_ms: float = 0.0
    usage: dict[str, object] = field(default_factory=dict)


@dataclass
class M0Report:
    mode: ProviderMode
    budget: RunBudget
    manifest: RunManifest
    attempts: list[M0Attempt] = field(default_factory=list)
    started_at: UtcDatetime | None = None
    ended_at: UtcDatetime | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "budget": asdict(self.budget) | {"started_at": None},
                "manifest": json.loads(self.manifest.model_dump_json()),
                "attempts": [asdict(attempt) for attempt in self.attempts],
            },
            ensure_ascii=False,
            indent=2,
        )


def measure_call(kind: str, source: str, page: int, call) -> M0Attempt:
    """Time one provider call and capture its error honestly."""
    start = time.monotonic()
    try:
        call()
        ok, error = True, None
    except Exception as exc:  # provider/technical failure is recorded, not hidden
        ok, error = False, f"{type(exc).__name__}: {exc}"
    return M0Attempt(
        kind=kind,
        source=source,
        page=page,
        ok=ok,
        error=error,
        elapsed_ms=(time.monotonic() - start) * 1000,
    )


def write_m0_report(report: M0Report, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / "m0-manifest.json"
    path.write_text(report.to_json(), encoding="utf-8")
    return path
