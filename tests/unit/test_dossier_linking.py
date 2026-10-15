"""Server-owned dossier linking (14/10/2026).

The employee never picks a standing activity: the backend decides the link from
strong evidence (inherited / document reference / transaction identity) and only
asks a human when the basis is weak or conflicting. The weak basis (name/purpose/
date/amount) is candidates-only — never an automatic link, even with one match.
"""

from __future__ import annotations

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.reconciliation.linking import (
    ActivityCandidate,
    AdvanceLinkCandidate,
    AdvanceLinkEvidence,
    LedgerTxn,
    link_advance_multifield,
    link_dossier,
)

SHA = "a" * 64


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


def _activity(activity_id: str, name: str, *, references=(), purpose=None) -> ActivityCandidate:
    return ActivityCandidate(
        activity_id=activity_id, name=name, purpose=purpose,
        references=tuple(references), refs=(_ref(activity_id),),
    )


def test_inherited_link_needs_no_activity_choice() -> None:
    # A settlement started from a known advance dossier: the server-owned link is
    # inherited; the employee is not asked to choose an activity.
    result = link_dossier(
        employee="employee:a",
        current_activity="activity:adv-1",
        current_activity_proposed=False,
        catalog=(_activity("activity:adv-1", "Tạm ứng TU-1"),),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-1"
    assert result.basis == "INHERITED"
    assert result.inherited is True
    assert result.requires_confirmation is False


def test_document_reference_links_the_right_dossier() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity="activity:proposed",
        current_activity_proposed=True,
        document_references=("TU-2026-001",),
        catalog=(
            _activity("activity:adv-1", "Tạm ứng 1", references=("TU-2026-001",)),
            _activity("activity:adv-2", "Tạm ứng 2", references=("TU-2026-002",)),
        ),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-1"
    assert result.basis == "DOCUMENT_REFERENCE"


def test_transaction_identity_links_via_ledger() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        transaction_references=("ACB-001",),
        ledger=(
            LedgerTxn(external_key="bank:ACB-001", activity="activity:adv-1",
                      employee="employee:a", amount=4_000_000, kind="ADVANCE_RECEIVED",
                      namespace="bank", reference="ACB-001", refs=(_ref("ACB-001"),)),
        ),
        catalog=(_activity("activity:adv-1", "Tạm ứng 1"),),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-1"
    assert result.basis == "TRANSACTION_IDENTITY"


def test_weak_name_match_is_candidates_only() -> None:
    # Only a name/purpose similarity: never an automatic link, even with one hit.
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        weak_text="Tiếp khách dự án",
        catalog=(
            _activity("activity:adv-1", "Tiếp khách dự án"),
            _activity("activity:adv-2", "Công tác Hà Nội"),
        ),
    )
    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None
    assert result.requires_confirmation is True
    assert result.owner == "employee"
    assert [c.activity_id for c in result.candidates] == ["activity:adv-1"]


def test_single_weak_candidate_is_not_an_automatic_link() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        weak_text="Tiếp khách dự án",
        catalog=(_activity("activity:adv-1", "Tiếp khách dự án"),),
    )
    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None


def test_strong_bases_to_different_dossiers_conflict() -> None:
    # A document reference and a ledger transaction point at DIFFERENT dossiers:
    # keep the conflict, never pick by priority order.
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        document_references=("TU-2026-001",),
        transaction_references=("ACB-001",),
        catalog=(
            _activity("activity:adv-1", "Tạm ứng 1", references=("TU-2026-001",)),
            _activity("activity:adv-2", "Tạm ứng 2"),
        ),
        ledger=(
            LedgerTxn(external_key="bank:ACB-001", activity="activity:adv-2",
                      employee="employee:a", amount=4_000_000, kind="ADVANCE_RECEIVED",
                      namespace="bank", reference="ACB-001", refs=(_ref("ACB-001"),)),
        ),
    )
    assert result.status == "CONFLICT"
    assert result.activity_id is None
    assert result.owner == "accountant"
    assert set(result.conflicting_fields) == {"activity"}


def test_document_reference_to_another_employee_conflicts() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        transaction_references=("ACB-001",),
        ledger=(
            LedgerTxn(external_key="bank:ACB-001", activity="activity:adv-1",
                      employee="employee:B", amount=4_000_000, kind="ADVANCE_RECEIVED",
                      namespace="bank", reference="ACB-001", refs=(_ref("ACB-001"),)),
        ),
    )
    assert result.status == "CONFLICT"
    assert result.owner == "accountant"


