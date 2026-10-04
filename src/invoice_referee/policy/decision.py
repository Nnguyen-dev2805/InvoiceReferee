"""Decision reducer and case-level policy/authority evaluation (T03, Rulebook §5/§6).

Pure: no provider calls, no SQLite, no UI, no testcase IDs or filenames.
``evaluate`` turns a ``CaseSnapshot`` + ``EvidenceBundle`` into a ``Decision``:

1. config not active -> technical NONE (no business completion);
2. known supported-rule refusal (MODE-01/ELIG-01) -> REJECT;
3. unresolved factual blocker -> REQUEST_INFO (grounded outside/authority issues
   stay open; no binding amount approval is requested for an unclear amount);
4. only outside-policy/authority blockers open -> ESCALATE to the owner;
5. all applicable checks pass with required authorizations in force ->
   CREATE_PAYMENT_REQUEST.

``completion_basis`` is ROUTINE_AUTO (within automatic authority) or
HUMAN_AUTHORIZED (after a valid approval/exception). A N/A of one check never
equals whole-case eligibility, and a missing check in the matrix is a technical
INVALID_ANALYSIS (never ``all(empty) = True``).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from invoice_referee.domain.models import (
    Authorization,
    CaseSnapshot,
    CheckResult,
    Decision,
    EvidenceBundle,
    Issue,
)
from invoice_referee.policy.expenses import context_check, document_checks
from invoice_referee.policy.inventory import arithmetic_checks, inventory_checks
from invoice_referee.policy.numeric import DECIMAL_CONTEXT
from invoice_referee.policy.quality import derive_fact

# The exact Rulebook §3 matrix. Every rule must be reported exactly once.
_RULE_MATRIX = (
    'SRC-01', 'SRC-02', 'SRC-03', 'CTX-01', 'MODE-01', 'MODE-02',
    'SCOPE-01', 'SCOPE-02', 'ELIG-01', 'AMT-01', 'AMT-02',
    'LIM-01', 'AUTH-01', 'INV-01', 'INV-02',
)

_REFUSAL_PAYERS = ('COMPANY', 'ADVANCE', 'VENDOR')


def _vnd(value: int) -> str:
    return f'{value:,}'.replace(',', '.')


def next_action(*, technical: bool, refusal: bool, issues: list[Issue]) -> str:
    """Reducer anchor. Apply only AFTER full coverage/eligibility validation."""
    if technical:
        return 'NONE'
    if refusal:
        return 'REJECT'
    if any(i.status == 'OPEN' and i.issue_class == 'FACTUAL_UNKNOWN' for i in issues):
        return 'REQUEST_INFO'
    if any(i.status == 'OPEN' for i in issues):
        return 'ESCALATE'
    return 'CREATE_PAYMENT_REQUEST'


def _open_factual(
    rule_id: str, *, owner: str, question: str, key_parts: tuple[str, ...] = ('case',), refs=None
) -> Issue:
    stable = '|'.join((rule_id, *key_parts))
    return Issue(
        id=stable, stable_key=stable, issue_class='FACTUAL_UNKNOWN',
        owner_mode=owner, question=question, refs=list(refs or []),
        blockers=[rule_id], status='OPEN',
    )


def _policy_issue(
    rule_id: str, *, owner: str, question: str, key_parts: tuple[str, ...] = ('case',)
) -> Issue:
    stable = '|'.join((rule_id, *key_parts))
    return Issue(
        id=stable, stable_key=stable, issue_class='OUTSIDE_POLICY',
        owner_mode=owner, question=question, refs=[], blockers=[rule_id], status='OPEN',
    )


def _authority_issue(
    rule_id: str, *, owner: str, question: str, key_parts: tuple[str, ...] = ('case',)
) -> Issue:
    stable = '|'.join((rule_id, *key_parts))
    return Issue(
        id=stable, stable_key=stable, issue_class='BEYOND_AUTHORITY',
        owner_mode=owner, question=question, refs=[], blockers=[rule_id], status='OPEN',
    )


def _authorization_applies(
    auth: Authorization, snapshot: CaseSnapshot, accepted: int
) -> bool:
    if auth.action_id not in snapshot.active_action_ids:
        return False
    return (
        auth.case_version == snapshot.case_version
        and auth.policy_version == snapshot.policy.version
        and auth.profile == snapshot.claim.profile
        and auth.purpose == snapshot.claim.purpose
        and auth.amount_vnd == accepted
    )


def _closed_by_exception(snapshot: CaseSnapshot, accepted: int) -> bool:
    return any(
        a.kind == 'POLICY_EXCEPTION' and _authorization_applies(a, snapshot, accepted)
        for a in snapshot.authorizations
    )


def _closed_by_amount_approval(snapshot: CaseSnapshot, accepted: int) -> bool:
    return any(
        a.kind == 'AMOUNT_APPROVAL' and _authorization_applies(a, snapshot, accepted)
        for a in snapshot.authorizations
    )


# Worst-status ordering for aggregating the same rule across documents.
_STATUS_RANK = {'FAIL': 3, 'UNKNOWN': 2, 'PASS': 1, 'NOT_APPLICABLE': 0}

# Document-level rules that a registry-less document cannot be checked for.
_DOC_RULES = ('SRC-02', 'SRC-03', 'SCOPE-02')


def _ref_key(ref) -> tuple[str, int, str, str, str]:
    return (ref.evidence_id, ref.page_index, ref.block_id, ref.locator, ref.raw_value)


def _merge_checks(existing: CheckResult, incoming: CheckResult) -> CheckResult:
    """Worst-status-wins merge; dependencies/refs/issue_ids are unioned."""
    status = existing.status
    if _STATUS_RANK[incoming.status] > _STATUS_RANK[existing.status]:
        status = incoming.status
    dependencies = list(dict.fromkeys([*existing.dependencies, *incoming.dependencies]))
    issue_ids = list(dict.fromkeys([*existing.issue_ids, *incoming.issue_ids]))
    seen: set[tuple[str, int, str, str, str]] = set()
    refs = []
    for ref in [*existing.refs, *incoming.refs]:
        key = _ref_key(ref)
        if key not in seen:
            seen.add(key)
            refs.append(ref)
    reason = existing.reason if _STATUS_RANK[existing.status] >= _STATUS_RANK[incoming.status] \
        else incoming.reason
    return CheckResult(
        rule_id=existing.rule_id, status=status, dependencies=dependencies,
        refs=refs, reason=reason, issue_ids=issue_ids,
    )


def _merge_documents(
    snapshot: CaseSnapshot, bundle: EvidenceBundle
) -> list[CheckResult]:
    """Document-level checks aggregated by rule_id (each rule appears once).

    A document without a registry cannot be checked; it contributes UNKNOWN for
    the document-level rules instead of being silently dropped, so its evidence
    gap is flagged rather than lost.
    """
    merged: dict[str, CheckResult] = {}
    for doc in bundle.documents:
        registry = bundle.registries.get(doc.evidence_id)
        if registry is None:
            doc_checks = [
                CheckResult(
                    rule_id=rule, status='UNKNOWN', dependencies=['document'],
                    refs=[], reason=f'Thiếu registry cho document {doc.evidence_id}.',
                    issue_ids=[],
                )
                for rule in _DOC_RULES
            ]
        else:
            doc_checks = document_checks(doc, registry, snapshot.policy)
        for check in doc_checks:
            if check.rule_id in merged:
                merged[check.rule_id] = _merge_checks(merged[check.rule_id], check)
            else:
                merged[check.rule_id] = check
    return list(merged.values())


def evaluate(snapshot: CaseSnapshot, bundle: EvidenceBundle) -> Decision:
    """Evaluate a case snapshot + evidence bundle into a pure ``Decision``."""
    checks: list[CheckResult] = []
    issues: list[Issue] = []

    # --- Config readiness (technical, not a business violation) ---------------
    if not snapshot.policy.active:
        return Decision(
            action='NONE', completion_basis=None, accepted_amount_vnd=None,
            checks=[], issues=[], reasons=['Policy chưa active.'],
            technical_code='CONFIG_NOT_ACTIVE',
        )

    # --- Refusals decided from declarations before provider output -------------
    refusal = False
    claim = snapshot.claim
    if claim.payer_type in _REFUSAL_PAYERS:
        refusal = True
        checks.append(CheckResult(
            rule_id='MODE-01', status='FAIL', dependencies=['payer_type'], refs=[],
            reason='Payer là COMPANY/ADVANCE/VENDOR: luồng khác B1.', issue_ids=[]))
    else:
        checks.append(CheckResult(
            rule_id='MODE-01', status='PASS', dependencies=['payer_type'], refs=[],
            reason='Payer là PERSONAL.', issue_ids=[]))

    if claim.purpose_type == 'PERSONAL':
        refusal = True
        checks.append(CheckResult(
            rule_id='ELIG-01', status='FAIL', dependencies=['purpose_type'], refs=[],
            reason='Khai báo xác định chi cá nhân không phục vụ công việc.', issue_ids=[]))
    else:
        checks.append(CheckResult(
            rule_id='ELIG-01', status='PASS', dependencies=['purpose_type'], refs=[],
            reason='Mục đích công việc.', issue_ids=[]))

    if refusal:
        return Decision(
            action='REJECT', completion_basis=None, accepted_amount_vnd=None,
            checks=checks, issues=issues,
            reasons=['Known supported-rule refusal.'], technical_code=None,
        )

    # --- Scope ----------------------------------------------------------------
    if claim.profile == 'OTHER':
        checks.append(CheckResult(
            rule_id='SCOPE-01', status='FAIL', dependencies=['profile'], refs=[],
            reason='Profile ngoài catalog B1.', issue_ids=['SCOPE-01:case']))
        issues.append(_policy_issue(
            'SCOPE-01', owner='POLICY_OWNER',
            question='Profile này chưa nằm trong catalog; cần phân loại hoặc từ chối.'))
    else:
        checks.append(CheckResult(
            rule_id='SCOPE-01', status='PASS', dependencies=['profile'], refs=[],
            reason='Profile trong catalog B1.', issue_ids=[]))

    # --- Primary bill presence (SRC-01) ---------------------------------------
    # SRC-01 fires only on a DECLARED-primary-absent case. A declared primary
    # whose analyzed kind is non-BILL (UNKNOWN/CREDIT_NOTE) is a kind/scope
    # concern handled by SCOPE-02/SRC-02, so it must not be double-reported here
    # as "missing bill".
    primary_ids = {e.id for e in snapshot.evidence if e.role == 'PRIMARY_BILL'}
    if not primary_ids:
        checks.append(CheckResult(
            rule_id='SRC-01', status='FAIL', dependencies=['PRIMARY_BILL'], refs=[],
            reason='Thiếu primary bill bắt buộc.', issue_ids=['SRC-01:case']))
        issues.append(_open_factual(
            'SRC-01', owner='EMPLOYEE',
            question='Hồ sơ thiếu primary bill bắt buộc; vui lòng bổ sung chứng từ gốc.'))
    else:
        checks.append(CheckResult(
            rule_id='SRC-01', status='PASS', dependencies=['PRIMARY_BILL'], refs=[],
            reason='Có khai báo primary bill.', issue_ids=[]))

    # --- Per-document source/scope checks (aggregated by rule_id) -------------
    doc_checks = _merge_documents(snapshot, bundle)
    checks.extend(doc_checks)
    # When no document (or no registry) exists, document-level rules are still
    # reported so the matrix stays complete; these are UNKNOWN (never PASS,
    # never a technical invalid).
    _present = {c.rule_id for c in checks}
    for rule in ('SRC-02', 'SRC-03', 'SCOPE-02'):
        if rule not in _present:
            checks.append(CheckResult(
                rule_id=rule, status='UNKNOWN', dependencies=['document'], refs=[],
                reason='Không có document/registry để kiểm rule này.', issue_ids=[]))
    for check in doc_checks:
        if check.status in ('FAIL', 'UNKNOWN') and check.rule_id == 'SRC-02':
            issues.append(_open_factual(
                'SRC-02', owner='REVIEWER',
                question='Primary bill thiếu/không dùng được trường bắt buộc; cần đọc lại nguồn.'))
        if check.status in ('FAIL', 'UNKNOWN') and check.rule_id == 'SCOPE-02':
            issues.append(_policy_issue(
                'SCOPE-02', owner='POLICY_OWNER',
                question='Loại tiền/document cần FX hoặc credit-note chưa được B1 hỗ trợ.'))

    # --- MODE-02 payer unknown/contradictory ----------------------------------
    if claim.payer_type == 'UNKNOWN':
        checks.append(CheckResult(
            rule_id='MODE-02', status='FAIL', dependencies=['payer_type'], refs=[],
            reason='Payer UNKNOWN; chưa kết luận employee đã trả.', issue_ids=['MODE-02:case']))
        issues.append(_open_factual(
            'MODE-02', owner='EMPLOYEE',
            question='Chưa xác định phương thức chi trả; vui lòng khai báo ai đã trả khoản này.'))
    else:
        checks.append(CheckResult(
            rule_id='MODE-02', status='PASS', dependencies=['payer_type'], refs=[],
            reason='Payer rõ ràng.', issue_ids=[]))

    # --- Context (CTX-01) -----------------------------------------------------
    ctx = context_check(claim, snapshot.policy)
    checks.append(ctx)
    if ctx.status == 'FAIL':
        issues.append(_open_factual(
            'CTX-01', owner='EMPLOYEE',
            question='Thiếu khai báo context cần cho profile: ' + ', '.join(ctx.dependencies)))

    # --- Arithmetic (AMT-02), independent of consistency ----------------------
    checks.extend(arithmetic_checks(bundle, snapshot.policy))
    amt02 = next(c for c in checks if c.rule_id == 'AMT-02')
    if amt02.status == 'FAIL':
        issues.append(_open_factual(
            'AMT-02', owner='EMPLOYEE',
            question='Arithmetic trên bill có mâu thuẫn; cần làm rõ phép tính và căn cứ.'))
    elif amt02.status == 'UNKNOWN':
        issues.append(_open_factual(
            'AMT-02', owner='REVIEWER',
            question='Chưa đủ dữ kiện template/basis để kiểm arithmetic; cần đọc lại nguồn.'))

    # --- Accepted amount and AMT-01 -------------------------------------------
    requested = claim.requested_amount_vnd
    verified_total = _verified_total(snapshot, bundle)
    accepted: int | None = None
    if requested is not None and verified_total is not None:
        if requested == verified_total:
            accepted = requested
            checks.append(CheckResult(
                rule_id='AMT-01', status='PASS', dependencies=['requested_amount_vnd', 'total'],
                refs=[], reason='Requested khớp verified bill.', issue_ids=[]))
        else:
            checks.append(CheckResult(
                rule_id='AMT-01', status='FAIL', dependencies=['requested_amount_vnd', 'total'],
                refs=[], reason='Requested amount không khớp verified bill.', issue_ids=['AMT-01|requested_amount_vnd|total']))
            issues.append(_open_factual(
                'AMT-01', owner='EMPLOYEE', key_parts=('requested_amount_vnd', 'total'),
                question=_amount_conflict_question(requested, verified_total)))
    else:
        checks.append(CheckResult(
            rule_id='AMT-01', status='UNKNOWN', dependencies=['requested_amount_vnd', 'total'],
            refs=[], reason='Chưa xác định được requested/verified amount.', issue_ids=['AMT-01|requested_amount_vnd|total']))
        issues.append(_open_factual(
            'AMT-01', owner='EMPLOYEE', key_parts=('requested_amount_vnd', 'total'),
            question='Chưa xác định được số tiền đề nghị/đã xác minh; cần bổ sung căn cứ.'))

    # --- Inventory (INV-01/02) ------------------------------------------------
    checks.extend(inventory_checks(
        bundle, snapshot.policy,
        profile=claim.profile, received_full=claim.received_full))
    for check in checks:
        if check.rule_id == 'INV-01' and check.status == 'FAIL':
            issues.append(_open_factual(
                'INV-01', owner='EMPLOYEE',
                question='Thiếu formal receipt hoặc chưa xác nhận nhận đủ hàng; cần bổ sung nguồn.'))
        if check.rule_id == 'INV-02' and check.status in ('FAIL', 'UNKNOWN'):
            issues.append(_open_factual(
                'INV-02', owner='REVIEWER',
                question='Đối chiếu inventory có conflict/thiếu căn cứ; cần xác minh nguồn.'))

    # --- Policy limit and authority (LIM-01/AUTH-01) --------------------------
    if accepted is not None:
        checks.extend(_policy_authority_checks(snapshot, accepted, issues))
    else:
        # Amount not determined: keep LIM/AUTH as UNKNOWN (not PASS).
        checks.append(CheckResult(
            rule_id='LIM-01', status='UNKNOWN', dependencies=['accepted_amount_vnd'],
            refs=[], reason='Chưa xác định accepted amount.', issue_ids=[]))
        checks.append(CheckResult(
            rule_id='AUTH-01', status='UNKNOWN', dependencies=['accepted_amount_vnd'],
            refs=[], reason='Chưa xác định accepted amount.', issue_ids=[]))

    # --- Full coverage validation (missing check => technical invalid) --------
    reported = {c.rule_id for c in checks}
    missing_rules = [r for r in _RULE_MATRIX if r not in reported]
    if missing_rules:
        return Decision(
            action='NONE', completion_basis=None, accepted_amount_vnd=None,
            checks=checks, issues=issues,
            reasons=['INVALID_ANALYSIS: missing check(s) ' + ', '.join(missing_rules)],
            technical_code='INVALID_ANALYSIS',
        )

    # SRC-03 contract-invalid (duplicate/foreign IDs) is technical.
    if any(c.rule_id == 'SRC-03' and c.status == 'FAIL' for c in checks):
        return Decision(
            action='NONE', completion_basis=None, accepted_amount_vnd=None,
            checks=checks, issues=issues,
            reasons=['INVALID_ANALYSIS: document contract violation (SRC-03).'],
            technical_code='INVALID_ANALYSIS',
        )

    # --- Reduce ---------------------------------------------------------------
    open_issues = [i for i in issues if i.status == 'OPEN']
    action = next_action(technical=False, refusal=False, issues=open_issues)
    completion_basis = None
    final_amount = None
    if action == 'CREATE_PAYMENT_REQUEST':
        final_amount = accepted
        # A request above the automatic limit can only be produced by a valid
        # amount approval, so it is HUMAN_AUTHORIZED; otherwise it is routine.
        over_limit = accepted is not None and accepted > snapshot.policy.auto_approval_max
        completion_basis = 'HUMAN_AUTHORIZED' if over_limit else 'ROUTINE_AUTO'

    return Decision(
        action=action, completion_basis=completion_basis, accepted_amount_vnd=final_amount,
        checks=checks, issues=issues, reasons=[], technical_code=None,
    )


def _policy_authority_checks(
    snapshot: CaseSnapshot, accepted: int, issues: list[Issue]
) -> list[CheckResult]:
    policy = snapshot.policy
    checks: list[CheckResult] = []

    # LIM-01: over standard policy max (inclusive).
    if accepted > policy.standard_policy_max:
        closed = _closed_by_exception(snapshot, accepted)
        if closed:
            checks.append(CheckResult(
                rule_id='LIM-01', status='PASS', dependencies=['accepted_amount_vnd'], refs=[],
                reason='Policy exception hợp lệ đóng LIM-01.', issue_ids=[]))
        else:
            checks.append(CheckResult(
                rule_id='LIM-01', status='FAIL', dependencies=['accepted_amount_vnd'], refs=[],
                reason='Vượt standard_policy_max; cần case-specific exception.',
                issue_ids=['LIM-01:case']))
            issues.append(_policy_issue(
                'LIM-01', owner='POLICY_OWNER',
                question=f'Khoản {_vnd(accepted)}đ vượt hạn mức policy thông thường; cần exception cho đúng case.'))
    else:
        checks.append(CheckResult(
            rule_id='LIM-01', status='PASS', dependencies=['accepted_amount_vnd'], refs=[],
            reason='Trong standard policy.', issue_ids=[]))

    # AUTH-01: over auto approval max (inclusive).
    if accepted > policy.auto_approval_max:
        closed = _closed_by_amount_approval(snapshot, accepted)
        if closed:
            checks.append(CheckResult(
                rule_id='AUTH-01', status='PASS', dependencies=['accepted_amount_vnd'], refs=[],
                reason='Có amount approval hợp lệ.', issue_ids=[]))
        else:
            owner = 'POLICY_OWNER' if accepted > policy.standard_policy_max else 'APPROVER'
            checks.append(CheckResult(
                rule_id='AUTH-01', status='FAIL', dependencies=['accepted_amount_vnd'], refs=[],
                reason='Vượt auto_approval_max; cần explicit amount approval.',
                issue_ids=['AUTH-01:case']))
            issues.append(_authority_issue(
                'AUTH-01', owner=owner,
                question=f'Khoản {_vnd(accepted)}đ vượt quyền tự động; cần approval đúng số tiền.'))
    else:
        checks.append(CheckResult(
            rule_id='AUTH-01', status='PASS', dependencies=['accepted_amount_vnd'], refs=[],
            reason='Trong quyền tự động.', issue_ids=[]))
    return checks


def _verified_total(snapshot: CaseSnapshot, bundle: EvidenceBundle) -> int | None:
    """Verified primary-bill total as an integer đồng when a usable total exists.

    Only the primary BILL total is authoritative for AMT-01; a goods-receipt
    total is inventory evidence, not the requested expense amount.
    """
    threshold = Decimal(snapshot.policy.word_review_threshold)
    ordered = sorted(bundle.documents, key=lambda d: 0 if d.kind == 'BILL' else 1)
    for doc in ordered:
        registry = bundle.registries.get(doc.evidence_id)
        fact = doc.fields.get('total')
        if registry is None or fact is None:
            continue
        derived = derive_fact(fact, registry, True, threshold, None)
        if derived.usability != 'USABLE':
            continue
        try:
            with localcontext(DECIMAL_CONTEXT):
                value = Decimal(str(derived.normalized_value))
        except (InvalidOperation, ValueError):
            continue
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
    return None


def _amount_conflict_question(requested: int, verified: int) -> str:
    diff = abs(requested - verified)
    return (
        f'Bill ghi {_vnd(verified)}đ, đề nghị là {_vnd(requested)}đ. '
        f'Phần {_vnd(diff)}đ chênh là khoản nào và căn cứ nào xác nhận?'
    )
