"""Expense-eligibility and document policy checks (T03, Rulebook §3).

Pure evaluators: no provider calls, no storage, no UI, no testcase IDs/filenames.
``document_checks`` covers the document-level rules SRC-02, SRC-03 and SCOPE-02;
``context_check`` covers CTX-01. The case-level rules (SRC-01, MODE-01/02,
SCOPE-01, ELIG-01, AMT-01/02, LIM-01, AUTH-01, INV-01/02) are assembled by
``decision.evaluate``, which is the single entry point.

Rule IDs and reactions are the Rulebook §3 matrix:

- SRC-01 no required primary bill -> FACTUAL_UNKNOWN
- SRC-02 required field missing/uncertain/unusable -> FACTUAL_UNKNOWN
- SRC-03 duplicate/foreign IDs or contract contradiction -> technical invalid
- CTX-01 purpose/attendees/trip missing for profile -> FACTUAL_UNKNOWN
- MODE-01 declared COMPANY/ADVANCE/VENDOR -> REJECT (out of B1 scope)
- MODE-02 payer UNKNOWN / contradictory -> FACTUAL_UNKNOWN
- SCOPE-01 profile OTHER / not in catalog -> OUTSIDE_POLICY
- SCOPE-02 foreign currency / credit-note kind -> OUTSIDE_POLICY
- ELIG-01 declared personal, not for work -> REJECT
- AMT-01 requested amount != verified bill -> FACTUAL_UNKNOWN
- AMT-02 arithmetic contradiction -> FACTUAL_UNKNOWN (see ``inventory`` for math)
- LIM-01 eligible expense over standard_policy_max -> OUTSIDE_POLICY
- AUTH-01 accepted amount over auto_approval_max -> BEYOND_AUTHORITY

All thresholds are inclusive. A case can carry both LIM-01 and AUTH-01.
"""
from __future__ import annotations

from decimal import Decimal

from invoice_referee.domain.models import (
    CheckResult,
    DocumentFacts,
    FieldFact,
    PolicyConfig,
    SourceRef,
    SourceRegistry,
)
from invoice_referee.policy.quality import derive_fact

# Required primary fields per profile (Rulebook §2). Purpose/attendees/trip are
# declarations, not invoice facts.
_HEADER_FIELDS = ('merchant', 'date', 'total', 'currency')


def _issue_id(rule_id: str, stable_suffix: str) -> str:
    return f'{rule_id}:{stable_suffix}'


def _fact_refs(fact: FieldFact | None) -> list[SourceRef]:
    return list(fact.refs) if fact is not None else []


def _derive(
    fact: FieldFact | None,
    registry: SourceRegistry,
    policy: PolicyConfig,
    numeric: bool,
) -> FieldFact | None:
    if fact is None:
        return None
    threshold = Decimal(policy.word_review_threshold)
    return derive_fact(fact, registry, numeric, threshold, None)


