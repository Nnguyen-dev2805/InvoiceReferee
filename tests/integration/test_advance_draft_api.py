"""D: the "record advance received" draft endpoint reads an uploaded document.

The accountant uploads a transfer receipt / cash voucher; the endpoint runs the
evidence pipeline and returns a prefilled DRAFT. It is a READ: no money is
recorded and no case version changes. The client cannot set the actor/scope.
"""

from __future__ import annotations

from tests.factories import clear_ocr_page

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate, OcrPage, OcrSourceResult
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:uc03-pilot"
ACCOUNTANT = "employee:accountant-demo"
ACTIVITY = "activity:uc03-f01"
SHA = "a" * 64
PDF = b"%PDF-1.4\n%fake\n"


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _source_field(source: dict, name: str, value: object, quote: str) -> FieldCandidate:
    return FieldCandidate(
        field=name,
        state="FOUND",
        value=value,  # type: ignore[arg-type]
        refs=(EvidenceRef(
            source_id=source["id"],
            source_sha256=source["digest"],
            page=1,
            exact_quote=quote,
        ),),
    )


class _Reader:
    """A fake reader returning one transfer-receipt page."""

    def __init__(self, *, activity_reference: str = "REF-OTHER", payment_purpose: str = "Ứng tiền tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"):
        self.activity_reference = activity_reference
        self.payment_purpose = payment_purpose

    async def read_source(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
        status_text = "Đang xử lý" if "pending" in source.filename.lower() else "Hoàn tất"
        return OcrSourceResult(
            source_id=source.id, source_digest=source.digest, provider="fake", model="fake",
            pages=(clear_ocr_page(markdown=f"BIÊN NHẬN CHUYỂN KHOẢN\nCÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH\nSố tiền 4.000.000 đ\nNgày giao dịch 05/10/2026\nTrạng thái {status_text}\nBên nhận NGUYỄN MINH AN\nMã giao dịch FT-1\nMã hồ sơ {self.activity_reference}\nNội dung chuyển tiền {self.payment_purpose}\nNgân hàng Demo"),),
        )


class _Classifier:
    def __init__(self, *, missing_payer: bool = False, activity_reference: str = "REF-OTHER", payment_purpose: str = "Ứng tiền tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"):
        self.missing_payer = missing_payer
        self.activity_reference = activity_reference
        self.payment_purpose = payment_purpose

    async def complete_json(self, *, system, user, budget):
        if "classify" in system.lower():
            import json

            docs = json.loads(user)["documents"]
            return {"documents": [
                {"source_id": d["source_id"], "page_range": [1, 1], "document_type": "PAYMENT_PROOF",
                 "roles": ["PAYMENT_EVIDENCE"], "classification_confidence": 0.9}
                for d in docs
            ]}
        if "TABLE ROWS" in system or "line_items" in system:
            fields = [
                {"field": "transaction_reference", "state": "FOUND", "value": "FT-1", "quote": "FT-1", "page": 1},
                {"field": "event_at", "state": "FOUND", "value": "2026-10-05", "quote": "05/10/2026", "page": 1},
                {"field": "advance_reference", "state": "FOUND", "value": self.activity_reference, "quote": self.activity_reference, "page": 1},
                {"field": "payment_description", "state": "FOUND", "value": self.payment_purpose, "quote": self.payment_purpose, "page": 1},
                {"field": "transaction_status", "state": "FOUND", "value": "Đang xử lý" if "Đang xử lý" in user else "Hoàn tất", "quote": "Đang xử lý" if "Đang xử lý" in user else "Hoàn tất", "page": 1},
                {"field": "payee_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                {"field": "amount", "state": "FOUND", "value": "4.000.000 đ", "quote": "4.000.000 đ", "page": 1},
                {"field": "payment_provider", "state": "FOUND", "value": "Ngân hàng Demo", "quote": "Ngân hàng Demo", "page": 1},
            ]
            if not self.missing_payer:
                fields.append({
                    "field": "payer_name",
                    "state": "FOUND",
                    "value": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                    "quote": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                    "page": 1,
                })
            return {"fields": fields, "line_items": []}
        # OCR quality review: no findings.
        return {"assessments": []}


@pytest.fixture
async def fixture(tmp_path: Path):
    import json

    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.enable_evidence_read(reader=_Reader(), classifier=_Classifier(), artifacts_root=tmp_path / "a")
    org = json.loads((Path(__file__).resolve().parents[2] / "data/test-kit/uc03-pilot/f01-cong-tac-thu-lai-tien-thua/input/organization.json").read_text())
    from invoice_referee.domain.organization import OrganizationContext

    wf.import_company_context(OrganizationContext.model_validate_json(json.dumps(org)), origin="SIMULATED")
    app = create_app(wf, mode="LIVE", frontend_dir=None)
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://testserver")
    session = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    client.cookies.set(SESSION_COOKIE, session.session_id)
    # Create a root for the accountant to attach the advance doc to.
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    employee = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    created = await wf.execute(
        CommandContext(session_id=employee.session_id, actor_id="employee:employee-a", command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="a", occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="p")),
    )
    yield client, wf, created.case_view.id
    await client.aclose()


def test_activity_acceptance_signal_migration_preserves_v8_schema(tmp_path: Path) -> None:
    db = Database(tmp_path / "legacy-v8.sqlite")
    db.migrate()
    with db.transaction() as cx:
        columns = {str(row["name"]) for row in cx.execute("PRAGMA table_info(case_activity_acceptances)")}
        if "link_signals_json" in columns:
            cx.execute("ALTER TABLE case_activity_acceptances DROP COLUMN link_signals_json")
        cx.execute("PRAGMA user_version = 8")

    db.migrate()

    with db.connect() as cx:
        columns = {str(row["name"]) for row in cx.execute("PRAGMA table_info(case_activity_acceptances)")}
        version = int(cx.execute("PRAGMA user_version").fetchone()[0])
    assert version == 10
    assert "link_signals_json" in columns
    with db.connect() as cx:
        draft_table = cx.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'case_money_drafts'"
        ).fetchone()
    assert draft_table is not None


