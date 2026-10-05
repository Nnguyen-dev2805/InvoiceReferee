"""Production pipeline: preflight -> providers -> pure evaluators (T06, System §6).

Ledger §3.2:

- ``preflight(snapshot) -> Decision | None`` short-circuits the cases that need
  NO provider call (config not ready, a known supported-rule refusal, a missing
  or ambiguous primary bill). It returns ``None`` when providers must run.
- ``process(snapshot, providers, checkpoint, artifact_writer) -> PipelineResult``
  runs OCR -> ``registry_from_ocr`` -> AnalyzeDocument -> contract validation ->
  re-derivation at the ACTIVE policy threshold -> optional cross-source -> the
  pure ``evaluate``. It NEVER inserts a payment request; ``Repository.finalize_run``
  (T08) is the only writer.

Design rulings (recorded at T06):

- **Providers are called only for the per-document path.** A missing/ambiguous
  required source or a declaration-grounded refusal is decided by code, so no OCR
  or Kimi call is made just to discover it.
- **Usability is re-derived with the ACTIVE policy threshold.** ``validate_document``
  (T05) derives at a FIXED 0.85; the pipeline re-derives every fact with
  ``snapshot.policy.word_review_threshold`` so a calibrated B2 threshold applies.
  ``threshold_version`` travels in the hashed request as identity, not a value.
- **Applicability is code-decided** via ``is_applicable``; a document may not
  waive a mandatory breakdown/inventory check by claiming TOTAL_ONLY.
- **Error classification** keeps technical failures (transport/contract) separate
  from business results: empty OCR/missing scores are factual blockers, malformed
  structure/invalid output are technical NONE with a ``technical_code``.
- **Stop** is checked before/after every SDK call, before applying facts, before
  ``evaluate`` and before returning. ``StoppedRun`` propagates so T08 marks the
  run STOPPED, never FAILED. No business action is applied after a stop.
- **No leakage**: no testcase IDs/filenames, no employee prose into prompts.
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Callable

from invoice_referee.domain.models import (
    AnalysisRequest,
    CaseSnapshot,
    CheckResult,
    Decision,
    DocumentFacts,
    DomainError,
    Evidence,
    EvidenceBundle,
    FieldFact,
    Issue,
    ItemFacts,
    MappingProposal,
    PipelineResult,
    SourceRegistry,
    StageIdentity,
    StoppedRun,
)
from invoice_referee.extraction.providers import Providers, registry_from_ocr
from invoice_referee.extraction.validation import NUMERIC_FIELDS, is_applicable
from invoice_referee.policy.decision import evaluate
from invoice_referee.policy.quality import derive_fact

# Declarations that ground a REJECT before any provider call (Rulebook §3).
_REFUSAL_PAYERS = ('COMPANY', 'ADVANCE', 'VENDOR')

# Required-field hints per evidence role. A CONTEXT file is NOT required to carry
# total/items like a bill; it only needs the payer/purpose facts it is submitted for.
_REQUIRED_FIELDS = {
    'PRIMARY_BILL': ('merchant', 'date', 'total', 'currency'),
    'GOODS_RECEIPT': ('merchant', 'date', 'total', 'currency', 'items'),
    'CONTEXT': ('payer',),
}

# Context fields whose value can contradict a PERSONAL payer declaration.
_CONTEXT_PAYER_FIELDS = ('payer', 'payer_type')

_ROLE_ORDER = {'PRIMARY_BILL': 0, 'GOODS_RECEIPT': 1, 'CONTEXT': 2}

Checkpoint = Callable[[str], None]
ArtifactWriter = Callable[[str, bytes], object]


# --- Preflight -----------------------------------------------------------------

def preflight(snapshot: CaseSnapshot) -> Decision | None:
    """Decide the no-provider cases; return ``None`` when providers must run."""
    policy = snapshot.policy
    if not policy.active or not policy.version.strip() or not policy.threshold_version.strip():
        return _technical('CONFIG_NOT_ACTIVE')

    claim = snapshot.claim
    if claim.payer_type in _REFUSAL_PAYERS or claim.purpose_type == 'PERSONAL':
        return _refusal(claim)

    primaries = [e for e in snapshot.evidence if e.role == 'PRIMARY_BILL']
    if not primaries:
        return _missing_primary()
    if len(primaries) > 1:
        return _ambiguous_primary()
    return None


def _refusal(claim) -> Decision:
    checks: list[CheckResult] = []
    if claim.payer_type in _REFUSAL_PAYERS:
        checks.append(CheckResult(
            rule_id='MODE-01', status='FAIL', dependencies=['payer_type'], refs=[],
            reason='Payer COMPANY/ADVANCE/VENDOR: ngoài phạm vi B1.', issue_ids=[]))
    if claim.purpose_type == 'PERSONAL':
        checks.append(CheckResult(
            rule_id='ELIG-01', status='FAIL', dependencies=['purpose_type'], refs=[],
            reason='Khai báo xác định chi cá nhân không phục vụ công việc.', issue_ids=[]))
    return Decision(
        action='REJECT', completion_basis=None, accepted_amount_vnd=None,
        checks=checks, issues=[], reasons=['Known supported-rule refusal.'], technical_code=None,
    )


def _missing_primary() -> Decision:
    issue = Issue(
        id='SRC-01:case', stable_key='SRC-01:case', issue_class='FACTUAL_UNKNOWN',
        owner_mode='EMPLOYEE', refs=[], blockers=['SRC-01'], status='OPEN',
        question='Hồ sơ thiếu primary bill bắt buộc; vui lòng bổ sung chứng từ gốc.',
    )
    check = CheckResult(
        rule_id='SRC-01', status='FAIL', dependencies=['PRIMARY_BILL'], refs=[],
        reason='Thiếu primary bill bắt buộc.', issue_ids=['SRC-01:case'])
    return Decision(
        action='REQUEST_INFO', completion_basis=None, accepted_amount_vnd=None,
        checks=[check], issues=[issue],
        reasons=['Thiếu primary bill; không gọi provider để phát hiện file thiếu.'],
        technical_code=None,
    )


def _ambiguous_primary() -> Decision:
    issue = Issue(
        id='SRC-01:multiple', stable_key='SRC-01:multiple', issue_class='FACTUAL_UNKNOWN',
        owner_mode='EMPLOYEE', refs=[], blockers=['SRC-01'], status='OPEN',
        question='Hồ sơ có nhiều primary bill; vui lòng làm rõ bill nào là chứng từ chính '
                 'hoặc tách hồ sơ.',
    )
    check = CheckResult(
        rule_id='SRC-01', status='FAIL', dependencies=['PRIMARY_BILL'], refs=[],
        reason='Nhiều primary bill cần làm rõ.', issue_ids=['SRC-01:multiple'])
    return Decision(
        action='REQUEST_INFO', completion_basis=None, accepted_amount_vnd=None,
        checks=[check], issues=[issue],
        reasons=['Nhiều primary bill; cần làm rõ, không tự chọn file đầu.'],
        technical_code=None,
    )


def _technical(code: str) -> Decision:
    return Decision(
        action='NONE', completion_basis=None, accepted_amount_vnd=None,
        checks=[], issues=[], reasons=[f'Technical: {code}.'], technical_code=code,
    )


# --- Process -------------------------------------------------------------------

def process(
    snapshot: CaseSnapshot,
    providers: Providers,
    checkpoint: Checkpoint,
    artifact_writer: ArtifactWriter,
) -> PipelineResult:
    """Run the full pipeline for one snapshot. Never inserts a payment request."""
    durations: dict[str, int] = {}
    artifacts: list[str] = []
    identities: list[StageIdentity] = []
    captured = 0

    def capture_identities() -> None:
        # Capture EVERY invocation identity in order, including repairs that share
        # an identity with their predecessor. ``captured`` keeps this idempotent
        # across calls without deduplicating distinct invocations.
        nonlocal captured
        all_identities = getattr(providers, 'identities', [])
        identities.extend(all_identities[captured:])
        captured = len(all_identities)

    def mark(stage: str, since: float) -> None:
        durations[stage] = durations.get(stage, 0) + int((time.perf_counter() - since) * 1000)

    def run_stage(stage: str, call: Callable[[], object]) -> object:
        checkpoint(f'{stage}:before')
        started = time.perf_counter()
        value = call()
        mark(stage, started)
        checkpoint(f'{stage}:after')
        return value

    def finish(decision: Decision, bundle: EvidenceBundle) -> PipelineResult:
        capture_identities()
        checkpoint('before:return')
        calls = getattr(providers, 'calls', None)
        # FakeProviders traces ``.calls``; LiveProviders has none, so its identity
        # count (one per invocation, incl. repairs) is the provider-call count.
        provider_calls = len(calls) if calls is not None else len(identities)
        return PipelineResult(
            decision=decision, bundle=bundle, artifacts=artifacts,
            identities=list(identities), stage_durations_ms=dict(durations),
            provider_calls=provider_calls, repair_calls=getattr(providers, 'repair_calls', 0),
        )

    early = preflight(snapshot)
    if early is not None:
        return finish(early, EvidenceBundle())

    documents: list[DocumentFacts] = []
    registries: dict[str, SourceRegistry] = {}
    context_issues: list[Issue] = []

    try:
        for evidence in sorted(snapshot.evidence, key=lambda e: _ROLE_ORDER.get(e.role, 9)):
            raw = run_stage(f'ocr:{evidence.id}', lambda e=evidence: providers.ocr(e))
            _store(artifact_writer, artifacts, f'{evidence.id}-ocr.json',
                   json.dumps(raw.payload, ensure_ascii=False).encode('utf-8'))
            registry = _source_registry(providers, evidence, raw)
            _store(artifact_writer, artifacts, f'{evidence.id}-registry.json',
                   registry.model_dump_json().encode('utf-8'))
            registries[evidence.id] = registry

            request = AnalysisRequest(
                evidence=evidence, registry=registry,
                required_fields=list(_REQUIRED_FIELDS.get(evidence.role, ('payer',))),
                threshold_version=snapshot.policy.threshold_version,
            )
            document = run_stage(
                f'analyze:{evidence.id}', lambda r=request: providers.analyze(r))
            _store(artifact_writer, artifacts, f'{evidence.id}-document.json',
                   document.model_dump_json().encode('utf-8'))

            checkpoint(f'apply:{evidence.id}')
            document = _rederive(document, registry, snapshot.policy)
            if evidence.role == 'CONTEXT':
                context_issues.extend(_context_conflicts(document, evidence))
            else:
                documents.append(document)

        mapping = _maybe_cross_source(snapshot, documents, registries, providers, run_stage, artifact_writer, artifacts)
        bundle = EvidenceBundle(documents=documents, registries=registries, mapping=mapping)
        _reject_waived_checks(bundle)
    except StoppedRun:
        raise
    except DomainError as exc:
        # Technical failure: never fabricate a business violation or approval.
        return finish(_technical(exc.code), EvidenceBundle(documents=documents, registries=registries))

    checkpoint('before:evaluate')
    decision = evaluate(snapshot, bundle)
    if context_issues and decision.action != 'NONE':
        decision = _merge_context_issues(decision, context_issues)
    return finish(decision, bundle)


def _source_registry(providers: Providers, evidence: Evidence, raw) -> SourceRegistry:
    """Registry from OCR; a replay/fake provider may inject a prebuilt one.

    ``LiveProviders`` never exposes ``.registries``, so OCR always wins in
    production. ``FakeProviders`` (and a future replay) injects registries built
    without a network call, so tests exercise the same per-document path.
    """
    registry = registry_from_ocr(evidence, raw)
    if registry.blocks:
        return registry
    injected = getattr(providers, 'registries', None)
    if injected and evidence.id in injected:
        return injected[evidence.id]
    return registry


def _store(writer: ArtifactWriter, artifacts: list[str], name: str, content: bytes) -> None:
    path = writer(name, content)
    artifacts.append(str(path))


def _rederive(document: DocumentFacts, registry: SourceRegistry, policy) -> DocumentFacts:
    """Re-derive usability with the ACTIVE policy threshold (not T05's fixed 0.85)."""
    threshold = Decimal(policy.word_review_threshold)

    def derive(fact: FieldFact, numeric: bool) -> FieldFact:
        if fact.usability == 'NOT_APPLICABLE':
            return fact
        return derive_fact(fact, registry, numeric, threshold, None)

    fields = {name: derive(fact, name in NUMERIC_FIELDS) for name, fact in document.fields.items()}
    items = [
        ItemFacts(
            id=item.id,
            name=derive(item.name, False),
            quantity=derive(item.quantity, True),
            unit=derive(item.unit, False),
            unit_price=derive(item.unit_price, True),
            line_amount=derive(item.line_amount, True),
        )
        for item in document.items
    ]
    return document.model_copy(update={'fields': fields, 'items': items})


def _reject_waived_checks(bundle: EvidenceBundle) -> None:
    """Applicability is code-decided; a document may not waive a mandatory check."""
    for document in bundle.documents:
        registry = bundle.registries.get(document.evidence_id)
        if registry is None:
            continue
        if (
            is_applicable(document, 'breakdown', registry)
            and document.template == 'TOTAL_ONLY'
        ):
            raise DomainError(
                'INVALID_ANALYSIS',
                f'{document.evidence_id}: breakdown applicable nhưng khai TOTAL_ONLY.',
            )


def _usable_required(document: DocumentFacts, registry: SourceRegistry | None) -> bool:
    """Header fields (merchant/date/total/currency) must be USABLE, never N/A."""
    if registry is None:
        return False
    for name in ('merchant', 'date', 'total', 'currency'):
        fact = document.fields.get(name)
        if fact is None or fact.usability != 'USABLE':
            return False
    return True


def _items_usable(document: DocumentFacts) -> bool:
    """True when every item carries the numeric basis a mapping comparison needs."""
    if not document.items:
        return False
    for item in document.items:
        for fact in (item.quantity, item.unit_price, item.line_amount):
            if fact.usability != 'USABLE':
                return False
    return True


def _maybe_cross_source(
    snapshot: CaseSnapshot,
    documents: list[DocumentFacts],
    registries: dict[str, SourceRegistry],
    providers: Providers,
    run_stage: Callable[[str, Callable[[], object]], object],
    artifact_writer: ArtifactWriter,
    artifacts: list[str],
) -> MappingProposal | None:
    """Map primary<->receipt items for WORK_PURCHASE.

    B1 self-joins rows whose normalized names match uniquely 1:1 and there is no
    contradiction (System §4), so a model that returns no pairs does not block a
    case code can resolve. The model's ``cross_source`` proposal is still used for
    unclear semantics; both go through the same INV-02 gate in ``evaluate``.
    """
    if snapshot.claim.profile != 'WORK_PURCHASE':
        return None
    primary = next((d for d in documents if d.kind == 'BILL'), None)
    receipt = next((d for d in documents if d.kind == 'GOODS_RECEIPT'), None)
    if primary is None or receipt is None:
        return None
    if not _usable_required(primary, registries.get(primary.evidence_id)):
        return None
    if not _usable_required(receipt, registries.get(receipt.evidence_id)):
        return None
    # Item numerics the mapping compares must be usable before spending the call.
    if not _items_usable(primary) or not _items_usable(receipt):
        return None

    partial = EvidenceBundle(
        documents=[primary, receipt],
        registries={primary.evidence_id: registries[primary.evidence_id],
                    receipt.evidence_id: registries[receipt.evidence_id]},
    )
    proposal = run_stage('cross_source', lambda: providers.cross_source(partial))
    _store(artifact_writer, artifacts, 'cross-source.json',
           proposal.model_dump_json().encode('utf-8'))

    # Code-side unique normalized-name 1:1 join; only when the model was silent on
    # pairs and flagged no conflicts. Full-coverage/uniqueness are re-checked by
    # INV-02, so this never loosens the gate.
    if not proposal.pairs and not proposal.conflicts:
        joined = _unique_name_mapping(primary, receipt)
        if joined is not None:
            return joined
    return proposal


def _normalized_name(item: ItemFacts) -> str:
    value = item.name.normalized_value
    return str(value).strip().casefold()


def _unique_name_mapping(
    primary: DocumentFacts, receipt: DocumentFacts
) -> MappingProposal | None:
    """Join items whose normalized names match uniquely 1:1, else ``None``.

    Requires full one-to-one coverage and no duplicate names on either side, so
    the join is unambiguous. Unclear semantics stay for the model/reviewer.
    """
    primary_names = [_normalized_name(item) for item in primary.items]
    receipt_names = [_normalized_name(item) for item in receipt.items]
    if not primary_names or not receipt_names:
        return None
    if any(not name for name in primary_names + receipt_names):
        return None
    if len(set(primary_names)) != len(primary_names):
        return None
    if len(set(receipt_names)) != len(receipt_names):
        return None
    if set(primary_names) != set(receipt_names):
        return None

    receipt_by_name = {name: item.id for name, item in zip(receipt_names, receipt.items)}
    pairs = [(item.id, receipt_by_name[name]) for item, name in zip(primary.items, primary_names)]
    refs = [ref for item in primary.items for ref in item.name.refs]
    return MappingProposal(pairs=pairs, refs=refs, conflicts=[])


# --- Context conflict surfacing ------------------------------------------------

def _context_conflicts(document: DocumentFacts, evidence: Evidence) -> list[Issue]:
    """A submitted source that says the payer is a company must not be ignored."""
    for name in _CONTEXT_PAYER_FIELDS:
        fact = document.fields.get(name)
        if fact is None:
            continue
        value = str(fact.normalized_value).strip().upper()
        if value in _REFUSAL_PAYERS:
            return [Issue(
                id='MODE-02:context', stable_key='MODE-02:context',
                issue_class='FACTUAL_UNKNOWN', owner_mode='EMPLOYEE',
                refs=list(fact.refs), blockers=['MODE-02'], status='OPEN',
                question=f'Nguồn {evidence.id} ghi khoản đã được trả bởi {value}; '
                         'cần xác nhận ai đã chi trả khoản này.',
            )]
    return []


def _merge_context_issues(decision: Decision, context_issues: list[Issue]) -> Decision:
    existing = {issue.stable_key for issue in decision.issues}
    merged = list(decision.issues)
    for issue in context_issues:
        if issue.stable_key not in existing:
            merged.append(issue)
            existing.add(issue.stable_key)

    # Exactly one MODE-02 CheckResult (matrix contract): replace the entry
    # ``evaluate`` already emitted (PASS) with the context-conflict FAIL rather
    # than appending a second one.
    conflict_check = CheckResult(
        rule_id='MODE-02', status='FAIL', dependencies=['context'], refs=[],
        reason='Nguồn context mâu thuẫn khai báo payer.', issue_ids=['MODE-02:context'])
    checks: list[CheckResult] = []
    replaced = False
    for check in decision.checks:
        if check.rule_id == 'MODE-02':
            checks.append(conflict_check)
            replaced = True
        else:
            checks.append(check)
    if not replaced:
        checks.append(conflict_check)

    return decision.model_copy(update={
        'action': 'REQUEST_INFO', 'completion_basis': None,
        'accepted_amount_vnd': None, 'issues': merged, 'checks': checks,
    })


__all__ = ['preflight', 'process']
