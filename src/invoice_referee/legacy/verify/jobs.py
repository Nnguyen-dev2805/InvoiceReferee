"""Background Verify jobs for the API (T11).

A Verify suite runs in ONE background thread that drives the real ``CaseService``
and waits. The provider execution still happens on the service's single executor;
the job thread only orchestrates submit/start/wait, so it never blocks the HTTP
handler or the executor. ``GET`` returns live progress; a report is only present
once the run finished (never fabricated).
"""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

from invoice_referee.application.service import CaseService
from invoice_referee.verify.manifest import VerifyJob, VerifyManifest, VerifyReport
from invoice_referee.verify.runner import VerifyRunner


class VerifyJobs:
    def __init__(self, service: CaseService, result_root: Path) -> None:
        self._service = service
        self._root = Path(result_root)
        self._jobs: dict[str, VerifyJob] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self, manifest: VerifyManifest) -> VerifyJob:
        job_id = f'vj-{uuid.uuid4().hex[:12]}'
        job = VerifyJob(id=job_id, status='QUEUED', completed_count=0,
                        total_count=len(manifest.cases), report=None)
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run, args=(job_id, manifest), daemon=True)
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return job

    def get(self, job_id: str) -> VerifyJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            from invoice_referee.domain.models import DomainError

            raise DomainError('NOT_FOUND', f'Không tìm thấy verify job {job_id}.')
        return job

    def _run(self, job_id: str, manifest: VerifyManifest) -> None:
        self._set(job_id, status='RUNNING')
        runner = VerifyRunner(self._service, self._root)
        try:
            report = runner.run(manifest, owner_id=job_id)
        except Exception as exc:  # noqa: BLE001 — a job failure is surfaced, not hidden
            self._set(job_id, status='FAILED', report=None)
            return
        self._set(job_id, status='SUCCEEDED', report=report,
                  completed_count=len(report.results))

    def _set(self, job_id: str, **updates) -> None:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                return
            self._jobs[job_id] = current.model_copy(update=updates)
