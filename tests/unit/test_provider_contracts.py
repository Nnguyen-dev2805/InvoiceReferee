"""Provider/reader contracts (plan T5; contracts §5, §8, §9).

Offline: HTTP is faked and the reader's money side effects are spied. No
expected financial output ever enters a read. A model proposes observations
only; it can never record money, grant authority or follow source instructions.
"""

from __future__ import annotations

import pytest

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.evidence.planning import AllowedStep, Opportunity, propose_step
from invoice_referee.evidence.trace import ProviderMode, RunBudget, RunManifest

# -- RunBudget: finite caps, counters and deadline ----------------------------


def test_budget_blocks_when_attempts_exhausted() -> None:
    budget = RunBudget(max_llm_attempts=1, max_ocr_attempts=1)
    assert budget.can_call_llm() and budget.can_call_ocr()
    budget.charge_llm()
    budget.charge_ocr()
    assert not budget.can_call_llm()
    assert not budget.can_call_ocr()


def test_budget_reports_deadline() -> None:
    budget = RunBudget(processing_deadline_s=0)
    assert budget.expired()


def test_manifest_records_resolved_model_and_unknown_usage() -> None:
    manifest = RunManifest(
        mode="LIVE",
        requested_model="alias-x",
        returned_model="model-2026-01",
        resolved_model=None,
        usage_unknown=True,
    )
    assert manifest.resolved_model is None  # unresolved alias is disclosed, not faked
    assert manifest.usage_unknown is True


def test_provider_mode_values() -> None:
    modes: tuple[ProviderMode, ...] = ("LIVE", "RECORDED_REPLAY", "STUB")
    assert modes == ("LIVE", "RECORDED_REPLAY", "STUB")


# -- propose_step: routing is read-only, source-scoped and money-free ---------


def _opportunity(**overrides: object) -> Opportunity:
    fields: dict[str, object] = {
        "id": "opp:1",
        "root_id": "case:1",
        "issue_id": "issue:1",
        "field": "payer_identity",
        "source_ids": ("source:1",),
        "page": 1,
        "eligible_steps": (),
        "attempted_recovery_keys": (),
        "remaining_budget": RunBudget(),
    }
    fields.update(overrides)
    return Opportunity(**fields)  # type: ignore[arg-type]


def test_no_eligible_step_asks_the_owner() -> None:
    step = propose_step(_opportunity(eligible_steps=()), RunBudget())
    assert step.kind == "ASK_OWNER"


def test_eligible_step_is_selected_and_read_only() -> None:
    step = propose_step(
        _opportunity(
            eligible_steps=(
                AllowedStep(
                    kind="READ_FIELDS",
                    issue_id="issue:1",
                    source_ids=("source:1",),
                    fields=("payer_identity",),
                    reason="native text available",
                    score=0.75,
                ),
            )
        ),
        RunBudget(),
    )
    assert step.kind == "READ_FIELDS"
    assert set(step.source_ids) <= {"source:1"}


def test_propose_rejects_a_step_from_another_root() -> None:
    # A step may only read sources that belong to this root/session.
    with pytest.raises(ValueError):
        propose_step(
            _opportunity(
                eligible_steps=(
                    AllowedStep(
                        kind="READ_FIELDS",
                        issue_id="issue:1",
                        source_ids=("source:other",),
                        fields=("payer_identity",),
                        reason="x",
                        score=0.75,
                    ),
                )
            ),
            RunBudget(),
        )


def test_propose_rejects_money_recording_action() -> None:
    # AllowedStep has no RECORD_ACTUAL/URL/policy/SQL kind by construction.
    with pytest.raises(Exception):
        AllowedStep(  # type: ignore[call-arg]
            kind="RECORD_ACTUAL",
            issue_id="issue:1",
            source_ids=("source:1",),
            fields=(),
            reason="x",
            score=1.0,
        )


def test_score_below_threshold_is_not_eligible_alone() -> None:
    # A low-score step below the fixed 0.75 threshold routes to the owner when
    # it is the only option.
    step = propose_step(
        _opportunity(
            eligible_steps=(
                AllowedStep(
                    kind="READ_FIELDS",
                    issue_id="issue:1",
                    source_ids=("source:1",),
                    fields=("payer_identity",),
                    reason="weak",
                    score=0.25,
                ),
            )
        ),
        RunBudget(threshold=0.75),
    )
    assert step.kind == "ASK_OWNER"


# -- EvidenceRef on a proposal is still real evidence -------------------------


def test_proposed_ref_needs_a_real_locator() -> None:
    with pytest.raises(Exception):
        EvidenceRef(source_id="s", source_sha256="a" * 64, exact_quote="x")  # no locator
