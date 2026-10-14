"""Pure dossier↔advance/activity linking (server-owned identity; 14/10/2026).

The employee uploads settlement documents and reviews a draft; the BACKEND
decides which advance/work dossier the settlement belongs to. The employee never
picks a standing "activity" code. This module is PURE: no I/O, no model call. It
expresses, with source refs, one of four outcomes:

- ``LINKED``            a strong basis identified exactly one dossier/activity;
- ``NEEDS_CONFIRMATION`` only a weak basis (name/purpose/date/amount) matched, or
  several candidates remain — a human must confirm;
- ``NOT_FOUND``         no basis matched; the draft is accepted as a NEW,
  server-owned dossier (no fabricated budget/grant);
- ``CONFLICT``          strong bases point at DIFFERENT dossiers — the conflict is
  kept, never resolved by priority order or by dropping the contradicting source.

Basis priority (strongest first):
  A. INHERITED            the settlement started from a known advance dossier
                          (a server-owned link on the root).
  B. DOCUMENT_REFERENCE   an advance/dossier number printed on the document,
                          matched in THIS company with a unique namespace.
  C. TRANSACTION_IDENTITY a transaction/voucher code that already exists in the
                          company ledger, matched by a namespaced reference.
  D. WEAK_SIMILARITY      name/purpose/date/amount similarity — candidates only,
                          never an automatic link even when there is just one.

The LLM extracts; code decides. Exact equality of purpose/name is NEVER an
automatic link, and the first list element is never taken as the answer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from invoice_referee.domain.common import EvidenceRef

LinkStatus = Literal["LINKED", "NEEDS_CONFIRMATION", "NOT_FOUND", "CONFLICT"]
LinkBasis = Literal[
    "INHERITED", "DOCUMENT_REFERENCE", "TRANSACTION_IDENTITY", "WEAK_SIMILARITY"
]

# Order matters: a stronger basis outranks a weaker one when picking the result.
_BASIS_RANK: dict[str, int] = {
    "INHERITED": 4,
    "DOCUMENT_REFERENCE": 3,
    "TRANSACTION_IDENTITY": 2,
    "WEAK_SIMILARITY": 1,
}


@dataclass(frozen=True)
class ActivityCandidate:
    """One catalog activity a settlement could belong to (server-owned)."""

    activity_id: str
    name: str
    status: str = "AUTHORIZED"
    purpose: str | None = None
    # The namespaced reference(s) printed on an advance/dossier for THIS activity
    # (e.g. "TU-2026-001"). A bare number is not a global unique id.
    references: tuple[str, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class LedgerTxn:
    """A company ledger money event used for reference matching (read-only)."""

    external_key: str
    activity: str
    employee: str
    amount: int
    kind: str
    # The namespaced transaction identity: "<namespace>:<reference>"
    # (e.g. "bank:ACB-001", "cash:PC-2026-014"). None when the source has none.
    namespace: str | None = None
    reference: str | None = None
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class LinkCandidate:
    """One dossier/activity the settlement could link to, with its basis."""

    activity_id: str
    name: str
    basis: LinkBasis
    refs: tuple[EvidenceRef, ...] = ()
    amount: int | None = None
    occurred_at: str | None = None
    employee: str | None = None


@dataclass(frozen=True)
class LinkResult:
    """The server's linking decision for one settlement draft."""

    status: LinkStatus
    activity_id: str | None = None
    basis: LinkBasis | None = None
    candidates: tuple[LinkCandidate, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()
    reasons: tuple[str, ...] = ()
    # The material fields the strong bases disagreed on (CONFLICT only).
    conflicting_fields: tuple[str, ...] = ()
    # Who must resolve an open question: "employee" (confirm a link) or
    # "accountant" (a money/identity question). None when nothing is open.
    owner: str | None = None
    requires_confirmation: bool = False
    # True when the result was derived from a server-owned inherited link.
    inherited: bool = False


def _norm(value: object) -> str:
    """Format-only normalization (case/whitespace/diacritics). No fuzzy match."""
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _ref_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _refs_match(a: str, b: str) -> bool:
    """Two references name the same document.

    Normalized-equal always matches. A suffix match tolerates a serial prefix
    ("IR26E00000101" vs "00000101": the char before the suffix is a letter), but
    NOT a bare number that is glued to a preceding digit ("001" vs "TU-2026-001"
    → "2026001"): there the "001" is part of a larger number, not its own token.
    """
    na, nb = _ref_key(a), _ref_key(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if len(na) < len(nb):
        shorter, longer = na, nb
    elif len(nb) < len(na):
        shorter, longer = nb, na
    else:
        return False
    if not longer.endswith(shorter):
        return False
    # Reject a suffix that is glued to a preceding DIGIT (part of a bigger number).
    preceding = longer[len(longer) - len(shorter) - 1]
    return not preceding.isdigit()


def link_dossier(
    *,
    employee: str,
    current_activity: str | None,
    current_activity_proposed: bool,
    document_references: tuple[str, ...] = (),
    transaction_references: tuple[str, ...] = (),
    catalog: tuple[ActivityCandidate, ...] = (),
    ledger: tuple[LedgerTxn, ...] = (),
    weak_text: str | None = None,
    weak_amount: int | None = None,
    weak_date: str | None = None,
) -> LinkResult:
    """Decide which dossier/activity a settlement belongs to (pure).

    Only strong bases (A/B/C) can produce ``LINKED``; the weak basis (D) can only
    produce candidates. Strong bases pointing at different dossiers produce
    ``CONFLICT`` and are never collapsed by priority order.
    """
    strong: list[LinkCandidate] = []
    reasons: list[str] = []

    # A. INHERITED: a known server-owned link on the root.
    if current_activity and not current_activity_proposed:
        entry = _find_activity(catalog, current_activity)
        strong.append(
            LinkCandidate(
                activity_id=current_activity,
                name=entry.name if entry is not None else current_activity,
                basis="INHERITED",
                refs=entry.refs if entry is not None else (),
                employee=employee,
            )
        )
        reasons.append("Hồ sơ quyết toán kế thừa liên kết tạm ứng đã có trên máy chủ.")

    # B. DOCUMENT_REFERENCE: an advance/dossier number printed on the document.
    for ref in document_references:
        for entry in catalog:
            if any(_refs_match(ref, candidate) for candidate in entry.references):
                strong.append(
                    LinkCandidate(
                        activity_id=entry.activity_id,
                        name=entry.name,
                        basis="DOCUMENT_REFERENCE",
                        refs=entry.refs,
                        employee=employee,
                    )
                )
                reasons.append(
                    f"Số hồ sơ/tạm ứng '{ref}' trên tài liệu khớp hoạt động {entry.activity_id}."
                )

    # C. TRANSACTION_IDENTITY: a namespaced transaction code in the ledger.
    for ref in transaction_references:
        for txn in ledger:
            if txn.reference is None:
                continue
            if _refs_match(ref, txn.reference) or (
                txn.namespace is not None and _refs_match(ref, f"{txn.namespace}:{txn.reference}")
            ):
                strong.append(
                    LinkCandidate(
                        activity_id=txn.activity,
                        name=_activity_name(catalog, txn.activity),
                        basis="TRANSACTION_IDENTITY",
                        refs=txn.refs,
                        amount=txn.amount,
                        employee=txn.employee,
                    )
                )
                reasons.append(
                    f"Mã giao dịch '{ref}' đã có trong lịch sử công ty (hoạt động {txn.activity})."
                )

    # A strong basis to a DIFFERENT employee is a material contradiction, not a
    # link: the settlement's employee must own the linked dossier.
    mismatched = [c for c in strong if c.employee is not None and _norm(c.employee) != _norm(employee)]
    if mismatched:
        return LinkResult(
            status="CONFLICT",
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons) + (
                "Căn cứ mạnh trỏ tới hồ sơ của nhân viên khác; không tự gắn.",
            ),
            conflicting_fields=("employee",),
            owner="accountant",
        )

    distinct = _distinct_activities(strong)
    if len(distinct) > 1:
        # Strong bases to different dossiers: keep the conflict.
        return LinkResult(
            status="CONFLICT",
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons) + (
                "Nhiều căn cứ mạnh trỏ tới các hồ sơ khác nhau; giữ mâu thuẫn để xác minh.",
            ),
            conflicting_fields=("activity",),
            owner="accountant",
        )
    if len(distinct) == 1:
        best = max(strong, key=lambda c: _BASIS_RANK[c.basis])
        return LinkResult(
            status="LINKED",
            activity_id=best.activity_id,
            basis=best.basis,
            candidates=tuple(_dedupe(strong)),
            refs=_all_refs(strong),
            reasons=tuple(reasons),
            inherited=best.basis == "INHERITED",
        )

    # D. WEAK_SIMILARITY: candidates only, never an automatic link.
    weak = _weak_candidates(
        catalog, text=weak_text, amount=weak_amount, date=weak_date, employee=employee
    )
    if weak:
        return LinkResult(
            status="NEEDS_CONFIRMATION",
            candidates=weak,
            refs=tuple(r for c in weak for r in c.refs),
            reasons=(
                "Chỉ có căn cứ yếu (tên/nội dung/ngày/số tiền); cần người xác nhận.",
            ),
            owner="employee",
            requires_confirmation=True,
        )

    return LinkResult(
        status="NOT_FOUND",
        reasons=("Không tìm thấy hồ sơ tạm ứng/công việc khớp; tiếp nhận hồ sơ độc lập.",),
    )


