"""Per-type document field profiles (contracts §12.2; plan E4/E5).

The required/any-of fields and the criticality matrix come from Hoangha's
`policy/document_validity.py` (pinned revision `1ee33487…`), plus a new
`SETTLEMENT_FORM` entry the final workflow adds. A field is critical when a
missing/low-confidence value on it must leave the document unresolved rather
than pass; the SETTLEMENT_FORM critical set is a lead call (plan E0), recorded
here so E3/E5 can test it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from invoice_referee.domain.documents import DOCUMENT_TYPES


@dataclass(frozen=True)
class DocumentProfile:
    required_fields: tuple[str, ...] = ()
    any_of_fields: tuple[str, ...] = ()
    field_importance: dict[str, str] = field(default_factory=dict)
    allowed_fields: tuple[str, ...] = ()
    field_types: dict[str, str] = field(default_factory=dict)

    @property
    def critical_fields(self) -> frozenset[str]:
        return frozenset(
            name
            for name, importance in self.field_importance.items()
            if importance == "CRITICAL"
        )


_COMMON_INVOICE = (
    "issuer_name",
    "issuer_tax_code",
    "buyer_name",
    "buyer_tax_code",
    # The natural-person buyer ("Họ tên người mua"). In the demo policy a valid
    # invoice bound to the right employee is the employee-paid basis; the buyer
    # person is the binding key (never the company buyer, which is not a payer).
    "buyer_person_name",
    "document_number",
    "template_number",
    "serial_number",
    "document_date",
    "subtotal",
    "discount",
    "tax",
    "service_charge",
    "total_amount",
    "currency",
    "payment_method_text",
    "payment_confirmation_text",
)

# SETTLEMENT_FORM: the final workflow's own paper settlement form. Criticality
# is a lead call (plan E0): identity, trip context, the printed totals and the
# per-row amount/reference decide the money, so they are critical.
#
# T1: the paper contract is COMMON (identity/purpose/total/words) with a
# travel-specific refinement. Trip fields are required only when the activity
# profile is TRAVEL; a general (WORK_EXPENSE) paper is not forced to carry trip
# context (see `required_fields_for`). The stored `required_fields` is the common
# baseline; the travel refinement adds trip context.
_SETTLEMENT_FORM_COMMON = (
    "declared_name",
    "purpose",
)
_SETTLEMENT_FORM_TRAVEL = (
    "trip_destination",
    "trip_start",
    "trip_end",
)
_SETTLEMENT_FORM = DocumentProfile(
    required_fields=_SETTLEMENT_FORM_COMMON,
    any_of_fields=("printed_total", "printed_return", "printed_reimbursement"),
    field_importance={
        "declared_name": "CRITICAL",
        # Optional source date used to compare settlement-paper chronology with
        # an advance voucher. It is never a substitute for the work period.
        "document_date": "NON_CRITICAL",
        "trip_destination": "CRITICAL",
        "trip_start": "CRITICAL",
        "trip_end": "CRITICAL",
        "purpose": "CRITICAL",
        "declared_advance": "CRITICAL",
        "printed_total": "CRITICAL",
        "printed_return": "CRITICAL",
        "printed_reimbursement": "CRITICAL",
        "amount_words": "CRITICAL",
        "case_no_evidence_reason": "NON_CRITICAL",
        # An advance/dossier number printed on the form (14/10/2026): optional
        # evidence for backend dossier linking (DOCUMENT_REFERENCE). The LLM
        # extracts it with quote refs; code decides the link.
        "advance_reference": "NON_CRITICAL",
    },
    allowed_fields=(
        "declared_name",
        "document_date",
        "trip_destination",
        "trip_start",
        "trip_end",
        "purpose",
        "declared_advance",
        "printed_total",
        "printed_return",
        "printed_reimbursement",
        "amount_words",
        "case_no_evidence_reason",
        "advance_reference",
    ),
    field_types={
        "declared_advance": "money",
        "printed_total": "money",
        "printed_return": "money",
        "printed_reimbursement": "money",
    },
)


def required_fields_for(
    document_type: str, activity_profile: str | None
) -> tuple[str, ...]:
    """The required fields for a document type under an activity profile.

    Common settlement fields apply to every profile; the TRAVEL refinement adds
    trip context. Non-settlement types are profile-agnostic. This keeps one
    paper contract with a travel-specific refinement rather than a global
    hard-coded TRAVEL requirement (plan T1).
    """
    profile = DOCUMENT_PROFILES.get(document_type)
    if profile is None:
        return ()
    if document_type == "SETTLEMENT_FORM" and activity_profile == "TRAVEL":
        return _SETTLEMENT_FORM_COMMON + _SETTLEMENT_FORM_TRAVEL
    return profile.required_fields


_E_INVOICE = DocumentProfile(
    required_fields=("issuer_name", "document_number", "document_date", "total_amount"),
    field_importance={
        "issuer_name": "CRITICAL",
        "document_number": "CRITICAL",
        "document_date": "CRITICAL",
        "total_amount": "CRITICAL",
    },
    allowed_fields=_COMMON_INVOICE,
)

_RECEIPT_LIKE = DocumentProfile(
    required_fields=("issuer_name", "total_amount"),
    field_importance={"issuer_name": "CRITICAL", "total_amount": "CRITICAL"},
    allowed_fields=(
        "issuer_name",
        "document_number",
        "document_date",
        "description",
        "total_amount",
        "currency",
        "payer_name",
        "collection_reason",
        "payment_confirmation_text",
        # A printed advance/dossier code (14/10/2026, ADR0008): optional
        # evidence for backend dossier linking, never required.
        "advance_reference",
    ),
)

# A collection receipt can name both sides of a transfer. Keep this separate
# from generic PAPER_RECEIPT so payment-specific party extraction does not widen
# the vocabulary for ordinary purchase receipts.
_COLLECTION_RECEIPT = DocumentProfile(
    required_fields=_RECEIPT_LIKE.required_fields,
    field_importance=_RECEIPT_LIKE.field_importance,
    allowed_fields=(*_RECEIPT_LIKE.allowed_fields, "payee_name"),
)

_HOTEL = DocumentProfile(
    required_fields=("issuer_name", "total_amount"),
    field_importance={
        "issuer_name": "CRITICAL",
        "total_amount": "CRITICAL",
        "check_in": "CRITICAL",
        "check_out": "CRITICAL",
    },
    allowed_fields=(
        "issuer_name",
        "guest_name",
        "document_number",
        "document_date",
        "check_in",
        "check_out",
        "nights",
        "room_amount",
        "extra_charges",
        "total_amount",
        "currency",
    ),
)

_TRANSPORT = DocumentProfile(
    required_fields=("issuer_name", "fare_amount"),
    field_importance={"issuer_name": "CRITICAL", "fare_amount": "CRITICAL"},
    allowed_fields=(
        "issuer_name",
        "passenger_name",
        "booking_reference",
        "origin",
        "destination",
        "departure_at",
        "return_at",
        "ticket_status",
        "fare_amount",
        "fees",
        "total_amount",
        "currency",
    ),
)

_PAYMENT_PROOF = DocumentProfile(
    required_fields=("payment_provider", "payer_name", "payee_name", "amount"),
    field_importance={
        "payment_provider": "CRITICAL",
        "payer_name": "CRITICAL",
        "payee_name": "CRITICAL",
        "amount": "CRITICAL",
        "event_at": "CRITICAL",
        "transaction_reference": "CRITICAL",
        "transaction_status": "CRITICAL",
        # A printed advance/dossier code (14/10/2026, ADR0008): optional
        # evidence for backend dossier linking, never required.
        "advance_reference": "NON_CRITICAL",
    },
    allowed_fields=(
        "payment_provider",
        "payer_name",
        "payee_name",
        "event_at",
        "transaction_reference",
        "transaction_status",
        "payment_description",
        "fee_amount",
        "account_suffix",
        "amount",
        "currency",
        "advance_reference",
    ),
)

_CARD_SLIP = DocumentProfile(
    required_fields=("payment_provider", "event_at", "transaction_reference"),
    field_importance={
        "payment_provider": "CRITICAL",
        "event_at": "CRITICAL",
        "transaction_reference": "CRITICAL",
        "transaction_status": "CRITICAL",
        "card_suffix": "NON_CRITICAL",
        # A printed advance/dossier code (14/10/2026, ADR0008): optional
        # evidence for backend dossier linking, never required.
        "advance_reference": "NON_CRITICAL",
    },
    allowed_fields=(
        "payment_provider",
        "event_at",
        "transaction_reference",
        "authorization_code",
        "transaction_status",
        "card_suffix",
        "advance_reference",
    ),
)

_SUPPORTING = DocumentProfile(
    required_fields=("issuer_name",),
    field_importance={"issuer_name": "NON_CRITICAL"},
    allowed_fields=(
        "issuer_name",
        "document_number",
        "document_date",
        "description",
        "total_amount",
        "currency",
        "valid_from",
        "valid_to",
        "scope_description",
        "contract_value",
        "valid_until",
        "accepted_value",
        "delivery_status",
        "receipt_status",
        "confirmation_present",
        "confirmation_text",
        "confirmed_status",
        "related_document_refs",
    ),
)

_OTHER = DocumentProfile(
    required_fields=(),
    field_importance={},
    allowed_fields=(
        "issuer_name",
        "buyer_name",
        "document_number",
        "document_date",
        "description",
        "total_amount",
        "currency",
    ),
)

_UNKNOWN = DocumentProfile(required_fields=(), field_importance={}, allowed_fields=())

DOCUMENT_PROFILES: dict[str, DocumentProfile] = {
    "SETTLEMENT_FORM": _SETTLEMENT_FORM,
    "E_INVOICE": _E_INVOICE,
    "PAPER_RECEIPT": _RECEIPT_LIKE,
    "COLLECTION_RECEIPT": _COLLECTION_RECEIPT,
    "HOTEL_RECEIPT": _HOTEL,
    "TRANSPORT_TICKET": _TRANSPORT,
    "PAYMENT_PROOF": _PAYMENT_PROOF,
    "CARD_SLIP": _CARD_SLIP,
    "CONTRACT": _SUPPORTING,
    "QUOTATION": _SUPPORTING,
    "PURCHASE_ORDER": _SUPPORTING,
    "ACCEPTANCE_RECORD": _SUPPORTING,
    "DELIVERY_NOTE": _SUPPORTING,
    "GOODS_RECEIPT": _SUPPORTING,
    "SUPPLIER_CONFIRMATION": _SUPPORTING,
    "OTHER": _OTHER,
    "UNKNOWN": _UNKNOWN,
}

assert set(DOCUMENT_PROFILES) == set(DOCUMENT_TYPES)  # code-owned, no gaps
