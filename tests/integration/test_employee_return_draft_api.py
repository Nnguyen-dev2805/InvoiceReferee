"""Employee return evidence is pending until the accountant records it."""

from __future__ import annotations

from tests.factories import clear_ocr_page

import json
from datetime import datetime, timezone

import pytest

from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import RecordActual
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import OcrPage, OcrSourceResult
from invoice_referee.domain.finance import RecordMoneyInput
from invoice_referee.workflow.db import Database

TENANT = "tenant:demo"
EMPLOYEE = "employee:employee-a"
ACCOUNTANT = "employee:accountant-demo"
RETURN_PDF = b"%PDF-1.4\nSynthetic employee transfer receipt\n%%EOF\n"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"


NOW = datetime.fromisoformat("2026-10-15T12:00:00+07:00")


def _return_text(
    *,
    amount: str = "1.000.000 đồng",
    payee: str = COMPANY,
    status: str = "Hoàn tất",
    reference: str = "RET-TC01-001",
) -> str:
    return f"""BIÊN NHẬN CHUYỂN KHOẢN
Ngân hàng Demo
Mã giao dịch: {reference}
Ngày giao dịch: 15/10/2026
Trạng thái giao dịch: {status}
Bên chuyển: NGUYỄN MINH AN
Bên nhận: {payee}
Số tiền: {amount}
"""


class _ReturnReader:
    def __init__(self, text: str):
        self.text = text

    async def read_source(
        self,
        source,
        *,
        budget,
        artifacts,
        source_bytes,
        expected_pages=None,
        root_id="",
    ):
        return OcrSourceResult(
            source_id=source.id,
            source_digest=source.digest,
            provider="fake-return-reader",
            model="fixture",
            pages=(clear_ocr_page(markdown=self.text),),
        )


class _ReturnClassifier:
    def __init__(self, *, amount: str, payee: str, status: str, reference: str):
        self.amount = amount
        self.payee = payee
        self.status = status
        self.reference = reference

    async def complete_json(self, *, system, user, budget):
        if "classify" in system.lower():
            documents = json.loads(user)["documents"]
            return {
                "documents": [
                    {
                        "source_id": document["source_id"],
                        "page_range": [1, 1],
                        "document_type": "PAYMENT_PROOF",
                        "roles": ["PAYMENT_EVIDENCE"],
                        "classification_confidence": 0.99,
                    }
                    for document in documents
                ]
            }
        if "TABLE ROWS" in system or "line_items" in system:
            fields = [
                ("payment_provider", "Ngân hàng Demo", "Ngân hàng Demo"),
                ("payer_name", "NGUYỄN MINH AN", "Bên chuyển: NGUYỄN MINH AN"),
                ("payee_name", self.payee, f"Bên nhận: {self.payee}"),
                ("amount", self.amount, f"Số tiền: {self.amount}"),
                ("event_at", "2026-10-15", "Ngày giao dịch: 15/10/2026"),
                (
                    "transaction_reference",
                    self.reference,
                    f"Mã giao dịch: {self.reference}",
                ),
                (
                    "transaction_status",
                    self.status,
                    f"Trạng thái giao dịch: {self.status}",
                ),
            ]
            return {
                "fields": [
                    {
                        "field": field,
                        "state": "FOUND",
                        "value": value,
                        "quote": quote,
                        "page": 1,
                    }
                    for field, value, quote in fields
                ],
                "line_items": [],
            }
        return {"assessments": []}


