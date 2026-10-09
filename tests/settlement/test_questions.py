"""W04 questions: issues materialize as owner-scoped questions; a declaration
without source never resolves them; a proper source + re-check does.
Fixtures follow the plan (receipt_unknown_case, employee_response).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from invoice_referee.settlement.models import (
    Command,
    ResponsePayload,
    Submission,
    Upload,
)
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

_CUTOFF = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)

# chi hợp lệ 5tr + budget; KHÔNG có history advance → A unknown
LEDGER_UNKNOWN = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)
# nguồn company-side riêng: chỉ history, không upload lại hóa đơn
LEDGER_HISTORY_ONLY = (
    "fact H1 history.advance.received 2000000\n"
    "fact H2 history.advance.returned 0\n"
    "fact H3 history.reimbursement.received 0\n"
    "fact H4 history.reimbursement.returned 0\n"
)


@pytest.fixture
def service(tmp_path):
    from invoice_referee.settlement.models import AuthorityGrant

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    return Service(store, reader, config=ServiceConfig(authority=[
        AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                       max_settlement_vnd=100_000_000),
    ]))


def _create_case(service, job="B7", work_ref="CT-Q"):
    submission = Submission(employee_ref="NV-01", work_ref=work_ref, job=job,
                           money_as_of=_CUTOFF, knowledge_cutoff=_CUTOFF,
                           form={"purpose": "Công tác A"})
    command = Command(key=f"create-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                      demo_role="EMPLOYEE", expected_case_version=None, body={})
    return service.submit(submission, command)


def _upload(service, case, content: str, actor="NV-01", role="EMPLOYEE"):
    view = service.get_case(case.id)
    command = Command(key=f"src-{uuid.uuid4().hex[:8]}", actor_id=actor,
                      demo_role=role, expected_case_version=view.case_version,
                      body={})
    service.add_source(case.id, Upload(filename="nguon.txt",
                                        content=content.encode("utf-8")), command)
    return service.get_case(case.id)


def _start(service, case_id, actor="NV-01", role="EMPLOYEE"):
    view = service.get_case(case_id)
    command = Command(key=f"run-{uuid.uuid4().hex[:8]}", actor_id=actor,
                      demo_role=role, expected_case_version=view.case_version,
                      body={})
    return service.start(case_id, command)


def wait_report(service, case_id):
    view = service.get_case(case_id)
    run = service.wait(view.current_run_id, timeout=10)
    assert run.status == "SUCCEEDED", run.detail
    return service.report(run.id)


def response_command(case):
    return Command(key=f"resp-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                   demo_role="EMPLOYEE", expected_case_version=case.case_version,
                   body={})


def accountant_response_command(case):
    return Command(key=f"resp-{uuid.uuid4().hex[:8]}", actor_id="ACC-01",
                   demo_role="ACCOUNTANT", expected_case_version=case.case_version,
                   body={})


def next_run_command(case):
    return Command(key=f"run-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                   demo_role="EMPLOYEE", expected_case_version=case.case_version,
                   body={})


@pytest.fixture
def receipt_unknown_case(service):
    case = _create_case(service)
    _upload(service, case, LEDGER_UNKNOWN)
    _start(service, case.id)
    report = wait_report(service, case.id)
    assert report.completion == "INCOMPLETE"  # A unknown → không tự suy 0
    return service.get_case(case.id)


@pytest.fixture
def employee_response():
    return ResponsePayload(content="đã nhận 2 triệu", source_ids=[])


def test_answer_without_source_does_not_resolve_receipt_question(
        service, receipt_unknown_case, employee_response):
    question = service.questions(receipt_unknown_case.id)[0]
    service.respond(question.id, employee_response,
                    response_command(service.get_case(receipt_unknown_case.id)))
    service.start(receipt_unknown_case.id,
                  next_run_command(service.get_case(receipt_unknown_case.id)))
    report = wait_report(service, receipt_unknown_case.id)
    assert report.proposed_net_vnd is None
    assert any(issue.issue_id == question.issue_id and issue.unresolved
               for issue in report.issues)


def test_question_names_owner_refs_and_open_status(service, receipt_unknown_case):
    question = service.questions(receipt_unknown_case.id)[0]
    assert question.owner == "ACCOUNTANT"
    assert question.status == "OPEN"
    assert question.refs, "question phải giữ refs để mở nguồn/vị trí liên quan"
    assert "không suy bằng 0" in question.message or "nguồn" in question.message


def test_wrong_owner_response_is_recorded_but_not_accepted(service, receipt_unknown_case):
    question = service.questions(receipt_unknown_case.id)[0]
    view = service.get_case(receipt_unknown_case.id)
    response = service.respond(
        question.id, ResponsePayload(content="tôi đã nhận 2 triệu", source_ids=[]),
        response_command(view))
    assert response.accepted is False
    assert service.questions(receipt_unknown_case.id)[0].status == "OPEN"


def test_valid_source_and_recheck_resolves_question(service, receipt_unknown_case):
    question = service.questions(receipt_unknown_case.id)[0]
    view = _upload(service, receipt_unknown_case, LEDGER_HISTORY_ONLY,
                    actor="ACC-01", role="ACCOUNTANT")
    response = service.respond(
        question.id,
        ResponsePayload(content="sao kê xác nhận đã ứng 2 triệu",
                        source_ids=[view.sources[-1].id]),
        accountant_response_command(view))
    assert response.accepted is True
    assert service.questions(receipt_unknown_case.id)[0].status == "ANSWERED"
    service.start(receipt_unknown_case.id,
                  next_run_command(service.get_case(receipt_unknown_case.id)))
    report = wait_report(service, receipt_unknown_case.id)
    assert report.completion == "COMPLETE"
    assert report.proposed_net_vnd == 3_000_000
    assert service.questions(receipt_unknown_case.id)[0].status == "RESOLVED"


def test_revision_keeps_initial_run_and_assisted_history(service, receipt_unknown_case):
    first_run = receipt_unknown_case.current_run_id
    view = service.get_case(receipt_unknown_case.id)
    submission = view.submission.model_copy(
        update={"form": {"purpose": "Công tác A (sửa)"}})
    service.revise(receipt_unknown_case.id, submission,
                   Command(key=f"edit-{uuid.uuid4().hex[:8]}", actor_id="NV-01",
                           demo_role="EMPLOYEE",
                           expected_case_version=view.case_version,
                           body={"reason": "làm rõ mục đích"}))
    service.start(receipt_unknown_case.id,
                  next_run_command(service.get_case(receipt_unknown_case.id)))
    wait_report(service, receipt_unknown_case.id)
    history = service.store.history(receipt_unknown_case.id)
    kinds = [entry.kind for entry in history]
    assert kinds.count("RUN_STARTED") == 2
    assert "SUBMISSION_REVISED" in kinds
    # run đầu vẫn đọc được nguyên trạng
    first_report = service.report(first_run)
    assert first_report.completion == "INCOMPLETE"


def test_complete_report_creates_no_questions(service):
    case = _create_case(service, work_ref="CT-OK")
    _upload(service, case, LEDGER_UNKNOWN + LEDGER_HISTORY_ONLY)
    _start(service, case.id)
    report = wait_report(service, case.id)
    assert report.completion == "COMPLETE"
    assert service.questions(case.id) == []