def test_no_basis_is_not_found_not_a_fabricated_link() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=(_activity("activity:adv-1", "Tạm ứng 1"),),
    )
    assert result.status == "NOT_FOUND"
    assert result.activity_id is None
    assert result.candidates == ()


def test_bare_number_reference_needs_unique_namespace() -> None:
    # The same bare number in two activities must not link by itself.
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        document_references=("001",),
        catalog=(
            _activity("activity:adv-1", "Tạm ứng 1", references=("TU-2026-001",)),
            _activity("activity:adv-2", "Tạm ứng 2", references=("TU-2026-002",)),
        ),
    )
    assert result.status == "NOT_FOUND"


def test_serial_prefixed_reference_still_matches() -> None:
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        document_references=("TU26E00000001",),
        catalog=(_activity("activity:adv-1", "Tạm ứng 1", references=("TU-2026-001",)),),
    )
    # "TU26E00000001" and "TU-2026-001" normalize to different digit-runs; a
    # suffix match on the numeric part is tolerated only when it is unambiguous.
    # Here they differ, so no link (a wrong number must not link).
    assert result.status == "NOT_FOUND"


def test_purpose_equality_is_not_an_automatic_link() -> None:
    # Exact purpose equality is still a WEAK basis: candidates only.
    result = link_dossier(
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        weak_text="Công tác Hà Nội",
        catalog=(_activity("activity:adv-1", "Công tác Hà Nội"),),
    )
    assert result.status == "NEEDS_CONFIRMATION"
    assert result.basis is None


def _advance_candidate(
    *,
    root_id: str = "case:current",
    activity_id: str = "activity:proposed:current",
    employee_id: str = "employee:a",
    employee_name: str = "NGUYỄN MINH AN",
    purpose: str | None = "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
    declared_advance: int | None = 4_000_000,
    settlement_date: str | None = "2026-10-10",
) -> AdvanceLinkCandidate:
    return AdvanceLinkCandidate(
        root_id=root_id,
        activity_id=activity_id,
        employee_id=employee_id,
        employee_name=employee_name,
        purpose=purpose,
        declared_advance=declared_advance,
        settlement_date=settlement_date,
        declared_name=employee_name,
        source_clear=True,
        work_start=None,
        work_end=None,
        purpose_refs=(_ref("Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"),),
        declared_advance_refs=(_ref("Số tiền đã tạm ứng: 4.000.000"),),
        settlement_date_refs=(_ref("ngày 10 tháng 10 năm 2026"),),
        employee_refs=(_ref("Người đề nghị: NGUYỄN MINH AN"),),
        declared_name_refs=(_ref("Người đề nghị: NGUYỄN MINH AN"),),
    )


def _advance_evidence(**overrides) -> AdvanceLinkEvidence:
    values = {
        "root_id": "case:current",
        "activity_id": "activity:proposed:current",
        "employee_id": "employee:a",
        "employee_name": "NGUYỄN MINH AN",
        "employee_name_unique": True,
        "expected_company_names": ("CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",),
        "payer_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "payee_name": "NGUYỄN MINH AN",
        "amount": 4_000_000,
        "transaction_reference": "FT-TC01-0001",
        "payment_date": "2026-10-05",
        "payment_purpose": "Ứng tiền tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
        "payer_refs": (_ref("Bên chuyển: CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"),),
        "payee_refs": (_ref("Bên nhận: NGUYỄN MINH AN"),),
        "amount_refs": (_ref("SỐ TIỀN THỰC NHẬN: 4.000.000 đ"),),
        "transaction_reference_refs": (_ref("Mã giao dịch: FT-TC01-0001"),),
        "payment_date_refs": (_ref("Ngày giao dịch: 05/10/2026"),),
        "payment_purpose_refs": (_ref("Ứng tiền tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"),),
        "activity_reference": "TU-TC01",
        "mapped_reference_activity": None,
        "transaction_owner_root": None,
        "other_draft_roots": (),
    }
    values.update(overrides)
    return AdvanceLinkEvidence(**values)


def test_tc01_multifield_evidence_links_without_registered_reference() -> None:
    result = link_advance_multifield(
        _advance_evidence(), (_advance_candidate(),)
    )

    assert result.status == "LINKED"
    assert result.activity_id == "activity:proposed:current"
    assert result.basis == "MULTI_FIELD_MATCH"
    assert result.candidate_count == 1
    assert {signal.field: signal.state for signal in result.signals} == {
        "employee": "MATCHED",
        "company": "MATCHED",
        "purpose": "MATCHED",
        "advance_amount": "MATCHED",
        "time": "MATCHED",
        "reference": "UNMAPPED",
        "transaction": "MATCHED",
        "candidates": "MATCHED",
    }
    purpose_signal = next(signal for signal in result.signals if signal.field == "purpose")
    assert {ref.exact_quote for ref in purpose_signal.refs} == {
        "Ứng tiền tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
        "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
    }


