"""Coverage validity and the assessment clock (contracts §3; plan A3).

A coverage OBJECT is not a valid coverage. It is valid only when it names the
scope (employee/activity), covers the assessment time, lists the fund set and
flow kinds, states an opening balance and carries witness refs. A stale or
incomplete coverage must not establish a zero A/P/R or an instruction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from invoice_referee.domain.case import CaseScope
from invoice_referee.domain.finance import CoverageRecord
from invoice_referee.reconciliation.admission import coverage_is_valid

SCOPE = CaseScope(
    tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL"
)


def _ref():
    from invoice_referee.domain.common import EvidenceRef

    return EvidenceRef(source_id="s", source_sha256="a" * 64, page=1, exact_quote="x")


def _coverage(**overrides) -> CoverageRecord:
    from invoice_referee.domain.common import Fact

    fields = {
        "scope": "activity:1",
        "start": datetime(2026, 9, 1, tzinfo=UTC),
        "as_of": datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
        "funds": ("company:bank",),
        "flow_kinds": ("ADVANCE_RECEIVED", "EMPLOYEE_RETURN"),
        "opening_balance": Fact[int](key="coverage:opening", value=0, state="KNOWN", refs=(_ref(),)),
        "ledger_version": "ledger:v1",
        "witness_refs": (_ref(),),
    }
    fields.update(overrides)
    return CoverageRecord(**fields)


def test_complete_coverage_is_valid_at_its_as_of() -> None:
    cov = _coverage(witness_refs=(_ref(),))
    assert coverage_is_valid(cov, scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC))


def test_stale_coverage_is_invalid_for_a_later_decision() -> None:
    # Coverage only through 10/10 must not decide a 14/10 assessment.
    cov = _coverage(witness_refs=(_ref(),))
    assert not coverage_is_valid(cov, scope=SCOPE, as_of=datetime(2026, 10, 14, 11, 0, tzinfo=UTC))


def test_coverage_without_witness_is_invalid() -> None:
    assert not coverage_is_valid(
        _coverage(witness_refs=()), scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC)
    )


def test_coverage_without_funds_is_invalid() -> None:
    assert not coverage_is_valid(
        _coverage(funds=(), witness_refs=(_ref(),)),
        scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )


def test_coverage_without_flow_kinds_is_invalid() -> None:
    assert not coverage_is_valid(
        _coverage(flow_kinds=(), witness_refs=(_ref(),)),
        scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )


def test_coverage_without_opening_balance_is_invalid() -> None:
    assert not coverage_is_valid(
        _coverage(opening_balance=None, witness_refs=(_ref(),)),
        scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )


def test_coverage_with_wrong_scope_is_invalid() -> None:
    assert not coverage_is_valid(
        _coverage(scope="activity:other", witness_refs=(_ref(),)),
        scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )


def test_missing_coverage_is_invalid() -> None:
    assert not coverage_is_valid(None, scope=SCOPE, as_of=datetime(2026, 10, 10, 11, 0, tzinfo=UTC))
