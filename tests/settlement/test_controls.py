"""W05 controls (C04): Stop ack persists, late output never becomes current,
resume creates a new epoch without reviving the old run.
Fixtures follow the plan (barrier_reader, running_case, start/stop commands).
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import Command, Submission, Upload
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

_CUTOFF = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)

LEDGER = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 2000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 0\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


class BarrierReader(StructuredLedgerReader):
    """Chặn pipeline trong read() để Stop đến giữa chừng (mid-call)."""

    def __init__(self, root):
        super().__init__(root)
        self.entered = threading.Event()
        self.release_gate = threading.Event()

    def read(self, source, keys, budget):
        self.entered.set()
        if not self.release_gate.wait(timeout=10):
            raise AssertionError("release không đến trong 10s")
        return super().read(source, keys, budget)

    def wait_entered(self) -> None:
        assert self.entered.wait(timeout=10), "reader chưa vào read()"

    def release(self) -> None:
        self.release_gate.set()


@pytest.fixture
def barrier_reader(tmp_path):
    store_dir = tmp_path / "artifacts"
    store_dir.mkdir(parents=True, exist_ok=True)
    reader = BarrierReader(store_dir)
    yield reader
    reader.release()  # teardown luôn release trước khi close


@pytest.fixture
def service(tmp_path, barrier_reader):
    from invoice_referee.settlement.models import AuthorityGrant

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    return Service(store, barrier_reader, config=ServiceConfig(authority=[
        AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                       max_settlement_vnd=100_000_000),
    ]))


@pytest.fixture
def running_case(service):
    submission = Submission(employee_ref="NV-01", work_ref="CT-CTRL", job="B7",
                            money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                            form={"purpose": "Công tác A"})
    case = service.submit(submission, Command(
        key="create-1", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id, Upload(filename="d.txt",
                                       content=LEDGER.encode()), Command(
        key="src-1", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=case.case_version, body={}))
    return service.get_case(case.id)


def start_command(case):
    return Command(key=f"run-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                   demo_role="EMPLOYEE", expected_case_version=case.case_version,
                   body={})


def stop_command(case):
    return Command(key=f"stop-{uuid.uuid4().hex[:8]}", actor_id="ACC-01",
                   demo_role="ACCOUNTANT", expected_case_version=case.case_version,
                   body={"reason": "kiểm tra lại"})


def resume_command(case):
    return Command(key=f"resume-{uuid.uuid4().hex[:8]}", actor_id="ACC-01",
                   demo_role="ACCOUNTANT", expected_case_version=case.case_version,
                   body={"reason": "đã xử lý"})


def test_stop_ack_then_late_report_cannot_be_current(service, barrier_reader,
                                                     running_case):
    run = service.start(running_case.id, start_command(running_case))
    barrier_reader.wait_entered()
    service.control(running_case.id, "STOP",
                    stop_command(service.get_case(running_case.id)))
    barrier_reader.release()
    ended = service.wait(run.id)
    assert ended.status == "STOPPED"
    assert service.handoff_allowed(running_case.id) is False
    assert service.closed(running_case.id) is False


def test_stop_blocks_new_runs_and_financial_actions(service, barrier_reader,
                                                    running_case):
    barrier_reader.hold = True
    run = service.start(running_case.id, start_command(running_case))
    barrier_reader.wait_entered()
    service.control(running_case.id, "STOP",
                    stop_command(service.get_case(running_case.id)))
    barrier_reader.release()
    service.wait(run.id)
    view = service.get_case(running_case.id)
    with pytest.raises(DomainError) as error:
        service.start(view.id, start_command(view))
    assert error.value.code == "STOP_ACTIVE"
    with pytest.raises(DomainError) as error:
        service.decide(view.id, {"kind": "SETTLEMENT", "amount_vnd": 1,
                                 "direction": "PAY_EMPLOYEE", "reason": "x",
                                 "basis_report_id": "R-x"}, start_command(view))
    assert error.value.code == "STOP_ACTIVE"
    # nguồn/tiền đã xảy ra vẫn record khi Stop (chỉ không mở action mới)
    service.add_source(view.id, Upload(filename="extra.txt",
                                       content=b"fact Z budget.approved 1\n"),
                       Command(key="src-2", actor_id="NV-01",
                               demo_role="EMPLOYEE",
                               expected_case_version=view.case_version, body={}))


def test_resume_new_epoch_allows_run_but_not_old_revival(service, barrier_reader,
                                                          running_case):
    run = service.start(running_case.id, start_command(running_case))
    barrier_reader.wait_entered()
    service.control(running_case.id, "STOP",
                    stop_command(service.get_case(running_case.id)))
    barrier_reader.release()
    stopped = service.wait(run.id)
    assert stopped.status == "STOPPED"

    view = service.get_case(running_case.id)
    before_epoch = view.control_epoch
    service.control(view.id, "RESUME", resume_command(service.get_case(view.id)))
    resumed = service.get_case(view.id)
    assert resumed.control_epoch == before_epoch + 1
    assert resumed.stop_active is False
    # run cũ không hồi phục; run mới chạy bình thường
    assert service.get_run(run.id).status == "STOPPED"
    new_run = service.start(view.id, start_command(resumed))
    ended = service.wait(new_run.id, timeout=10)
    assert ended.status == "SUCCEEDED"


def test_startup_interrupts_stale_active_runs(tmp_path, barrier_reader):
    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    service = Service(store, barrier_reader, config=ServiceConfig())
    submission = Submission(employee_ref="NV-01", work_ref="CT-INT", job="B7",
                            money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                            form={"purpose": "A"})
    case = service.submit(submission, Command(
        key="c", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=None, body={}))
    service.add_source(case.id, Upload(filename="d.txt",
                                       content=LEDGER.encode()), Command(
        key="s", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=case.case_version, body={}))
    run = service.start(case.id, Command(
        key="r", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=service.get_case(case.id).case_version, body={}))
    barrier_reader.wait_entered()
    # process "khởi động lại": Store mới trên cùng DB đánh dấu active runs
    rebooted = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    assert rebooted.get_run(run.id).status == "INTERRUPTED"
    barrier_reader.release()
    service.wait(run.id, timeout=10)
    assert rebooted.get_run(run.id).status == "INTERRUPTED"  # không bị ghi đè
