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
from invoice_referee.settlement.b3_workflow import b3_route_for
from invoice_referee.settlement.b7_linked import is_linked_b7
from invoice_referee.settlement.models import (
    AuthorityGrant,
    B3AdvanceEventPayload,
    B3AdvanceEventView,
    B3DecisionPayload,
    B3DecisionView,
    B3PresentPayload,
    B3PresentationView,
    B7CompanyConfig,
    B7LinkedIntake,
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


def _merge_b3_decision_into_history(
        context: B3CompanyContext, decision) -> tuple[B3CompanyContext, str]:
    """Fold a case's own verified B3 approval into its company history.

    Produces one linked record set (WORK_DECISION/BUDGET_DECISION/
    ADVANCE_APPROVAL) sharing the decision's namespace ``b3decision:<id>`` with
    the effective/known times, so a re-check of the same request does not raise
    a false duplicate-approval issue. Never a money event, and never applied to
    a foreign approval. Returns the new context and the ADVANCE_APPROVAL ref.
    """
    from invoice_referee.settlement.b3 import B3HistoryRecord

    namespace = f"b3decision:{decision.id}"
    employee_ref = decision.employee_ref
    work_ref = decision.work_ref
    effective_at = decision.effective_at
    known_at = decision.created_at
    records = [
        B3HistoryRecord(
            event_ref=f"{namespace}:work", employee_ref=employee_ref,
            work_ref=work_ref, kind="WORK_DECISION",
            amount_vnd=None, event_at=effective_at, known_at=known_at,
            status="APPROVED", ref=f"{namespace}:work"),
        B3HistoryRecord(
            event_ref=f"{namespace}:budget", employee_ref=employee_ref,
            work_ref=work_ref, kind="BUDGET_DECISION",
            amount_vnd=decision.budget_vnd, event_at=effective_at,
            known_at=known_at, status="APPROVED", ref=f"{namespace}:budget"),
        B3HistoryRecord(
            event_ref=f"{namespace}:advance", employee_ref=employee_ref,
            work_ref=work_ref, kind="ADVANCE_APPROVAL",
            amount_vnd=decision.advance_vnd, event_at=effective_at,
            known_at=known_at, status="APPROVED", ref=f"{namespace}:advance"),
    ]
    merged = context.model_copy(update={"history": [*context.history, *records]})
    return merged, f"{namespace}:advance"


def _merge_b3_advances_into_history(
        context: B3CompanyContext, events) -> B3CompanyContext:
    """Fold confirmed RECEIVED advance events into company history as ADVANCE.

    So a re-run of the same case sees the recorded advance (kind ADVANCE/
    RECEIVED) in its company history under a ``b3advance:<id>`` namespace. Only
    confirmed events count; pending/unknown are not fabricated as ADVANCE 0.
    """
    from invoice_referee.settlement.b3 import B3HistoryRecord

    records = [
        B3HistoryRecord(
            event_ref=f"b3advance:{event.id}", employee_ref=event.employee_ref,
            work_ref=event.work_ref, kind="ADVANCE", amount_vnd=event.gross_vnd,
            event_at=event.event_at or event.created_at,
            known_at=event.created_at, status="RECEIVED",
            ref=f"b3advance:{event.id}")
        for event in events
    ]
    if not records:
        return context
    return context.model_copy(
        update={"history": [*context.history, *records]})


class ServiceConfig(BaseModel):
    """Pilot envelope (System §S5) plus explicit demo authority grants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = "FAKE_OR_REPLAY"
    max_active_runs: StrictInt = 2
    run_deadline_seconds: float = 240.0
    max_provider_calls_per_run: StrictInt = 32
    authority: list[AuthorityGrant] = Field(default_factory=list)
    b3_context: B3CompanyContext | None = None
    b7_context: "B7CompanyConfig | None" = None
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

    def submit(self, submission: Submission, command: Command,
               origin: str = "USER") -> CaseView:
        if is_b3_v1(submission.form):
            raise DomainError(
                "INVALID_PAYLOAD",
                "Hồ sơ B3 v1 phải tạo qua POST /api/b3-cases; employee/work/"
                "clock do backend cap, không tự nhập.",
            )
        if is_linked_b7(submission.form):
            raise DomainError(
                "INVALID_PAYLOAD",
                "Hồ sơ quyết toán liên kết phải tạo qua "
                "POST /api/cases/{b3_id}/settlements; link/employee/work do "
                "backend cấp, không tự nhập.",
            )
        return self.store.create_case(submission, command, origin=origin)

    def submit_b3(self, actor_id: str, intake: B3Intake,
                  command: Command, origin: str = "USER") -> CaseView:
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
            origin=origin,
        )

    def get_case(self, case_id: str) -> CaseView:
        return self.store.get_case(case_id)

    def delete_case(self, case_id: str) -> None:
        """Delete a case from the database and remove its artifacts."""
        self.store.delete_case(case_id)

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
        if is_linked_b7(case.submission.form) or is_linked_b7(submission.form):
            raise DomainError(
                "INVALID_PAYLOAD",
                "Hồ sơ quyết toán liên kết phải sửa qua "
                "PUT /api/cases/{id}/settlement-submission; không đổi "
                "link/employee/work.",
            )
        return self.store.revise(case_id, submission, command)

    # --- B6→B7 linked settlement ---------------------------------------------

    def prepare_linked_b7(self, origin_case_id: str,
                          command: Command) -> CaseView:
        """Employee opens a linked B7 settlement child for their B3 parent."""
        context = self._b3_context()
        parent = self.store.get_case(origin_case_id)
        if not is_b3_v1(parent.submission.form):
            raise DomainError(
                "LINKED_B7_INVALID",
                "Chỉ hồ sơ B3 v1 mới mở được hồ sơ quyết toán liên kết.",
            )
        route = b3_route_for(context, parent.submission.employee_ref)
        if (command.demo_role != "EMPLOYEE"
                or command.actor_id != parent.submission.employee_ref):
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role}/{command.actor_id} không phải nhân "
                f"viên {parent.submission.employee_ref}; không mở hồ sơ quyết "
                f"toán liên kết.",
            )
        return self.store.prepare_linked_b7(origin_case_id, command)

    def revise_linked_b7(self, case_id: str, intake: B7LinkedIntake,
                         command: Command) -> CaseView:
        """Employee saves/confirms the linked child's declarations."""
        case = self.store.get_case(case_id)
        if not is_linked_b7(case.submission.form):
            raise DomainError(
                "LINKED_B7_INVALID",
                "Hồ sơ này không phải hồ sơ quyết toán liên kết.",
            )
        if (command.demo_role != "EMPLOYEE"
                or command.actor_id != case.submission.employee_ref):
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role}/{command.actor_id} không phải nhân "
                f"viên {case.submission.employee_ref}; không sửa khai báo.",
            )
        # Every claim source must resolve to a retained source of this child.
        case_source_ids = {s.id for s in case.sources}
        for row in intake.expense_rows:
            for source_id in row.source_ids:
                if source_id not in case_source_ids:
                    raise DomainError(
                        "BASIS_MISMATCH",
                        f"Nguồn {source_id} của khoản {row.claim_id} không "
                        f"thuộc hồ sơ {case_id}.",
                    )
        return self.store.revise_linked_b7(case_id, intake, command)

    def record_b7_company_packet(self, case_id: str, payload: dict,
                                 command: Command) -> CaseView:
        """Accountant records the source-backed company packet for a child."""
        case = self.store.get_case(case_id)
        if case.linked_b7 is None:
            raise DomainError(
                "LINKED_B7_INVALID",
                "Company packet chỉ áp dụng cho hồ sơ quyết toán liên kết.",
            )
        if command.demo_role != "ACCOUNTANT":
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role} không phải kế toán; company packet "
                f"thuộc ACCOUNTANT.",
            )
        context = self.config.b7_context
        authority_version = (context.version
                             if context is not None and context.activated
                             else None)
        return self.store.record_b7_company_packet(
            case_id, payload, command, self.policy, authority_version)

    def refresh_linked_b7_context(self, case_id: str,
                                  command: Command) -> CaseView:
        case = self.store.get_case(case_id)
        if case.linked_b7 is None:
            raise DomainError(
                "LINKED_B7_INVALID",
                "Refresh context chỉ áp dụng cho hồ sơ quyết toán liên kết.",
            )
        allowed = (command.demo_role == "ACCOUNTANT"
                   or (command.demo_role == "EMPLOYEE"
                       and command.actor_id == case.submission.employee_ref))
        if not allowed:
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role}/{command.actor_id} không được refresh "
                f"context của hồ sơ này.",
            )
        context = self.config.b7_context
        authority_version = (context.version
                             if context is not None and context.activated
                             else None)
        return self.store.refresh_linked_b7_context(
            case_id, command, self.policy, authority_version)

    def add_source(self, case_id: str, upload: Upload,
                   command: Command) -> SourceRecord:
        return self.store.add_source(case_id, upload, command)

    # --- runs ----------------------------------------------------------------

    def start(self, case_id: str, command: Command) -> RunView:
        snapshot = self.store.snapshot(case_id)
        b3_v1 = is_b3_v1(snapshot.submission.form)
        linked_b7 = is_linked_b7(snapshot.submission.form)
        context = self.config.b3_context if b3_v1 else None
        config: dict[str, Any] = {"reader_mode": self.reader.mode}
        sources = snapshot.sources
        if linked_b7:
            # A linked B7 run uses B7 rights only — never the broad generic
            # authority, and never the B3 advance grant. Missing B7 config means
            # no authority (an unresolved AUTHORITY issue), not a fallback.
            b7 = self.config.b7_context
            linked_authority = (list(b7.grants)
                                if b7 is not None and b7.activated else [])
            if b7 is not None and b7.activated and b7.synthetic \
                    and b7.demo_clock is not None:
                config["simulation_clock"] = b7.demo_clock.isoformat()
        else:
            linked_authority = list(self.config.authority)
        if b3_v1:
            # B5 advance-proof sources are fulfillment evidence, not proposal
            # input: they never enter the B3 Reader/basis. Filtered by the
            # backend-owned audit source-use, never by filename/provenance text.
            proof_ids = self.store._b3_proof_source_ids(case_id)
            sources = [s for s in sources if s.id not in proof_ids]
        if (b3_v1 and context is not None and context.activated
                and context.synthetic and context.demo_clock is not None):
            # Clock mô phỏng là mốc business/knowledge của fixture; audit nhận
            # file vẫn giữ timestamp máy thật. UI công bố nguồn mô phỏng.
            config["simulation_clock"] = context.demo_clock.isoformat()
            sources = [source.model_copy(
                update={"received_at": context.demo_clock})
                for source in sources]
        if b3_v1 and context is not None:
            # Fold this case's own verified approval into the company history so
            # re-checking the SAME request does not raise a false
            # duplicate-approval issue; a foreign approval is never folded in.
            own = self.store.current_b3_decision(case_id)
            if own is not None:
                context, own_ref = _merge_b3_decision_into_history(context, own)
                config["b3_current_decision_ref"] = own_ref
            # Fold confirmed RECEIVED advance events so a re-run sees them as
            # company history (kind ADVANCE/RECEIVED) rather than absence.
            confirmed = self.store.confirmed_b3_advances(case_id)
            context = _merge_b3_advances_into_history(context, confirmed)
        run_input = RunInput(
            case_id=snapshot.case_id,
            case_version=snapshot.case_version,
            input_revision=snapshot.input_revision,
            control_epoch=snapshot.control_epoch,
            submission=snapshot.submission,
            sources=sources,
            coverage=None,
            policy=self.policy,
            authority=linked_authority,
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
                              for g in linked_authority],
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
                linked_snapshot = None
                if is_linked_b7(run_input.submission.form):
                    try:
                        linked_snapshot = self.store.get_linked_b7_context(
                            run_input.case_id)
                    except DomainError:
                        linked_snapshot = None  # no context yet: report-only
                report = process(run_input, self.reader, budget, checkpoint,
                                 run_id=run_id, linked_snapshot=linked_snapshot)
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
        """Demo authority gate: role APPROVER plus a scoped covering grant.

        Uses the shared ``covering_grant`` so a decision is bounded by the same
        employee/work scope, effective window and settlement limit as the
        engine — not by comparing the payload amount alone.
        """
        from invoice_referee.settlement.rules import covering_grant

        if command.demo_role != "APPROVER":
            return None
        scoped = [g for g in self.config.authority
                  if g.actor_ref == command.actor_id]
        if not scoped:
            return None
        return covering_grant(
            scoped, employee_ref=case.submission.employee_ref,
            work_ref=case.submission.work_ref,
            effective_at=case.submission.money_as_of,
            employee_cost_vnd=None,
            settlement_vnd=amount_vnd,
            total_work_cost_vnd=None,
            exception_required=False,
        )

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

    # --- B3 present-and-approve (b3-intake-v1) -------------------------------

    def _b3_context(self):
        context = self.config.b3_context
        if context is None or not context.activated:
            raise DomainError(
                "CONFIG_NOT_ACTIVE",
                "Chưa cấu hình company context B3; không trình/quyết định B3.",
            )
        return context

    def present_b3(self, case_id: str, payload: dict[str, Any],
                   command: Command) -> B3PresentationView:
        context = self._b3_context()
        present = self._parse_payload(B3PresentPayload, payload)
        return self.store.record_b3_presentation(
            case_id, present, command, context, self.policy)

    def decide_b3(self, case_id: str, payload: dict[str, Any],
                  command: Command) -> B3DecisionView:
        from invoice_referee.settlement.b3_workflow import (
            authorize_b3_decision,
            effective_b3_time,
        )

        context = self._b3_context()
        decision = self._parse_payload(B3DecisionPayload, payload)
        case = self.store.get_case(case_id)
        if case.b3_workflow is None or case.b3_workflow.presentation is None:
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Chưa có presentation để quyết định; kế toán phải trình trước.",
            )
        proposal = None
        run = self.store.get_run(case.b3_workflow.presentation.basis_report_id)
        report = self.store.get_report(run.id)
        if report is not None:
            proposal = report.b3
        requested = proposal.intake.request_amount_vnd if proposal else None
        effective_at = effective_b3_time(context)
        grant = authorize_b3_decision(
            context, case.submission.employee_ref, case.submission.work_ref,
            decision, command.actor_id, effective_at, requested)
        return self.store.record_b3_decision(
            case_id, decision, command, context, self.policy,
            grant.ref, effective_at)

    # --- B5: advance receipts (actual money to employee) ---------------------

    def add_b3_advance_proof(self, case_id: str, upload: Upload,
                             command: Command) -> SourceRecord:
        """Attach a receiver/cash proof source for a B3 advance.

        Backend-owned source use (B3_ADVANCE_PROOF), accountant-only; this is
        bookkeeping evidence, not a proposal input — it bumps case_version but
        not input_revision, so an approved proposal does not go stale merely
        because a receipt arrived.
        """
        context = self._b3_context()
        case = self.store.get_case(case_id)
        if case.b3_workflow is None:
            raise DomainError(
                "B3_WORKFLOW_BLOCKED",
                "Chứng từ ứng chỉ áp dụng cho hồ sơ b3-intake-v1.",
            )
        route = b3_route_for(context, case.submission.employee_ref)
        if (command.demo_role != "ACCOUNTANT" or route is None
                or route.accountant_ref != command.actor_id):
            raise DomainError(
                "BEYOND_AUTHORITY",
                f"Vai {command.demo_role}/{command.actor_id} không phải kế toán "
                f"được phân công; không tải chứng từ ứng.",
            )
        return self.store.add_source(case_id, upload, command,
                                     source_use="B3_ADVANCE_PROOF")

    def record_b3_advance(self, case_id: str, payload: dict[str, Any],
                          command: Command) -> B3AdvanceEventView:
        context = self._b3_context()
        event = self._parse_payload(B3AdvanceEventPayload, payload)
        return self.store.record_b3_advance(case_id, event, command, context)

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