async def _collect_case(
    app_fixture,
    tmp_path,
    *,
    packet="money-i4",
    amount="1.000.000 đồng",
    payee=COMPANY,
    status="Hoàn tất",
    reference="RET-TC01-001",
    activity="activity:travel-a",
):
    app_fixture.workflow._clock = lambda: NOW
    view = await app_fixture.submit_packet(packet, mode="STUB", activity=activity)
    assert view.instructions[0].direction == "PAY"
    source = view.sources[0]
    accountant = app_fixture.workflow.start_session(
        tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT
    )
    money = RecordMoneyInput(
        external_key="transfer:SETUP-ADVANCE-EXTRA",
        claimed_kind="ADVANCE_RECEIVED",
        claimed_scope=view.activity or "activity:travel-a",
        payer="company:demo",
        payee=EMPLOYEE,
        amount=5_000_000,
        event_at=datetime(2026, 10, 10, 9, tzinfo=timezone.utc),
        completion_claim="Đã kiểm tra chứng từ khoản ứng bổ sung.",
        reason="Tạo dữ liệu kiểm thử lệnh thu còn 1 triệu.",
        refs=(
            EvidenceRef(
                source_id=source.id,
                source_sha256=source.digest,
                page=1,
                exact_quote="Chứng từ ứng bổ sung",
            ),
        ),
    )
    updated = await app_fixture.workflow.execute(
        CommandContext(
            session_id=accountant.session_id,
            actor_id=ACCOUNTANT,
            command_id="cmd:return-test-extra-advance",
            expected_case_version=view.version,
        ),
        RecordActual(root_id=view.id, money=money),
    )
    collect = next(
        (
            item
            for item in updated.case_view.instructions
            if item.direction == "COLLECT"
        ),
        None,
    )
    assert collect is not None
    assert collect.remaining == 1_000_000
    app_fixture.workflow.enable_evidence_read(
        reader=_ReturnReader(
            _return_text(amount=amount, payee=payee, status=status, reference=reference)
        ),
        classifier=_ReturnClassifier(
            amount=amount, payee=payee, status=status, reference=reference
        ),
        artifacts_root=tmp_path / "return-artifacts",
        provider_mode="STUB",
    )
    return updated.case_view, collect


async def _upload_employee_return(
    app_fixture,
    view,
    collect,
    *,
    filename="employee-return.pdf",
    amount="1.000.000 đồng",
    payee=COMPANY,
    status="Hoàn tất",
    reference="RET-TC01-001",
):
    text = _return_text(amount=amount, payee=payee, status=status, reference=reference)
    pdf = b"%PDF-1.4\n" + text.encode("utf-8") + b"\n%%EOF\n"
    employee = _client(app_fixture, actor=EMPLOYEE, persona="employee")
    attached = await employee.post(
        f"/api/cases/{view.id}/sources",
        files={"files": (filename, pdf, "application/pdf")},
        headers={
            "X-Command-Id": f"cmd:source:{reference}",
            "X-Expected-Version": str(view.version),
        },
    )
    assert attached.status_code == 200, attached.text
    source = next(
        item
        for item in attached.json()["case_view"]["sources"]
        if item["filename"] == filename
    )
    response = await employee.post(
        f"/api/cases/{view.id}/return-draft",
        headers={
            "X-Command-Id": f"cmd:return-read:{reference}",
            "X-Expected-Version": str(attached.json()["case_view"]["version"]),
        },
        json={"source_id": source["id"], "instruction_id": collect.id},
    )
    return employee, source, response


async def _confirm_return(app_fixture, view, collect, draft, *, command_id: str):
    accountant = _client(app_fixture, actor=ACCOUNTANT, persona="accountant")
    return await accountant.post(
        f"/api/cases/{view.id}/actuals",
        headers={
            "X-Command-Id": command_id,
            "X-Expected-Version": str(
                app_fixture.workflow._query_one(
                    "SELECT version FROM cases WHERE id = ?", (view.id,)
                )["version"]
            ),
        },
        json={
            "money": {
                "external_key": draft["external_key"],
                "claimed_kind": "EMPLOYEE_RETURN",
                "claimed_scope": view.activity,
                "payer": EMPLOYEE,
                "payee": "company:demo",
                "amount": draft["amount"],
                "event_at": draft["event_at"],
                "completion_claim": "Kế toán xác nhận đã nhận khoản hoàn theo chứng từ.",
                "reason": "Xác nhận khoản hoàn thực nhận theo bằng chứng đã đối chiếu.",
                "instrument_method": "TRANSFER",
                "instrument_status": draft["instrument_status"],
                "instrument_reference": draft["transaction_reference"],
                "instruction_id": collect.id,
                "money_movement_draft_id": draft["draft_id"],
                "refs": draft["refs"],
            }
        },
    )


