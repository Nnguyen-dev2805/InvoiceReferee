"""T08 CaseService — orchestration, one-active-run slot, atomic Stop/action.

Ledger §3.2 interface (exact):

    CaseService(repo, providers, policy)
      submit(claim, uploads) -> CaseRecord
      start_run(case_id, *, owner_id=None) -> RunRecord
      get_run(run_id) -> RunRecord
      act(action) -> CaseRecord
      stop(run_id) -> StopReply
      wait(run_id, timeout_seconds) -> RunRecord
      set_policy(policy, *, actor_mode, reason) -> None
      close() -> None

Design rulings (recorded at T08; System §6–§8, Rulebook §5/§6):

- **One active run per process.** A ``ThreadPoolExecutor(max_workers=1)`` runs the
  pipeline off the request thread and a slot lock rejects a queued second run.
  ``start_run`` captures the snapshot/policy, persists the run under the lock and
  returns immediately; the worker runs ``process`` with persisted checkpoints,
  then ``finalize_run`` in ONE transaction (the final Stop guard). The slot is
  released only after the worker ends.
- **Busy semantics.** Human input/approval/override while a run is RUNNING raises
  ``RUN_BUSY``; STOP is always accepted. ``act`` validates + persists + starts the
  reevaluation on the SAME slot lock, so two requests cannot interleave.
- **Stop.** Routed through ``Repository.request_stop`` (NOT ``apply_human_action``):
  the stop flag + event are persisted BEFORE acknowledgement, the stop carries no
  case_version change, and the final transaction refuses any late payment. A
  ``StoppedRun`` ends STOPPED (never FAILED); an unexpected exception ends
  FAILED/NONE with a technical event.
- **Startup** marks an in-flight run interrupted (no auto-rerun) and uses the
  persisted active config when present, else the (inactive) file config.
- **set_policy** is idle-only. ``actor_mode=SYSTEM`` may change ONLY the active
  config's ``word_review_threshold``/``threshold_version``; a human POLICY_OWNER
  activation is a distinct actor. The audit event distinguishes automatic
  adaptation (``automatic=True``) from human approval.
- **Deep confirmation checks** (T07 owns the shape/ownership; the bundle lives
  here): CONFIRM_FIELD refs must resolve in the owning registry and the confirmed
  fact must exist; CONFIRM_MAPPING pairs must resolve to real item IDs, cover
  every item one-to-one, and not match items on ambiguous units.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path

from invoice_referee.application.executor import RunExecutor
from invoice_referee.application.human import validate_human_action
from invoice_referee.application.pipeline import process
from invoice_referee.domain.models import (
    AuditEvent,
    CaseRecord,
    CaseSnapshot,
    Claim,
    Decision,
    DemoMode,
    DomainError,
    EvidenceBundle,
    HumanAction,
    PaymentRequest,
    PipelineResult,
    PolicyActor,
    PolicyConfig,
    RunRecord,
    SourceRef,
    StopReply,
    StoppedRun,
    Upload,
)
from invoice_referee.extraction.providers import Providers
from invoice_referee.extraction.validation import check_ref
from invoice_referee.policy.numeric import UNIT_FACTORS
from invoice_referee.storage.artifacts import put_artifact
from invoice_referee.storage.repository import Repository

# A run that is no longer in flight; a new run may start.
_TERMINAL = {'STOPPED', 'SUCCEEDED', 'FAILED'}
# Protected config fields a SYSTEM threshold update may never touch.
_SYSTEM_PROTECTED = (
    'version', 'origin', 'activation_id', 'active', 'currency',
    'auto_approval_max', 'standard_policy_max', 'inventory_date_gap_days',
    'comparison_money_tolerance', 'normalized_unit_price_tolerance',
)


def _invalid(message: str) -> DomainError:
    return DomainError('INVALID_ACTION', message)


class CaseService:
    """One-process application service: run lifecycle, Stop and human actions."""

    def __init__(self, repo: Repository, providers: Providers, policy: PolicyConfig) -> None:
        self._repo = repo
        self._providers = providers
        self._policy = self._resolve_policy(policy)
        # Startup: any run left in flight by a previous process is presented as
        # interrupted/technical failed; it is never auto-rerun (System §8).
        self._repo.mark_interrupted_runs()
        self._executor = RunExecutor()
        # The worker future per run id. ``wait`` joins it so it returns only after
        # the worker has RELEASED the slot (deterministic "run over" semantics).
        self._futures: dict[str, Future] = {}
        self._closed = False
        # Owner id of a Verify suite holding a reservation (T11); None when free.
        self._reserved_by: str | None = None

    # --- properties -----------------------------------------------------------

    @property
    def policy(self) -> PolicyConfig:
        """The active policy config the next run will use."""
        return self._policy

    @property
    def providers(self) -> Providers:
        """The provider boundary (T11 Verify swaps artifacts through this).

        Read-only projection: a caller may adjust a replay provider's per-case
        artifacts, but must not replace the provider stack mid-process.
        """
        return self._providers

    # --- Verify reservation (T11) ---------------------------------------------
    # A Verify suite holds a reservation for its whole run so an interactive
    # run/action/policy update cannot interleave between its cases. The suite
    # passes its owner id to ``start_run``; a different owner is refused busy.

    def reserve(self, owner_id: str) -> None:
        if self._reserved_by is not None and self._reserved_by != owner_id:
            raise DomainError('RUN_BUSY', 'Đang có phiên Verify giữ chỗ xử lý.')
        self._reserved_by = owner_id

    def release_reservation(self, owner_id: str) -> None:
        if self._reserved_by == owner_id:
            self._reserved_by = None

    # --- read-only projections (T09 API routes) -------------------------------
    # Narrow read accessors so the API never receives the mutable Repository (a
    # route could otherwise bypass ``_ensure_open`` and mutate state). These only
    # read; every mutation still goes through a service method.

    def get_case(self, case_id: str) -> CaseRecord:
        """Read one case (projection). Raises ``NOT_FOUND`` when absent."""
        return self._repo.get_case(case_id)

    def list_cases(self) -> list[CaseRecord]:
        """Read all local cases (no tenancy)."""
        return self._repo.list_cases()

    def open_issue_owners(self) -> dict[str, list[str]]:
        """Per case, the owner modes with an OPEN issue in the current run.

        Feeds the role inbox; it only reads persisted issue ownership and never
        recomputes a decision.
        """
        return self._repo.open_issue_owners()

    def case_history(self, case_id: str) -> list[AuditEvent]:
        """Read the audit timeline for a case."""
        return self._repo.history(case_id)

    def payment_request(self, case_id: str) -> PaymentRequest | None:
        """Read the current (CREATED) payment request, if any."""
        return self._repo.get_payment_request(case_id)

    # --- intake ---------------------------------------------------------------

    def submit(self, claim: Claim, uploads: list[Upload]) -> CaseRecord:
        self._ensure_open()
        return self._repo.create_case(claim, uploads)

    # --- runs -----------------------------------------------------------------

    def start_run(self, case_id: str, *, owner_id: str | None = None) -> RunRecord:
        """Capture the snapshot/policy, persist the run, and start the worker."""
        self._ensure_open()
        # A Verify suite holds the slot for its whole run; an interactive caller
        # (a different owner) is refused while the reservation is active.
        if self._reserved_by is not None and owner_id != self._reserved_by:
            raise DomainError('RUN_BUSY', 'Đang có phiên Verify giữ chỗ xử lý.')
        self._executor.acquire()
        submitted = False
        try:
            run = self._start_locked(case_id)
            submitted = True
        finally:
            if not submitted:
                self._executor.release()
        return run

    def get_run(self, run_id: str) -> RunRecord:
        return self._repo.get_run(run_id)

    def wait(self, run_id: str, timeout_seconds: float) -> RunRecord:
        """Poll until the run is terminal or the timeout elapses.

        A timeout returns the CURRENT (non-terminal) run; it never flips the
        execution status to SUCCEEDED.
        """
        deadline = time.monotonic() + timeout_seconds
        while True:
            run = self._repo.get_run(run_id)
            if run.status in _TERMINAL:
                # Join the worker so the slot is already released when wait returns
                # (the worker releases it right after finalize).
                future = self._futures.get(run_id)
                if future is not None:
                    try:
                        future.result(timeout=max(0.0, deadline - time.monotonic()))
                    except Exception:  # noqa: BLE001 — worker errors are already persisted
                        # A worker exception is already persisted as FAILED (and a
                        # TimeoutError just means the worker is still unwinding);
                        # wait reports the run, never the worker's raw traceback.
                        pass
                return run
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return run
            time.sleep(min(0.01, remaining))

    def stop(self, run_id: str) -> StopReply:
        """Acknowledge a Stop by persisting the flag/event BEFORE returning."""
        return self._repo.request_stop(run_id)

    # --- human actions --------------------------------------------------------

    def act(self, action: HumanAction) -> CaseRecord:
        """Validate, persist and reevaluate in ONE slot window (no interleaving).

        The slot is acquired for the whole mutation + new run, so a second human
        request cannot interleave between persisting the action and starting its
        reevaluation. STOP is a dedicated route (``stop``), not a human action.
        """
        self._ensure_open()
        if action.kind == 'STOP':
            raise _invalid('STOP dùng route stop(run_id), không qua act().')
        self._executor.acquire()
        submitted = False
        try:
            self._require_idle(action.case_id)
            submitted = self._apply_and_start(action)
            return self._repo.get_case(action.case_id)
        finally:
            if not submitted:
                self._executor.release()

    def add_evidence(
        self, *, case_id: str, mode: DemoMode, uploads: list[Upload], reason: str,
        issue_id: str | None = None,
    ) -> CaseRecord:
        """Atomically attach uploads and start a reevaluation.

        Extra beyond the ledger (T09's multipart ADD_EVIDENCE needs it): the
        uploads are staged all-or-nothing, then an ``ADD_EVIDENCE`` action naming
        the NEW evidence ids is validated/persisted/applied on the SAME slot, so a
        version bump can never be recorded without the linked evidence rows. If
        every upload duplicates stored bytes, nothing changes and the case is
        returned unchanged.
        """
        self._ensure_open()
        self._executor.acquire()
        submitted = False
        try:
            self._require_idle(case_id)
            rows = self._repo.stage_evidence(case_id, uploads)
            if not rows:
                return self._repo.get_case(case_id)  # nothing new; no version bump
            snapshot = self._repo.snapshot(case_id, self._policy)
            action = HumanAction(
                id=f'ha-{uuid.uuid4().hex}', case_id=case_id,
                case_version=snapshot.case_version, issue_id=issue_id, mode=mode,
                kind='ADD_EVIDENCE', payload={'evidence_ids': [e.id for e in rows]},
                reason=reason, created_at=datetime.now(timezone.utc),
            )
            submitted = self._apply_and_start(action)
            return self._repo.get_case(case_id)
        finally:
            if not submitted:
                self._executor.release()

    # --- policy ---------------------------------------------------------------

    def set_policy(
        self, policy: PolicyConfig, *, actor_mode: PolicyActor, reason: str
    ) -> None:
        """Persist a policy change (idle only) and update the active config."""
        self._ensure_open()
        if self._reserved_by is not None:
            raise DomainError('RUN_BUSY', 'Đang có phiên Verify giữ chỗ xử lý.')
        self._executor.acquire()
        try:
            effective = self._system_threshold(policy) if actor_mode == 'SYSTEM' else policy
            self._repo.record_policy_change(effective, actor_mode=actor_mode, reason=reason)
            self._policy = effective
        finally:
            self._executor.release()

    # --- lifetime -------------------------------------------------------------

    def close(self) -> None:
        """Stop accepting work and wait for the running worker to finish."""
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

    # --- internal: policy -----------------------------------------------------

    def _resolve_policy(self, policy: PolicyConfig) -> PolicyConfig:
        persisted = self._repo.get_active_policy()
        return persisted if persisted is not None else policy

    def _system_threshold(self, policy: PolicyConfig) -> PolicyConfig:
        base = self._policy
        if not base.active:
            raise DomainError('INVALID_INPUT', 'Chưa có policy active để cập nhật threshold.')
        for name in _SYSTEM_PROTECTED:
            if getattr(policy, name) != getattr(base, name):
                raise DomainError('INVALID_INPUT', f'SYSTEM không được đổi {name}.')
        return base.model_copy(update={
            'word_review_threshold': policy.word_review_threshold,
            'threshold_version': policy.threshold_version,
        })

    # --- internal: run lifecycle ----------------------------------------------

    def _start_locked(self, case_id: str) -> RunRecord:
        """Persist the run and hand it to the worker. Caller holds the slot."""
        snapshot = self._repo.snapshot(case_id, self._policy)
        run = self._repo.create_run(snapshot)
        # MVP bound: at most one run is in flight, so dropping DONE futures here
        # keeps ``_futures`` to ~1 entry instead of growing per run.
        self._futures = {rid: f for rid, f in self._futures.items() if not f.done()}
        self._futures[run.id] = self._executor.submit(lambda: self._run_sync(run.id, snapshot))
        return run

    def _run_sync(self, run_id: str, snapshot: CaseSnapshot) -> None:
        if self._closed:
            self._repo.finalize_technical(
                run_id, code='SERVICE_CLOSED', reason='Service đã đóng trước khi run bắt đầu.')
            return

        def checkpoint(stage: str) -> None:
            self._repo.record_stage(run_id, stage, None, f'stage {stage}')
            self._repo.assert_run_current(run_id)

        def writer(name: str, content: bytes) -> Path:
            return put_artifact(self._repo._artifact_root, snapshot.case_id, run_id, name, content)

        try:
            result = process(
                snapshot, self._providers, checkpoint, writer,
                confirmations=snapshot.confirmations,
            )
        except StoppedRun:
            self._repo.finalize_run(run_id, _stopped_result())
            return
        except DomainError as exc:
            self._repo.finalize_technical(run_id, code=exc.code, reason=exc.message)
            return
        except Exception as exc:  # noqa: BLE001 — never leak a raw traceback as a business result
            self._repo.finalize_technical(
                run_id, code='EXECUTION_FAILED', reason=f'{type(exc).__name__}: unexpected failure.')
            return
        self._repo.finalize_run(run_id, result)

    def _require_idle(self, case_id: str) -> None:
        """Reject a mutation while the case still has an in-flight run."""
        if self._reserved_by is not None:
            raise DomainError('RUN_BUSY', 'Đang có phiên Verify giữ chỗ xử lý.')
        case = self._repo.get_case(case_id)
        if case.current_run_id is not None:
            current = self._repo.get_run(case.current_run_id)
            if current.status not in _TERMINAL:
                raise DomainError(
                    'RUN_BUSY',
                    'Đang có run chạy; hãy Stop và chờ kết thúc rồi cập nhật.',
                )

    def _apply_and_start(self, action: HumanAction) -> bool:
        """Validate + persist + start the reevaluation. Caller holds the slot.

        Returns ``True`` when a background worker was submitted (it will release
        the slot), or ``False`` when the action was fully handled synchronously
        (DENY / OVERRIDE-DENY: a REJECT decision is finalized inline, no worker),
        in which case the CALLER must release the slot.
        """
        case = self._repo.get_case(action.case_id)
        snapshot = self._repo.snapshot(action.case_id, self._policy)
        decision = self._current_decision(case)
        validated = validate_human_action(action, snapshot, decision)
        _deep_validate(validated, self._current_bundle(case))
        self._repo.apply_human_action(validated)
        if _is_deny(validated):
            self._finalize_deny(action.case_id, validated)
            return False
        self._start_locked(action.case_id)
        return True

    def _current_decision(self, case: CaseRecord) -> Decision:
        if case.current_run_id is None:
            return Decision(action='NONE', reasons=[])
        run = self._repo.get_run(case.current_run_id)
        return run.result.decision if run.result is not None else Decision(action='NONE', reasons=[])

    def _current_bundle(self, case: CaseRecord) -> EvidenceBundle:
        if case.current_run_id is None:
            return EvidenceBundle()
        run = self._repo.get_run(case.current_run_id)
        return run.result.bundle if run.result is not None else EvidenceBundle()

    def _finalize_deny(self, case_id: str, action: HumanAction) -> CaseRecord:
        """DENY persists a REJECT decision with the human reason; no providers."""
        snapshot = self._repo.snapshot(case_id, self._policy)
        run = self._repo.create_run(snapshot)
        decision = Decision(
            action='REJECT', completion_basis=None, accepted_amount_vnd=None,
            checks=[], issues=[], reasons=[action.reason], technical_code=None,
        )
        self._repo.finalize_run(run.id, PipelineResult(
            decision=decision, bundle=EvidenceBundle(), artifacts=[],
            identities=[], stage_durations_ms={}, provider_calls=0, repair_calls=0,
        ))
        return self._repo.get_case(case_id)

    def _ensure_open(self) -> None:
        if self._closed:
            raise DomainError('OUT_OF_DOMAIN', 'CaseService đã đóng.')


# --- Deep confirmation validation (bundle-aware; T07 owns shape/ownership) -----

def _is_deny(action: HumanAction) -> bool:
    if action.kind == 'DENY':
        return True
    return action.kind == 'OVERRIDE' and action.payload.get('operation') == 'DENY'


def _parse_field_path(field: str) -> tuple[str, str, object]:
    parts = field.split('.')
    if len(parts) == 3 and parts[1] == 'fields' and parts[0] and parts[2]:
        return parts[0], 'fields', parts[2]
    if len(parts) == 4 and parts[1] == 'items' and parts[0] and parts[2] and parts[3]:
        return parts[0], 'items', (parts[2], parts[3])
    raise _invalid(f'field {field!r} không phải field path hợp lệ.')


def _document(bundle: EvidenceBundle, evidence_id: str):
    doc = next((d for d in bundle.documents if d.evidence_id == evidence_id), None)
    if doc is None:
        raise _invalid(f'Không có document {evidence_id!r} trong bundle hiện hành.')
    return doc


def _resolve_refs(refs: object, bundle: EvidenceBundle, evidence_id: str) -> list[SourceRef]:
    if not isinstance(refs, list) or not refs:
        raise _invalid('Confirmation cần refs không rỗng.')
    parsed: list[SourceRef] = []
    for entry in refs:
        try:
            ref = SourceRef.model_validate(entry)
        except Exception:  # noqa: BLE001 — any malformed ref is an invalid action
            raise _invalid('Ref xác nhận không đúng cấu trúc SourceRef.')
        if ref.evidence_id != evidence_id:
            raise _invalid(f'Ref thuộc {ref.evidence_id!r}, không phải {evidence_id!r}.')
        registry = bundle.registries.get(evidence_id)
        if registry is None:
            raise _invalid(f'Không có registry cho {evidence_id!r}.')
        try:
            check_ref(ref, registry)
        except DomainError as exc:
            raise _invalid(f'Ref không resolve được: {exc.message}')
        parsed.append(ref)
    return parsed


def _ref_key(ref: SourceRef) -> tuple[str, int, str, str, str]:
    return (ref.evidence_id, ref.page_index, ref.block_id, ref.locator, ref.raw_value)


def _deep_validate(action: HumanAction, bundle: EvidenceBundle) -> None:
    """Enforce the bundle-aware checks T07's signature cannot (T08-owned)."""
    if action.kind == 'CONFIRM_FIELD':
        _deep_confirm_field(action, bundle)
    elif action.kind == 'CONFIRM_MAPPING':
        _deep_confirm_mapping(action, bundle)
    elif action.kind == 'OVERRIDE':
        operation = action.payload.get('operation')
        values = action.payload.get('values') or {}
        inner = action.model_copy(update={'kind': operation, 'payload': dict(values)})
        if operation == 'CONFIRM_FIELD':
            _deep_confirm_field(inner, bundle)
        elif operation == 'CONFIRM_MAPPING':
            _deep_confirm_mapping(inner, bundle)


def _deep_confirm_field(action: HumanAction, bundle: EvidenceBundle) -> None:
    evidence_id, segment, key = _parse_field_path(action.payload['field'])
    doc = _document(bundle, evidence_id)
    if segment == 'fields':
        fact = doc.fields.get(str(key))
        if fact is None:
            raise _invalid(f'Document {evidence_id!r} không có field {key!r}.')
    else:
        item_id, subfield = key  # type: ignore[misc]
        item = next((it for it in doc.items if it.id == item_id), None)
        if item is None:
            raise _invalid(f'Document {evidence_id!r} không có item {item_id!r}.')
        if not hasattr(item, subfield):
            raise _invalid(f'Item {item_id!r} không có sub-field {subfield!r}.')
        fact = getattr(item, subfield)
        if subfield in ('quantity', 'unit_price', 'line_amount') and item.unit.refs:
            # A confirmed item number is only meaningful on a known unit basis;
            # its unit source must resolve or the basis is ambiguous.
            _resolve_refs(item.unit.refs, bundle, evidence_id)
    parsed = _resolve_refs(action.payload['refs'], bundle, evidence_id)
    fact_keys = {_ref_key(r) for r in fact.refs}
    if fact_keys and not fact_keys <= {_ref_key(r) for r in parsed}:
        raise _invalid('Ref xác nhận không bao phủ nguồn của field.')


def _deep_confirm_mapping(action: HumanAction, bundle: EvidenceBundle) -> None:
    primary = next((d for d in bundle.documents if d.kind == 'BILL'), None)
    receipt = next((d for d in bundle.documents if d.kind == 'GOODS_RECEIPT'), None)
    if primary is None or receipt is None:
        raise _invalid('CONFIRM_MAPPING cần cả primary bill và goods receipt.')
    for entry in action.payload['refs']:
        try:
            ref = SourceRef.model_validate(entry)
        except Exception:  # noqa: BLE001
            raise _invalid('Ref mapping không đúng cấu trúc SourceRef.')
        registry = bundle.registries.get(ref.evidence_id)
        if registry is None:
            raise _invalid(f'Không có registry cho {ref.evidence_id!r}.')
        try:
            check_ref(ref, registry)
        except DomainError as exc:
            raise _invalid(f'Ref mapping không resolve được: {exc.message}')

    primary_items = {item.id: item for item in primary.items}
    receipt_items = {item.id: item for item in receipt.items}
    seen_primary: set[str] = set()
    seen_receipt: set[str] = set()
    for pair in action.payload['pairs']:
        pid, rid = pair
        if pid not in primary_items:
            raise _invalid(f'Item primary {pid!r} không tồn tại.')
        if rid not in receipt_items:
            raise _invalid(f'Item receipt {rid!r} không tồn tại.')
        if pid in seen_primary or rid in seen_receipt:
            raise _invalid('Cặp mapping trùng ID.')
        seen_primary.add(pid)
        seen_receipt.add(rid)
        _require_compatible_units(primary_items[pid], receipt_items[rid])
    if seen_primary != set(primary_items) or seen_receipt != set(receipt_items):
        raise _invalid('Mapping phải phủ một-một toàn bộ item hai bên.')


def _require_compatible_units(primary_item, receipt_item) -> None:
    p_unit = str(primary_item.unit.normalized_value).strip().lower()
    r_unit = str(receipt_item.unit.normalized_value).strip().lower()
    p_base = UNIT_FACTORS.get(p_unit, (p_unit, '1'))[0]
    r_base = UNIT_FACTORS.get(r_unit, (r_unit, '1'))[0]
    if p_base != r_base:
        raise _invalid(f'Đơn vị {p_unit!r} và {r_unit!r} không cùng basis; mapping mơ hồ.')


def _stopped_result() -> PipelineResult:
    return PipelineResult(
        decision=Decision(action='NONE', completion_basis=None, accepted_amount_vnd=None,
                          checks=[], issues=[], reasons=['Run stopped.'], technical_code=None),
        bundle=EvidenceBundle(), artifacts=[], identities=[], stage_durations_ms={},
        provider_calls=0, repair_calls=0,
    )


__all__ = ['CaseService']