async def _multifield_root(client, wf, *, suffix: str, purpose: str):
    """Create a source-backed settlement root with no activity reference code."""
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    employee = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    created = await wf.execute(
        CommandContext(
            session_id=employee.session_id,
            actor_id="employee:employee-a",
            command_id=f"cmd:{suffix}:create",
            expected_case_version=0,
        ),
        CreateDraft(activity_data=ActivityData(
            activity_id=f"activity:proposed:{suffix}",
            name=purpose,
            occurred_at="2026-10-10T09:00:00+07:00",
            declared_purpose=purpose,
        )),
    )
    attached = await client.post(
        f"/api/cases/{created.case_view.id}/sources",
        files={"files": (f"{suffix}-settlement.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": f"cmd:{suffix}:settlement-source",
            "X-Expected-Version": str(created.case_view.version),
        },
    )
    assert attached.status_code == 200, attached.text
    source = attached.json()["case_view"]["sources"][0]
    report = ReadResult(documents=(DocumentAnalysis(
        source_id=source["id"],
        document_id=f"settlement:{suffix}",
        document_type="SETTLEMENT_FORM",
        fields=(
            _source_field(source, "declared_name", "NGUYỄN MINH AN", "Người đề nghị: NGUYỄN MINH AN"),
            _source_field(source, "purpose", purpose, purpose),
            _source_field(source, "declared_advance", 4_000_000, "Số tiền đã tạm ứng: 4.000.000 đồng"),
            _source_field(source, "printed_total", 3_240_000, "Tổng cộng: 3.240.000 đồng"),
            _source_field(source, "document_date", "2026-10-10", "ngày 10 tháng 10 năm 2026"),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    ),))
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_evidence_reports (root_id, tenant, report_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (created.case_view.id, TENANT, report.model_dump_json(), wf._now_iso()),
        )
    return created.case_view.id, attached.json()["case_view"]


async def test_saved_advance_draft_relinks_vietnamese_date_without_provider_or_money(fixture) -> None:
    client, wf, _ = fixture
    root, view = await _multifield_root(
        client, wf, suffix="saved-date", purpose="Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"
    )
    with wf.db.transaction() as cx:
        report = json.loads(cx.execute(
            "SELECT report_json FROM case_evidence_reports WHERE root_id = ?", (root,)
        ).fetchone()[0])
        next(field for field in report["documents"][0]["fields"] if field["field"] == "document_date")["value"] = "10 tháng 10 năm 2026"
        cx.execute("UPDATE case_evidence_reports SET report_json = ? WHERE root_id = ?", (json.dumps(report), root))
    response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "saved-date-read", "X-Expected-Version": str(view["version"])},
    )
    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    with wf.db.transaction() as cx:
        old = dict(draft, activity_link_status="NEEDS_CONFIRMATION", activity_link_basis=None, matched_activity_id=None)
        cx.execute("UPDATE case_advance_drafts SET draft_json = ? WHERE draft_id = ?", (json.dumps(old), draft["draft_id"]))
    # Simulate a restart with no reader/provider configured. A saved read must suffice.
    restarted = CaseWorkflow(wf.db, uploads_dir=wf.uploads_dir)
    app = create_app(restarted, mode="LIVE", frontend_dir=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver", cookies=client.cookies) as restored:
        result = await restored.get(f"/api/cases/{root}/advance/draft?draft_id={draft['draft_id']}")
        assert result.status_code == 200, result.text
        payload = result.json()
        assert payload["draft"]["draft_id"] == draft["draft_id"]
        assert payload["draft"]["activity_link_status"] == "LINKED"
        assert payload["draft"]["activity_link_basis"] == "MULTI_FIELD_MATCH"
        assert next(s for s in payload["draft"]["activity_link_signals"] if s["field"] == "time")["state"] == "MATCHED"
        assert payload["case_view"]["version"] == response.json()["case_view"]["version"]
        assert payload["case_view"]["activity_acceptances"] == []
        assert payload["case_view"]["coverage_record"] is None
        assert payload["case_view"]["instructions"] == []
        foreign = await restored.get(f"/api/cases/{root}/advance/draft?draft_id=not-this-root")
        assert foreign.status_code == 404
    assert wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"] == 0


async def test_saved_advance_draft_requires_accountant(fixture) -> None:
    client, wf, root = fixture
    employee = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    client.cookies.set(SESSION_COOKIE, employee.session_id)
    response = await client.get(f"/api/cases/{root}/advance/draft")
    assert response.status_code == 403


async def test_advance_draft_prefills_from_the_uploaded_document(fixture) -> None:
    client, wf, root = fixture
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:adv", "X-Expected-Version": str(version)},
    )
    assert response.status_code == 200, response.text
    body = response.json()["draft"]
    assert body["amount"] == 4_000_000
    assert body["payee_name"] == "NGUYỄN MINH AN"
    assert body["transaction_reference"] == "FT-1"
    assert body["instrument_status"] == "COMPLETED"
    assert body["requires_confirmation"] is True