def _src_checks(
    doc: DocumentFacts, registry: SourceRegistry, policy: PolicyConfig
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    # SRC-03: duplicate item IDs (contract integrity) checked first, before any
    # dict construction that could drop/overwrite a line.
    item_ids = [item.id for item in doc.items]
    if len(item_ids) != len(set(item_ids)):
        checks.append(CheckResult(
            rule_id='SRC-03', status='FAIL',
            dependencies=['items'], refs=[],
            reason='Trùng item ID trong cùng document; không dựng dict để tránh mất dòng.',
            issue_ids=[],
        ))
        return checks
    checks.append(CheckResult(
        rule_id='SRC-03', status='PASS', dependencies=['items'], refs=[],
        reason='Item IDs duy nhất và refs hợp lệ.', issue_ids=[],
    ))

    # SRC-02: every required primary field must be present and usable. The
    # missing field names are carried in ``dependencies`` so the reducer can
    # build the factual issue (issues belong to ``decision``).
    required = list(_HEADER_FIELDS)
    missing: list[str] = []
    for name in required:
        derived = _derive(doc.fields.get(name), registry, policy, numeric=name == 'total')
        if derived is None or derived.usability != 'USABLE':
            missing.append(name)
    if missing:
        refs = [r for name in missing for r in _fact_refs(doc.fields.get(name))]
        checks.append(CheckResult(
            rule_id='SRC-02', status='FAIL', dependencies=missing, refs=refs,
            reason='Required primary field missing/uncertain/unusable.',
            issue_ids=[],
        ))
    else:
        checks.append(CheckResult(
            rule_id='SRC-02', status='PASS', dependencies=required, refs=[],
            reason='Primary required fields usable.', issue_ids=[],
        ))
    return checks


def _currency_status(
    doc: DocumentFacts, registry: SourceRegistry, policy: PolicyConfig
) -> tuple[str, list[SourceRef]]:
    """SCOPE-02 currency leg: PASS / FAIL / UNKNOWN (never PASS when unusable)."""
    fact = doc.fields.get('currency')
    if fact is None:
        return 'UNKNOWN', []
    derived = _derive(fact, registry, policy, numeric=False)
    refs = _fact_refs(fact)
    if derived is None or derived.usability != 'USABLE':
        return 'UNKNOWN', refs
    if str(derived.normalized_value).strip().upper() != policy.currency.upper():
        return 'FAIL', refs
    return 'PASS', refs


def document_checks(
    doc: DocumentFacts, registry: SourceRegistry, policy: PolicyConfig
) -> list[CheckResult]:
    """Per-document source checks (SRC-02/SRC-03) and SCOPE-02.

    Returns results in matrix order; the reducer merges across documents and adds
    the case-level rules. Duplicate IDs are reported as SRC-03 FAIL so the reducer
    treats them as a technical invalid-analysis result.
    """
    checks: list[CheckResult] = []
    src_checks = _src_checks(doc, registry, policy)
    checks.extend(src_checks)
    if any(c.rule_id == 'SRC-03' and c.status == 'FAIL' for c in src_checks):
        return checks  # contract invalid; do not fabricate further results

    # SCOPE-02: credit-note/foreign currency is out of B1 scope. An unknown kind
    # or an unusable currency fact cannot be a scope PASS.
    currency_status, refs = _currency_status(doc, registry, policy)
    if doc.kind == 'CREDIT_NOTE':
        status = 'FAIL'
        reason = 'Credit-note cần logic refund chưa được B1 hỗ trợ.'
    elif doc.kind == 'UNKNOWN':
        status = 'UNKNOWN'
        reason = 'Chưa xác định được document kind để kết luận scope.'
    else:
        status = currency_status
        reason = (
            'Currency ngoài VND cần FX chưa được B1 hỗ trợ.' if status == 'FAIL'
            else 'Chưa dùng được currency fact để kết luận scope.' if status == 'UNKNOWN'
            else 'Kind/currency trong phạm vi B1.'
        )
    checks.append(CheckResult(
        rule_id='SCOPE-02', status=status, dependencies=['kind', 'currency'],
        refs=refs, reason=reason, issue_ids=[],
    ))
    return checks


def context_check(snapshot_claim, policy: PolicyConfig) -> CheckResult:
    """CTX-01: profile-required purpose/attendees/trip declarations present."""
    profile = snapshot_claim.profile
    missing: list[str] = []
    if not snapshot_claim.purpose.strip():
        missing.append('purpose')
    if snapshot_claim.purpose_type == 'UNKNOWN':
        missing.append('purpose_type')
    if profile == 'CLIENT_MEAL' and not snapshot_claim.attendees:
        missing.append('attendees')
    if profile == 'TRAVEL' and not snapshot_claim.trip.strip():
        missing.append('trip')
    if missing:
        return CheckResult(
            rule_id='CTX-01', status='FAIL', dependencies=missing, refs=[],
            reason='Thiếu khai báo cần cho profile: ' + ', '.join(missing),
            issue_ids=[_issue_id('CTX-01', missing[0])],
        )
    return CheckResult(
        rule_id='CTX-01', status='PASS', dependencies=[], refs=[],
        reason='Đủ khai báo context cho profile.', issue_ids=[],
    )
