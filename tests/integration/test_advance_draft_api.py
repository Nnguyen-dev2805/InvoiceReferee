"""D: the "record advance received" draft endpoint reads an uploaded document.

The accountant uploads a transfer receipt / cash voucher; the endpoint runs the
evidence pipeline and returns a prefilled DRAFT. It is a READ: no money is
recorded and no case version changes. The client cannot set the actor/scope.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate, OcrPage, OcrSourceResult
from invoice_referee.domain.common import EvidenceRef
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


class _Reader:
    """A fake reader returning one transfer-receipt page."""

    async def read_source(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
        return OcrSourceResult(
            source_id=source.id, source_digest=source.digest, provider="fake", model="fake",
            pages=(OcrPage(page=1, markdown="BIÊN NHẬN CHUYỂN KHOẢN\nSố tiền 4.000.000 đ\nTrạng thái Hoàn tất\nBên nhận Nguyễn An\nMã giao dịch FT-1\nNgân hàng Demo"),),
        )


class _Classifier:
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
            return {"fields": [
                {"field": "transaction_reference", "state": "FOUND", "value": "FT-1", "quote": "FT-1", "page": 1},
                {"field": "transaction_status", "state": "FOUND", "value": "Hoàn tất", "quote": "Hoàn tất", "page": 1},
                {"field": "payee_name", "state": "FOUND", "value": "Nguyễn An", "quote": "Nguyễn An", "page": 1},
                {"field": "payer_name", "state": "FOUND", "value": "Công ty InvoiceReferee", "quote": "BIÊN NHẬN", "page": 1},
                {"field": "amount", "state": "FOUND", "value": "4.000.000 đ", "quote": "4.000.000 đ", "page": 1},
                {"field": "payment_provider", "state": "FOUND", "value": "Ngân hàng Demo", "quote": "Ngân hàng Demo", "page": 1},
            ], "line_items": []}
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


async def test_advance_draft_prefills_from_the_uploaded_document(fixture) -> None:
    client, wf, root = fixture
    response = await client.post(
        f"/api/cases/{root}/advance/draft?method=TRANSFER",
        files={"files": ("03-bien-nhan-chuyen-khoan.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:adv"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == 4_000_000
    assert body["payee_name"] == "Nguyễn An"
    assert body["transaction_reference"] == "FT-1"
    assert body["instrument_status"] == "COMPLETED"
    assert body["requires_confirmation"] is True


async def test_advance_draft_does_not_record_money(fixture) -> None:
    client, wf, root = fixture
    before = wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"]
    await client.post(
        f"/api/cases/{root}/advance/draft",
        files={"files": ("x.pdf", PDF, "application/pdf")},
        headers={"X-Command-Id": "cmd:adv2"},
    )
    after = wf._query_one("SELECT COUNT(*) AS n FROM money_events")["n"]
    assert int(after) == int(before) == 0