async def test_advance_draft_attaches_the_read_source_to_the_case(fixture) -> None:
    client, wf, root = fixture
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:adv-persist",
            "X-Expected-Version": str(version),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft"]["amount"] == 4_000_000
    assert body["case_view"]["version"] > version
    assert len(body["case_view"]["sources"]) == 1
    with wf.db.connect() as cx:
        source = cx.execute(
            "SELECT storage_key, digest FROM case_sources WHERE root_id = ?", (root,)
        ).fetchone()
    assert source is not None
    assert (wf.uploads_dir / source["storage_key"]).read_bytes() == PDF
    assert source["digest"] == __import__("hashlib").sha256(PDF).hexdigest()


async def test_advance_source_and_read_report_survive_workflow_restart(fixture) -> None:
    client, wf, root = fixture
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    response = await client.post(
        f"/api/cases/{root}/advance/draft",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:advance-restart", "X-Expected-Version": str(version)},
    )
    assert response.status_code == 200, response.text
    source_id = response.json()["draft"]["source_id"]

    restarted = CaseWorkflow(Database(wf.db.path), uploads_dir=wf.uploads_dir)
    restarted.db.migrate()
    account = restarted.start_session(
        tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT
    )
    app = create_app(restarted, mode="LIVE", frontend_dir=None)
    reopened = AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
    reopened.cookies.set(SESSION_COOKIE, account.session_id)
    try:
        source_response = await reopened.get(
            f"/api/cases/{root}/sources/{source_id}"
        )
    finally:
        await reopened.aclose()

    assert source_response.status_code == 200
    assert source_response.content == PDF
    with restarted.db.connect() as cx:
        draft = cx.execute(
            "SELECT draft_json, report_json FROM case_advance_drafts WHERE root_id = ?",
            (root,),
        ).fetchone()
    assert draft is not None
    assert '"transaction_reference": "FT-1"' in draft["draft_json"]
    assert source_id in draft["report_json"]


