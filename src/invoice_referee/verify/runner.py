"""Sequential Verify runner over the real ``CaseService`` (T11).

The runner is the ONLY place expected labels live. It submits each synthetic case
through ``CaseService.submit``/``start_run``/``wait`` (the same production path
the UI uses), compares the actual decision to the manifest's expected outcome,
and produces a ``VerifyReport``. It never imports a second evaluator.

Mode:
- ``POLICY_REPLAY`` / ``PIPELINE_FAKE_OR_REPLAY``: a ``ReplayProviders`` supplies
  the frozen OCR/document/registry artifacts; the pipeline still runs validation,
  active-threshold re-derivation and ``evaluate``. No network.
- ``LIVE_END_TO_END``: not wired here (needs live providers + spend authorization,
  T15). The runner reports INCONCLUSIVE with a reason rather than fabricating.

An actual business ``REQUEST_INFO``/``ESCALATE`` can still be a testcase PASS when
it matches the expected outcome; the actual business status is never the verdict.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from invoice_referee.application.service import CaseService
from invoice_referee.domain.models import (
    DocumentFacts,
    EvidenceBundle,
    MappingProposal,
    SourceRegistry,
    Upload,
)
from invoice_referee.verify.manifest import (
    VerifyCase,
    VerifyManifest,
    VerifyReport,
    VerifyResult,
)
from invoice_referee.verify.replay import ReplayProviders

_TERMINAL = {'SUCCEEDED', 'FAILED', 'STOPPED'}


class VerifyRunner:
    def __init__(self, service: CaseService, result_root: Path) -> None:
        self._service = service
        self._root = Path(result_root)

    # --- public API -----------------------------------------------------------

    def run(self, manifest: VerifyManifest, *, owner_id: str | None = None) -> VerifyReport:
        started_at = datetime.now(timezone.utc)
        results: list[VerifyResult] = []
        reservation = owner_id or f'verify-{uuid.uuid4().hex[:8]}'
        if hasattr(self._service, 'reserve'):
            self._service.reserve(reservation)
        try:
            for case in manifest.cases:
                results.append(self._run_case(case, manifest, reservation))
        finally:
            if hasattr(self._service, 'release_reservation'):
                self._service.release_reservation(reservation)

        from invoice_referee.verify.metrics import summarize

        finished_at = datetime.now(timezone.utc)
        return VerifyReport(
            id=f'vr-{uuid.uuid4().hex[:12]}',
            manifest_hash=manifest.sha256,
            policy_version=manifest.policy_version,
            threshold_version=self._service.policy.threshold_version,
            mode=manifest.mode,
            results=results,
            metrics=summarize(results),
            started_at=started_at,
            finished_at=finished_at,
        )

    # --- one case -------------------------------------------------------------

    def _run_case(self, case: VerifyCase, manifest: VerifyManifest, owner_id: str) -> VerifyResult:
        started = time.perf_counter()
        if case.mode == 'LIVE_END_TO_END':
            return self._inconclusive(
                case, 'LIVE_END_TO_END chưa được nối; cần provider thật + cho phép chi tiêu (T15).',
                started,
            )

        uploads = [self._upload(case, up) for up in case.uploads]
        record = self._service.submit(case.claim, uploads)

        # Load replay artifacts, remapping the fixture's role-keyed evidence ids
        # to the ids the Repository actually assigned, onto the service's
        # provider boundary (a ReplayProviders in replay mode).
        provider = self._service.providers
        if isinstance(provider, ReplayProviders):
            provider.load(*self._artifacts(case, record))

        run = self._service.start_run(record.id, owner_id=owner_id)
        ended = self._service.wait(run.id, timeout_seconds=30)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        actual = self._actual(ended, self._service)
        verdict = self._verdict(case, actual)
        trace = self._write_trace(case, ended, actual)
        return VerifyResult(
            case_id=case.id,
            run_id=ended.id,
            input_hash=ended.input_hash,
            timestamp=datetime.now(timezone.utc),
            expected=case.expected,
            actual=actual,
            verdict=verdict,
            mode=case.mode,
            elapsed_ms=elapsed_ms,
            trace_path=str(trace) if trace else None,
        )

    # --- helpers --------------------------------------------------------------

    def _upload(self, case: VerifyCase, up) -> Upload:
        path = self._resolve(case, up.path)
        content = path.read_bytes()
        return Upload(original_name=path.name, mime=up.mime, content=content, role=up.role)

    def _resolve(self, case: VerifyCase, rel: str) -> Path:
        # ``raw_ground_truth_path`` is ``<fixture_root>/gold/<id>.json``; the
        # uploads/replay artifacts are stored relative to ``<fixture_root>``.
        fixture_root = Path(case.raw_ground_truth_path).parent.parent
        return (fixture_root / rel).resolve()

    def _artifacts(self, case: VerifyCase, record) -> tuple[dict, dict, MappingProposal | None]:
        # The fixture artifacts carry LOGICAL evidence ids ('e-primary'/'e-receipt');
        # remap them to the real ids the Repository assigned (by role) so the
        # pipeline resolves refs against the right evidence.
        logical_to_real = {
            'e-primary': next((e.id for e in record.evidence if e.role == 'PRIMARY_BILL'), None),
            'e-receipt': next((e.id for e in record.evidence if e.role == 'GOODS_RECEIPT'), None),
        }
        logical_to_real = {k: v for k, v in logical_to_real.items() if v is not None}

        docs: dict[str, DocumentFacts] = {}
        regs: dict[str, SourceRegistry] = {}
        mapping = None
        for kind, rel in case.replay_artifacts.items():
            payload = self._remap(json.loads(self._resolve(case, rel).read_text(encoding='utf-8')), logical_to_real)
            if kind == 'document':
                doc = DocumentFacts.model_validate(payload)
                docs[doc.evidence_id] = doc
            elif kind == 'registry':
                reg = SourceRegistry.model_validate(payload)
                regs[reg.evidence_id] = reg
            elif kind == 'receipt_document':
                doc = DocumentFacts.model_validate(payload)
                docs[doc.evidence_id] = doc
            elif kind == 'receipt_registry':
                reg = SourceRegistry.model_validate(payload)
                regs[reg.evidence_id] = reg
            elif kind == 'mapping':
                mapping = MappingProposal.model_validate(payload)
        return docs, regs, mapping

    @staticmethod
    def _remap(obj, mapping: dict[str, str]):
        if isinstance(obj, dict):
            return {k: VerifyRunner._remap(v, mapping) for k, v in obj.items()}
        if isinstance(obj, list):
            return [VerifyRunner._remap(v, mapping) for v in obj]
        if isinstance(obj, str) and obj in mapping:
            return mapping[obj]
        return obj

    def _actual(self, ended, service: CaseService) -> dict:
        result = ended.result
        decision = result.decision if result is not None else None
        request = service.payment_request(ended.case_id)
        return {
            'execution_status': ended.status,
            'action': decision.action if decision else None,
            'completion_basis': decision.completion_basis if decision else None,
            'issue_classes': sorted({i.issue_class for i in decision.issues}) if decision else [],
            'owners': sorted({i.owner_mode for i in decision.issues}) if decision else [],
            'rules': sorted({c.rule_id for c in decision.checks}) if decision else [],
            'amount_vnd': decision.accepted_amount_vnd if decision else None,
            'request_count': 1 if request is not None else 0,
            'technical_code': decision.technical_code if decision else None,
        }

    def _verdict(self, case: VerifyCase, actual: dict) -> str:
        exp = case.expected
        if actual['execution_status'] != exp.execution_status:
            # A FAILED execution for a case that expected SUCCEEDED is a FAIL;
            # an expected FAILED/technical case (TC15) passes when it matches.
            return 'FAIL'
        if actual['action'] != exp.action:
            return 'FAIL'
        if exp.completion_basis is not None and actual['completion_basis'] != exp.completion_basis:
            return 'FAIL'
        if exp.amount_vnd is not None and actual['amount_vnd'] != exp.amount_vnd:
            return 'FAIL'
        if actual['request_count'] != exp.request_count:
            return 'FAIL'
        if not set(exp.issue_classes).issubset(set(actual['issue_classes'])):
            return 'FAIL'
        if not set(exp.owners).issubset(set(actual['owners'])):
            return 'FAIL'
        if not set(exp.required_rules).issubset(set(actual['rules'])):
            return 'FAIL'
        return 'PASS'

    def _inconclusive(self, case: VerifyCase, reason: str, started: float) -> VerifyResult:
        return VerifyResult(
            case_id=case.id,
            run_id=None,
            input_hash=None,
            timestamp=datetime.now(timezone.utc),
            expected=case.expected,
            actual={'reason': reason},
            verdict='INCONCLUSIVE',
            mode=case.mode,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            trace_path=None,
        )

    def _write_trace(self, case: VerifyCase, ended, actual: dict) -> Path | None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f'{case.id}-{ended.id}.json'
        payload = {
            'case_id': case.id,
            'run_id': ended.id,
            'status': ended.status,
            'input_hash': ended.input_hash,
            'policy_version': ended.policy_version,
            'threshold_version': ended.threshold_version,
            'identities': [i.model_dump(mode='json') for i in ended.identities],
            'actual': actual,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return path
