"""T07 human-action validation: role/scope, payload schema and revision
(System §7, Rulebook §5).

Ledger §3.2 signature: ``validate_human_action(action, snapshot, decision) ->
HumanAction``. The returned (validated) action is the ONLY input the service
passes to ``Repository.apply_human_action``; the repository then applies it in
ONE transaction. This module is pure: it reads the snapshot/decision and raises
``DomainError('INVALID_ACTION')`` — it never touches SQLite, providers or the UI.

Design rulings (recorded at T07):

- **Discriminated payload validation.** Every kind has an exact allowed key set
  (extra keys rejected, e.g. no ``approve_all`` boolean) and a required subset.
  A confirmation is effective only for the field/source/case-version it names.
- **Role/scope is enforced here.** EMPLOYEE cannot approve/waive; REVIEWER
  confirms fields/mappings; APPROVER approves amounts up to the standard policy
  max; POLICY_OWNER grants a scoped exception and (only with a matching
  exception) approves an amount above the standard max. Demo modes are not
  enterprise identity, but the backend still checks the business meaning.
- **Approvals/exceptions bind to case_version, policy_version, profile, purpose
  and amount** (``authorization_matches``). A mismatched authorization never
  authorizes.
- **Declarations/evidence/confirmed facts change effective data** (repository
  bumps case_version and invalidates authorizations); approval/exception only
  changes active action IDs (input hash). This module validates; the repository
  applies.
- **No approve-all boolean, no raw-OCR edit.** A REVIEWER confirmation must name
  owned refs; it adds a HumanConfirmedFact, it does not rewrite OCR.
- **Partial allocation** is not supported in B1: a correction over only part of a
  bill is refused with a request to split the case, never an arbitrary amount.

Scope of T07's validation (signature has no bundle): this module enforces
role/scope, the exact payload keyset (extra keys rejected, including inside an
OVERRIDE), ownership of referenced evidence, the field-path SHAPE (evidence +
fields/items + item_id + sub-field), and the canonical form of a confirmed value.
It CANNOT resolve refs against a `SourceRegistry`, prove full item coverage, or
check unit ambiguity — those need the `EvidenceBundle`, which only the T08
service holds. T08 is assigned the DEEP checks (ref resolution, full mapping
coverage, non-ambiguous units) and wiring confirmations into `process()`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from invoice_referee.domain.models import (
    Authorization,
    CaseSnapshot,
    Claim,
    Decision,
    DemoMode,
    DomainError,
    HumanAction,
)

# --- Exact payload schemas (discriminated union, extra keys rejected) ----------
# kind -> (required keys, allowed keys)
_SCHEMA: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    'SUPPLY_DECLARATION': (frozenset({'changes'}), frozenset({'changes'})),
    'ADD_EVIDENCE': (frozenset({'evidence_ids'}), frozenset({'evidence_ids'})),
    'PROPOSE_CORRECTION': (frozenset({'field', 'value'}), frozenset({'field', 'value', 'refs'})),
    'CONFIRM_FIELD': (frozenset({'field', 'value', 'refs'}), frozenset({'field', 'value', 'refs'})),
    'CONFIRM_MAPPING': (frozenset({'pairs', 'refs'}), frozenset({'pairs', 'refs'})),
    'GRANT_POLICY_EXCEPTION': (
        frozenset({'amount_vnd', 'profile', 'purpose', 'policy_version'}),
        frozenset({'amount_vnd', 'profile', 'purpose', 'policy_version'}),
    ),
    'APPROVE_AMOUNT': (
        frozenset({'amount_vnd', 'profile', 'purpose', 'policy_version'}),
        frozenset({'amount_vnd', 'profile', 'purpose', 'policy_version'}),
    ),
    'DENY': (frozenset({'issue_id'}), frozenset({'issue_id'})),
    'OVERRIDE': (frozenset({'operation', 'values'}), frozenset({'operation', 'values'})),
    'STOP': (frozenset({'run_id'}), frozenset({'run_id'})),
    # CLASSIFY_PROFILE is only reachable as an OVERRIDE operation; its inner
    # payload is validated against this entry.
    'CLASSIFY_PROFILE': (frozenset({'profile'}), frozenset({'profile'})),
}

# OVERRIDE is a wrapper around exactly these operations (System §7).
_OVERRIDE_OPERATIONS = {
    'CONFIRM_FIELD', 'CONFIRM_MAPPING', 'CLASSIFY_PROFILE',
    'GRANT_POLICY_EXCEPTION', 'APPROVE_AMOUNT', 'DENY',
}

# CLASSIFY_PROFILE only reclassifies an OTHER case into a supported catalog
# profile; it may not invent a profile or reopen an OTHER case.
_CLASSIFY_TARGETS = {'TRAVEL', 'CLIENT_MEAL', 'WORK_PURCHASE'}

# A field path names an evidence and either its total or an item sub-field.
_ITEM_SUBFIELDS = {'quantity', 'unit', 'unit_price', 'line_amount', 'name'}
_CLAIM_FIELDS = {
    'employee_id', 'profile', 'purpose_type', 'purpose', 'trip', 'attendees',
    'requested_amount_vnd', 'payer_type', 'received_full',
}

# Technical money bound (ledger §3.1); a claim/payment amount is a positive
# integer VND at or below this. It is a parser bound, not a company allowance.
_MAX_VND = 999_999_999_999_999


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_ACTION', message)


def validate_human_action(
    action: HumanAction, snapshot: CaseSnapshot, decision: Decision
) -> HumanAction:
    """Validate a human action against role/scope/payload/version.

    Returns the SAME action when valid (it is already immutable and carries the
    scope); raises ``DomainError('INVALID_ACTION')`` otherwise. The service must
    apply only the returned action.
    """
    if action.case_id != snapshot.case_id:
        raise _invalid('Hành động không thuộc hồ sơ này.')
    if action.case_version != snapshot.case_version:
        raise _invalid('Hành động gắn với case_version cũ; cần tải lại hồ sơ.')
    if not action.reason or not action.reason.strip():
        raise _invalid('Cần lý do cho hành động.')

    _validate_payload_keys(action)
    handler = _HANDLERS.get(action.kind)
    if handler is None:
        raise _invalid(f'Loại hành động không hỗ trợ: {action.kind}.')
    handler(action, snapshot, decision)
    return action


# --- Payload keyset ------------------------------------------------------------

def _validate_payload_keys(action: HumanAction) -> None:
    required, allowed = _SCHEMA[action.kind]
    keys = set(action.payload)
    extra = keys - allowed
    if extra:
        raise _invalid(f'{action.kind} có trường không hợp lệ: {sorted(extra)}.')
    missing = required - keys
    if missing:
        raise _invalid(f'{action.kind} thiếu trường: {sorted(missing)}.')


# --- Role and value helpers ----------------------------------------------------

def _require_mode(action: HumanAction, *modes: DemoMode) -> None:
    if action.mode not in modes:
        raise _invalid(
            f'{action.kind} cần mode {" hoặc ".join(modes)}; nhận {action.mode}.'
        )


def _positive_vnd(value: object, field: str = 'amount_vnd') -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _invalid(f'{field} phải là số nguyên dương VND.')
    if value > _MAX_VND:
        raise _invalid(f'{field} vượt giới hạn kỹ thuật.')
    return value


def _refs(payload: dict, *, field: str = 'refs') -> list:
    refs = payload.get(field)
    if not isinstance(refs, list) or not refs:
        raise _invalid(f'{field} phải là danh sách nguồn không rỗng.')
    return refs


def _owned_evidence_ids(snapshot: CaseSnapshot) -> set[str]:
    return {ev.id for ev in snapshot.evidence}


def _ref_evidence_id(ref: object) -> str | None:
    if isinstance(ref, dict):
        value = ref.get('evidence_id')
        return value if isinstance(value, str) else None
    value = getattr(ref, 'evidence_id', None)
    return value if isinstance(value, str) else None


def _require_owned_refs(action: HumanAction, snapshot: CaseSnapshot, refs: list) -> None:
    owned = _owned_evidence_ids(snapshot)
    for ref in refs:
        evidence_id = _ref_evidence_id(ref)
        if evidence_id is None:
            raise _invalid('Nguồn tham chiếu thiếu evidence_id.')
        if evidence_id not in owned:
            raise _invalid(f'Nguồn {evidence_id} không thuộc hồ sơ này.')


def _find_issue(issue_id: object, decision: Decision):
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise _invalid('issue_id không hợp lệ.')
    for issue in decision.issues:
        if issue.id == issue_id:
            return issue
    raise _invalid(f'Không tìm thấy issue {issue_id} trong decision hiện hành.')


# --- Handlers per kind ---------------------------------------------------------

def _handle_supply_declaration(action, snapshot, decision) -> None:
    _require_mode(action, 'EMPLOYEE')
    changes = action.payload['changes']
    if not isinstance(changes, dict) or not changes:
        raise _invalid('changes phải là dict không rỗng.')
    unknown = set(changes) - _CLAIM_FIELDS
    if unknown:
        raise _invalid(f'Khai báo có trường không thuộc Claim: {sorted(unknown)}.')
    # Profile classification is not an employee declaration: only a POLICY_OWNER
    # OVERRIDE classify may move OTHER into a supported catalog profile.
    if 'profile' in changes and changes['profile'] != snapshot.claim.profile:
        raise _invalid('Phân loại profile chỉ do POLICY_OWNER thực hiện bằng OVERRIDE classify.')
    # Type-check the changed fields against the Claim contract HERE, so a
    # malformed value surfaces as INVALID_ACTION (not a raw pydantic error at
    # apply time). Only the changed fields are overridden; the rest stay valid.
    try:
        Claim.model_validate({**snapshot.claim.model_dump(), **changes})
    except ValidationError as exc:
        raise _invalid(f'Khai báo sai kiểu/giá trị: {exc.error_count()} trường không hợp lệ.')


def _handle_add_evidence(action, snapshot, decision) -> None:
    _require_mode(action, 'EMPLOYEE')
    evidence_ids = action.payload['evidence_ids']
    if not isinstance(evidence_ids, list) or not evidence_ids:
        raise _invalid('evidence_ids phải là danh sách không rỗng.')
    owned = _owned_evidence_ids(snapshot)
    for evidence_id in evidence_ids:
        if not isinstance(evidence_id, str) or evidence_id not in owned:
            raise _invalid(
                f'Evidence {evidence_id!r} không thuộc hồ sơ này; '
                'chỉ nhận chứng từ đã tải lên backend.'
            )


def _handle_propose_correction(action, snapshot, decision) -> None:
    _require_mode(action, 'EMPLOYEE')
    field = action.payload['field']
    if not isinstance(field, str) or not field.strip():
        raise _invalid('field không hợp lệ.')
    refs = action.payload.get('refs')
    if refs is not None:
        _require_owned_refs(action, snapshot, _refs(action.payload))
    # A proposal is not yet an effective fact; it is recorded and reviewed.


def _handle_confirm_field(action, snapshot, decision) -> None:
    _require_mode(action, 'REVIEWER')
    field = action.payload['field']
    if not isinstance(field, str) or not field.strip():
        raise _invalid('field không hợp lệ.')
    refs = _refs(action.payload)
    _require_owned_refs(action, snapshot, refs)
    numeric = _validate_field_path(field, snapshot)
    _validate_confirmed_value(action.payload['value'], numeric=numeric)


def _handle_confirm_mapping(action, snapshot, decision) -> None:
    _require_mode(action, 'REVIEWER')
    pairs = action.payload['pairs']
    if not isinstance(pairs, list) or not pairs:
        raise _invalid('pairs phải là danh sách không rỗng.')
    seen_primary: set[str] = set()
    seen_receipt: set[str] = set()
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise _invalid('Mỗi cặp mapping phải có đúng hai ID.')
        primary_id, receipt_id = pair
        if not isinstance(primary_id, str) or not isinstance(receipt_id, str):
            raise _invalid('ID cặp mapping phải là chuỗi.')
        # IDs are document-owned item IDs, not evidence IDs; require a non-empty
        # unique one-to-one coverage (full coverage of the pairs given).
        if not primary_id or not receipt_id:
            raise _invalid('ID cặp mapping không được rỗng.')
        if primary_id in seen_primary or receipt_id in seen_receipt:
            raise _invalid('Cặp mapping trùng ID; cần phủ một-một rõ ràng.')
        seen_primary.add(primary_id)
        seen_receipt.add(receipt_id)
    _require_owned_refs(action, snapshot, _refs(action.payload))


def _handle_grant_exception(action, snapshot, decision) -> None:
    _require_mode(action, 'POLICY_OWNER')
    _authorization_payload(action, snapshot)
    # A policy exception closes LIM-01 only; it grants no FX/scope capability.


def _handle_approve_amount(action, snapshot, decision) -> None:
    _require_mode(action, 'APPROVER', 'POLICY_OWNER')
    amount, profile, purpose, policy_version = _authorization_payload(action, snapshot)
    if action.mode == 'APPROVER':
        if amount > snapshot.policy.standard_policy_max:
            raise _invalid(
                'APPROVER chỉ duyệt trong standard policy; vượt hạn mức cần POLICY_OWNER.'
            )
        return
    # POLICY_OWNER may approve above the standard max only with a matching,
    # in-force exception for the exact amount/scope.
    if amount > snapshot.policy.standard_policy_max:
        if not any(
            auth.kind == 'POLICY_EXCEPTION' and authorization_matches(auth, snapshot, amount)
            for auth in snapshot.authorizations
        ):
            raise _invalid('Vượt standard policy cần exception khớp đúng amount/scope trước.')


def _authorization_payload(action, snapshot) -> tuple[int, str, str, str]:
    payload = action.payload
    amount = _positive_vnd(payload['amount_vnd'])
    profile = payload['profile']
    if profile != snapshot.claim.profile:
        raise _invalid('Authorization phải khớp profile của hồ sơ.')
    if profile not in ('TRAVEL', 'CLIENT_MEAL', 'WORK_PURCHASE'):
        raise _invalid('Không thể authorization cho profile ngoài catalog B1.')
    purpose = payload['purpose']
    if purpose != snapshot.claim.purpose:
        raise _invalid('Authorization phải khớp purpose của hồ sơ.')
    policy_version = payload['policy_version']
    if policy_version != snapshot.policy.version:
        raise _invalid('Authorization phải khớp policy version đang active.')
    return amount, profile, purpose, policy_version


def _handle_deny(action, snapshot, decision) -> None:
    issue = _find_issue(action.payload['issue_id'], decision)
    if action.mode != issue.owner_mode:
        raise _invalid(f'DENY issue {issue.id} cần mode {issue.owner_mode}; nhận {action.mode}.')


def _handle_override(action, snapshot, decision) -> None:
    operation = action.payload['operation']
    if operation not in _OVERRIDE_OPERATIONS:
        raise _invalid(f'Override operation không hỗ trợ: {operation!r}.')
    values = action.payload['values']
    if not isinstance(values, dict):
        raise _invalid('Override values phải là dict.')
    # The wrapped operation's own keyset is enforced for EVERY operation,
    # including DENY and CLASSIFY_PROFILE (extra keys are rejected globally).
    inner = action.model_copy(update={'kind': operation, 'payload': dict(values)})
    _validate_payload_keys(inner)
    if operation == 'DENY':
        # The wrapper's mode must still satisfy the underlying issue-owner scope.
        issue = _find_issue(values.get('issue_id'), decision)
        if action.mode != issue.owner_mode:
            raise _invalid(f'Override DENY cần mode {issue.owner_mode}; nhận {action.mode}.')
        return
    if operation == 'CLASSIFY_PROFILE':
        _require_mode(action, 'POLICY_OWNER')
        _validate_classify(values, snapshot)
        return
    # CONFIRM_FIELD / CONFIRM_MAPPING / GRANT_POLICY_EXCEPTION / APPROVE_AMOUNT:
    # validate the underlying role/scope against the synthesized inner action,
    # which keeps the WRAPPER's mode (so the wrapper must satisfy the role).
    handler = _HANDLERS.get(operation)
    if handler is None:
        raise _invalid(f'Override không áp dụng cho {operation!r}.')
    handler(inner, snapshot, decision)


def _validate_classify(values: dict, snapshot: CaseSnapshot) -> None:
    target = values.get('profile')
    if target not in _CLASSIFY_TARGETS:
        raise _invalid('CLASSIFY_PROFILE chỉ đổi OTHER sang TRAVEL/CLIENT_MEAL/WORK_PURCHASE.')
    if snapshot.claim.profile != 'OTHER':
        raise _invalid('CLASSIFY_PROFILE chỉ áp dụng cho hồ sơ đang ở profile OTHER.')
    # The new profile's requirements still apply on reevaluation (no bypass).


def _handle_stop(action, snapshot, decision) -> None:
    # STOP is a dedicated control route: any demo mode may stop, the run id is
    # validated by the repository/executor against a real run. It never changes
    # case_version.
    run_id = action.payload['run_id']
    if not isinstance(run_id, str) or not run_id.strip():
        raise _invalid('run_id không hợp lệ.')


# --- Field path and canonical value --------------------------------------------

def _validate_field_path(field: str, snapshot: CaseSnapshot) -> bool:
    """A confirmation field is ``evidence_id.fields.total`` or
    ``evidence_id.items.item_id.<subfield>``.

    Enforces the PATH SHAPE only: the evidence is owned by the case, the
    ``fields``/``items`` segment is known, the item ID is present and the
    sub-field is a supported one. It deliberately does NOT resolve the refs or
    verify item coverage/unit ambiguity — the deep check needs the bundle and is
    assigned to T08 (see module docstring / report).

    Returns ``True`` when the field is numeric (must be confirmed with a
    canonical numeric value).
    """
    parts = field.split('.')
    owned = _owned_evidence_ids(snapshot)
    if len(parts) == 3 and parts[0] in owned and parts[1] == 'fields':
        if parts[2] == 'total':
            return True
        if parts[2] in ('merchant', 'date', 'currency'):
            return False
        raise _invalid(f'fields path không hỗ trợ: {field!r}.')
    if len(parts) == 4 and parts[0] in owned and parts[1] == 'items':
        if not parts[2]:
            raise _invalid(f'items path thiếu item_id: {field!r}.')
        if parts[3] in _ITEM_SUBFIELDS:
            return parts[3] in ('quantity', 'unit_price', 'line_amount')
        raise _invalid(f'items path không hỗ trợ: {field!r}.')
    raise _invalid(
        f'field {field!r} không hợp lệ; dùng <evidence_id>.fields.total hoặc '
        '<evidence_id>.items.<item_id>.<subfield>.'
    )


def _validate_confirmed_value(value: object, *, numeric: bool) -> None:
    """Validate (and require canonical form for) a confirmation value.

    A numeric confirmation must be a canonical decimal STRING (no grouping
    separators, no exponent, never an int/float) — the same canonical contract
    the source layer uses. This is NOT an FX or allocation capability: it only
    fixes the value's spelling for the HumanConfirmedFact; raw OCR is never
    modified.
    """
    if isinstance(value, bool):
        raise _invalid('Giá trị xác nhận không hợp lệ.')
    if not isinstance(value, str):
        raise _invalid('Giá trị xác nhận phải là chuỗi canonical.')
    stripped = value.strip()
    if not stripped:
        raise _invalid('Giá trị xác nhận không được rỗng.')
    if not numeric:
        return
    try:
        parsed = Decimal(stripped)
    except (InvalidOperation, ValueError):
        raise _invalid(f'Giá trị xác nhận không phải số hợp lệ: {value!r}.')
    if not parsed.is_finite():
        raise _invalid('Giá trị xác nhận không phải số hữu hạn.')
    if format(parsed.normalize(), 'f') != stripped:
        raise _invalid(
            f'Giá trị xác nhận phải ở dạng canonical: {format(parsed.normalize(), "f")!r}.'
        )


# --- Authorization binding (ledger §3.2) ---------------------------------------

def authorization_matches(auth: Authorization, snapshot: CaseSnapshot, amount: int) -> bool:
    """An authorization authorizes only when it binds the exact current scope."""
    return (
        auth.case_version == snapshot.case_version
        and auth.policy_version == snapshot.policy.version
        and auth.profile == snapshot.claim.profile
        and auth.purpose == snapshot.claim.purpose
        and auth.amount_vnd == amount
    )


_HANDLERS = {
    'SUPPLY_DECLARATION': _handle_supply_declaration,
    'ADD_EVIDENCE': _handle_add_evidence,
    'PROPOSE_CORRECTION': _handle_propose_correction,
    'CONFIRM_FIELD': _handle_confirm_field,
    'CONFIRM_MAPPING': _handle_confirm_mapping,
    'GRANT_POLICY_EXCEPTION': _handle_grant_exception,
    'APPROVE_AMOUNT': _handle_approve_amount,
    'DENY': _handle_deny,
    'OVERRIDE': _handle_override,
    'STOP': _handle_stop,
}


__all__ = ['validate_human_action', 'authorization_matches']
