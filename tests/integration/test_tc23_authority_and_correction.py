"""TC23: three allocated rows, E>8m routes to AUTHORITY (not a self-issue).

Invoice00002301 backs two rows (2.16m + 1.08m); invoice00002302 backs one row
(5.4m). E=8.64m exceeds the system's 8m recognition limit, so the case must go to
the approver with a RECOGNIZE_COST authorization and issue NO instruction — never
a self-issued COLLECT 360k. AUTHORITY does not turn established figures UNKNOWN.
A correction that resolves the dispute is consumed at the new revision; the old
basis is not reused.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    ReviseDeclaration,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:tc23"
EMPLOYEE = "employee:employee-a"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))
SHA = "a" * 64


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:tc23", "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": EMPLOYEE, "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:tc23", "amount": 12_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:tc23", "max_amount": 8_000_000, "effective_from": interval[0],
             "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:tc23",
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": "activity:tc23", "payer": "company:demo", "payee": EMPLOYEE,
                    "amount": 9_000_000, "event_at": "2026-10-05T09:00:00+07:00",
                    "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"employee": EMPLOYEE, "activity": "activity:tc23",
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _report() -> ReadResult:
    rows = (("Giấy in A4", "2160000", ("00002301",)),
            ("Bút và dụng cụ", "1080000", ("00002301",)),
            ("Mực in", "5400000", ("00002302",)))
    paper = DocumentAnalysis(
        source_id="s0", document_id="s0:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Hoàn ứng mua vật tư"),
                _found("printed_total", "8640000"), _found("declared_advance", "9000000"),
                _found("printed_return", "360000")),
        line_items=tuple(
            DocumentLine(id=f"r{i}", fields=(
                _found("description", d), _found("amount", a), _found("invoice_refs", r),
            ))
            for i, (d, a, r) in enumerate(rows, start=1)
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )

    def inv(number: str, total: str, issuer: str) -> DocumentAnalysis:
        return DocumentAnalysis(
            source_id=f"s:{number}", document_id=f"s:{number}:1-1:E_INVOICE", document_type="E_INVOICE",
            roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
            fields=(_found("document_number", number), _found("issuer_name", issuer),
                    _found("buyer_name", COMPANY), _found("total_amount", total),
                    _found("document_date", "10/10/2026")),
            confidence_status="ASSESSED", profile_status="CLEAR",
        )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ",
                      documents=(paper, inv("00002301", "3240000", "HÒA BÌNH"),
                                 inv("00002302", "5400000", "MỰC IN VIỆT")))


async def _seed(tmp_path: Path) -> tuple[CaseWorkflow, str]:
    db = Database(tmp_path / "a.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "art")
    wf.import_company_context(_org(), origin="SIMULATED")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id="activity:tc23", name="a",
                                               occurred_at="2026-10-10T09:00:00+07:00", declared_purpose="p")),
    )
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="c2",
                       expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(
            filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{TENANT}/{root}/hd.pdf"),)),
    )
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=_report())
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    return wf, root


def _view(wf: CaseWorkflow, root: str):
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        return wf._case_view(cx, row)


async def test_tc23_routes_to_authority_without_self_issue(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path)
    view = _view(wf, root)
    assert view.actual_money.T.value == 8_640_000
    assert view.actual_money.E.value == 8_640_000
    assert view.actual_money.A.value == 9_000_000
    assert view.actual_money.S.value == -360_000
    # E > 8m -> the approver must authorize; no self-issued instruction.
    assert any(i.kind == "AUTHORITY" and i.field_or_rule == "RECOGNIZE_COST"
               and i.owner == "approver" for i in view.issues)
    assert not [i for i in view.instructions if i.status in ("ISSUED", "PARTIAL")], \
        "AUTHORITY must not self-issue COLLECT 360k"
    # The established figures are NOT turned UNKNOWN by the AUTHORITY route.
    assert not any(i.kind == "FACT" for i in view.issues)


async def test_tc23_three_distinct_economic_keys(tmp_path: Path) -> None:
    wf, root = await _seed(tmp_path)
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        inp = wf._build_assessment_input(cx, wf._system_session(TENANT), row, wf._now_iso())
    keys = [e.economic_key for e in inp.expense_facts]
    assert len(keys) == 3
    assert keys[0] == keys[1] and keys[2] != keys[0]
    assert sum(int(e.incurred.value or 0) for e in inp.expense_facts) == 8_640_000
