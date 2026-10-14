"""A5 evidence->finance consumer wiring tests (plan A5).

After the evidence worker publishes a typed report, the workflow must assess it
through the pure admission mapper + Reconciler, with the same atomic
version/Stop protection as the STUB path. A missing report stays EVIDENCE_READY
(never a seeded STUB transcription in LIVE/REPLAY).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from invoice_referee.domain.documents import DocumentAnalysis, DocumentLine, FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

TENANT = "tenant:uc03-pilot"
EMPLOYEE = "employee:employee-a"
ACTIVITY = "activity:uc03-f01"
PILOT = Path(__file__).resolve().parents[2] / "data" / "test-kit" / "uc03-pilot" / "f01-cong-tac-thu-lai-tien-thua"
SHA = "a" * 64


def _ref(quote: str = "x") -> EvidenceRef:
    return EvidenceRef(source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote)


def _uploaded_ref() -> EvidenceRef:
    import hashlib

    return EvidenceRef(
        source_id="file:hd.pdf", source_sha256=hashlib.sha256(b"pdf").hexdigest(),
        page=1, exact_quote="3.240.000 đ",
    )


def _found(name: str, value: object) -> FieldCandidate:
    return FieldCandidate(field=name, state="FOUND", value=value, refs=(_ref(),))  # type: ignore[arg-type]


def _report() -> ReadResult:
    paper = DocumentAnalysis(
        source_id="source:1", document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(_found("declared_name", "Nguyễn An"), _found("printed_total", "3240000")),
        line_items=(DocumentLine(id="row:1", fields=(
            _found("description", "Bữa ăn"), _found("amount", "3240000"), _found("invoice_refs", ("IR26101001",)),
        )),),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoice = DocumentAnalysis(
        source_id="source:2", document_id="source:2:1-1:E_INVOICE",
        document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
        fields=(_found("document_number", "IR26101001"), _found("issuer_name", "An Bình"), _found("total_amount", "3240000")),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, invoice))


# The pilot's historical decision instant (2026-10-10T18:00+07:00 == 11:00 UTC);
# the harness clock is pinned to it so the context coverage is valid at the
# decision time (plan A3/C: controlled clock).
PILOT_CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def _workflow(tmp_path: Path) -> CaseWorkflow:
    db = Database(tmp_path / "app.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "uploads", clock=lambda: PILOT_CLOCK)
    # Wire the evidence pipeline (a sentinel reader is enough: the test only
    # needs `_evidence_reader is not None` to select the typed consumer).
    wf.enable_evidence_read(
        reader=object(), classifier=object(), artifacts_root=tmp_path / "artifacts"
    )
    from invoice_referee.domain.organization import OrganizationContext

    wf.import_company_context(
        OrganizationContext.model_validate_json((PILOT / "input" / "organization.json").read_text()),
        origin="SIMULATED",
    )
    return wf


async def _seed_case(wf: CaseWorkflow, *, state: str = "EVIDENCE_READY") -> str:
    import hashlib

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import ActivityData, CreateDraft, SourceUpload, AttachSources

    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    ctx = CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:1", expected_case_version=0)
    created = await wf.execute(ctx, CreateDraft(activity_data=ActivityData(
        activity_id=ACTIVITY, name="Công tác", occurred_at="2026-10-06T09:00:00+07:00", declared_purpose="Công tác",
    )))
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:2", expected_case_version=created.case_view.version),
        AttachSources(root_id=root, uploads=(SourceUpload(filename="hd.pdf", media="PDF", digest=digest, storage_key=f"{TENANT}/{root}/hd.pdf"),)),
    )
    with wf.db.transaction() as cx:
        cx.execute("UPDATE cases SET state = ?, version = version + 1 WHERE id = ?", (state, root))
    return root


def _publish(wf: CaseWorkflow, root: str) -> None:
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx, tenant=TENANT, root_id=root, report=_report())


async def _admit_and_commit(wf: CaseWorkflow, root: str) -> None:
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        session = wf.session(cx.execute("SELECT session_id FROM demo_sessions LIMIT 1").fetchone()[0])
        wf._assess_and_commit(cx, session, row, wf._now_iso())


async def test_published_report_reaches_exact_effects(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    _publish(wf, root)
    # A Q32 claim matching the pilot invoice.
    from invoice_referee.domain.commands import Declaration, EmployeePaidClaim, Submit

    session_id = wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"]
    from invoice_referee.domain.case import CommandContext

    await wf.execute(
        CommandContext(session_id=str(session_id), actor_id=EMPLOYEE, command_id="cmd:claim", expected_case_version=wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="Công tác"),
               employee_paid_claims=(EmployeePaidClaim(invoice_reference="IR26101001", amount=3_240_000, refs=(_uploaded_ref(),), reason="đã trả"),)),
    )
    await _admit_and_commit(wf, root)
    with wf.db.transaction() as cx:
        case = cx.execute("SELECT state FROM cases WHERE id = ?", (root,)).fetchone()
        inst = cx.execute("SELECT direction, amount FROM instructions WHERE root_id = ?", (root,)).fetchall()
    assert case["state"] == "READY_TO_EXECUTE"
    assert [(i["direction"], int(i["amount"])) for i in inst] == [("COLLECT", 760_000)]


async def test_missing_report_stays_evidence_ready(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    await _admit_and_commit(wf, root)
    with wf.db.transaction() as cx:
        case = cx.execute("SELECT state FROM cases WHERE id = ?", (root,)).fetchone()
        inst = cx.execute("SELECT COUNT(*) AS n FROM instructions WHERE root_id = ?", (root,)).fetchone()
    assert case["state"] == "EVIDENCE_READY"
    assert int(inst["n"]) == 0


async def test_stop_before_commit_writes_no_instruction(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _seed_case(wf, state="STOPPED")
    _publish(wf, root)
    await _admit_and_commit(wf, root)
    with wf.db.transaction() as cx:
        n = cx.execute("SELECT COUNT(*) AS n FROM instructions WHERE root_id = ?", (root,)).fetchone()
    assert int(n["n"]) == 0


async def test_workflow_clock_reaches_admission_as_of(tmp_path: Path) -> None:
    # The assessment time must come from the workflow clock (server/harness),
    # not datetime.now, so coverage freshness and every gate use the same
    # instant.
    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    _publish(wf, root)
    captured: dict[str, object] = {}

    import invoice_referee.workflow.evidence_assessment as ea

    real = ea.build_evidence_assessment_input

    def spy(cx, **kwargs):
        captured["as_of"] = kwargs.get("as_of")
        return real(cx, **kwargs)

    ea.build_evidence_assessment_input = spy  # type: ignore[assignment]
    try:
        await _admit_and_commit(wf, root)
    finally:
        ea.build_evidence_assessment_input = real  # type: ignore[assignment]
    assert captured.get("as_of") == PILOT_CLOCK


async def test_stale_context_coverage_blocks_the_effect(tmp_path: Path) -> None:
    # A clock AFTER the context coverage (through 10/10) must not issue an
    # instruction: the coverage is stale for that decision time (contract §3).
    from datetime import UTC, datetime

    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    _publish(wf, root)
    wf._clock = lambda: datetime(2026, 10, 14, 11, 0, tzinfo=UTC)
    from invoice_referee.domain.commands import Declaration, EmployeePaidClaim, Submit

    session_id = wf._query_one("SELECT session_id FROM demo_sessions LIMIT 1")["session_id"]
    from invoice_referee.domain.case import CommandContext

    await wf.execute(
        CommandContext(session_id=str(session_id), actor_id=EMPLOYEE, command_id="cmd:claim",
                      expected_case_version=wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]),
        Submit(root_id=root, declaration=Declaration(activity_id=ACTIVITY, declared_purpose="Công tác"),
               employee_paid_claims=(EmployeePaidClaim(invoice_reference="IR26101001", amount=3_240_000, refs=(_uploaded_ref(),), reason="đã trả"),)),
    )
    await _admit_and_commit(wf, root)
    with wf.db.transaction() as cx:
        n = cx.execute("SELECT COUNT(*) AS n FROM instructions WHERE root_id = ?", (root,)).fetchone()
        issue = cx.execute("SELECT 1 FROM case_issues WHERE root_id = ? AND field_or_rule = 'ledger:coverage'", (root,)).fetchone()
    assert int(n["n"]) == 0
    assert issue is not None
