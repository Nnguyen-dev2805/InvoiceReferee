"""T1 contract tests.

Covers the task's named behaviours (strict money, no aggregate value on
UNKNOWN/CONFLICT, evidence refs need a digest plus a locator, DTOs reject
unknown fields) and the T1 gate: the application accepts no expected/oracle
field, and tests/factories.snapshot() yields an AssessmentInput.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from invoice_referee.domain.common import EvidenceRef, Fact, KnownAmount

AS_OF = datetime(2026, 10, 13, 3, 0, tzinfo=UTC)

ORACLE_FIELD_NAMES = ("expected", "expected_amount", "latent", "oracle", "gold", "allowed")


def _ref(**overrides: object) -> EvidenceRef:
    base: dict[str, object] = {
        "source_id": "source:receipt-1",
        "source_sha256": "a" * 64,
        "page": 1,
        "exact_quote": "Tổng cộng 450.000",
    }
    return EvidenceRef(**{**base, **overrides})


def test_money_rejects_bool_float_and_currency() -> None:
    for value in (True, 1.25, "USD 3"):
        with pytest.raises(ValidationError):
            KnownAmount(value=value, currency="VND")
    with pytest.raises(ValidationError):
        KnownAmount(value=450_000, currency="USD")


def test_unknown_has_no_value() -> None:
    unknown = Fact[int](key="expense:incurred", state="UNKNOWN", refs=(_ref(),))
    assert unknown.value is None

    for state in ("UNKNOWN", "CONFLICT"):
        with pytest.raises(ValidationError):
            Fact[int](key="expense:incurred", value=5, state=state, refs=(_ref(),))

    with pytest.raises(ValidationError):
        Fact[int](key="expense:incurred", state="KNOWN", refs=(_ref(),))

    known = Fact[int](key="expense:incurred", value=5, state="KNOWN", refs=(_ref(),))
    assert known.value == 5


def test_ref_needs_digest_locator() -> None:
    with pytest.raises(ValidationError):
        _ref(source_sha256="")
    with pytest.raises(ValidationError):
        _ref(page=None)
    with pytest.raises(ValidationError):
        _ref(page=0)

    by_record_key = _ref(page=None, record_key="ledger:row-7")
    assert by_record_key.record_key == "ledger:row-7"
    assert _ref().page == 1


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        KnownAmount(value=1_000, currency="VND", amount=1_000)
    with pytest.raises(ValidationError):
        _ref(payer="employee:a")


def test_domain_dtos_reject_oracle_fields() -> None:
    for name in ORACLE_FIELD_NAMES:
        with pytest.raises(ValidationError):
            KnownAmount(**{"value": 1_000, "currency": "VND", name: 1_000})
        with pytest.raises(ValidationError):
            Fact[int](**{"key": "k", "state": "KNOWN", "value": 5, name: 5})
        with pytest.raises(ValidationError):
            _ref(**{name: "x"})


def test_no_domain_model_declares_oracle_fields() -> None:
    from invoice_referee.domain import case, commands, common, evidence, finance, issues, policy

    for module in (common, evidence, finance, policy, case, issues, commands):
        for name, obj in vars(module).items():
            fields = getattr(obj, "model_fields", None)
            if not isinstance(fields, dict) or not fields:
                continue
            overlap = set(fields) & set(ORACLE_FIELD_NAMES)
            assert not overlap, f"{module.__name__}.{name} declares {overlap}"


def test_snapshot_builds_assessment_input() -> None:
    from invoice_referee.domain.case import AssessmentInput
    from tests.factories import snapshot

    assessment = snapshot(
        T=10_000_000,
        E=5_000_000,
        C=3_000_000,
        A=2_000_000,
        P=0,
        R=0,
        B=8_000_000,
    )
    assert isinstance(assessment, AssessmentInput)
    assert assessment.coverage is not None
    assert assessment.coverage.ledger_version == "ledger:v1"
    assert assessment.expense_facts[0].incurred.value == 10_000_000

    uncovered = snapshot(
        T=0, E=0, C=0, A=0, P=0, R=0, B=8_000_000, coverage=False
    )
    assert uncovered.coverage is None
    assert uncovered.expense_facts[0].incurred.state == "UNKNOWN"


def test_cli_main_returns_int() -> None:
    from invoice_referee.cli import main

    assert main([]) == 0


def test_decision_amount_rejects_bool() -> None:
    from invoice_referee.domain.issues import DecisionCommand

    with pytest.raises(ValidationError):
        DecisionCommand(
            issue_ids=("issue:1",),
            basis_id="basis:1",
            actions=("RECOGNIZE_COST",),
            effect_scope="activity:travel-a",
            amount=True,
            reason="granted",
        )


def test_strict_models_reject_bool_where_int_expected() -> None:
    from invoice_referee.domain.case import ReadSet

    with pytest.raises(ValidationError):
        ReadSet(
            input_revision=True,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=1,
        )


def test_command_result_matches_contract_fields() -> None:
    from invoice_referee.domain.commands import CommandResult

    assert set(CommandResult.model_fields) == {
        "case_view",
        "job_id",
        "duplicate_command",
    }


def test_required_identity_fields_are_not_defaulted() -> None:
    from invoice_referee.domain.finance import Expense, MoneyEvent

    incurred = Fact[int](
        key="expense:1:incurred", value=1_000, state="KNOWN", refs=(_ref(),)
    )
    with pytest.raises(ValidationError):
        Expense(
            id="expense:1",
            activity="activity:travel-a",
            incurred=incurred,
            incurred_at=AS_OF,
            eligibility="ELIGIBLE",
        )
    with pytest.raises(ValidationError):
        MoneyEvent(
            id="event:1",
            kind="ADVANCE_RECEIVED",
            scope="activity:travel-a",
            payer="company:demo",
            payee="employee:a",
            amount=1_000,
            event_at=AS_OF,
            recorded_at=AS_OF,
            verification_state="CONFIRMED",
        )


def test_settings_live_ready_tracks_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    from invoice_referee.config import Settings

    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    assert settings.live_ready is False


def test_settings_report_missing_live_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    from invoice_referee.config import LIVE_REQUIRED_SETTINGS, Settings

    for name in LIVE_REQUIRED_SETTINGS:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)
    assert settings.mistral_api_key is None
    assert set(settings.missing_for_live()) == set(LIVE_REQUIRED_SETTINGS)
