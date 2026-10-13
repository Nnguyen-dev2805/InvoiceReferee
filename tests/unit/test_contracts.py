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


# -- datetime boundary: aware, ISO-8601 JSON, normalized UTC (contracts §1) -----


def test_timestamp_fields_normalize_to_utc() -> None:
    from datetime import timedelta, timezone

    from invoice_referee.domain.policy import Grant

    tz7 = datetime(2026, 10, 13, 10, 0, tzinfo=timezone(timedelta(hours=7)))
    grant = Grant(
        id="grant:1",
        version="v1",
        actor="employee:a",
        actions=("RECOGNIZE_COST",),
        scope="activity:travel-a",
        max_amount=1_000,
        effective_from=tz7,
    )
    assert grant.effective_from == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
    assert grant.effective_from.utcoffset() == timedelta(0)


def test_naive_timestamp_is_rejected() -> None:
    from invoice_referee.domain.finance import Expense

    with pytest.raises(ValidationError):
        Expense(
            id="expense:1",
            economic_key="invoice:1",
            activity="activity:travel-a",
            incurred=Fact[int](key="expense:1:incurred", value=1, state="KNOWN"),
            incurred_at=datetime(2026, 1, 1),
            eligibility="ELIGIBLE",
        )


def test_iso8601_json_datetime_accepted_at_domain_boundary() -> None:
    from invoice_referee.domain.commands import CreateDraft

    payload = (
        '{"activity_data": {"activity_id": "a", "name": "n", '
        '"occurred_at": "2026-10-13T03:00:00Z", "declared_purpose": "p"}}'
    )
    assert CreateDraft.model_validate_json(payload).activity_data.occurred_at == datetime(
        2026, 10, 13, 3, 0, tzinfo=UTC
    )
    # FastAPI parses a JSON body into a python dict before model validation, so
    # the python-mode path must accept the same ISO-8601 string.
    as_dict = CreateDraft.model_validate(
        {
            "activity_data": {
                "activity_id": "a",
                "name": "n",
                "occurred_at": "2026-10-13T03:00:00Z",
                "declared_purpose": "p",
            }
        }
    )
    assert as_dict.activity_data.occurred_at == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)


# -- EvidenceRef must carry a real digest, quote and locator (T1 gate) ---------


def test_evidence_ref_requires_real_digest_quote_and_locator() -> None:
    good = _ref(source_sha256="a" * 64, page=1, exact_quote="Tổng cộng 450.000")
    assert good.source_sha256 == "a" * 64

    for bad in (
        {"source_sha256": "x"},  # not 64 hex chars
        {"source_sha256": "g" * 64},  # 64 chars but not hex
        {"source_sha256": "A" * 64},  # uppercase hex is not canonical sha256
        {"exact_quote": ""},  # blank quote
        {"exact_quote": "   "},  # whitespace-only quote
        {"page": None, "record_key": ""},  # empty record key is no locator
        {"page": None, "record_key": "   "},  # whitespace-only record key
    ):
        with pytest.raises(ValidationError):
            _ref(**bad)


# -- Instruction money invariants (contracts §4) -------------------------------


def test_instruction_remaining_matches_amount_minus_fulfilled() -> None:
    from invoice_referee.domain.case import Instruction

    good = Instruction(
        id="instruction:1",
        root_id="case:1",
        direction="PAY",
        amount=10,
        status="PARTIAL",
        basis="basis:1",
        fulfilled_amount=2,
        remaining=8,
        execution_state="OPEN",
    )
    assert good.remaining == 8

    with pytest.raises(ValidationError):  # remaining must equal amount - fulfilled
        Instruction(
            id="instruction:1",
            root_id="case:1",
            direction="PAY",
            amount=10,
            status="PARTIAL",
            basis="basis:1",
            fulfilled_amount=2,
            remaining=999,
            execution_state="OPEN",
        )
    with pytest.raises(ValidationError):  # fulfilled cannot exceed amount
        Instruction(
            id="instruction:1",
            root_id="case:1",
            direction="PAY",
            amount=4,
            status="PARTIAL",
            basis="basis:1",
            fulfilled_amount=10,
            remaining=0,
            execution_state="OPEN",
        )


# -- MarkExecution may not reset an instruction to NOT_STARTED (contracts §9) ---


def test_mark_execution_rejects_not_started() -> None:
    from invoice_referee.domain.commands import MarkExecution

    for state in ("OPEN", "CLOSED_CONFIRMED", "UNKNOWN"):
        MarkExecution(
            root_id="case:1", instruction_id="instruction:1", execution_state=state, reason="x"
        )
    with pytest.raises(ValidationError):
        MarkExecution(
            root_id="case:1",
            instruction_id="instruction:1",
            execution_state="NOT_STARTED",
            reason="reset",
        )


# -- latent traps: bare Fact, page_range order --------------------------------


def test_bare_fact_rejects_untyped_value() -> None:
    for value in (True, 1.25, "x"):
        with pytest.raises(ValidationError):
            Fact(key="k", value=value, state="KNOWN")


def test_evidence_unit_page_range_is_ordered_and_1_based() -> None:
    from invoice_referee.domain.evidence import EvidenceUnit

    EvidenceUnit(source="source:1", page_range=(1, 3), role="INVOICE")
    EvidenceUnit(source="source:1", page_range=(2, 2), role="INVOICE")
    for bad in ((5, 2), (0, 1)):
        with pytest.raises(ValidationError):
            EvidenceUnit(source="source:1", page_range=bad, role="INVOICE")


# -- test-helper honesty and the CLI entry point -------------------------------


def test_snapshot_rejects_negative_amounts() -> None:
    from tests.factories import snapshot

    for field in ("T", "E", "C", "A", "P", "R", "B"):
        kwargs: dict[str, int] = {
            "T": 0,
            "E": 0,
            "C": 0,
            "A": 0,
            "P": 0,
            "R": 0,
            "B": 8_000_000,
        }
        kwargs[field] = -1
        with pytest.raises(ValueError):
            snapshot(**kwargs)  # type: ignore[arg-type]


def test_package_declares_console_entry_point() -> None:
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["invoice-referee"] == "invoice_referee.cli:main"
