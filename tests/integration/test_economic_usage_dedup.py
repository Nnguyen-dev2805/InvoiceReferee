"""Economic usage/dedup over the LIVE (evidence) path, keyed by bound identity.

The dedup/usage consumer must see the SAME canonical identity the admission
produced for the document bound to each cost. Two roots in ONE tenant that claim
the same verified invoice must not both issue; a root claiming a DIFFERENT
invoice is legitimate supplementation and issues independently. This exercises
the real workflow commit, not just the key helper.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    SourceUpload,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:dedup"
EMPLOYEE = "employee:employee-a"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))
SHA = "a" * 64


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _org(activity: str) -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": activity, "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": EMPLOYEE, "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": f"b:{activity}", "activity": activity, "amount": 20_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": f"g:r:{activity}", "version": "v1", "actor": "system:referee",
             "actions": ["RECOGNIZE_COST"], "scope": activity, "max_amount": 8_000_000,
             "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": f"g:i:{activity}", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": activity,
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": (),
        "coverage": {"employee": EMPLOYEE, "activity": activity,
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _report(invoice_number: str, amount: int) -> ReadResult:
    paper = DocumentAnalysis(
        source_id="s0", document_id="s0:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Hoàn ứng"),
                _found("printed_total", str(amount))),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Vật tư"), _found("amount", str(amount)),
            _found("invoice_refs", (invoice_number,)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", invoice_number), _found("issuer_name", "NHÀ CUNG CẤP"),
                _found("buyer_name", COMPANY), _found("total_amount", str(amount)),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


async def _new_root(wf: CaseWorkflow, *, activity: str, invoice_number: str, amount: int) -> str:
    wf.import_company_context(_org(activity), origin="SIMULATED")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE,
                       command_id=f"c1:{activity}", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id=activity, name="a",
                                               occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    digest = hashlib.sha256(activity.encode()).hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id=f"c2:{activity}",
                       expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(
            filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{TENANT}/{root}/hd.pdf"),)),
    )
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=_report(invoice_number, amount))
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    return root


def _view(wf: CaseWorkflow, root: str):
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        return wf._case_view(cx, row)


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "dedup.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "art")
    return wf


async def test_second_root_with_same_invoice_is_not_issued(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    a = await _new_root(wf, activity="activity:dup-a", invoice_number="00002301", amount=3_240_000)
    b = await _new_root(wf, activity="activity:dup-b", invoice_number="00002301", amount=3_240_000)
    va, vb = _view(wf, a), _view(wf, b)
    assert [i.direction for i in va.instructions] == ["PAY"]
    assert vb.instructions == (), "the same verified obligation must not issue twice"
    with wf.db.transaction() as cx:
        owners = [r["owner_root"] for r in cx.execute("SELECT owner_root FROM usage_registry").fetchall()]
    assert len(owners) == 1


async def test_different_invoice_is_legitimate_supplementation(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    a = await _new_root(wf, activity="activity:supp-a", invoice_number="00002301", amount=3_240_000)
    b = await _new_root(wf, activity="activity:supp-b", invoice_number="00002302", amount=3_000_000)
    va, vb = _view(wf, a), _view(wf, b)
    assert [i.direction for i in va.instructions] == ["PAY"]
    assert [i.direction for i in vb.instructions] == ["PAY"], "a different invoice is its own obligation"
    with wf.db.transaction() as cx:
        keys = sorted(r["economic_key"] for r in cx.execute("SELECT economic_key FROM usage_registry").fetchall())
    assert len(keys) == 2 and keys[0] != keys[1]
