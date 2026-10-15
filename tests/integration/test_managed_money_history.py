"""Typed financial loop: one intake assertion, no repeated coverage ceremony."""

from datetime import datetime

from httpx import ASGITransport, AsyncClient
import pytest

from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.workflow.service import CaseWorkflow
from tests.integration.test_f01_two_flows import (
    _workflow, _seed, _submit, _assess, _record_advance, _report, PILOT_CLOCK, TENANT, EMPLOYEE, ACCOUNTANT,
)
from tests.integration.test_employee_return_draft_api import _ReturnReader, _ReturnClassifier, _return_text

NOW = datetime.fromisoformat("2026-10-15T12:00:00+07:00")
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"


async def prepare(tmp_path, *, total=None, imported=False):
    wf = _workflow(tmp_path, advance=4_000_000 if imported else 0)
    wf._clock = lambda: PILOT_CLOCK if imported else NOW
    root = await _seed(wf)
    if total is not None:
        report = _report()
        documents = tuple(document.model_copy(update={
            "fields": tuple(field.model_copy(update={"value": str(total)})
                            if field.field in ("printed_total", "total_amount") else field
                            for field in document.fields),
            "line_items": tuple(line.model_copy(update={
                "fields": tuple(field.model_copy(update={"value": str(total)})
                                if field.field == "amount" else field for field in line.fields)
            }) for line in document.line_items),
        }) for document in report.documents)
        with wf.db.transaction() as cx:
            wf._publish_evidence_report(cx, tenant=TENANT, root_id=root,
                                        report=report.model_copy(update={"documents": documents}))
    await _submit(wf, root)
    if imported:
        await _assess(wf, root)
    if not imported:
        await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:INITIAL-4M")
    wf._clock = lambda: NOW
    app = create_app(wf, mode="STUB", frontend_dir=None)
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    accountant = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    client.cookies.set(SESSION_COOKIE, accountant.session_id)
    return wf, client, root


async def post(client, root, suffix, body, key):
    view = (await client.get(f"/api/cases/{root}")).json()
    return await client.post(f"/api/cases/{root}/{suffix}", json=body,
                             headers={"X-Command-Id": key, "X-Expected-Version": str(view["version"])})


