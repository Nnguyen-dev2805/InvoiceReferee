"""Settlement service (W02): application workflow over store + pipeline.

The service owns the in-process executor: a run is accepted (persisted QUEUED),
then executed on a worker thread bounded by a semaphore (pilot: 2 concurrent
runs). ``wait`` blocks on a per-run event so tests and UI can follow a run to a
terminal state. Stop/revision/epoch guards are re-checked at publish inside
the store transaction, so late output never becomes current.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.b3 import B3CompanyContext, B3Intake, is_b3_v1
from invoice_referee.settlement.models import (
    AuthorityGrant,
    CaseView,
    ClosurePayload,
    ClosureView,
    Command,
    DecisionPayload,
    DecisionView,
    HandoffPayload,
    MoneyEventPayload,
    MoneyEventView,
    QuestionView,
    Report,
    ResponsePayload,
    ResponseView,
    ReviewPayload,
    ReviewView,
    RunBudget,
    RunInput,
    RunStatus,
    RunView,
    SourceRecord,
    Submission,
    Upload,
    fingerprint,
)
from invoice_referee.settlement.pipeline import process
from invoice_referee.settlement.reader import Reader
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
    b3_context: B3CompanyContext | None = None
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
        if is_b3_v1(submission.form):
            raise DomainError(
                "INVALID_PAYLOAD",
                "Hồ sơ B3 v1 phải tạo qua POST /api/b3-cases; employee/work/"
                "clock do backend cap, không tự nhập.",
            )
        return self.store.create_case(submission, command)

    def submit_b3(self, actor_id: str, intake: B3Intake,
                  command: Command) -> CaseView:
        """B3 v1 intake: persona tra cứu trong company fixture; work id và
        clock do backend cap; replay key tra truoc khi tao id moi."""
        context = self.config.b3_context
        if context is None or not context.activated:
            raise DomainError(
                "CONFIG_NOT_ACTIVE",
                "Chưa cấu hình SETTLEMENT_B3_CONTEXT_PATH (company fixture "
                "B3); không tạo hồ sơ B3 v1 với quyền/context do client nhập.",
            )
        person = next((p for p in context.people
                       if p.actor_ref == actor_id), None)
        if person is None or person.role != "EMPLOYEE":
            raise DomainError(
                "PERSONA_MISMATCH",
                f"Người nộp {actor_id} không phải persona nhân viên trong "
                f"company fixture; chỉ nhân viên tự nộp đề nghị B3.",
            )
        clock = (context.demo_clock
                 if context.demo_clock is not None
                 else datetime.now(timezone.utc))

        def build(work_ref: str) -> Submission:
            return Submission(
                employee_ref=actor_id, work_ref=work_ref, job="B3",
                money_as_of=clock, knowledge_cutoff=clock,
                form=intake.model_dump(mode="json"),
            )

        return self.store.create_b3_case(
            build, command,
            {"actor_id": actor_id, "intake": intake.model_dump(mode="json")},
        )

    def get_case(self, case_id: str) -> CaseView:
        return self.store.get_case(case_id)

    def revise(self, case_id: str, submission: Submission,
               command: Command) -> CaseView:
        case = self.store.get_case(case_id)
        if is_b3_v1(case.submission.form) or is_b3_v1(submission.form):
            if not is_b3_v1(case.submission.form):
                raise DomainError(
                    "INVALID_PAYLOAD",
                    "Hồ sơ legacy không nhận form b3-intake-v1; không âm thầm "
                    "di trú hồ sơ cũ.",
                )
            try:
                intake = B3Intake.model_validate(submission.form)
            except ValidationError as error:
                raise DomainError(
                    "INVALID_PAYLOAD",
                    f"Form B3 không hợp lệ: {error}",
                ) from error
            # B3 v1: employee/work/clocks immutable; chỉ form (lời khai) đổi.
            merged = case.submission.model_copy(
                update={"form": intake.model_dump(mode="json")})
            return self.store.revise(case_id, merged, command)
        return self.store.revise(case_id, submission, command)

    def add_source(self, case_id: str, upload: Upload,
                   command: Command) -> SourceRecord:
        return self.store.add_source(case_id, upload, command)

    # --- runs ----------------------------------------------------------------

    def start(self, case_id: str, command: Command) -> RunView:
        snapshot = self.store.snapshot(case_id)
        b3_v1 = is_b3_v1(snapshot.submission.form)
        context = self.config.b3_context if b3_v1 else None
        config: dict[str, Any] = {"reader_mode": self.reader.mode}
        sources = snapshot.sources
        if (b3_v1 and context is not None and context.activated
                and context.synthetic and context.demo_clock is not None):
            # Clock mô phỏng là mốc business/knowledge của fixture; audit nhận
            # file vẫn giữ timestamp máy thật. UI công bố nguồn mô phỏng.
            config["simulation_clock"] = context.demo_clock.isoformat()
            sources = [source.model_copy(
                update={"received_at": context.demo_clock})
                for source in sources]
        run_input = RunInput(
            case_id=snapshot.case_id,
            case_version=snapshot.case_version,
            input_revision=snapshot.input_revision,
            control_epoch=snapshot.control_epoch,
            submission=snapshot.submission,
            sources=sources,
            coverage=None,
            policy=self.policy,
            authority=self.config.authority,
            response_refs=[],
            config=config,
            b3_context=context,
            snapshot_hash=fingerprint("RUN_SNAPSHOT", {
                "case_id": snapshot.case_id,
                "input_revision": snapshot.input_revision,
                "control_epoch": snapshot.control_epoch,
                "sources": [[s.id, s.sha256] for s in snapshot.sources],
                "submission": snapshot.submission.model_dump(mode="json"),
                "policy": self.policy,
                "authority": [g.model_dump(mode="json")
                              for g in self.config.authority],
                "b3_context": (context.model_dump(mode="json")
                               if context is not None else None),
                "reader_mode": self.reader.mode,
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
                if hasattr(self.reader, "reset_trace"):
                    self.reader.reset_trace()
                checkpoint = self._checkpoint(run_id, run_input)
                report = process(run_input, self.reader, budget, checkpoint,
                                 run_id=run_id)
                published = self.store.publish(run_id, report)
                if published.status == "SUCCEEDED":
                    self._sync_questions(run_id, report)
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
            if hasattr(self.reader, "trace_entries"):
                try:
                    self.store.set_run_trace(
                        run_id, [entry.model_dump(mode="json")
                                 for entry in self.reader.trace_entries()])
                except DomainError:
                    pass  # run đã terminal và bị dọn; trace chỉ là diagnostics
            event.set()
            with self._events_lock:
                self._events.pop(run_id, None)

    def _checkpoint(self, run_id: str,
                    run_input: RunInput) -> Callable[[str], None]:
        """Validate Stop/revision/epoch before each pipeline stage."""

        def check(stage: str) -> None:
            self.store.update_run_stage(run_id, stage)
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

    # --- questions ------------------------------------------------------------

    def questions(self, case_id: str) -> list[QuestionView]:
        self.store.get_case(case_id)
        return self.store.list_questions(case_id)

    def respond(self, question_id: str, response: ResponsePayload,
                command: Command) -> ResponseView:
        question = self.store.get_question(question_id)
        accepted = command.demo_role == question.owner
        reason = (""
                  if accepted
                  else f"Phản hồi từ vai {command.demo_role} không phải owner "
                       f"{question.owner} của câu hỏi; ghi nhận lịch sử, "
                       f"không resolve.")
        return self.store.record_response(question_id, response, command,
                                          accepted, reason)

    def _sync_questions(self, run_id: str, report: Report) -> None:
        """Questions follow the report: new issues open, cleared ones resolve."""
        case_id = report.run_id and self.store.get_run(run_id).case_id
        unresolved = [issue for issue in report.issues if issue.unresolved]
        self.store.ensure_questions(case_id, unresolved, run_id)
        self.store.resolve_questions(case_id,
                                     {issue.issue_id for issue in unresolved},
                                     run_id)

    def report(self, run_id: str) -> Report:
        run = self.store.get_run(run_id)
        report = self.store.get_report(run_id)
        if report is None or run.status != "SUCCEEDED":
            raise DomainError(
                "REPORT_NOT_READY",
                f"Run {run_id} chưa có report (status {run.status}).",
            )
        return report

    # --- W05: decision, review, money, control, handoff, closure -------------

    @staticmethod
    def _parse_payload(model, payload: dict[str, Any]):
        """Validate a payload dict; shape errors are technical, not silent."""
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise DomainError(
                "INVALID_PAYLOAD",
                f"Payload không hợp lệ cho {model.__name__}: {error}",
            ) from error

    def _grant_for(self, command: Command, case: CaseView,
                   amount_vnd: int | None):
        """Demo authority gate: role APPROVER plus a grant covering work/amount."""
        if command.demo_role != "APPROVER":
            return None
        for grant in self.config.authority:
            if grant.actor_ref != command.actor_id:
                continue
            if grant.work_ref is not None and grant.work_ref != case.submission.work_ref:
                continue
            if amount_vnd is not None and amount_vnd > grant.max_settlement_vnd:
                continue
            return grant
        return None

    def decide(self, case_id: str, payload: dict[str, Any],
               command: Command) -> DecisionView:
        case = self.store.get_case(case_id)
        if is_b3_v1(case.submission.form):
            raise DomainError(
                "B3_REPORT_ONLY",
                "Hồ sơ B3 v1 chỉ tạo report intake; không dùng action "
                "SETTLEMENT để duyệt ứng — duyệt work/B/advance là "
                "lifecycle riêng chưa triển khai.",
            )
        if case.stop_active:
            raise DomainError(
                "STOP_ACTIVE",
                "Hồ sơ đang Stop; không nhận quyết định mới.",
            )
        decision = self._parse_payload(DecisionPayload, payload)
        grant = self._grant_for(command, case, decision.amount_vnd)
        if grant is None:
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role}/{command.actor_id} không có quyền duyệt "
                f"số tiền này cho công việc {case.submission.work_ref}; "
                f"quyết định không được ghi.",
            )
        return self.store.record_decision(case_id, decision, command)

    def review(self, case_id: str, payload: dict[str, Any],
               command: Command) -> ReviewView:
        if "amount_vnd" in payload:
            raise DomainError(
                "REVIEW_NOT_APPROVAL",
                "Review không được mang amount; phê duyệt phải qua DECIDE.",
            )
        if command.demo_role != "ACCOUNTANT":
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role} không phải kế toán; review thuộc ACCOUNTANT.",
            )
        review = self._parse_payload(ReviewPayload, payload)
        return self.store.record_review(case_id, review, command)

    def record_money(self, case_id: str, payload: dict[str, Any],
                     command: Command) -> MoneyEventView:
        event = self._parse_payload(MoneyEventPayload, payload)
        case = self.store.get_case(case_id)
        after_cutoff = event.event_at > case.submission.money_as_of
        return self.store.record_money(case_id, event, after_cutoff, command)

    def control(self, case_id: str, action: str,
                command: Command) -> dict[str, Any]:
        if action not in ("STOP", "RESUME"):
            raise DomainError(
                "CONTROL_INVALID",
                f"Hành động control phải là STOP hoặc RESUME, nhận {action!r}.",
            )
        return self.store.control(case_id, action, command)

    def handoff(self, case_id: str, payload: dict[str, Any],
                command: Command) -> dict[str, Any]:
        handoff = self._parse_payload(HandoffPayload, payload)
        return self.store.handoff(case_id, handoff.decision_id, command)

    def close_case(self, case_id: str, payload: dict[str, Any],
                   command: Command) -> ClosureView:
        closure = self._parse_payload(ClosurePayload, payload)
        return self.store.close_case(case_id, closure, command)

    def closed(self, case_id: str) -> bool:
        return self.store.closed(case_id)

    def handoff_allowed(self, case_id: str) -> bool:
        return self.store.handoff_allowed(case_id)
