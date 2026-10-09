"""Settlement service (W02): application workflow over store + pipeline.

The service owns the in-process executor: a run is accepted (persisted QUEUED),
then executed on a worker thread bounded by a semaphore (pilot: 2 concurrent
runs). ``wait`` blocks on a per-run event so tests and UI can follow a run to a
terminal state. Stop/revision/epoch guards are re-checked at publish inside
the store transaction, so late output never becomes current.
"""
from __future__ import annotations

import threading
from time import monotonic
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    AuthorityGrant,
    CaseView,
    Command,
    Report,
    RunBudget,
    RunInput,
    RunStatus,
    RunView,
    SourceRecord,
    Submission,
    Upload,
    fingerprint,
)
from invoice_referee.settlement.pipeline import Reader, process
from invoice_referee.settlement.store import Store

_STATUS_BY_CODE = {
    "STOP_ACTIVE": "STOPPED",
    "STALE_INPUT": "SUPERSEDED",
    "BUDGET_EXHAUSTED": "TIMED_OUT",
}


class ServiceConfig(BaseModel):
    """Pilot envelope (System §S5) plus explicit demo authority grants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = "FAKE_OR_REPLAY"
    max_active_runs: StrictInt = 2
    run_deadline_seconds: float = 240.0
    max_provider_calls_per_run: StrictInt = 32
    authority: list[AuthorityGrant] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=lambda: {
        "version": "settlement-demo-v0", "activated": True,
        "origin": "RULEBOOK 2026-10-09 (demo, not company law)",
    })


class Service:
    """Workflow facade shared by API, UI and evaluator."""

    def __init__(self, store: Store, reader: Reader,
                 policy: dict[str, Any] | None = None,
                 config: ServiceConfig | None = None) -> None:
        self.store = store
        self.reader = reader
        self.config = config or ServiceConfig()
        self.policy = policy or self.config.policy
        self._events: dict[str, threading.Event] = {}
        self._events_lock = threading.Lock()
        self._slots = threading.Semaphore(self.config.max_active_runs)

    # --- W01 passthroughs ---------------------------------------------------

    def submit(self, submission: Submission, command: Command) -> CaseView:
        return self.store.create_case(submission, command)

    def get_case(self, case_id: str) -> CaseView:
        return self.store.get_case(case_id)

    def revise(self, case_id: str, submission: Submission,
               command: Command) -> CaseView:
        return self.store.revise(case_id, submission, command)

    def add_source(self, case_id: str, upload: Upload,
                   command: Command) -> SourceRecord:
        return self.store.add_source(case_id, upload, command)

    # --- runs ----------------------------------------------------------------

    def start(self, case_id: str, command: Command) -> RunView:
        snapshot = self.store.snapshot(case_id)
        run_input = RunInput(
            case_id=snapshot.case_id,
            case_version=snapshot.case_version,
            input_revision=snapshot.input_revision,
            control_epoch=snapshot.control_epoch,
            submission=snapshot.submission,
            sources=snapshot.sources,
            coverage=None,
            policy=self.policy,
            authority=self.config.authority,
            response_refs=[],
            config={"reader_mode": self.reader.mode},
            snapshot_hash=fingerprint("RUN_SNAPSHOT", {
                "case_id": snapshot.case_id,
                "input_revision": snapshot.input_revision,
                "control_epoch": snapshot.control_epoch,
                "sources": [[s.id, s.sha256] for s in snapshot.sources],
                "submission": snapshot.submission.model_dump(mode="json"),
            }),
        )
        run = self.store.create_run(run_input, command)
        if run.idempotent_replay:
            return run
        event = threading.Event()
        with self._events_lock:
            self._events[run.id] = event
        budget = RunBudget(
            deadline=monotonic() + self.config.run_deadline_seconds,
            max_calls=self.config.max_provider_calls_per_run,
        )
        worker = threading.Thread(target=self._execute, daemon=True,
                                  args=(run.id, run_input, budget, event))
        worker.start()
        return run

    def _execute(self, run_id: str, run_input: RunInput,
                 budget: RunBudget, event: threading.Event) -> None:
        try:
            with self._slots:
                self.store.mark_run(run_id, "RUNNING")
                checkpoint = self._checkpoint(run_input)
                report = process(run_input, self.reader, budget, checkpoint,
                                 run_id=run_id)
                self.store.publish(run_id, report)
        except DomainError as error:
            status: RunStatus = _STATUS_BY_CODE.get(error.code, "FAILED")
            try:
                self.store.mark_run(run_id, status,
                                    detail=f"{error.code}: {error.message}")
            except DomainError:
                pass  # already terminal (e.g. publish guard set STOPPED)
        except Exception as error:  # noqa: BLE001 — technical failure axis
            try:
                self.store.mark_run(run_id, "FAILED", detail=f"TECHNICAL: {error}")
            except DomainError:
                pass
        finally:
            event.set()
            with self._events_lock:
                self._events.pop(run_id, None)

    def _checkpoint(self, run_input: RunInput) -> Callable[[str], None]:
        """Validate Stop/revision/epoch before each pipeline stage."""

        def check(stage: str) -> None:
            case = self.store.get_case(run_input.case_id)
            if case.stop_active:
                raise DomainError("STOP_ACTIVE",
                                  "Hồ sơ đang Stop; dừng tại stage " + stage)
            if (case.control_epoch != run_input.control_epoch
                    or case.input_revision != run_input.input_revision):
                raise DomainError("STALE_INPUT",
                                  "Input đã thay đổi; run bị thay thế tại " + stage)

        return check

    def wait(self, run_id: str, timeout: float | None = None) -> RunView:
        with self._events_lock:
            event = self._events.get(run_id)
        if event is not None:
            event.wait(timeout if timeout is not None else
                       self.config.run_deadline_seconds + 5)
        return self.store.get_run(run_id)

    def get_run(self, run_id: str) -> RunView:
        return self.store.get_run(run_id)

    def report(self, run_id: str) -> Report:
        run = self.store.get_run(run_id)
        report = self.store.get_report(run_id)
        if report is None or run.status != "SUCCEEDED":
            raise DomainError(
                "REPORT_NOT_READY",
                f"Run {run_id} chưa có report (status {run.status}).",
            )
        return report