@pytest.mark.parametrize("imported", [False, True])
@pytest.mark.parametrize("amount,expected_s,expected_state", [
    ("760.000 đồng", 0, "SETTLED"), ("400.000 đồng", -360_000, "READY_TO_EXECUTE"),
])
async def test_typed_tc01_tracks_confirmed_return_without_second_history_confirmation(
    tmp_path, amount, expected_s, expected_state, imported,
):
    wf, client, root = await prepare(tmp_path, imported=imported)
    async with client:
        if imported:
            view = (await client.get(f"/api/cases/{root}")).json()
        else:
            confirmed = await post(client, root, "money-history/confirm",
                                   {"all_prior_money_recorded": True}, "cmd:history")
            assert confirmed.status_code == 200, confirmed.text
            view = confirmed.json()["case_view"]
        coverage_before_upload = view["coverage_current"]
        assert view["actual_money"]["S"]["value"] == -760_000
        collect = next(i for i in view["instructions"] if i["direction"] == "COLLECT")
        wf.enable_evidence_read(
            reader=_ReturnReader(_return_text(amount=amount)),
            classifier=_ReturnClassifier(amount=amount, payee=COMPANY, status="Hoàn tất", reference="RET-TC01-001"),
            artifacts_root=tmp_path / "return-artifacts", provider_mode="STUB",
        )
        employee = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
        client.cookies.set(SESSION_COOKIE, employee.session_id)
        uploaded = await client.post(f"/api/cases/{root}/sources",
            files={"files": ("return.pdf", b"%PDF-1.4\nreturn\n%%EOF", "application/pdf")},
            headers={"X-Command-Id": "cmd:upload-return", "X-Expected-Version": str(view["version"])})
        assert uploaded.status_code == 200, uploaded.text
        source = next(s for s in uploaded.json()["case_view"]["sources"] if s["filename"] == "return.pdf")
        read = await post(client, root, "return-draft",
                          {"source_id": source["id"], "instruction_id": collect["id"]}, "cmd:read-return")
        assert read.status_code == 200, read.text
        assert read.json()["case_view"]["actual_money"]["R"]["value"] == 0
        assert read.json()["case_view"]["coverage_current"] is coverage_before_upload
        draft = read.json()["draft"]
        accountant = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
        client.cookies.set(SESSION_COOKIE, accountant.session_id)
        body = {"money": {
            "external_key": draft["external_key"], "claimed_kind": "EMPLOYEE_RETURN",
            "claimed_scope": view["activity"], "payer": EMPLOYEE, "payee": "company:demo",
            "amount": draft["amount"], "event_at": draft["event_at"],
            "completion_claim": "Kế toán xác nhận đã nhận tiền hoàn.", "reason": "Đối chiếu chứng từ thực nhận.",
            "instrument_method": "TRANSFER", "instrument_status": "COMPLETED",
            "instrument_reference": draft["transaction_reference"], "instruction_id": collect["id"],
            "money_movement_draft_id": draft["draft_id"], "refs": draft["refs"],
        }}
        recorded = await post(client, root, "actuals", body, "cmd:confirm-return")
        assert recorded.status_code == 200, recorded.text
        final = recorded.json()["case_view"]
        assert final["coverage_current"] is True
        assert final["actual_money"]["S"]["value"] == expected_s
        assert final["state"] == expected_state
        assert wf._query_one("SELECT COUNT(*) AS n FROM case_coverage_records WHERE root_id = ?", (root,))["n"] == 1
        retried = await post(client, root, "actuals", body, "cmd:confirm-return-retry")
        assert retried.status_code == 200, retried.text
        assert sum(e["kind"] == "EMPLOYEE_RETURN" for e in retried.json()["case_view"]["money_history"]) == 1
        restarted = CaseWorkflow(wf.db, uploads_dir=wf.uploads_dir, clock=lambda: NOW)
        session = restarted.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
        assert restarted.view(session, root).coverage_current is True


async def test_out_of_band_money_invalidates_managed_history(tmp_path):
    wf, client, root = await prepare(tmp_path)
    async with client:
        confirmed = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:history")
        assert confirmed.status_code == 200, confirmed.text
        # Even a confirmed generic advance is outside the reviewed draft path.
        await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:LATE-HISTORICAL")
        view = (await client.get(f"/api/cases/{root}")).json()
        assert view["coverage_current"] is False
        assert view["actual_money"]["S"]["state"] == "UNKNOWN"
        assert view["state"] != "SETTLED"


@pytest.mark.parametrize("total,event_day,tracked", [
    (4_400_000, "2026-10-15", True), (4_000_000, "2026-10-15", True),
    (4_400_000, "2026-10-14", False),
])
async def test_managed_history_supports_pay_and_balanced_without_zero_instruction(tmp_path, total, event_day, tracked):
    wf, client, root = await prepare(tmp_path, total=total)
    async with client:
        confirmed = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:history")
        assert confirmed.status_code == 200, confirmed.text
        view = confirmed.json()["case_view"]
        if total == 4_000_000:
            assert view["state"] == "SETTLED"
            assert view["instructions"] == []
            return
        instruction = next(i for i in view["instructions"] if i["direction"] == "PAY")
        assert instruction["amount"] == 400_000
        source = view["sources"][0]
        paid = await post(client, root, "actuals", {"money": {
            "external_key": "transfer:PAY-400K", "claimed_kind": "REIMBURSEMENT_RECEIVED",
            "claimed_scope": view["activity"], "payer": "company:demo", "payee": EMPLOYEE,
            "amount": 400_000, "event_at": event_day, "instruction_id": instruction["id"],
            "instrument_method": "TRANSFER", "instrument_status": "COMPLETED",
            "instrument_reference": "PAY-400K", "completion_claim": "Kế toán xác nhận chi bổ sung đã thực nhận.",
            "reason": "Đối chiếu chứng từ chi theo lệnh.",
            "refs": [{"source_id": source["id"], "source_sha256": source["digest"], "page": 1, "exact_quote": "Chứng từ chi bổ sung"}],
        }}, "cmd:pay")
        assert paid.status_code == 200, paid.text
        final = paid.json()["case_view"]
        assert final["coverage_current"] is tracked
        if not tracked:
            assert final["actual_money"]["S"]["state"] == "UNKNOWN"
            assert final["state"] != "SETTLED"
            return
        assert final["actual_money"]["P"]["value"] == 400_000
        assert final["actual_money"]["S"]["value"] == 0
        assert final["state"] == "SETTLED"