async def test_explicit_return_read_after_model_change_does_not_reuse_old_status(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(
        app_fixture, tmp_path, reference="RET-VERSION-1"
    )
    employee, source, response = await _upload_employee_return(
        app_fixture, view, collect, reference="RET-VERSION-1"
    )
    assert response.status_code == 200
    wf = app_fixture.workflow
    wf._evidence_classifier.model = "new-return-reader-version"
    wf._evidence_classifier.status = "Đang xử lý"
    wf._evidence_reader.text = _return_text(
        status="Đang xử lý", reference="RET-VERSION-1"
    )
    reread = await employee.post(
        f"/api/cases/{view.id}/return-draft",
        headers={
            "X-Command-Id": "cmd:reread-version",
            "X-Expected-Version": str(response.json()["case_view"]["version"]),
        },
        json={"source_id": source["id"], "instruction_id": collect.id},
    )
    assert reread.status_code == 200, reread.text
    assert reread.json()["draft"]["instrument_status"] == "PENDING"
    assert (
        reread.json()["case_view"]["employee_return_drafts"][-1]["instrument_status"]
        == "PENDING"
    )


def _client(app_fixture, *, actor: str, persona: str):
    client = app_fixture.fresh_client()
    client.cookies.set(
        SESSION_COOKIE,
        app_fixture.session_for(tenant=TENANT, actor=actor, persona=persona),
    )
    return client


def test_v9_database_migrates_the_additive_money_draft_table(tmp_path):
    database = Database(tmp_path / "legacy-v9.sqlite")
    database.migrate()
    with database.transaction() as cx:
        cx.execute("PRAGMA user_version = 9")
    database.migrate()
    with database.connect() as cx:
        version = cx.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row["name"]
            for row in cx.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert version == 12
    assert "case_money_drafts" in tables


async def test_employee_return_upload_is_durable_but_does_not_record_R(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(app_fixture, tmp_path)
    employee = _client(app_fixture, actor=EMPLOYEE, persona="employee")
    attached = await employee.post(
        f"/api/cases/{view.id}/sources",
        files={"files": ("employee-return.pdf", RETURN_PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:employee-return-source",
            "X-Expected-Version": str(view.version),
        },
    )
    assert attached.status_code == 200, attached.text
    source = next(
        item
        for item in attached.json()["case_view"]["sources"]
        if item["filename"] == "employee-return.pdf"
    )

    draft_response = await employee.post(
        f"/api/cases/{view.id}/return-draft",
        headers={
            "X-Command-Id": "cmd:employee-return-read",
            "X-Expected-Version": str(attached.json()["case_view"]["version"]),
        },
        json={"source_id": source["id"], "instruction_id": collect.id},
    )

    assert draft_response.status_code == 200, draft_response.text
    body = draft_response.json()
    assert body["draft"]["instruction_id"] == collect.id
    assert body["draft"]["amount"] == 1_000_000
    assert body["draft"]["transaction_reference"] == "RET-TC01-001"
    assert body["draft"]["match_status"] == "MATCHED"
    assert not any(
        event["kind"] == "EMPLOYEE_RETURN"
        for event in body["case_view"]["money_history"]
    )
    assert body["case_view"]["actual_money"]["R"] == view.actual_money.R.model_dump(
        mode="json"
    )
    assert body["case_view"]["coverage_current"] == view.coverage_current
    stored = app_fixture.query_one(
        "SELECT status, instruction_id, source_id FROM case_money_drafts WHERE draft_id = ?",
        (body["draft"]["draft_id"],),
    )
    assert stored is not None
    assert stored["status"] == "WAITING_ACCOUNTANT"
    assert stored["instruction_id"] == collect.id
    assert stored["source_id"] == source["id"]

    restarted = type(app_fixture.workflow)(
        app_fixture.workflow.db,
        uploads_dir=app_fixture.workflow.uploads_dir,
    )
    restarted._clock = lambda: NOW
    restarted_session = restarted.start_session(
        tenant=TENANT, persona="employee", actor_id=EMPLOYEE
    )
    restored = await restarted.read_employee_return_draft(
        restarted_session,
        view.id,
        source["id"],
        collect.id,
        method_hint="TRANSFER",
        expected_case_version=int(body["case_view"]["version"]),
    )
    assert restored["draft"]["draft_id"] == body["draft"]["draft_id"]
    assert (
        restored["case_view"]["actual_money"]["R"]["value"] == view.actual_money.R.value
    )


async def test_accountant_confirmation_records_one_instruction_bound_return(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(app_fixture, tmp_path)
    employee = _client(app_fixture, actor=EMPLOYEE, persona="employee")
    attached = await employee.post(
        f"/api/cases/{view.id}/sources",
        files={"files": ("employee-return.pdf", RETURN_PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:return-source-confirm",
            "X-Expected-Version": str(view.version),
        },
    )
    source = next(
        item
        for item in attached.json()["case_view"]["sources"]
        if item["filename"] == "employee-return.pdf"
    )
    read = await employee.post(
        f"/api/cases/{view.id}/return-draft",
        headers={
            "X-Command-Id": "cmd:return-read-confirm",
            "X-Expected-Version": str(attached.json()["case_view"]["version"]),
        },
        json={"source_id": source["id"], "instruction_id": collect.id},
    )
    assert read.status_code == 200, read.text
    draft = read.json()["draft"]

    accountant = _client(app_fixture, actor=ACCOUNTANT, persona="accountant")

    async def confirm(command_id: str, version: int):
        return await accountant.post(
            f"/api/cases/{view.id}/actuals",
            headers={"X-Command-Id": command_id, "X-Expected-Version": str(version)},
            json={
                "money": {
                    "external_key": draft["external_key"],
                    "claimed_kind": "EMPLOYEE_RETURN",
                    "claimed_scope": view.activity,
                    "payer": EMPLOYEE,
                    "payee": "company:demo",
                    "amount": 1_000_000,
                    "event_at": draft["event_at"],
                    "completion_claim": "Kế toán xác nhận đã nhận khoản hoàn theo chứng từ.",
                    "reason": "Xác nhận khoản hoàn thực nhận theo bằng chứng đã đối chiếu.",
                    "instrument_method": "TRANSFER",
                    "instrument_status": "COMPLETED",
                    "instrument_reference": draft["transaction_reference"],
                    "instruction_id": collect.id,
                    "money_movement_draft_id": draft["draft_id"],
                    "refs": draft["refs"],
                }
            },
        )

    recorded = await confirm(
        "cmd:return-record-once", read.json()["case_view"]["version"]
    )
    assert recorded.status_code == 200, recorded.text
    after = recorded.json()["case_view"]
    returns = [
        event for event in after["money_history"] if event["kind"] == "EMPLOYEE_RETURN"
    ]
    assert len(returns) == 1
    assert returns[0]["instruction_id"] == collect.id
    assert returns[0]["money_movement_draft_id"] == draft["draft_id"]
    assert after["instructions"][0]["status"] == "FULFILLED"
    assert after["instructions"][0]["remaining"] == 0

    retry = await confirm("cmd:return-record-retry", after["version"])
    assert retry.status_code == 200, retry.text
    assert (
        len(
            [
                event
                for event in retry.json()["case_view"]["money_history"]
                if event["kind"] == "EMPLOYEE_RETURN"
            ]
        )
        == 1
    )


async def test_employee_return_draft_from_another_role_is_forbidden(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(app_fixture, tmp_path)
    accountant = _client(app_fixture, actor=ACCOUNTANT, persona="accountant")
    response = await accountant.post(
        f"/api/cases/{view.id}/return-draft",
        headers={
            "X-Command-Id": "cmd:accountant-cannot-upload-return",
            "X-Expected-Version": str(view.version),
        },
        json={"source_id": view.sources[0].id, "instruction_id": collect.id},
    )
    assert response.status_code == 403, response.text


async def test_pending_second_return_cannot_confirm_after_collect_is_fulfilled(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(app_fixture, tmp_path)
    _employee, _source, first_response = await _upload_employee_return(
        app_fixture,
        view,
        collect,
        filename="return-first.pdf",
        reference="RET-STALE-FIRST",
    )
    assert first_response.status_code == 200, first_response.text
    employee_session = app_fixture.workflow.start_session(
        tenant=TENANT, persona="employee", actor_id=EMPLOYEE
    )
    current_view = app_fixture.workflow.view(employee_session, view.id)
    _employee, _source, second_response = await _upload_employee_return(
        app_fixture,
        current_view,
        collect,
        filename="return-second.pdf",
        reference="RET-STALE-SECOND",
    )
    assert second_response.status_code == 200, second_response.text
    first = first_response.json()["draft"]
    second = second_response.json()["draft"]
    accepted = await _confirm_return(
        app_fixture, view, collect, first, command_id="cmd:confirm-first-return"
    )
    assert accepted.status_code == 200, accepted.text
    stale = await _confirm_return(
        app_fixture, view, collect, second, command_id="cmd:confirm-stale-second-return"
    )
    assert stale.status_code == 409, stale.text
    with app_fixture.workflow.db.connect() as cx:
        assert (
            cx.execute(
                "SELECT COUNT(*) FROM money_events WHERE root_id = ? AND kind = 'EMPLOYEE_RETURN'",
                (view.id,),
            ).fetchone()[0]
            == 1
        )


async def test_partial_return_keeps_remaining_amount_on_the_same_collect_instruction(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(
        app_fixture, tmp_path, amount="400.000 đồng", reference="RET-PART-001"
    )
    _employee, _source, response = await _upload_employee_return(
        app_fixture,
        view,
        collect,
        filename="partial-return.pdf",
        amount="400.000 đồng",
        reference="RET-PART-001",
    )
    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    recorded = await _confirm_return(
        app_fixture, view, collect, draft, command_id="cmd:confirm-partial-return"
    )

    assert recorded.status_code == 200, recorded.text
    after = recorded.json()["case_view"]
    assert after["instructions"][0]["id"] == collect.id
    assert after["instructions"][0]["status"] == "PARTIAL"
    assert after["instructions"][0]["fulfilled_amount"] == 400_000
    assert after["instructions"][0]["remaining"] == 600_000


async def test_overpaid_return_is_recorded_but_raises_a_specific_blocker(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(
        app_fixture, tmp_path, amount="1.200.000 đồng", reference="RET-OVER-001"
    )
    _employee, _source, response = await _upload_employee_return(
        app_fixture,
        view,
        collect,
        filename="over-return.pdf",
        amount="1.200.000 đồng",
        reference="RET-OVER-001",
    )
    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    assert draft["match_status"] == "OVERPAY"

    recorded = await _confirm_return(
        app_fixture, view, collect, draft, command_id="cmd:confirm-over-return"
    )
    assert recorded.status_code == 200, recorded.text
    after = recorded.json()["case_view"]
    assert after["money_history"][-1]["amount"] == 1_200_000
    assert after["instructions"][0]["fulfilled_amount"] == 1_000_000
    assert after["instructions"][0]["remaining"] == 0
    assert any(
        issue["field_or_rule"] == f"overpay:{collect.id}" for issue in after["issues"]
    )
    assert after["state"] != "SETTLED"


async def test_wrong_company_payee_is_a_conflict_and_not_a_return_event(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(
        app_fixture, tmp_path, payee="CÔNG TY KHÁC", reference="RET-WRONG-001"
    )
    _employee, _source, response = await _upload_employee_return(
        app_fixture,
        view,
        collect,
        filename="wrong-payee-return.pdf",
        payee="CÔNG TY KHÁC",
        reference="RET-WRONG-001",
    )

    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    assert draft["match_status"] == "CONFLICT"
    assert any(
        signal["field"] == "payee" and signal["state"] == "CONFLICT"
        for signal in draft["signals"]
    )
    with app_fixture.workflow.db.connect() as cx:
        assert (
            cx.execute(
                "SELECT COUNT(*) FROM money_events WHERE root_id = ? AND kind = 'EMPLOYEE_RETURN'",
                (view.id,),
            ).fetchone()[0]
            == 0
        )


async def test_failed_return_transfer_is_not_recorded_as_received(
    app_fixture, tmp_path
):
    view, collect = await _collect_case(
        app_fixture, tmp_path, status="Thất bại", reference="RET-FAILED-001"
    )
    _employee, _source, response = await _upload_employee_return(
        app_fixture,
        view,
        collect,
        filename="failed-return.pdf",
        status="Thất bại",
        reference="RET-FAILED-001",
    )

    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    assert draft["match_status"] == "NOT_COMPLETED"
    recorded = await _confirm_return(
        app_fixture, view, collect, draft, command_id="cmd:confirm-failed-return"
    )
    assert recorded.status_code == 409, recorded.text
    with app_fixture.workflow.db.connect() as cx:
        assert (
            cx.execute(
                "SELECT COUNT(*) FROM money_events WHERE root_id = ? AND kind = 'EMPLOYEE_RETURN'",
                (view.id,),
            ).fetchone()[0]
            == 0
        )
