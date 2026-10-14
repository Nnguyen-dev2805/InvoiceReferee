"""A0 admission/basis contract tests (plan A0, contracts §12/§3; ADR0007).

Freezes the money-confirmation basis vocabulary and the per-expense employee
paid-claim DTO. Money is strict integer VND; a client may state a claim but not
supply the actor/verifier/known state the server owns.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from invoice_referee.domain.case import AssessmentInput, CaseScope, ReadSet
from invoice_referee.domain.commands import EmployeePaidClaim, Submit
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.finance import ExpensePayment, PaymentBasisKind, PaymentBasisView
from invoice_referee.evidence.document_profiles import DOCUMENT_PROFILES

SHA = "a" * 64


def _ref() -> EvidenceRef:
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote="3.240.000 đ")


def _scope() -> CaseScope:
    return CaseScope(tenant="tenant:demo", employee="employee:a", activity="activity:1", profile="TRAVEL")


def _read_set() -> ReadSet:
    return ReadSet(
        input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0
    )


# --- money is strict integer VND, never bool/float --------------------------


def test_employee_paid_claim_rejects_bool_and_float_amount() -> None:
    with pytest.raises(ValidationError):
        EmployeePaidClaim(invoice_reference="IR1", amount=True, refs=(_ref(),), reason="x")
    with pytest.raises(ValidationError):
        EmployeePaidClaim(invoice_reference="IR1", amount=3_240_000.0, refs=(_ref(),), reason="x")  # type: ignore[arg-type]


def test_employee_paid_claim_accepts_integer_amount() -> None:
    claim = EmployeePaidClaim(
        invoice_reference="IR26101001", amount=3_240_000, refs=(_ref(),), reason="đã trả"
    )
    assert claim.amount == 3_240_000


def test_employee_paid_claim_rejects_client_supplied_actor_or_state() -> None:
    # The client may state a claim, not the actor/verifier/known state.
    for bad in ("actor", "verifier", "known", "state", "verified_by"):
        with pytest.raises(ValidationError):
            EmployeePaidClaim(
                invoice_reference="IR1", amount=1, refs=(_ref(),), reason="x", **{bad: "x"}
            )


def test_submit_carries_employee_paid_claims_default_empty() -> None:
    from invoice_referee.domain.commands import Declaration

    submit = Submit(root_id="case:1", declaration=Declaration(activity_id="activity:1", declared_purpose="p"))
    assert submit.employee_paid_claims == ()


# --- payment basis vocabulary ------------------------------------------------


def test_payment_basis_kinds_are_frozen() -> None:
    kinds = {
        "INDEPENDENT_PAYMENT",
        "FINANCIAL_CONFIRMATION",
        "EMPLOYEE_DECLARATION_Q32",
        "UNSPECIFIED_LEGACY",
    }
    # The Literal is the source of truth; check every member is accepted.
    for kind in kinds:
        view = PaymentBasisView(expense_id="expense:1", kind=kind, actor=None, refs=(), rule_id=None)  # type: ignore[arg-type]
        assert view.kind == kind


def test_payment_basis_view_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PaymentBasisView(expense_id="expense:1", kind="BANK_VERIFIED", actor=None, refs=(), rule_id=None)  # type: ignore[arg-type]


def test_stub_constructor_defaults_to_unspecified_legacy() -> None:
    # A compatibility constructor (no explicit basis) is UNSPECIFIED_LEGACY, so a
    # LIVE admission can refuse it (plan A0/A3).
    payment = ExpensePayment(
        external_key="external:1",
        payer="employee:a",
        payee="vendor:demo",
        amount=1_000,
        expense_id="expense:1",
        received_state="CLEAR",
        refs=(_ref(),),
    )
    assert payment.basis_kind == "UNSPECIFIED_LEGACY"
    assert payment.responsible_actor is None


def test_payment_basis_is_not_a_generic_confidence_label() -> None:
    # The Q32 kind is the employee declaration, never an independent bank fact.
    assert PaymentBasisKind is not None
    view = PaymentBasisView(
        expense_id="expense:1", kind="EMPLOYEE_DECLARATION_Q32",
        actor="employee:a", refs=(_ref(),), rule_id="Q32",
    )
    assert view.kind != "INDEPENDENT_PAYMENT"


# --- assessment input carries conditional admission fields ------------------


def test_assessment_input_defaults_are_backward_compatible() -> None:
    inp = AssessmentInput(scope=_scope(), read_set=_read_set(), as_of="2026-10-10T11:00:00+00:00")
    assert inp.admission_issues == ()
    assert inp.admission_problems == ()
    assert inp.expense_set_complete is False


# --- contract drift: amount_words is critical -------------------------------


def test_settlement_form_amount_words_is_critical() -> None:
    # contracts §12.3 lists amount_words in the critical set; the code had it
    # NON_CRITICAL (drift). A missing/low-confidence words line must not pass.
    profile = DOCUMENT_PROFILES["SETTLEMENT_FORM"]
    assert "amount_words" in profile.critical_fields
