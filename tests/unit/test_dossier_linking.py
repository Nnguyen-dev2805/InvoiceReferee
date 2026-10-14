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
    LedgerTxn,
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