async def test_advance_draft_does_not_record_money(fixture) -> None:
    client, wf, root = fixture
    version = int(wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"])
    before = wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"]
    await client.post(
        f"/api/cases/{root}/advance/draft",
        files={"files": ("x.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:adv2", "X-Expected-Version": str(version)},
    )
    after = wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"]
    assert int(after) == int(before) == 0


async def test_tc01_specific_multi_field_basis_auto_links_and_records_only_after_accountant_confirms(
    fixture, tmp_path: Path,
) -> None:
    import json
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    # Keep the tenant's employee/company identity, but do not seed TU-TC01 into
    # any activity reference catalog. The second root is an ordinary proposed
    # work item with no pre-created activity fixture.
    employee = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    created = await wf.execute(
        CommandContext(
            session_id=employee.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:tc01-multifield-case",
            expected_case_version=0,
        ),
        CreateDraft(activity_data=ActivityData(
            activity_id="activity:proposed:tc01-multifield",
            name="Nâng cấp văn phòng 2026",
            occurred_at="2026-10-10T09:00:00+07:00",
            declared_purpose="Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
        )),
    )
    root = created.case_view.id
    # A matching-looking root in another tenant is invisible to this tenant's
    # candidate search and must not turn a unique local match into ambiguity.
    other_employee = wf.start_session(
        tenant="tenant:other", persona="employee", actor_id="employee:employee-a"
    )
    await wf.execute(
        CommandContext(
            session_id=other_employee.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:tc01-multifield-other-tenant",
            expected_case_version=0,
        ),
        CreateDraft(activity_data=ActivityData(
            activity_id="activity:other-tenant-same-purpose",
            name="Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
            occurred_at="2026-10-10T09:00:00+07:00",
            declared_purpose="Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
        )),
    )
    attached = await client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("report_hoan_ung.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:tc01-multifield-settlement-source",
            "X-Expected-Version": str(created.case_view.version),
        },
    )
    assert attached.status_code == 200, attached.text
    settlement_source = attached.json()["case_view"]["sources"][0]
    purpose = "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"
    report = ReadResult(documents=(DocumentAnalysis(
        source_id=settlement_source["id"],
        document_id="settlement:tc01-multifield",
        document_type="SETTLEMENT_FORM",
        fields=(
            _source_field(settlement_source, "declared_name", "NGUYỄN MINH AN", "Người đề nghị: NGUYỄN MINH AN"),
            _source_field(settlement_source, "purpose", purpose, purpose),
            _source_field(settlement_source, "declared_advance", 4_000_000, "Số tiền đã tạm ứng: 4.000.000 đồng"),
            _source_field(settlement_source, "printed_total", 3_240_000, "Tổng cộng: 3.240.000 đồng"),
            _source_field(settlement_source, "document_date", "2026-10-10", "ngày 10 tháng 10 năm 2026"),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    ),))
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_evidence_reports (root_id, tenant, report_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (root, TENANT, report.model_dump_json(), wf._now_iso()),
        )
        refs = [
            json.loads(row["references_json"] or "[]")
            for row in cx.execute("SELECT references_json FROM context_activities WHERE tenant = ?", (TENANT,))
        ]
    assert all("TU-TC01" not in item for values in refs for item in values)

    wf.enable_evidence_read(
        reader=_Reader(activity_reference="TU-TC01"),
        classifier=_Classifier(activity_reference="TU-TC01"),
        artifacts_root=tmp_path / "multifield-artifacts",
    )
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:tc01-multifield-advance-read",
            "X-Expected-Version": str(attached.json()["case_view"]["version"]),
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_result = draft_response.json()
    draft = draft_result["draft"]
    assert draft["activity_reference"] == "TU-TC01"
    assert draft["activity_link_status"] == "LINKED"
    assert draft["activity_link_basis"] == "MULTI_FIELD_MATCH"
    assert {signal["field"] for signal in draft["activity_link_signals"]} >= {
        "employee", "company", "purpose", "advance_amount", "time", "reference"
    }
    assert int(wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE tenant = ?", (TENANT,))["n"]) == 0

    # The source-bound record command is the accountant's confirmation;
    # no repeated free-text declaration is required for this routine draft.
    recorded = await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:tc01-multifield-advance-record",
            "X-Expected-Version": str(draft_result["case_view"]["version"]),
        },
        json={"money": {
            "external_key": "transfer:FT-1",
            "claimed_kind": "ADVANCE_RECEIVED",
            "claimed_scope": draft_result["case_view"]["activity"],
            "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
            "payee": "NGUYỄN MINH AN",
            "amount": 4_000_000,
            "event_at": "2026-10-05T09:00:00+07:00",
            "reason": "",
            "instrument_method": "TRANSFER",
            "instrument_status": "COMPLETED",
            "instrument_reference": "FT-1",
            "refs": draft["refs"],
            "advance_draft_id": draft["draft_id"],
        }},
    )
    assert recorded.status_code == 200, recorded.text
    updated = recorded.json()["case_view"]
    assert len(updated["activity_acceptances"]) == 1
    assert updated["activity_acceptances"][0]["link_basis"] == "MULTI_FIELD_MATCH"
    assert len(updated["activity_acceptances"][0]["link_signals"]) >= 5
    assert updated["coverage_record"]["source"] == "DOSSIER_RECORDS"
    assert updated["coverage_record"]["opening_balance"] is None
    assert updated["coverage_current"] is True
    assert updated["actual_money"]["A"]["value"] == 4_000_000
    assert updated["actual_money"]["P"]["value"] == 0
    assert updated["actual_money"]["R"]["value"] == 0
    assert not any("coverage" in issue["field_or_rule"] for issue in updated["issues"])
    assert updated["instructions"] == []
    event = wf._query_one("SELECT payload_json FROM money_events WHERE root_id = ?", (root,))
    event_payload = json.loads(event["payload_json"])
    assert event_payload["verification_state"] == "CONFIRMED"
    assert event_payload["recorded_by"] == ACCOUNTANT
    assert "xác nhận" in event_payload["record_reason"].lower()
    assert event_payload["advance_draft_id"] == draft["draft_id"]
    # The same physical receipt remains idempotent with a new command ID after reload.
    retry = await client.post(
        f"/api/cases/{root}/actuals",
        headers={"X-Command-Id": "cmd:tc01-one-click-retry", "X-Expected-Version": str(updated["version"])},
        json=json.loads(recorded.request.content),
    )
    assert retry.status_code == 200, retry.text
    assert len(retry.json()["case_view"]["money_history"]) == 1
    assert len(retry.json()["case_view"]["activity_acceptances"]) == 1
    assert int(wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE tenant = ? AND root_id = ?", (TENANT, root))["n"]) == 1
    activity_row = wf._query_one(
        "SELECT status FROM context_activities WHERE tenant = ? AND activity_id = ?",
        (TENANT, draft_result["case_view"]["activity"]),
    )
    assert activity_row is None or activity_row["status"] == "PROPOSED"


async def test_same_employee_same_project_and_amount_on_two_roots_needs_confirmation(
    fixture, tmp_path: Path,
) -> None:
    client, wf, _ = fixture
    purpose = "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"
    first_root, first_case = await _multifield_root(
        client, wf, suffix="tc01-compete-a", purpose=purpose
    )
    second_root, _ = await _multifield_root(
        client, wf, suffix="tc01-compete-b", purpose=purpose
    )
    wf.enable_evidence_read(
        reader=_Reader(activity_reference="TU-TC01"),
        classifier=_Classifier(activity_reference="TU-TC01"),
        artifacts_root=tmp_path / "competing-artifacts",
    )

    response = await client.post(
        f"/api/cases/{first_root}/advance/draft?method=TRANSFER",
        files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:tc01-competing-advance-read",
            "X-Expected-Version": str(first_case["version"]),
        },
    )

    assert response.status_code == 200, response.text
    draft = response.json()["draft"]
    assert draft["activity_link_status"] == "NEEDS_CONFIRMATION"
    assert draft["activity_link_candidate_count"] == 2
    assert draft["matched_activity_id"] is None
    assert second_root not in response.text
    assert int(wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE tenant = ?", (TENANT,))["n"]) == 0


async def test_concurrent_uploads_cannot_claim_one_transaction_for_two_roots(
    fixture, tmp_path: Path,
) -> None:
    client, wf, _ = fixture
    purpose = "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026"
    roots = [
        await _multifield_root(client, wf, suffix="tc01-race-a", purpose=purpose),
        await _multifield_root(
            client,
            wf,
            suffix="tc01-race-b",
            purpose="Chi phí mua thiết bị văn phòng",
        ),
    ]
    wf.enable_evidence_read(
        reader=_Reader(activity_reference="TU-TC01"),
        classifier=_Classifier(activity_reference="TU-TC01"),
        artifacts_root=tmp_path / "concurrent-artifacts",
    )

    async def upload(root: str, case_view: dict, command: str):
        return await client.post(
            f"/api/cases/{root}/advance/draft?method=TRANSFER",
            files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
            headers={
                "X-Command-Id": command,
                "X-Expected-Version": str(case_view["version"]),
            },
        )

    responses = await asyncio.gather(
        upload(roots[0][0], roots[0][1], "cmd:tc01-race-read-a"),
        upload(roots[1][0], roots[1][1], "cmd:tc01-race-read-b"),
    )

    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    drafts = [response.json()["draft"] for response in responses]
    linked = [draft for draft in drafts if draft["activity_link_status"] == "LINKED"]
    assert len(linked) <= 1
    assert all(
        draft["activity_link_status"] in {"NEEDS_CONFIRMATION", "CONFLICT"}
        for draft in drafts
        if draft not in linked
    )
    assert sum(draft["activity_link_basis"] == "MULTI_FIELD_MATCH" for draft in drafts) <= 1
    assert all(draft["matched_activity_id"] is None or draft["matched_activity_id"] == roots[index][1]["activity"]
               for index, draft in enumerate(drafts))
    for response, other_root in zip(responses, (roots[1][0], roots[0][0])):
        assert other_root not in response.text
    with wf.db.connect() as cx:
        saved = [json.loads(row["draft_json"]) for row in cx.execute(
            "SELECT draft_json FROM case_advance_drafts WHERE tenant = ?", (TENANT,)
        )]
    assert sum(item.get("activity_link_status") == "LINKED" for item in saved) == 1
    assert int(wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE tenant = ?", (TENANT,))["n"]) == 0


async def test_completed_voucher_and_accountant_link_accept_a_proposed_activity(
    fixture,
) -> None:
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    employee_session = wf.start_session(
        tenant=TENANT, persona="employee", actor_id="employee:employee-a"
    )
    created = await wf.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:new-proposed-advance-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:advance-acceptance-test",
                name="Tiếp khách đối tác",
                occurred_at="2026-10-10T09:00:00+07:00",
                declared_purpose="Làm việc với đối tác tại Hà Nội",
            )
        ),
    )
    root = created.case_view.id
    settlement_attachment = await client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("settlement.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:proposed-settlement-source",
            "X-Expected-Version": str(created.case_view.version),
        },
    )
    assert settlement_attachment.status_code == 200, settlement_attachment.text
    settlement_source = settlement_attachment.json()["case_view"]["sources"][0]
    settlement_ref = EvidenceRef(
        source_id=settlement_source["id"],
        source_sha256=settlement_source["digest"],
        page=1,
        exact_quote="Mã hồ sơ REF-OTHER",
    )
    settlement_report = ReadResult(
        documents=(
            DocumentAnalysis(
                source_id=settlement_source["id"],
                document_id="settlement:proposed-reference",
                document_type="SETTLEMENT_FORM",
                fields=(
                    FieldCandidate(
                        field="advance_reference",
                        state="FOUND",
                        value="REF-OTHER",
                        refs=(settlement_ref,),
                    ),
                ),
                confidence_status="ASSESSED",
                profile_status="CLEAR",
            ),
        )
    )
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_evidence_reports (root_id, tenant, report_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (root, TENANT, settlement_report.model_dump_json(), wf._now_iso()),
        )
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:proposed-advance-read",
            "X-Expected-Version": str(settlement_attachment.json()["case_view"]["version"]),
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_result = draft_response.json()
    draft = draft_result["draft"]
    case_view = draft_result["case_view"]

    recorded = await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:proposed-advance-record",
            "X-Expected-Version": str(case_view["version"]),
        },
        json={
            "money": {
                "external_key": "transfer:FT-1",
                "claimed_kind": "ADVANCE_RECEIVED",
                "claimed_scope": case_view["activity"],
                "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "payee": "NGUYỄN MINH AN",
                "amount": 4_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "completion_claim": "Kế toán đã kiểm tra chứng từ ứng hoàn tất.",
                "reason": "Đối chiếu phiếu ứng với hồ sơ tiếp khách đối tác.",
                "instrument_method": "TRANSFER",
                "instrument_status": "COMPLETED",
                "instrument_reference": "FT-1",
                "refs": draft["refs"],
                "advance_draft_id": draft["draft_id"],
                "activity_link_confirmed": True,
                "activity_link_reason": "Đã đối chiếu mã tham chiếu trên hai chứng từ cùng hồ sơ.",
            }
        },
    )

    assert recorded.status_code == 200, recorded.text
    updated = recorded.json()["case_view"]
    with wf.db.connect() as cx:
        event = cx.execute(
            "SELECT verification_state, allocation_state, payload_json FROM money_events "
            "WHERE tenant = ? AND root_id = ? AND external_key = ?",
            (TENANT, root, "transfer:FT-1"),
        ).fetchone()
        stored_draft = cx.execute(
            "SELECT draft_json, report_json FROM case_advance_drafts WHERE root_id = ?",
            (root,),
        ).fetchone()
        from datetime import UTC, datetime
        from invoice_referee.workflow.evidence_assessment import build_evidence_assessment_input

        assessment = build_evidence_assessment_input(
            cx,
            tenant=TENANT,
            root_id=root,
            report=ReadResult(),
            as_of=datetime.now(UTC),
        )
    assert event["verification_state"] == "CONFIRMED", dict(event)
    assert event["allocation_state"] == "ALLOCATED", dict(event)
    stored_report = ReadResult.model_validate_json(stored_draft["report_json"])
    assert len(updated["activity_acceptances"]) == 1, (
        stored_report.documents[0].profile_status,
        event["payload_json"],
    )
    acceptance = updated["activity_acceptances"][0]
    assert acceptance["activity"] == case_view["activity"]
    assert acceptance["employee"] == "employee:employee-a"
    assert acceptance["actor"] == ACCOUNTANT
    assert acceptance["link_basis"] == "ACCOUNTANT_CONFIRMATION"
    assert {ref["source_id"] for ref in acceptance["refs"]} >= {
        settlement_source["id"],
        draft["source_id"],
    }
    assert wf._query_one(
        "SELECT status FROM context_activities WHERE tenant = ? AND activity_id = ?",
        (TENANT, case_view["activity"]),
    )["status"] == "PROPOSED"
    assert not any(
        issue.field_or_rule == "activity:acceptance"
        for issue in assessment.admission_issues
    )


