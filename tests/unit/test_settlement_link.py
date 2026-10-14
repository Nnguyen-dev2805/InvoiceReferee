"""Backend settlement linking inputs (task 14/10/2026 RED).

Pure assembly: a typed ReadResult + server catalog/ledger -> link_dossier
inputs. document_references come only from an explicit advance_reference
field with source refs; transaction_references only from payment-document
identity fields with source refs. Purpose/name/date/amount are weak-only.
"""

from __future__ import annotations

from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.reconciliation.linking import ActivityCandidate, LedgerTxn
from invoice_referee.reconciliation.settlement_link import (
    catalog_from_entries,
    ledger_from_events,
    link_settlement,
)

SHA = "c" * 64


def _ref(quote: str = "q") -> EvidenceRef:
    return EvidenceRef(
        source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote
    )


def _found(field: str, value: object, quote: str = "q") -> FieldCandidate:
    return FieldCandidate(field=field, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _doc(
    dtype: str, *fields: FieldCandidate, source: str = "source:1"
) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id=source,
        document_id=f"{source}:1-1:{dtype}",
        document_type=dtype,  # type: ignore[arg-type]
        roles=("SUPPORTING_DOCUMENT",),
        page_range=(1, 1),
        fields=tuple(fields),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _paper(*fields: FieldCandidate) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1",
        document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),  # type: ignore[arg-type]
        page_range=(1, 1),
        fields=tuple(fields),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _report(*docs: DocumentAnalysis) -> ReadResult:
    return ReadResult(
        provider_mode="LIVE", data_origin="LIVE_READ", documents=tuple(docs)
    )


def _catalog() -> tuple[ActivityCandidate, ...]:
    return catalog_from_entries(
        [
            {
                "activity_id": "activity:adv-1",
                "name": "Tạm ứng 1",
                "references": ["TU-2026-001"],
            },
            {
                "activity_id": "activity:adv-2",
                "name": "Tạm ứng 2",
                "references": ["TU-2026-002"],
            },
        ]
    )


def test_continue_from_advance_dossier_needs_no_choice() -> None:
    result = link_settlement(
        _report(_paper(_found("purpose", "Quyết toán"))),
        employee="employee:a",
        current_activity="activity:adv-1",
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=(),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-1"
    assert result.basis == "INHERITED"


def test_printed_advance_reference_links() -> None:
    result = link_settlement(
        _report(
            _paper(
                _found("purpose", "Quyết toán"),
                _found(
                    "advance_reference", "TU-2026-002", quote="Số tạm ứng TU-2026-002"
                ),
            )
        ),
        employee="employee:a",
        current_activity="activity:proposed:1",
        current_activity_proposed=True,
        catalog=_catalog(),
        ledger=(),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-2"
    assert result.basis == "DOCUMENT_REFERENCE"


def test_same_amount_two_advances_never_auto_picks() -> None:
    ledger = ledger_from_events(
        [
            {
                "external_key": "bank:ADV-A",
                "activity": "activity:adv-1",
                "employee": "employee:a",
                "amount": 4_000_000,
                "kind": "ADVANCE_RECEIVED",
            },
            {
                "external_key": "bank:ADV-B",
                "activity": "activity:adv-2",
                "employee": "employee:a",
                "amount": 4_000_000,
                "kind": "ADVANCE_RECEIVED",
            },
        ]
    )
    result = link_settlement(
        _report(
            _paper(
                _found("purpose", "Tạm ứng 1"), _found("declared_advance", "4000000")
            )
        ),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=ledger,
    )
    assert result.status in ("NEEDS_CONFIRMATION", "NOT_FOUND")
    assert result.activity_id is None


def test_same_purpose_different_dossiers_never_links() -> None:
    result = link_settlement(
        _report(_paper(_found("purpose", "Công tác Hà Nội"))),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=catalog_from_entries(
            [
                {"activity_id": "activity:adv-1", "name": "Công tác Hà Nội"},
                {"activity_id": "activity:adv-2", "name": "Công tác Hà Nội"},
            ]
        ),
        ledger=(),
    )
    assert result.status == "NEEDS_CONFIRMATION"
    assert result.activity_id is None


def test_strong_refs_to_two_dossiers_conflict() -> None:
    ledger = ledger_from_events(
        [
            {
                "external_key": "bank:ACB-001",
                "activity": "activity:adv-2",
                "employee": "employee:a",
                "amount": 4_000_000,
                "kind": "ADVANCE_RECEIVED",
            },
        ]
    )
    proof = _doc(
        "PAYMENT_PROOF", _found("transaction_reference", "ACB-001", quote="CK ACB-001")
    )
    result = link_settlement(
        _report(
            _paper(
                _found("purpose", "Quyết toán"),
                _found("advance_reference", "TU-2026-001", quote="TU-2026-001"),
            ),
            proof,
        ),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=ledger,
    )
    assert result.status == "CONFLICT"
    assert result.activity_id is None


def test_reference_without_source_ref_is_ignored() -> None:
    naked = FieldCandidate.model_construct(
        field="advance_reference", state="FOUND", value="TU-2026-001", refs=()
    )
    paper = DocumentAnalysis.model_construct(
        source_id="source:1",
        document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),
        page_range=(1, 1),
        fields=(_found("purpose", "Quyết toán"), naked),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )
    result = link_settlement(
        _report(paper),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=(),
    )
    assert result.status in ("NEEDS_CONFIRMATION", "NOT_FOUND")
    assert not (result.status == "LINKED" and result.basis == "DOCUMENT_REFERENCE")


def test_advance_code_on_payment_document_links() -> None:
    # ADR0008 basis B: the code may be printed on any document, not only the
    # settlement form — here a transfer receipt states it with refs.
    proof = _doc(
        "PAYMENT_PROOF",
        _found("transaction_reference", "FT-UC03-F01-0001", quote="FT-UC03-F01-0001"),
        _found(
            "advance_reference", "TU-2026-002", quote="Tham chiếu khoản ứng TU-2026-002"
        ),
    )
    result = link_settlement(
        _report(_paper(_found("purpose", "Quyết toán")), proof),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=(),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-2"
    assert result.basis == "DOCUMENT_REFERENCE"


def test_advance_code_matches_ledger_identity() -> None:
    # The printed advance code is also the advance's transaction identity:
    # agreement between the bases links (here via the ledger).
    proof = _doc(
        "PAYMENT_PROOF",
        _found("advance_reference", "ADV-9", quote="Tham chiếu ADV-9"),
    )
    result = link_settlement(
        _report(_paper(_found("purpose", "Quyết toán")), proof),
        employee="employee:a",
        current_activity=None,
        current_activity_proposed=False,
        catalog=_catalog(),
        ledger=ledger_from_events([
            {"external_key": "transfer:ADV-9", "activity": "activity:adv-2",
             "employee": "employee:a", "amount": 4_000_000, "kind": "ADVANCE_RECEIVED"},
        ]),
    )
    assert result.status == "LINKED"
    assert result.activity_id == "activity:adv-2"
