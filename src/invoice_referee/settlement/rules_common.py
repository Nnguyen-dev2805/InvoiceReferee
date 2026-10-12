"""Shared rule helpers: constants, validation and fact resolution.

Key suffixes, money validation, coverage grants and the fact/quality/relation
resolvers used by both the B7 and B3 evaluators. ``rules.py`` imports these and
re-exports the public names.
"""
from __future__ import annotations

from typing import Any, Mapping

from invoice_referee.shared.errors import DomainError
from invoice_referee.settlement.models import (
    CheckResult,
    CriticalFact,
    Issue,
    MoneyComponents,
    Observation,
    Relation,
    RunInput,
)


MONEY_KEY_SUFFIXES = (
    ".amount", ".received", ".returned", "budget.approved",
    "advance.request.amount", "forecast.employee",
)

HISTORY_KEYS = (
    "history.advance.received", "history.advance.returned",
    "history.reimbursement.received", "history.reimbursement.returned",
)


def calculate_net(components: MoneyComponents) -> int | None:
    """S = E - (A - RA) - (P - RP); any unknown component keeps the result None."""
    values = (components.e, components.a, components.ra, components.p, components.rp)
    if any(value is None for value in values):
        return None
    return components.e - (components.a - components.ra) - (components.p - components.rp)


# --- input validation (SYS-02: reject before aggregation) -------------------