async def test_pending_advance_does_not_accept_the_proposed_activity(fixture) -> None:
    # A pending source remains observable but must never establish actual A or
    # work acceptance, even when the accountant confirms its activity link.
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    employee_session = wf.start_session(
        tenant=TENANT, persona="employee", actor_id="employee:employee-a"
    )
    created = await wf.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:new-pending-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:pending-advance-test",
                name="Tiếp khách đang xử lý",
                occurred_at="2026-10-10T09:00:00+07:00",
                declared_purpose="Làm việc với đối tác tại Hà Nội",
            )
        ),
    )
    root = created.case_view.id
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("pending-advance.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:pending-advance-read", "X-Expected-Version": str(created.case_view.version)},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_result = draft_response.json()
    draft = draft_result["draft"]
    case_view = draft_result["case_view"]
    response = await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:pending-advance-record",
            "X-Expected-Version": str(case_view["version"]),
        },
        json={
            "money": {
                "external_key": "transfer:FT-1",
                "claimed_kind": "ADVANCE_RECEIVED",
                "claimed_scope": case_view["activity"],
                "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "payee": "NGUYỄN MINH AN",
                "amount": 4_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "completion_claim": "Kế toán đã kiểm tra trạng thái chứng từ.",
                "reason": "Chứng từ ghi đang xử lý.",
                "instrument_method": "TRANSFER",
                "instrument_status": "PENDING",
                "instrument_reference": "FT-1",
                "refs": draft["refs"],
                "advance_draft_id": draft["draft_id"],
                "activity_link_confirmed": True,
                "activity_link_reason": "Đối chiếu nội dung phiếu với đúng hồ sơ đang xử lý.",
            }
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()["case_view"]
    assert updated["actual_money"]["A"]["state"] == "UNKNOWN"
    assert updated["activity_acceptances"] == []


async def test_explicit_reference_to_another_activity_cannot_be_overridden(fixture) -> None:
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO context_activities (activity_id, tenant, name, occurred_at, "
            "purpose, budget_amount, budget_effect_from, status, profile, references_json) "
            "VALUES (?, ?, ?, ?, ?, NULL, NULL, 'AUTHORIZED', 'WORK_EXPENSE', ?)",
            (
                "activity:other-advance-owner",
                TENANT,
                "Công việc trong hồ sơ khác",
                "2026-10-05T09:00:00+07:00",
                "Công việc khác của Nguyễn An",
                '["REF-OTHER"]',
            ),
        )
    employee_session = wf.start_session(
        tenant=TENANT, persona="employee", actor_id="employee:employee-a"
    )
    created = await wf.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:new-reference-conflict-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:current-advance-case",
                name="Công việc hiện tại",
                occurred_at="2026-10-10T09:00:00+07:00",
                declared_purpose="Công việc tiếp khách",
            )
        ),
    )
    root = created.case_view.id
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:reference-conflict-read",
            "X-Expected-Version": str(created.case_view.version),
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_result = draft_response.json()
    assert draft_result["draft"]["activity_reference"] == "REF-OTHER"
    assert draft_result["draft"]["activity_link_status"] == "CONFLICT"
    assert draft_result["draft"]["matched_activity_id"] is None
    assert "activity:other-advance-owner" not in draft_response.text
    draft = draft_result["draft"]
    case_view = draft_result["case_view"]

    response = await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:reference-conflict-record",
            "X-Expected-Version": str(case_view["version"]),
        },
        json={
            "money": {
                "external_key": "transfer:FT-1",
                "claimed_kind": "ADVANCE_RECEIVED",
                "claimed_scope": case_view["activity"],
                "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "payee": "NGUYỄN MINH AN",
                "amount": 4_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "completion_claim": "Kế toán đã kiểm tra giao dịch hoàn tất.",
                "reason": "Chứng từ đang được kiểm tra liên kết.",
                "instrument_method": "TRANSFER",
                "instrument_status": "COMPLETED",
                "instrument_reference": "FT-1",
                "refs": draft["refs"],
                "advance_draft_id": draft["draft_id"],
                "activity_link_confirmed": True,
                "activity_link_reason": "Tôi xác nhận đây là công việc hiện tại.",
            }
        },
    )
    assert response.status_code == 409, response.text
    assert int(wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (root,))["n"]) == 0