def _find_activity(
    catalog: tuple[ActivityCandidate, ...], activity_id: str
) -> ActivityCandidate | None:
    for entry in catalog:
        if entry.activity_id == activity_id:
            return entry
    return None


def _activity_name(catalog: tuple[ActivityCandidate, ...], activity_id: str) -> str:
    entry = _find_activity(catalog, activity_id)
    return entry.name if entry is not None else activity_id


def _distinct_activities(candidates: list[LinkCandidate]) -> set[str]:
    return {c.activity_id for c in candidates}


def _dedupe(candidates: list[LinkCandidate]) -> list[LinkCandidate]:
    seen: set[tuple[str, str]] = set()
    out: list[LinkCandidate] = []
    for c in candidates:
        key = (c.activity_id, c.basis)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _all_refs(candidates: list[LinkCandidate]) -> tuple[EvidenceRef, ...]:
    return tuple(r for c in candidates for r in c.refs)


def _weak_candidates(
    catalog: tuple[ActivityCandidate, ...],
    *,
    text: str | None,
    amount: int | None,
    date: str | None,
    employee: str,
) -> tuple[LinkCandidate, ...]:
    """Name/purpose similarity candidates. Never an automatic link, even if one.

    A weak match is a human-confirmable candidate: the purpose/name overlaps the
    activity's purpose/name. Amount/date are comparison metadata, not identity.
    """
    if not text:
        return ()
    needle = _norm(text)
    if not needle:
        return ()
    out: list[LinkCandidate] = []
    for entry in catalog:
        haystacks = [entry.name, entry.purpose or ""]
        if any(needle == _norm(h) for h in haystacks if h):
            out.append(
                LinkCandidate(
                    activity_id=entry.activity_id,
                    name=entry.name,
                    basis="WEAK_SIMILARITY",
                    refs=entry.refs,
                    amount=amount,
                    occurred_at=date,
                    employee=employee,
                )
            )
    return tuple(out)