def _validate_money(value: Any, key: str, fact_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DomainError(
            "INVALID_MONEY",
            f"Trường tiền {key} (fact {fact_id}) phải là integer VND, không bool/float/chuỗi.",
        )
    return value


def _validate_observations(observations: list[Observation]) -> None:
    """Reject duplicate IDs and non-integer money before any aggregation."""
    seen: set[str] = set()
    for observation in observations:
        if observation.fact_id in seen:
            raise DomainError(
                "DUPLICATE_FACT_ID",
                f"Fact ID trùng {observation.fact_id}; không ghi đè âm thầm.",
            )
        seen.add(observation.fact_id)
        if observation.read_state != "READ":
            continue
        if any(observation.key.endswith(suffix) or observation.key == suffix
                for suffix in MONEY_KEY_SUFFIXES):
            _validate_money(observation.value, observation.key, observation.fact_id)


def _is_money_key(key: str) -> bool:
    return any(key.endswith(suffix) or key == suffix for suffix in MONEY_KEY_SUFFIXES)


def _advance_event_refs(observations: list[Observation]) -> dict[str, Any]:
    """Collect sourced advance-event metadata (plan Task 3.3 reader keys).

    Recognises ``history.advance_event.<event_ref>.<field>`` where field is
    amount / receiver_ref / decision_ref / outcome / event_at. Missing metadata
    yields None fields (never guessed), and refs fall back to the fact sources.
    """
    info: dict[str, Any] = {"event_ref": None, "amount": None,
                            "receiver_ref": None, "decision_ref": None,
                            "outcome": None, "event_at": None, "refs": []}
    for observation in observations:
        parts = observation.key.split(".")
        if len(parts) == 4 and parts[0] == "history" \
                and parts[1] == "advance_event":
            event_ref, field = parts[2], parts[3]
            info["event_ref"] = event_ref
            if field in ("amount", "receiver_ref", "decision_ref", "outcome",
                         "event_at"):
                info[field] = observation.value
            for ref in (observation.source_id, observation.fact_id):
                if ref and ref not in info["refs"]:
                    info["refs"].append(ref)
    return info


def _advance_question(info: Mapping[str, Any], run_input: RunInput) -> str:
    """A specific advance-receipt question with event/amount/decision/cutoff."""
    cutoff = run_input.submission.money_as_of.isoformat()
    event_ref = info.get("event_ref") or "lệnh ứng"
    amount = info.get("amount")
    amount_txt = f"{amount:,} đ".replace(",", ".") if isinstance(amount, int) \
        else "số tiền đề nghị"
    decision = info.get("decision_ref")
    receiver = info.get("receiver_ref") or run_input.submission.employee_ref
    decision_txt = f" theo {decision}" if decision else ""
    return (f"Lệnh ứng {event_ref}, số đề nghị {amount_txt} cho {receiver}"
            f"{decision_txt}, chưa xác định tiền đã tới người nhận trước "
            f"{cutoff}. Vui lòng bổ sung biên nhận phía nhận hoặc kết quả đối "
            f"chiếu xác định số thực nhận/trạng thái cuối.")


def covering_grant(authority: list, employee_ref: str, work_ref: str,
                   effective_at: datetime, employee_cost_vnd: int | None,
                   settlement_vnd: int | None,
                   total_work_cost_vnd: int | None,
                   exception_required: bool = False):
    """Return a grant that covers the content, or None (Rulebook R8).

    A grant covers only when: the work/employee scope matches, the grant is
    effective at ``effective_at``, the employee cost is within
    ``max_employee_cost_vnd`` (a missing limit does NOT cover), and the absolute
    settlement is within ``max_settlement_vnd``. When ``exception_required``,
    the total work cost must be within ``max_exception_work_cost_vnd`` (a null
    exception limit does not cover). No limit is treated as unlimited.
    """
    for grant in authority:
        if grant.work_ref is not None and grant.work_ref != work_ref:
            continue
        if getattr(grant, "employee_ref", None) is not None \
                and grant.employee_ref != employee_ref:
            continue
        start = getattr(grant, "effective_from", None)
        end = getattr(grant, "effective_until", None)
        if start is not None and effective_at < start:
            continue
        if end is not None and effective_at > end:
            continue
        if employee_cost_vnd is not None:
            cap = getattr(grant, "max_employee_cost_vnd", None)
            if cap is None or employee_cost_vnd > cap:
                continue
        if settlement_vnd is not None:
            if abs(settlement_vnd) > grant.max_settlement_vnd:
                continue
        if exception_required:
            exc = getattr(grant, "max_exception_work_cost_vnd", None)
            if exc is None or total_work_cost_vnd is None \
                    or total_work_cost_vnd > exc:
                continue
        return grant
    return None


# --- fact resolution: quality, contradictions, no silent pick ---------------

def _usable_entries(observations: list[Observation],
                    key: str) -> list[Observation]:
    """Only READ + USABLE observations can make a value known."""
    return [o for o in observations
            if o.key == key and o.read_state == "READ" and o.usability == "USABLE"]


def _nonusable_entries(observations: list[Observation],
                       key: str) -> list[Observation]:
    """READ facts refused by the quality gate (never fabricated into known)."""
    return [o for o in observations
            if o.key == key and o.read_state == "READ" and o.usability != "USABLE"]


def _unclear_entries(observations: list[Observation],
                     key: str) -> list[Observation]:
    return [o for o in observations
            if o.key == key and o.read_state == "UNCLEAR"]


def _resolve(observations: list[Observation], key: str
             ) -> tuple[Any | None, list[str], bool]:
    """Resolve one key: (value, refs, contradicted); no first-non-null pick."""
    entries = _usable_entries(observations, key)
    if not entries:
        return None, [], False
    refs: list[str] = []
    for entry in entries:
        refs.extend([entry.source_id, entry.fact_id])
    distinct: list[Any] = []
    for entry in entries:
        if entry.value not in distinct:
            distinct.append(entry.value)
    if len(distinct) > 1:
        return None, refs, True
    return entries[0].value, refs, False


def _fact_state(observations: list[Observation], key: str) -> CriticalFact:
    """Expose one consumed fact with its quality state (KNOWN..UNUSABLE)."""
    value, refs, contradicted = _resolve(observations, key)
    if contradicted:
        return CriticalFact(key=key, value=None, state="CONTRADICTED", refs=refs)
    if value is not None:
        return CriticalFact(key=key, value=value, state="KNOWN", refs=refs)
    bad = _nonusable_entries(observations, key)
    if bad:
        return CriticalFact(key=key, value=None, state="UNUSABLE",
                             refs=[ref for o in bad
                                   for ref in (o.source_id, o.fact_id)])
    bad = _unclear_entries(observations, key)
    if bad:
        return CriticalFact(key=key, value=None, state="UNCLEAR",
                             refs=[ref for o in bad
                                   for ref in (o.source_id, o.fact_id)])
    return CriticalFact(key=key, value=None, state="UNKNOWN", refs=refs)


def _contradiction_issues(contradictions: list[tuple[str, list[str]]],
                          issues: list[Issue],
                          checks: list[CheckResult]) -> None:
    """One issue per contradictory key; money keys are MONEY_INCIDENT."""
    for key, refs in contradictions:
        if key in HISTORY_KEYS or key == "budget.approved":
            owner = "ACCOUNTANT"
            blocked = "net" if key in HISTORY_KEYS else "budget"
        else:
            owner = "EMPLOYEE"
            blocked = "components"
        issue_type = "MONEY_INCIDENT" if _is_money_key(key) else "FACT"
        issues.append(Issue(
            issue_id="I-CONTRADICTION", type=issue_type,  # type: ignore[arg-type]
            owner=owner,  # type: ignore[arg-type]
            message=f"Hai nguồn cho {key} khác nhau; giữ cả hai refs, "
                    f"không chọn một, không suy bằng 0.",
            refs=refs, blocked=blocked,
        ))
    if contradictions:
        keys = [key for key, _ in contradictions]
        checks.append(CheckResult(
            rule="contradictions", status="FAIL", refs=keys,
            reason="Có mâu thuẫn số liệu giữa các nguồn; làm rõ trước."))


def _quality_issues(observations: list[Observation], keys: list[str],
                    issues: list[Issue], checks: list[CheckResult]) -> None:
    """READ-but-unusable facts never become known (numeric quality gate)."""
    bad: list[str] = []
    for key in keys:
        bad.extend(ref for o in _nonusable_entries(observations, key)
                   for ref in (o.source_id, o.fact_id))
    if not bad:
        return
    checks.append(CheckResult(
        rule="fact_quality", status="UNRESOLVED", refs=bad,
        reason="Có fact đọc được nhưng chất lượng không đủ dùng làm known."))
    issues.append(Issue(
        issue_id="I-QUALITY", type="FACT", owner="EMPLOYEE",
        message="Có fact chất lượng không đạt (mờ/thiếu căn cứ); cần nguồn "
                "đọc được rõ hơn, không dùng READABLE thay số hợp lệ.",
        refs=bad, blocked="components",
    ))


def _link_issues(relations: list[Relation], issues: list[Issue],
                 checks: list[CheckResult]) -> None:
    """Only ESTABLISHED relations reconcile; others are surfaced, not used."""
    unestablished = [r.relation_id for r in relations
                     if r.status != "ESTABLISHED"]
    if not unestablished:
        checks.append(CheckResult(
            rule="relation_status", status="PASS",
            refs=[r.relation_id for r in relations],
            reason="Mọi quan hệ đối chiếu đã được xác lập."))
        return
    checks.append(CheckResult(
        rule="relation_status", status="UNRESOLVED", refs=unestablished,
        reason="Có quan hệ chưa ESTABLISHED (PROPOSED/UNCLEAR); không dùng "
               "làm căn cứ đối chiếu tiền."))
    issues.append(Issue(
        issue_id="I-LINK", type="FACT", owner="EMPLOYEE",
        message="Có quan hệ expense–payment/same-event chưa được xác lập; "
                "cần nguồn xác nhận, không tự coi đã ghép.",
        refs=unestablished, blocked="components",
    ))


def _validate_relations(relations: list[Relation],
                       expense_ids: set[str], payment_ids: set[str],
                       claim_ids: set[str] | None = None) -> None:
    seen: set[str] = set()
    known = expense_ids | payment_ids
    for relation in relations:
        if relation.relation_id in seen:
            raise DomainError(
                "DUPLICATE_RELATION_ID",
                f"Relation ID trùng {relation.relation_id}; không ghi đè âm thầm.",
            )
        seen.add(relation.relation_id)
        for ref in (relation.from_id, relation.to_id):
            if relation.kind == "EXPENSE_PAYMENT":
                if relation.from_id not in expense_ids or relation.to_id not in payment_ids:
                    raise DomainError(
                        "UNKNOWN_REF",
                        f"Relation {relation.relation_id} tham chiếu đối tượng không có trong facts ({ref}).",
                    )
            elif relation.kind == "CLAIM_EXPENSE":
                if claim_ids is None or relation.from_id not in claim_ids \
                        or relation.to_id not in expense_ids:
                    raise DomainError(
                        "UNKNOWN_REF",
                        f"Relation {relation.relation_id} tham chiếu claim/expense không có trong facts ({ref}).",
                    )
            elif relation.from_id not in known or relation.to_id not in known:
                raise DomainError(
                    "UNKNOWN_REF",
                    f"Relation {relation.relation_id} tham chiếu đối tượng không có trong facts ({ref}).",
                )
        if relation.portion_vnd is not None:
            _validate_money(relation.portion_vnd, f"relation.{relation.relation_id}",
                            relation.relation_id)


