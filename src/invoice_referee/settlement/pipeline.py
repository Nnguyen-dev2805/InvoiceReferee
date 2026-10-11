"""Settlement pipeline (W02/W03): orchestrate read → match → evaluate → report.

The Reader protocol lives in ``reader.py``. This module keeps orchestration
small: checkpoint guards between stages, per-source technical failures keep
partial output (recorded as TECHNICAL issues → INCOMPLETE report), run-level
failures (budget exhausted, Stop, superseded input) stop the run without
faking a result.
"""
from __future__ import annotations

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3_V1_KEYS, is_b3_v1
from invoice_referee.settlement.models import (
    Issue,
    Observation,
    Report,
    RunBudget,
    RunInput,
)
from invoice_referee.settlement.reader import Reader, is_per_source_error
from invoice_referee.settlement.rules import evaluate

REQUIRED_KEYS = {
    "B7": ["expense.", "payment.", "history.", "budget.", "relation"],
    "B3": ["advance.request", "forecast.", "history.advance.", "budget."],
}


def _technical_issue(source_id: str | None, error: DomainError,
                     index: int) -> Issue:
    return Issue(
        issue_id=f"I-TECH-{index}",
        type="TECHNICAL",
        owner="ACCOUNTANT",
        message=(f"Nguồn {source_id} không đọc/ghép được ({error.code}): "
                 f"{error.message}"),
        refs=[source_id] if source_id else [],
        blocked="source",
        unresolved=True,
    )


def process(run_input: RunInput, reader: Reader, budget: RunBudget,
            checkpoint, run_id: str = "R-PIPELINE",
            linked_snapshot=None) -> Report:
    """Run one job over the snapshot; checkpoint guards Stop/revision/epoch.

    For a linked B7 child, ``linked_snapshot`` supplies Python-derived
    observations/relations from the persisted context source (no LLM re-read);
    employee originals still flow through the Reader/matcher.
    """
    b3_v1 = is_b3_v1(run_input.submission.form)
    keys = (B3_V1_KEYS if b3_v1
            else REQUIRED_KEYS.get(run_input.submission.job, []))
    checkpoint("reading")
    observations: list[Observation] = []
    technical: list[Issue] = []
    for source in sorted(run_input.sources, key=lambda s: s.id):
        try:
            observations.extend(reader.read(source, keys, budget))
        except DomainError as error:
            if not is_per_source_error(error.code):
                raise
            technical.append(_technical_issue(source.id, error,
                                              len(technical) + 1))
    checkpoint("matching")
    relations = []
    # B3 v1 không gọi generic payment matcher B7; quan hệ đề nghị↔dự toán do
    # proposal evaluator dựng từ facts có nguồn (plan §2.4).
    if not b3_v1:
        try:
            relations = reader.match(run_input, observations, budget)
        except DomainError as error:
            if not is_per_source_error(error.code):
                raise
            technical.append(_technical_issue(None, error, len(technical) + 1))
    if linked_snapshot is not None:
        # Company context facts come from typed persisted records, not the LLM.
        from invoice_referee.settlement.b7_linked import (
            linked_context_observations,
        )
        ctx_obs, ctx_rel, ctx_issues = linked_context_observations(
            linked_snapshot, f"linkedctx:{linked_snapshot.origin_case_id}")
        observations = list(ctx_obs) + observations
        relations = list(ctx_rel) + relations
        technical = list(ctx_issues) + technical
    checkpoint("evaluating")
    report = evaluate(run_input, observations, relations, run_id=run_id,
                      mode=reader.mode, technical_issues=technical)
    checkpoint("publishing")
    return report
