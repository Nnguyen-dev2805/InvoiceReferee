"""Pure advance transaction identity + party guards (14/10/2026).

The accountant uploads an advance voucher; the EMPLOYEE upload never becomes
confirmed money by itself. This module is PURE: no I/O, no model call.

- ``build_external_key`` builds ``"<namespace>:<reference>"`` or None when the
  source has no transaction identity. Callers must NOT mint a UUID fallback
  and claim dedup protection.
- ``check_advance_parties`` blocks a CONFIRMED advance when the voucher payee
  is not the dossier employee, when the payer does not match the configured
  company source, or when a name is still unresolved.
- ``check_record_payload`` distinguishes a re-sent transaction (IDEMPOTENT)
  from the same reference with different material content (CONFLICT).
- ``decide_advance_resolution`` keeps PENDING/FAILED/UNKNOWN and
  confirmation-less claims OBSERVED, and missing identity UNRESOLVED.
- ``resolve_event_times`` keeps the source ``event_at`` apart from the
  server ``recorded_at``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PartyCheck:
    ok: bool
    reason: str


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def build_external_key(namespace: str | None, reference: str | None) -> str | None:
    """Return ``"<namespace>:<reference>"`` or None when identity is missing.

    A missing/blank namespace or reference stays unresolved — never a UUID.
    """
    ns = (namespace or "").strip().casefold()
    ref = (reference or "").strip()
    if not ns or not ref:
        return None
    return f"{ns}:{ref}"


def check_advance_parties(
    *,
    payee_name: str | None,
    employee: str,
    payer_name: str | None = None,
    expected_payer_names: tuple[str, ...] | None = None,
    employee_aliases: tuple[str, ...] = (),
    accept_company_ids: bool = True,
) -> PartyCheck:
    """Verify the voucher parties against the dossier and company source.

    The payee must be the dossier employee (id or display name). The payer
    must be the configured company source: the organization name from the
    imported context or a ``company:*`` namespaced source id — never a
    hard-coded company id for every context, and never an arbitrary name.
    An unresolved name stays unresolved for the accountant.
    """
    if payee_name is None or not str(payee_name).strip():
        return PartyCheck(
            ok=False,
            reason="Người nhận chưa xác định được; giữ unresolved cho kế toán xử lý.",
        )
    candidates = {_norm(employee)} | {
        _norm(a) for a in employee_aliases if str(a).strip()
    }
    if _norm(payee_name) not in candidates:
        return PartyCheck(
            ok=False,
            reason=f"Người nhận trên chứng từ ({payee_name}) khác nhân viên của hồ sơ; chặn công nhận ứng thực nhận.",
        )
    if payer_name is None or not str(payer_name).strip():
        return PartyCheck(
            ok=False,
            reason="Bên chi chưa xác định được; giữ unresolved cho kế toán xử lý.",
        )
    wanted = {_norm(name) for name in (expected_payer_names or ()) if str(name).strip()}
    if _norm(payer_name) in wanted:
        return PartyCheck(ok=True, reason="Người nhận và bên chi đã đối chiếu khớp.")
    if accept_company_ids and str(payer_name).strip().casefold().startswith("company:"):
        return PartyCheck(
            ok=True,
            reason="Bên chi là nguồn quỹ công ty có namespace; kế toán đã xác nhận có trách nhiệm.",
        )
    return PartyCheck(
        ok=False,
        reason=f"Bên chi trên chứng từ ({payer_name}) không khớp nguồn quỹ công ty đã cấu hình; kế toán kiểm tra.",
    )


def check_record_payload(
    existing: dict[str, object], claim: dict[str, object]
) -> Literal["IDEMPOTENT", "CONFLICT"]:
    """Compare a re-sent claim against the stored event with the same key.

    Only an identical material payload (kind/amount/payer/payee/scope) is an
    idempotent replay; any material difference is a conflict — never a silent
    success and never a double count.
    """
    for field in ("kind", "amount", "payer", "payee", "scope"):
        if existing.get(field) != claim.get(field):
            return "CONFLICT"
    return "IDEMPOTENT"


def decide_advance_resolution(
    *,
    amount: int | None,
    instrument_status: str | None,
    external_key: str | None,
    has_responsible_confirmation: bool,
) -> Literal["CONFIRMED", "OBSERVED", "UNRESOLVED_MISSING_IDENTITY"]:
    """Decide whether an advance claim may become confirmed money."""
    if external_key is None or amount is None:
        return "UNRESOLVED_MISSING_IDENTITY"
    if instrument_status != "COMPLETED":
        return "OBSERVED"
    if not has_responsible_confirmation:
        return "OBSERVED"
    return "CONFIRMED"


def resolve_event_times(
    *, event_at: str | None, recorded_at: str
) -> dict[str, str | None]:
    """Keep the source transaction time apart from the server record time."""
    return {"event_at": event_at, "recorded_at": recorded_at}
