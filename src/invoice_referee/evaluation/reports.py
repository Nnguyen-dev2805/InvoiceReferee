"""Suite reports and baselines (contracts §7, §8).

A SuiteReport keeps every actual result (including failures) so a run is never
prettified by dropping failures. Mode and timing are recorded, not assumed.
"""

from __future__ import annotations

import json
from pathlib import Path

from invoice_referee.domain.common import StrictModel
from invoice_referee.evaluation.scorer import ActualResult, ScoreRow


class SuiteReport(StrictModel):
    """The raw outcome of one suite run (before any scoring)."""

    suite: str
    mode: str
    total: int
    actuals: tuple[ActualResult, ...] = ()
    technical_failures: int = 0

    def with_scores(self, rows: list[ScoreRow]) -> "ScoredSuiteReport":
        return ScoredSuiteReport(report=self, rows=tuple(rows))


class ScoredSuiteReport(StrictModel):
    report: SuiteReport
    rows: tuple[ScoreRow, ...] = ()

    @property
    def union_dangerous_miss(self) -> int:
        return sum(row.union_dangerous_miss for row in self.rows)

    @property
    def correct_auto_completion(self) -> int:
        return sum(row.correct_auto_completion for row in self.rows)


def write_report(report: SuiteReport | ScoredSuiteReport, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{report.suite if isinstance(report, SuiteReport) else report.report.suite}-report.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
