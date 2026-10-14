"""Pure settlement-link assembly: ReadResult -> link_dossier inputs (14/10/2026).

The LLM extracts; code decides. Only explicit, source-bound identity fields
feed the strong bases:

- B DOCUMENT_REFERENCE: ``advance_reference`` FOUND on the settlement form or
  a payment document, with page/quote refs. A value without refs is ignored.
- C TRANSACTION_IDENTITY: ``transaction_reference`` FOUND on a payment
  document (PAYMENT_PROOF/CARD_SLIP/COLLECTION_RECEIPT), with refs — plus the
  printed ``advance_reference``, which is also the advance's transaction
  identity. An invoice ``document_number`` is an expense identity, never a
  money transaction identity (§10.2), so it is NOT used here.
- D WEAK_SIMILARITY: the form's purpose text — candidates only.

This module is PURE: no I/O, no model call.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from invoice_referee.domain.common import EvidenceRef, parse_vnd
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.reconciliation.linking import (
    ActivityCandidate,
    LedgerTxn,
    LinkResult,
    link_dossier,
)

_PAYMENT_DOCUMENT_TYPES = frozenset(
    {"PAYMENT_PROOF", "CARD_SLIP", "COLLECTION_RECEIPT"}
)


def catalog_from_entries(
    entries: list[dict[str, Any]],
) -> tuple[ActivityCandidate, ...]:
    """Server catalog entries -> link candidates (AUTHORIZED only)."""
    out: list[ActivityCandidate] = []
    for entry in entries:
        status = str(entry.get("status") or "AUTHORIZED")
        if status != "AUTHORIZED":
            continue
        activity_id = str(entry.get("activity_id") or "")
        if not activity_id:
            continue
        references = entry.get("references") or ()
        out.append(
            ActivityCandidate(
                activity_id=activity_id,
                name=str(entry.get("name") or activity_id),
                status=status,
                purpose=(str(entry["purpose"]) if entry.get("purpose") else None),
                references=tuple(str(r) for r in references if str(r).strip()),
            )
        )
    return tuple(out)


def ledger_from_events(events: list[dict[str, Any]]) -> tuple[LedgerTxn, ...]:
    """Money events -> namespaced transaction identities.

    ``external_key`` is ``"<namespace>:<reference>"`` (split on the first
    colon). A key without a namespace stays out of identity matching — the
    same reference under another namespace is a different transaction.
    """
    out: list[LedgerTxn] = []
    for event in events:
        key = str(event.get("external_key") or "")
        if ":" not in key:
            continue
        namespace, _, reference = key.partition(":")
        if not namespace.strip() or not reference.strip():
            continue
        out.append(
            LedgerTxn(
                external_key=key,
                activity=str(event.get("activity") or event.get("scope") or ""),
                employee=str(event.get("employee") or event.get("payee") or ""),
                amount=int(event.get("amount") or 0),
                kind=str(event.get("kind") or ""),
                namespace=namespace.strip(),
                reference=reference.strip(),
            )
        )
    return tuple(out)


def _found_values(
    document, *names: str
) -> list[tuple[object, tuple[EvidenceRef, ...]]]:
    """FOUND (value, refs) pairs for the named fields; ref-less values dropped."""
    out: list[tuple[object, tuple[EvidenceRef, ...]]] = []
    for candidate in document.fields:
        if candidate.field in names and candidate.state == "FOUND" and candidate.refs:
            out.append((candidate.value, tuple(candidate.refs)))
    return out


def _paper(report: ReadResult):
    return next(
        (d for d in report.documents if d.document_type == "SETTLEMENT_FORM"), None
    )


def link_settlement(
    report: ReadResult,
    *,
    employee: str,
    current_activity: str | None,
    current_activity_proposed: bool,
    catalog: tuple[ActivityCandidate, ...] = (),
    ledger: tuple[LedgerTxn, ...] = (),
) -> LinkResult:
    """Decide which dossier a settlement belongs to (pure)."""
    paper = _paper(report)

    document_references: list[str] = []
    transaction_references: list[str] = []
    field_refs: list[EvidenceRef] = []
    # B DOCUMENT_REFERENCE: an advance/dossier code printed on the settlement
    # form OR on a payment document (ADR0008: "ghi rõ trên tài liệu"), always
    # with page/quote refs. The same printed advance code is ALSO a money
    # transaction identity, so it feeds the C basis as well: agreement links,
    # disagreement across dossiers stays a CONFLICT (never a silent pick).
    # A value without refs is ignored.
    for document in report.documents:
        if document.document_type in ("SETTLEMENT_FORM", *_PAYMENT_DOCUMENT_TYPES):
            for value, refs in _found_values(document, "advance_reference"):
                values = value if isinstance(value, (list, tuple)) else (value,)
                for item in values:
                    text = str(item).strip()
                    if text:
                        document_references.append(text)
                        transaction_references.append(text)
                        field_refs.extend(refs)

    for document in report.documents:
        if document.document_type not in _PAYMENT_DOCUMENT_TYPES:
            continue
        for value, refs in _found_values(document, "transaction_reference"):
            text = str(value).strip()
            if text:
                transaction_references.append(text)
                field_refs.extend(refs)

    weak_text: str | None = None
    weak_amount: int | None = None
    if paper is not None:
        for value, _refs in _found_values(paper, "purpose"):
            weak_text = str(value)
            break
        for value, _refs in _found_values(paper, "declared_advance", "printed_total"):
            parsed = parse_vnd(value)
            if parsed is not None:
                weak_amount = parsed
                break

    result = link_dossier(
        employee=employee,
        current_activity=current_activity,
        current_activity_proposed=current_activity_proposed,
        document_references=tuple(document_references),
        transaction_references=tuple(transaction_references),
        catalog=catalog,
        ledger=ledger,
        weak_text=weak_text,
        weak_amount=weak_amount,
    )
    if field_refs:
        result = dataclasses.replace(
            result, refs=tuple(field_refs) + tuple(result.refs)
        )
    return result


def link_to_payload(result: LinkResult) -> dict[str, object]:
    """Serialize a LinkResult for the draft response (JSON-safe)."""
    return {
        "status": result.status,
        "activity_id": result.activity_id,
        "basis": result.basis,
        "candidates": [
            {
                "activity_id": c.activity_id,
                "name": c.name,
                "basis": c.basis,
                "amount": c.amount,
                "occurred_at": c.occurred_at,
                "employee": c.employee,
            }
            for c in result.candidates
        ],
        "reasons": list(result.reasons),
        "conflicting_fields": list(result.conflicting_fields),
        "owner": result.owner,
        "requires_confirmation": result.requires_confirmation,
        "inherited": result.inherited,
        "refs": [r.model_dump(mode="json") for r in result.refs],
    }