def test_generic_purpose_never_auto_links_even_for_only_root() -> None:
    evidence = _advance_evidence(payment_purpose="Ứng tiền tiếp khách")
    candidate = _advance_candidate(purpose="Chi phí tiếp khách")

    result = link_advance_multifield(evidence, (candidate,))

    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None
    assert next(signal for signal in result.signals if signal.field == "purpose").state != "MATCHED"


def test_different_project_does_not_auto_link() -> None:
    candidate = _advance_candidate(
        purpose="Chi phí tiếp khách phục vụ dự án Khai trương văn phòng 2026"
    )

    result = link_advance_multifield(_advance_evidence(), (candidate,))

    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None


def test_same_project_with_two_competing_roots_needs_confirmation() -> None:
    competitor = _advance_candidate(
        root_id="case:competitor", activity_id="activity:proposed:competitor"
    )

    result = link_advance_multifield(
        _advance_evidence(), (_advance_candidate(), competitor)
    )

    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None
    assert result.candidate_count == 2
    assert all(candidate.activity_id not in {"activity:proposed:competitor"} for candidate in result.candidates)


def test_wrong_employee_or_company_is_conflict_not_a_weak_candidate() -> None:
    wrong_employee = link_advance_multifield(
        _advance_evidence(payee_name="NGUYỄN MINH BÌNH"), (_advance_candidate(),)
    )
    wrong_company = link_advance_multifield(
        _advance_evidence(payer_name="CÔNG TY KHÁC"), (_advance_candidate(),)
    )

    assert wrong_employee.status == "CONFLICT"
    assert "employee" in wrong_employee.conflicting_fields
    assert wrong_company.status == "CONFLICT"
    assert "company" in wrong_company.conflicting_fields


def test_unmapped_reference_does_not_veto_but_reference_to_other_activity_conflicts() -> None:
    unmapped = link_advance_multifield(
        _advance_evidence(mapped_reference_activity=None), (_advance_candidate(),)
    )
    wrong_target = link_advance_multifield(
        _advance_evidence(mapped_reference_activity="activity:other"), (_advance_candidate(),)
    )

    assert unmapped.status == "LINKED"
    assert unmapped.basis == "MULTI_FIELD_MATCH"
    assert wrong_target.status == "CONFLICT"
    assert wrong_target.activity_id is None


def test_mismatched_advance_amount_is_not_confused_with_expense_total() -> None:
    # The invoice's 3.240m expense total is not an input to this linker; the
    # relevant comparison is actual transfer 4m against declared advance 4m.
    matched = link_advance_multifield(
        _advance_evidence(amount=4_000_000),
        (_advance_candidate(declared_advance=4_000_000),),
    )
    mismatched = link_advance_multifield(
        _advance_evidence(amount=4_000_000),
        (_advance_candidate(declared_advance=3_240_000),),
    )

    assert matched.status == "LINKED"
    assert mismatched.status == "NEEDS_CONFIRMATION"
    assert next(signal for signal in mismatched.signals if signal.field == "advance_amount").state == "MISMATCH"


def test_missing_or_backwards_advance_dates_do_not_auto_link() -> None:
    missing = link_advance_multifield(
        _advance_evidence(payment_date=None), (_advance_candidate(),)
    )
    later_transfer = link_advance_multifield(
        _advance_evidence(payment_date="2026-10-11"), (_advance_candidate(),)
    )

    assert missing.status == "NEEDS_CONFIRMATION"
    assert later_transfer.status == "NEEDS_CONFIRMATION"
    assert next(signal for signal in missing.signals if signal.field == "time").state == "MISSING"


def test_duplicate_transaction_owner_blocks_and_same_root_replay_is_idempotent() -> None:
    other_root = link_advance_multifield(
        _advance_evidence(transaction_owner_root="case:other"), (_advance_candidate(),)
    )
    same_root = link_advance_multifield(
        _advance_evidence(transaction_owner_root="case:current"), (_advance_candidate(),)
    )

    assert other_root.status == "CONFLICT"
    assert "transaction" in other_root.conflicting_fields
    assert same_root.status == "LINKED"
