"""Advance transaction identity + record_actual guards (task 14/10/2026 RED).

Covers behaviors 6-13 + 8-11:
6. payee on voucher != dossier employee -> block CONFIRMED A.
7. event_at from source kept, not replaced by confirm time.
8. reload same txn -> no double A.
9. same reference different material payload -> conflict.
10. same reference different namespace -> not merged.
11. missing txn identity -> no fabricated external identity, unresolved.
12. PENDING/FAILED/UNKNOWN -> never CONFIRMED.
13. employee-uploaded advance doc -> never auto-CONFIRMED.
"""

from __future__ import annotations

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.reconciliation.advance_identity import (
    build_external_key,
    check_advance_parties,
    check_record_payload,
    decide_advance_resolution,
)

SHA = "b" * 64


def _ref(quote: str = "q") -> EvidenceRef:
    return EvidenceRef(
        source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote
    )


def test_payee_mismatch_blocks_confirmed() -> None:
    res = check_advance_parties(payee_name="Nguyen Van B", employee="employee:a")
    assert res.ok is False
    assert "payee" in res.reason.casefold() or "nhân viên" in res.reason


def test_event_at_kept_not_replaced() -> None:
    from invoice_referee.reconciliation.advance_identity import resolve_event_times

    out = resolve_event_times(
        event_at="2026-10-01T09:00:00+07:00", recorded_at="2026-10-14T18:00:00+07:00"
    )
    assert out["event_at"] == "2026-10-01T09:00:00+07:00"
    assert out["recorded_at"] == "2026-10-14T18:00:00+07:00"
    assert out["event_at"] != out["recorded_at"]


def test_same_txn_reload_is_idempotent() -> None:
    existing = {
        "external_key": "bank:ACB-001",
        "amount": 4_000_000,
        "payer": "company:acme",
        "payee": "employee:a",
        "scope": "activity:x",
        "kind": "ADVANCE_RECEIVED",
    }
    claim = dict(existing)
    assert check_record_payload(existing, claim) == "IDEMPOTENT"


def test_same_ref_different_amount_conflicts() -> None:
    existing = {
        "external_key": "bank:ACB-001",
        "amount": 4_000_000,
        "payer": "company:acme",
        "payee": "employee:a",
        "scope": "activity:x",
        "kind": "ADVANCE_RECEIVED",
    }
    claim = dict(existing, amount=4_500_000)
    assert check_record_payload(existing, claim) == "CONFLICT"


def test_same_ref_different_payee_conflicts() -> None:
    existing = {
        "external_key": "bank:ACB-001",
        "amount": 4_000_000,
        "payer": "company:acme",
        "payee": "employee:a",
        "scope": "activity:x",
        "kind": "ADVANCE_RECEIVED",
    }
    claim = dict(existing, payee="employee:b")
    assert check_record_payload(existing, claim) == "CONFLICT"


def test_same_ref_different_namespace_not_merged() -> None:
    assert build_external_key("bank", "PC-001") != build_external_key("cash", "PC-001")


def test_missing_reference_has_no_external_identity() -> None:
    assert build_external_key("bank", None) is None
    assert build_external_key(None, "   ") is None
    res = decide_advance_resolution(
        amount=4_000_000,
        instrument_status="COMPLETED",
        external_key=None,
        has_responsible_confirmation=True,
    )
    assert res == "UNRESOLVED_MISSING_IDENTITY"


def test_pending_failed_unknown_never_confirmed() -> None:
    for status in ("PENDING", "FAILED", "UNKNOWN"):
        res = decide_advance_resolution(
            amount=4_000_000,
            instrument_status=status,
            external_key="bank:ACB-001",
            has_responsible_confirmation=True,
        )
        assert res == "OBSERVED", status


def test_employee_upload_is_not_confirmed_without_accountant() -> None:
    res = decide_advance_resolution(
        amount=4_000_000,
        instrument_status="COMPLETED",
        external_key="bank:ACB-001",
        has_responsible_confirmation=False,
    )
    assert res == "OBSERVED"


def test_no_uuid_fallback_for_missing_reference() -> None:
    # A missing reference must stay unresolved; callers must not mint a UUID
    # and claim dedup protection.
    key = build_external_key("transfer", "")
    assert key is None


def test_payer_must_match_configured_source() -> None:
    res = check_advance_parties(
        payee_name="employee:a",
        employee="employee:a",
        payer_name="Công ty Lạ",
        expected_payer_names=("Công ty Demo", "company:demo"),
    )
    assert res.ok is False


def test_unresolved_name_kept_unresolved() -> None:
    res = check_advance_parties(payee_name=None, employee="employee:a")
    assert res.ok is False
    assert "unresolved" in res.reason.casefold() or "chưa" in res.reason