async def test_imported_history_change_requires_review_again(tmp_path):
    from invoice_referee.domain.organization import OrganizationContext
    from invoice_referee.workflow.context_records import load_context

    wf, client, root = await prepare(tmp_path)
    async with client:
        confirmed = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:history")
        assert confirmed.status_code == 200, confirmed.text
        view = confirmed.json()["case_view"]
        with wf.db.connect() as cx:
            org = load_context(cx, TENANT, view["activity"], NOW)
        payload = org.model_dump(mode="json")
        payload["ledger"] = [{
            "id": "import:late", "external_key": "bank:IMPORTED-LATE", "kind": "ADVANCE_RECEIVED",
            "scope": view["activity"], "payer": "company:demo", "payee": EMPLOYEE,
            "amount": 100_000, "event_at": "2026-10-04T00:00:00Z", "recorded_at": "2026-10-04T00:00:00Z",
            "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED",
        }]
        wf.import_company_context(OrganizationContext.model_validate_json(__import__('json').dumps(payload)), origin="SIMULATED")
        changed = (await client.get(f"/api/cases/{root}")).json()
        assert changed["coverage_current"] is False


async def test_unallocated_movement_cannot_be_hidden_by_initial_confirmation(tmp_path):
    wf, client, root = await prepare(tmp_path)
    async with client:
        view = (await client.get(f"/api/cases/{root}")).json()
        source = view["sources"][0]
        observed = await post(client, root, "actuals", {"money": {
            "external_key": "bank:UNKNOWN-HISTORY", "claimed_kind": "OBSERVED_UNALLOCATED",
            "claimed_scope": view["activity"], "payer": "company:demo", "payee": EMPLOYEE,
            "amount": 50_000, "event_at": "2026-10-14", "instrument_status": "UNKNOWN",
            "reason": "Khoản tiền chưa xác định trong lịch sử.",
            "refs": [{"source_id": source["id"], "source_sha256": source["digest"], "page": 1, "exact_quote": "Chưa rõ khoản chi"}],
        }}, "cmd:observed")
        assert observed.status_code == 200, observed.text
        confirmed = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:history")
        assert confirmed.status_code == 400, confirmed.text
        assert wf._query_one("SELECT COUNT(*) AS n FROM case_coverage_records WHERE root_id = ?", (root,))["n"] == 0


async def test_reconfirm_after_review_uses_latest_checkpoint_even_at_same_clock_time(tmp_path):
    wf, client, root = await prepare(tmp_path)
    async with client:
        initial = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:initial")
        assert initial.status_code == 200, initial.text
        with wf.db.transaction() as cx:
            cx.execute("UPDATE case_coverage_records SET coverage_id = 'coverage:zzzz-old' WHERE root_id = ?", (root,))
        await _record_advance(wf, root, method="TRANSFER", status="COMPLETED", key="bank:LATE-REVIEWED")
        assert (await client.get(f"/api/cases/{root}")).json()["coverage_current"] is False
        reviewed = await post(client, root, "money-history/confirm", {"all_prior_money_recorded": True}, "cmd:reviewed")
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["case_view"]["coverage_current"] is True
        assert reviewed.json()["case_view"]["actual_money"]["A"]["value"] == 8_000_000
