"""W2/W3: the draft is read through OCR and reused on submit (no re-OCR).

The draft endpoint runs the §12 pipeline (not pypdf+regex). On submit, if the
sources are unchanged, the stored report is assessed without a second OCR/LLM
call. A provider failure surfaces as an error, never a fabricated draft.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData, AttachSources, CreateDraft, Declaration, SourceUpload, Submit
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import (
    DocumentAnalysis, DocumentLine, FieldCandidate, OcrPage, OcrSourceResult,
)
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:demo"
ACTOR = "employee:employee-a"
ACTIVITY = "activity:tc01"
SHA = "a" * 64
PDF = b"%PDF-1.4\n%tc01\n"


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


class _CountingReader:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def read_source(self, source, *, budget, artifacts, source_bytes, expected_pages=None, root_id=""):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider down")
        if (source.filename or "").startswith("report"):
            markdown = (
                "GIẤY ĐỀ NGHỊ HOÀN ỨNG\nNgười đề nghị: NGUYỄN MINH AN\n"
                "Nội dung: Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026\n"
                "STT\n1\n00000101\n3.240.000\n4.000.000"
            )
        else:
            markdown = "HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nSố: 00000101\nMINH PHÁT\nNgày 10/10/2026\nTổng cộng thanh toán 3.240.000"
        return OcrSourceResult(
            source_id=source.id, source_digest=source.digest, provider="fake", model="fake",
            pages=(OcrPage(page=1, markdown=markdown),),
        )


class _Classifier:
    async def complete_json(self, *, system, user, budget):
        if "classify" in system.lower():
            docs = json.loads(user)["documents"]
            return {"documents": [
                {"source_id": d["source_id"], "page_range": [1, 1],
                 "document_type": ("SETTLEMENT_FORM" if "HOÀN ỨNG" in d["pages"][0]["markdown"] else "E_INVOICE"),
                 "roles": ["SETTLEMENT_DECLARATION" if "HOÀN ỨNG" in d["pages"][0]["markdown"] else "ORIGINAL_EXPENSE_EVIDENCE"],
                 "classification_confidence": 0.9}
                for d in docs
            ]}
        if "line_items" in system or "TABLE ROWS" in system:
            md = json.loads(user)["pages"][0]["markdown"]
            if "HOÀN ỨNG" in md:
                return {"fields": [
                    {"field": "declared_name", "state": "FOUND", "value": "NGUYỄN MINH AN", "quote": "NGUYỄN MINH AN", "page": 1},
                    {"field": "purpose", "state": "FOUND", "value": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "quote": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "page": 1},
                    {"field": "printed_total", "state": "FOUND", "value": "3.240.000", "quote": "3.240.000", "page": 1},
                    {"field": "declared_advance", "state": "FOUND", "value": "4.000.000", "quote": "4.000.000", "page": 1},
                ], "line_items": [{"fields": [
                    {"field": "description", "state": "FOUND", "value": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "quote": "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026", "page": 1},
                    {"field": "amount", "state": "FOUND", "value": "3.240.000", "quote": "3.240.000", "page": 1},
                    {"field": "invoice_refs", "state": "FOUND", "value": ["00000101"], "quote": "00000101", "page": 1},
                ]}]}
            return {"fields": [
                {"field": "document_number", "state": "FOUND", "value": "00000101", "quote": "00000101", "page": 1},
                {"field": "issuer_name", "state": "FOUND", "value": "MINH PHÁT", "quote": "MINH PHÁT", "page": 1},
                {"field": "total_amount", "state": "FOUND", "value": "3.240.000", "quote": "3.240.000", "page": 1},
                {"field": "document_date", "state": "FOUND", "value": "10/10/2026", "quote": "10/10/2026", "page": 1},
            ], "line_items": []}
        return {"assessments": []}


def _context() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "tenant": TENANT, "profile": "WORK_EXPENSE", "company_name": "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
        "activity": {"activity_id": ACTIVITY, "name": "Tiếp khách dự án", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "Chi phí tiếp khách", "profile": "WORK_EXPENSE",
                     "authorization": {"id": "auth:tc01", "actor": "employee:approver", "grant_ref": "grant:tc01:approver", "effect_range": interval, "reason": "x", "record_key": "auth:tc01"}},
        "people": ({"id": ACTOR, "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "budget:tc01", "activity": ACTIVITY, "amount": 8_000_000, "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"], "scope": ACTIVITY, "max_amount": 8_000_000, "effective_from": interval[0], "effective_to": interval[1]},
            {"id": "g:i", "version": "v1", "actor": "system:referee", "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": ACTIVITY, "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED", "scope": ACTIVITY, "payer": "company:demo", "payee": ACTOR, "amount": 4_000_000, "event_at": "2026-10-05T09:00:00+07:00", "recorded_at": "2026-10-05T10:00:00+07:00", "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"activity": ACTIVITY, "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00", "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"], "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1", "witness_keys": ["cov:1"]},
    }))


def _workflow(tmp_path: Path, reader) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads")
    wf.enable_evidence_read(reader=reader, classifier=_Classifier(), artifacts_root=tmp_path / "a")
    wf.import_company_context(_context(), origin="SIMULATED")
    return wf


async def _case_with_sources(wf: CaseWorkflow) -> str:
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=ACTIVITY, name="Tiếp khách", occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="x")),
    )
    root = created.case_view.id
    import hashlib

    uploads = []
    for name in ("report_hoan_ung.pdf", "hoa_don_dien_tu.pdf"):
        payload = PDF + name.encode()
        uploads.append(SourceUpload(filename=name, media="PDF", digest=hashlib.sha256(payload).hexdigest(), storage_key=f"{TENANT}/{root}/{name}"))
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="c2", expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=tuple(uploads)),
    )
    return root


async def test_draft_uses_ocr_pipeline(tmp_path: Path) -> None:
    reader = _CountingReader()
    wf = _workflow(tmp_path, reader)
    root = await _case_with_sources(wf)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    draft = await wf.read_settlement_draft(
        session, root,
        (("report_hoan_ung.pdf", "PDF", PDF + b"report_hoan_ung.pdf"),
         ("hoa_don_dien_tu.pdf", "PDF", PDF + b"hoa_don_dien_tu.pdf")),
    )
    assert reader.calls == 2, "both documents must go through OCR"
    assert draft["declared_name"] == "NGUYỄN MINH AN"
    assert draft["incurred_total"] == 3_240_000
    assert draft["declared_advance"] == 4_000_000
    assert draft["expenses"][0]["invoice_no"] == "00000101"
    assert draft["destination"] is None  # no invented Hà Nội trip


async def test_submit_reuses_the_draft_report_without_second_ocr(tmp_path: Path) -> None:
    reader = _CountingReader()
    wf = _workflow(tmp_path, reader)
    root = await _case_with_sources(wf)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    await wf.read_settlement_draft(
        session, root,
        (("report_hoan_ung.pdf", "PDF", PDF + b"report_hoan_ung.pdf"),
         ("hoa_don_dien_tu.pdf", "PDF", PDF + b"hoa_don_dien_tu.pdf")),
    )
    assert reader.calls == 2
    version = wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="submit", expected_case_version=int(version)),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="x")),
    )
    assert reader.calls == 2, "submit must reuse the stored report, not re-OCR"
    view = wf.view(CommandContext(session_id=session.session_id, actor_id=ACTOR, command_id="v", expected_case_version=0), root)
    assert view.state == "WAITING"



async def test_provider_failure_raises_not_a_fake_draft(tmp_path: Path) -> None:
    reader = _CountingReader(fail=True)
    wf = _workflow(tmp_path, reader)
    root = await _case_with_sources(wf)
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=ACTOR)
    with pytest.raises(Exception):
        await wf.read_settlement_draft(session, root, (("report_hoan_ung.pdf", "PDF", PDF),))