@pytest.mark.parametrize("explain", [True, False])
async def test_accountant_can_correct_a_missing_party_field_from_the_saved_source(
    fixture, explain: bool,
) -> None:
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    wf.enable_evidence_read(
        reader=_Reader(),
        classifier=_Classifier(missing_payer=True),
        artifacts_root=Path(".runtime/test-missing-payer-artifacts"),
    )
    employee_session = wf.start_session(
        tenant=TENANT, persona="employee", actor_id="employee:employee-a"
    )
    created = await wf.execute(
        CommandContext(
            session_id=employee_session.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:missing-payer-case",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:missing-payer-case",
                name="Tiếp khách",
                occurred_at="2026-10-10T09:00:00+07:00",
                declared_purpose="Làm việc với đối tác",
            )
        ),
    )
    root = created.case_view.id
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:missing-payer-read", "X-Expected-Version": str(created.case_view.version)},
    )
    assert draft_response.status_code == 200, draft_response.text
    result = draft_response.json()
    draft = result["draft"]
    assert draft["payer_name"] is None
    assert "payer_name" in draft["missing_fields"]

    recorded = await client.post(
        f"/api/cases/{root}/actuals",
        headers={"X-Command-Id": "cmd:missing-payer-record", "X-Expected-Version": str(result["case_view"]["version"])},
        json={
            "money": {
                "external_key": "transfer:FT-1",
                "claimed_kind": "ADVANCE_RECEIVED",
                "claimed_scope": result["case_view"]["activity"],
                "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
                "payee": "NGUYỄN MINH AN",
                "amount": 4_000_000,
                "event_at": "2026-10-05T09:00:00+07:00",
                "reason": "Đã kiểm tra bên chi trên bản gốc đính kèm." if explain else "",
                "instrument_method": "TRANSFER",
                "instrument_status": "COMPLETED",
                "instrument_reference": "FT-1",
                "refs": draft["refs"],
                "advance_draft_id": draft["draft_id"],
                "activity_link_confirmed": True,
                "activity_link_reason": "Đối chiếu công việc và bổ sung bên chi từ chứng từ gốc." if explain else "",
            }
        },
    )
    if not explain:
        assert recorded.status_code == 400, recorded.text
        assert wf._query_one("SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (root,))["n"] == 0
        return
    assert recorded.status_code == 200, recorded.text
    with wf.db.connect() as cx:
        source_report = cx.execute(
            "SELECT report_json FROM case_advance_drafts WHERE root_id = ?", (root,)
        ).fetchone()
        recorded_event = cx.execute(
            "SELECT verification_state, allocation_state FROM money_events WHERE root_id = ?",
            (root,),
        ).fetchone()
    parsed = ReadResult.model_validate_json(source_report["report_json"])
    assert len(recorded.json()["case_view"]["activity_acceptances"]) == 1, (
        parsed.documents[0].profile_status,
        parsed.documents[0].confidence_status,
        [item.model_dump() for item in parsed.documents[0].profile_findings],
        dict(recorded_event),
    )


async def test_manual_activity_acceptance_keeps_settlement_and_advance_source_refs(fixture) -> None:
    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft

    client, wf, _ = fixture
    employee = wf.start_session(tenant=TENANT, persona="employee", actor_id="employee:employee-a")
    created = await wf.execute(
        CommandContext(
            session_id=employee.session_id,
            actor_id="employee:employee-a",
            command_id="cmd:manual-link-source-case",
            expected_case_version=0,
        ),
        CreateDraft(activity_data=ActivityData(
            activity_id="activity:proposed:manual-link-source",
            name="Tiếp khách đối tác",
            occurred_at="2026-10-10T09:00:00+07:00",
            declared_purpose="Làm việc với đối tác tại Hà Nội",
        )),
    )
    root = created.case_view.id
    attached = await client.post(
        f"/api/cases/{root}/sources",
        files={"files": ("settlement.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:manual-link-settlement-source",
            "X-Expected-Version": str(created.case_view.version),
        },
    )
    assert attached.status_code == 200, attached.text
    source = attached.json()["case_view"]["sources"][0]
    settlement_ref = EvidenceRef(
        source_id=source["id"],
        source_sha256=source["digest"],
        page=1,
        exact_quote="Về việc: Tiếp khách đối tác",
    )
    employee_ref = EvidenceRef(
        source_id=source["id"],
        source_sha256=source["digest"],
        page=1,
        exact_quote="Người đề nghị: NGUYỄN MINH AN",
    )
    report = ReadResult(documents=(DocumentAnalysis(
        source_id=source["id"],
        document_id="settlement:manual-link-source",
        document_type="SETTLEMENT_FORM",
        fields=(
            FieldCandidate(field="purpose", state="FOUND", value="Tiếp khách đối tác", refs=(settlement_ref,)),
            FieldCandidate(field="declared_name", state="FOUND", value="NGUYỄN MINH AN", refs=(employee_ref,)),
        ),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    ),))
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_evidence_reports (root_id, tenant, report_json, created_at) "
            "VALUES (?, ?, ?, ?)",
            (root, TENANT, report.model_dump_json(), wf._now_iso()),
        )
    draft_response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("advance.pdf", PDF, "application/pdf")},
        headers={
            "X-Command-Id": "cmd:manual-link-advance-read",
            "X-Expected-Version": str(attached.json()["case_view"]["version"]),
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_result = draft_response.json()
    draft = draft_result["draft"]
    recorded = await client.post(
        f"/api/cases/{root}/actuals",
        headers={
            "X-Command-Id": "cmd:manual-link-advance-record",
            "X-Expected-Version": str(draft_result["case_view"]["version"]),
        },
        json={"money": {
            "external_key": "transfer:FT-1",
            "claimed_kind": "ADVANCE_RECEIVED",
            "claimed_scope": draft_result["case_view"]["activity"],
            "payer": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
            "payee": "NGUYỄN MINH AN",
            "amount": 4_000_000,
            "event_at": "2026-10-05",
            "completion_claim": "Đã đối chiếu chứng từ ứng hoàn tất.",
            "reason": "Đã đọc giấy quyết toán và chứng từ ứng cùng hồ sơ.",
            "instrument_method": "TRANSFER",
            "instrument_status": "COMPLETED",
            "instrument_reference": "FT-1",
            "refs": draft["refs"],
            "advance_draft_id": draft["draft_id"],
            "activity_link_confirmed": True,
            "activity_link_reason": "Nội dung tiếp khách và người đề nghị khớp với hồ sơ này.",
        }},
    )
    assert recorded.status_code == 200, recorded.text
    acceptance = recorded.json()["case_view"]["activity_acceptances"][0]
    refs = acceptance["refs"]
    assert any(ref["source_id"] == source["id"] and ref["exact_quote"] == settlement_ref.exact_quote for ref in refs)
    assert any(ref["source_id"] == draft["source_id"] for ref in refs)
