from datetime import date

from invoice_referee.reconciliation.employee_return import match_employee_return


def _match(**overrides):
    values = {
        "root_id": "case:1",
        "instruction_id": "instruction:collect-1",
        "instruction_active": True,
        "instruction_remaining": 1_000_000,
        "instruction_date": date(2026, 10, 10),
        "as_of": date(2026, 10, 15),
        "employee_name": "NGUYỄN MINH AN",
        "company_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "payer_name": "NGUYỄN MINH AN",
        "payee_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "amount": 1_000_000,
        "event_date": date(2026, 10, 15),
        "transaction_reference": "RET-TC01-001",
        "instrument_status": "COMPLETED",
        "ambiguous_fields": (),
        "conflicting_fields": (),
        "transaction_owner_root": None,
        "already_recorded": False,
    }
    values.update(overrides)
    return match_employee_return(**values)


def test_matching_completed_return_is_ready_for_accountant_confirmation() -> None:
    result = _match()
    assert result.status == "MATCHED"
    assert {signal.field: signal.state for signal in result.signals} == {
        "instruction": "MATCHED",
        "payer": "MATCHED",
        "payee": "MATCHED",
        "amount": "MATCHED",
        "event_at": "MATCHED",
        "transaction": "MATCHED",
        "source_status": "MATCHED",
    }


def test_partial_return_matches_but_does_not_claim_the_remaining_amount() -> None:
    result = _match(amount=400_000)
    assert result.status == "MATCHED"
    assert next(signal for signal in result.signals if signal.field == "amount").state == "MATCHED"


def test_overpayment_is_explicit_and_requires_accountant_review() -> None:
    result = _match(amount=1_200_000)
    assert result.status == "OVERPAY"
    assert next(signal for signal in result.signals if signal.field == "amount").state == "OVERPAY"


def test_wrong_company_payee_is_non_overridable_conflict() -> None:
    result = _match(payee_name="CÔNG TY KHÁC")
    assert result.status == "CONFLICT"
    assert next(signal for signal in result.signals if signal.field == "payee").state == "CONFLICT"


def test_failed_or_pending_transfer_never_becomes_ready() -> None:
    result = _match(instrument_status="FAILED")
    assert result.status == "NOT_COMPLETED"
    assert next(signal for signal in result.signals if signal.field == "source_status").state == "NOT_COMPLETED"


def test_stale_instruction_or_transfer_before_request_cannot_be_confirmed() -> None:
    stale = _match(instruction_active=False)
    earlier = _match(event_date=date(2026, 10, 9))
    assert stale.status == "STALE"
    assert earlier.status == "NEEDS_REVIEW"


def test_duplicate_transaction_owned_by_another_root_is_conflict() -> None:
    result = _match(transaction_owner_root="case:other")
    assert result.status == "CONFLICT"
    assert next(signal for signal in result.signals if signal.field == "transaction").state == "CONFLICT"


def test_missing_date_or_transaction_reference_requires_review() -> None:
    missing_date = _match(event_date=None)
    missing_reference = _match(transaction_reference=None)
    assert missing_date.status == "NEEDS_REVIEW"
    assert missing_reference.status == "NEEDS_REVIEW"


def test_ambiguous_or_conflicting_source_field_does_not_auto_match() -> None:
    ambiguous = _match(ambiguous_fields=("payer_name",))
    conflict = _match(conflicting_fields=("payee_name",))
    assert ambiguous.status == "NEEDS_REVIEW"
    assert conflict.status == "CONFLICT"
