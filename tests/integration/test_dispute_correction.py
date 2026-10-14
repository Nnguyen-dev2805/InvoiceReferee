"""TC08 correction: a resolved dispute is consumed at the new revision.

A corrected/supplemental source changes the input basis, so the case is re-read
and re-assessed: the dispute FACT clears and the corrected figures are admitted.
A generic approval/EXCEPT_POLICY decision does NOT waive the dispute FACT — only a
new valid basis does. The stale read is not reused across the changed basis.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.case import CaseScope, CommandContext, ReadSet
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    SourceUpload,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.issues import DecisionCommand
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.domain.policy import ExceptionDecision
from invoice_referee.reconciliation.admission import admit_evidence
from invoice_referee.reconciliation.service import Reconciler
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:tc08"
EMPLOYEE = "employee:employee-a"
COMPANY = "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH"
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))
SHA = "a" * 64
AS_OF = datetime(2026, 10, 10, 11, 0, tzinfo=UTC)


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value,
                          refs=(EvidenceRef(source_id="s", source_sha256=SHA, page=1, exact_quote="x"),))  # type: ignore[arg-type]


def _org() -> OrganizationContext:
    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(json.dumps({
        "organization_id": TENANT, "profile": "WORK_EXPENSE", "company_name": COMPANY,
        "activity": {"activity_id": "activity:1", "name": "a", "occurred_at": "2026-10-10T09:00:00+07:00",
                     "purpose": "p", "profile": "WORK_EXPENSE", "authorization": {"id": "auth:1"}},
        "people": ({"id": EMPLOYEE, "name": "NGUYỄN MINH AN"},),
        "budgets": ({"id": "b:1", "activity": "activity:1", "amount": 8_000_000,
                     "effect_range": interval, "actor": "employee:approver"},),
        "grants": (
            {"id": "g:r", "version": "v1", "actor": "system:referee", "actions": ["RECOGNIZE_COST"],
             "scope": "activity:1", "max_amount": 8_000_000, "effective_from": interval[0],
             "effective_to": interval[1], "allowed_profiles": ["WORK_EXPENSE"]},
            {"id": "g:i", "version": "v1", "actor": "system:referee",
             "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"], "scope": "activity:1",
             "max_amount": 4_000_000, "effective_from": interval[0], "effective_to": interval[1],
             "allowed_profiles": ["WORK_EXPENSE"]},
        ),
        "ledger": ({"id": "adv:1", "external_key": "bank:ADV-1", "kind": "ADVANCE_RECEIVED",
                    "scope": "activity:1", "payer": "company:demo", "payee": EMPLOYEE,
                    "amount": 4_000_000, "event_at": "2026-10-05T09:00:00+07:00",
                    "recorded_at": "2026-10-05T10:00:00+07:00",
                    "verification_state": "CONFIRMED", "allocation_state": "ALLOCATED"},),
        "coverage": {"employee": EMPLOYEE, "activity": "activity:1",
                     "start": "2026-09-01T00:00:00+07:00", "as_of": "2026-10-10T18:00:00+07:00",
                     "fund_ids": ["company:bank"], "flow_kinds": ["ADVANCE_RECEIVED", "EMPLOYEE_RETURN"],
                     "opening_by_fund": {"company:bank": 0}, "ledger_version": "l:v1",
                     "witness_keys": ["cov:1"]},
    }))


def _report(*, paper_amount: str, invoice_total: str) -> ReadResult:
    paper = DocumentAnalysis(
        source_id="s1", document_id="s1:1-1:SETTLEMENT_FORM", document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("purpose", "Chi phí tiếp khách"),
                _found("declared_advance", "4000000"), _found("printed_total", paper_amount),
                _found("printed_return", "500000")),
        line_items=(DocumentLine(id="r1", fields=(
            _found("description", "Chi phí tiếp khách"), _found("amount", paper_amount),
            _found("invoice_refs", ("00000801",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="s2", document_id="s2:1-1:E_INVOICE", document_type="E_INVOICE",
        roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "00000801"), _found("issuer_name", "MINH PHÁT"),
                _found("buyer_name", COMPANY), _found("total_amount", invoice_total),
                _found("document_date", "10/10/2026")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


def _admit(report: ReadResult):
    return admit_evidence(
        report, scope=CaseScope(tenant=TENANT, employee=EMPLOYEE, activity="activity:1", profile="WORK_EXPENSE"),
        organization=_org(), confirmations=(), ledger=(), coverage=None,
        read_set=ReadSet(input_revision=1, control_epoch=0, context_version=1, ledger_version=1, usage_version=0),
        as_of=AS_OF,
    )


def test_generic_except_policy_does_not_waive_the_dispute_fact() -> None:
    inp = _admit(_report(paper_amount="3500000", invoice_total="3240000"))
    # A broad EXCEPT_POLICY decision (not bound to the dispute rule) must not clear
    # the dispute FACT; only a new valid basis does.
    inp = inp.model_copy(update={"exceptions": (
        ExceptionDecision(
            rule_id="expense:missing_required_evidence", expense_ids=("expense:1",),
            activity="activity:1", max_effect=1_000_000, actions=("EXCEPT_POLICY",),
            actor="employee:approver", grant_ref="g:approver",
            decided_at=AS_OF, effect_range=(datetime(2026, 10, 1, tzinfo=UTC), None),
            reason="chấp nhận chung",
        ),
    )})
    result = Reconciler().assess(inp)
    assert any("allocation" in i.field_or_rule for i in result.issues)
    assert result.allowed_effect is None


def test_corrected_basis_clears_the_dispute() -> None:
    # A corrected report (paper now agrees with the invoice) has no dispute FACT.
    corrected = _admit(_report(paper_amount="3240000", invoice_total="3240000"))
    result = Reconciler().assess(corrected)
    assert not any("allocation" in i.field_or_rule for i in result.issues)
    assert corrected.expense_facts[0].incurred.state == "KNOWN"
    assert corrected.expense_facts[0].eligibility == "ELIGIBLE"


async def _seed(tmp_path: Path, report: ReadResult) -> tuple[CaseWorkflow, str]:
    db = Database(tmp_path / "a.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.enable_evidence_read(reader=object(), classifier=object(), artifacts_root=tmp_path / "art")
    wf.import_company_context(_org(), origin="SIMULATED")
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="c1", expected_case_version=0),
        CreateDraft(activity_data=ActivityData(activity_id="activity:1", name="a",
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
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=report)
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    return wf, root


def _view(wf: CaseWorkflow, root: str):
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        return wf._case_view(cx, row)


async def test_new_revision_consumes_the_correction(tmp_path: Path) -> None:
    # Disputed basis first; a corrected report published at the next revision is
    # re-assessed and the dispute clears (the new revision is consumed).
    wf, root = await _seed(tmp_path, _report(paper_amount="3500000", invoice_total="3240000"))
    assert any("allocation" in i.field_or_rule for i in _view(wf, root).issues)

    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root,
                                    report=_report(paper_amount="3240000", invoice_total="3240000"))
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        wf._assess_and_commit(cx, wf._system_session(TENANT), row, wf._now_iso())
    after = _view(wf, root)
    assert not any("allocation" in i.field_or_rule for i in after.issues)
    assert after.actual_money.E.state == "KNOWN"
    assert after.actual_money.E.value == 3_240_000
