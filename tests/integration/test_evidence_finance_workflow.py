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
        fields=(_found("declared_name", "NGUYỄN MINH AN"), _found("printed_total", "3240000")),
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


def _invoice_ref(source_id: str, quote: str) -> EvidenceRef:
    return EvidenceRef(source_id=source_id, source_sha256=SHA, page=1, exact_quote=quote)


def _report_with_invoice_refs() -> ReadResult:
    report = _report()
    invoice = report.documents[1]
    fields = tuple(
        field.model_copy(update={"refs": (_invoice_ref(invoice.source_id, str(field.value)),)})
        for field in invoice.fields
    )
    return report.model_copy(
        update={
            "documents": (
                report.documents[0],
                invoice.model_copy(update={"fields": fields}),
            )
        }
    )


def _two_invoice_report() -> ReadResult:
    paper_ref = _invoice_ref("source:paper", "settlement")
    paper = DocumentAnalysis(
        source_id="source:paper", document_id="source:paper:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM", roles=("SETTLEMENT_DECLARATION",), page_range=(1, 1),
        fields=(FieldCandidate(field="declared_name", state="FOUND", value="NGUYỄN MINH AN", refs=(paper_ref,)),),
        line_items=(
            DocumentLine(id="row:a", fields=(
                FieldCandidate(field="description", state="FOUND", value="Khoản A", refs=(paper_ref,)),
                FieldCandidate(field="amount", state="FOUND", value="1000000", refs=(paper_ref,)),
                FieldCandidate(field="invoice_refs", state="FOUND", value=("IR-A",), refs=(paper_ref,)),
            )),
            DocumentLine(id="row:b", fields=(
                FieldCandidate(field="description", state="FOUND", value="Khoản B", refs=(paper_ref,)),
                FieldCandidate(field="amount", state="FOUND", value="2000000", refs=(paper_ref,)),
                FieldCandidate(field="invoice_refs", state="FOUND", value=("IR-B",), refs=(paper_ref,)),
            )),
        ),
        confidence_status="ASSESSED", profile_status="CLEAR",
    )
    invoices = tuple(
        DocumentAnalysis(
            source_id=f"source:{ref.lower()}", document_id=f"source:{ref.lower()}:1-1:E_INVOICE",
            document_type="E_INVOICE", roles=("ORIGINAL_EXPENSE_EVIDENCE",), page_range=(1, 1),
            fields=(
                FieldCandidate(field="document_number", state="FOUND", value=ref, refs=(_invoice_ref(f"source:{ref.lower()}", ref),)),
                FieldCandidate(field="issuer_name", state="FOUND", value="An Bình", refs=(_invoice_ref(f"source:{ref.lower()}", "issuer"),)),
                FieldCandidate(field="total_amount", state="FOUND", value=amount, refs=(_invoice_ref(f"source:{ref.lower()}", str(amount)),)),
            ),
            confidence_status="ASSESSED", profile_status="CLEAR",
        )
        for ref, amount in (("IR-A", "1000000"), ("IR-B", "2000000"))
    )
    return ReadResult(provider_mode="LIVE", data_origin="LIVE_READ", documents=(paper, *invoices))


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


def _publish(wf: CaseWorkflow, root: str, report: ReadResult | None = None) -> None:
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(
            cx, tenant=TENANT, root_id=root, report=report or _report()
        )


async def _admit_and_commit(wf: CaseWorkflow, root: str) -> None:
    with wf.db.transaction() as cx:
        row = cx.execute("SELECT * FROM cases WHERE id = ?", (root,)).fetchone()
        session = wf.session(cx.execute("SELECT session_id FROM demo_sessions LIMIT 1").fetchone()[0])
        wf._assess_and_commit(cx, session, row, wf._now_iso())


async def _live_payer_case(tmp_path: Path):
    from invoice_referee.domain.case import CommandContext

    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    _publish(wf, root, _report_with_invoice_refs())
    await _admit_and_commit(wf, root)
    cx = wf.db.connect()
    try:
        session_id = cx.execute(
            "SELECT session_id FROM demo_sessions WHERE tenant = ? LIMIT 1", (TENANT,)
        ).fetchone()["session_id"]
    finally:
        cx.close()
    session = wf.session(str(session_id))
    view = wf.view(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id="cmd:view",
            expected_case_version=0,
        ),
        root,
    )
    fact_key = "expense:IR26101001:employee_paid"
    issue = next(item for item in view.issues if item.field_or_rule == fact_key)
    return wf, root, session, view, issue


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


async def test_live_payer_answer_is_bound_to_invoice_amount_actor_and_activity(
    tmp_path: Path,
) -> None:
    import json

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.issues import Answer
    from invoice_referee.domain.commands import AnswerIssue

    wf, root, session, before, issue = await _live_payer_case(tmp_path)
    fact_key = "expense:IR26101001:employee_paid"

    result = await wf.execute(
        CommandContext(
            session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:answer-payer",
            expected_case_version=before.version,
        ),
        AnswerIssue(
            root_id=root,
            answer=Answer(
                issue_id=issue.id,
                basis_id=f"basis:{issue.id}",
                answer_kind="FACT",
                value=3_240_000,
                reason="Tôi trực tiếp thanh toán hóa đơn IR26101001.",
            ),
        ),
    )

    assert not any(item.field_or_rule == fact_key for item in result.case_view.issues)
    assert result.case_view.actual_money.E.state == "KNOWN"
    assert result.case_view.actual_money.E.value == 3_240_000
    assert [(basis.kind, basis.actor) for basis in result.case_view.payment_basis] == [
        ("EMPLOYEE_DECLARATION_Q32", EMPLOYEE)
    ]

    cx = wf.db.connect()
    try:
        confirmation = cx.execute(
            "SELECT fact_key, value, actor, scope, refs_json FROM case_confirmations "
            "WHERE root_id = ? AND fact_key = ?",
            (root, fact_key),
        ).fetchone()
    finally:
        cx.close()
    assert confirmation is not None
    assert confirmation["value"] == "3240000"
    assert confirmation["actor"] == EMPLOYEE
    assert confirmation["scope"] == ACTIVITY
    assert any(ref["source_id"] == "source:2" for ref in json.loads(confirmation["refs_json"]))


async def test_live_payer_answer_rejects_amount_above_invoice_total(tmp_path: Path) -> None:
    import pytest

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.domain.issues import Answer
    from invoice_referee.workflow.service import UnsupportedCommandError

    wf, root, session, before, issue = await _live_payer_case(tmp_path)
    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=session.session_id, actor_id=EMPLOYEE,
                command_id="cmd:answer-over-invoice", expected_case_version=before.version,
            ),
            AnswerIssue(
                root_id=root,
                answer=Answer(
                    issue_id=issue.id, basis_id=f"basis:{issue.id}", answer_kind="FACT",
                    value=3_240_001, reason="Xác nhận đã trả.",
                ),
            ),
        )
    cx = wf.db.connect()
    try:
        count = cx.execute(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchone()["n"]
    finally:
        cx.close()
    assert int(count) == 0


async def test_live_payer_answer_outside_q32_bounds_is_not_reported_as_success(
    tmp_path: Path,
) -> None:
    import pytest

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.domain.issues import Answer
    from invoice_referee.workflow.service import UnsupportedCommandError

    report = _report_with_invoice_refs()
    paper, invoice = report.documents
    paper_fields = tuple(
        field.model_copy(update={"value": "9000000"})
        if field.field == "printed_total"
        else field
        for field in paper.fields
    )
    line = paper.line_items[0]
    line_fields = tuple(
        field.model_copy(update={"value": "9000000"})
        if field.field == "amount"
        else field
        for field in line.fields
    )
    invoice_fields = tuple(
        field.model_copy(update={"value": "9000000"})
        if field.field == "total_amount"
        else field
        for field in invoice.fields
    )
    report = report.model_copy(
        update={
            "documents": (
                paper.model_copy(
                    update={
                        "fields": paper_fields,
                        "line_items": (line.model_copy(update={"fields": line_fields}),),
                    }
                ),
                invoice.model_copy(update={"fields": invoice_fields}),
            )
        }
    )
    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    _publish(wf, root, report)
    await _admit_and_commit(wf, root)
    cx = wf.db.connect()
    try:
        session_id = cx.execute(
            "SELECT session_id FROM demo_sessions WHERE tenant = ? LIMIT 1", (TENANT,)
        ).fetchone()["session_id"]
    finally:
        cx.close()
    session = wf.session(str(session_id))
    before = wf.view(
        CommandContext(
            session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:view",
            expected_case_version=0,
        ),
        root,
    )
    issue = next(
        item for item in before.issues
        if item.field_or_rule == "expense:IR26101001:employee_paid"
    )

    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=session.session_id, actor_id=EMPLOYEE,
                command_id="cmd:answer-over-q32", expected_case_version=before.version,
            ),
            AnswerIssue(
                root_id=root,
                answer=Answer(
                    issue_id=issue.id, basis_id=f"basis:{issue.id}", answer_kind="FACT",
                    value=9_000_000, reason="Tôi trực tiếp thanh toán hóa đơn IR26101001.",
                ),
            ),
        )
    cx = wf.db.connect()
    try:
        count = cx.execute(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchone()["n"]
    finally:
        cx.close()
    assert int(count) == 0


async def test_live_payer_answer_rejects_a_different_employee(tmp_path: Path) -> None:
    import pytest

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.domain.issues import Answer
    from invoice_referee.workflow.service import UnsupportedCommandError

    wf, root, session, before, issue = await _live_payer_case(tmp_path)
    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=session.session_id, actor_id="employee:other",
                command_id="cmd:answer-other-employee", expected_case_version=before.version,
            ),
            AnswerIssue(
                root_id=root,
                answer=Answer(
                    issue_id=issue.id, basis_id=f"basis:{issue.id}", answer_kind="FACT",
                    value=3_240_000, reason="Xác nhận đã trả.",
                ),
            ),
        )
    cx = wf.db.connect()
    try:
        count = cx.execute(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchone()["n"]
    finally:
        cx.close()
    assert int(count) == 0


async def test_live_unscoped_payer_answer_is_not_saved_as_success(tmp_path: Path) -> None:
    import pytest

    from invoice_referee.domain.case import CommandContext
    from invoice_referee.domain.commands import AnswerIssue
    from invoice_referee.domain.issues import Answer
    from invoice_referee.workflow.service import UnsupportedCommandError

    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    report = _report()
    report = report.model_copy(
        update={
            "documents": (
                report.documents[0],
                report.documents[1].model_copy(update={"profile_status": "NEEDS_HUMAN"}),
            )
        }
    )
    _publish(wf, root, report)
    await _admit_and_commit(wf, root)
    cx = wf.db.connect()
    try:
        session_id = cx.execute(
            "SELECT session_id FROM demo_sessions WHERE tenant = ? LIMIT 1", (TENANT,)
        ).fetchone()["session_id"]
    finally:
        cx.close()
    session = wf.session(str(session_id))
    before = wf.view(
        CommandContext(
            session_id=session.session_id, actor_id=EMPLOYEE, command_id="cmd:view",
            expected_case_version=0,
        ),
        root,
    )
    issue = next(item for item in before.issues if item.field_or_rule == "expense:payer")

    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=session.session_id, actor_id=EMPLOYEE,
                command_id="cmd:answer-unscoped-payer", expected_case_version=before.version,
            ),
            AnswerIssue(
                root_id=root,
                answer=Answer(
                    issue_id=issue.id, basis_id=f"basis:{issue.id}", answer_kind="FACT",
                    value=EMPLOYEE, reason="Tôi đã trả khoản này.",
                ),
            ),
        )
    cx = wf.db.connect()
    try:
        count = cx.execute(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (root,)
        ).fetchone()["n"]
    finally:
        cx.close()
    assert int(count) == 0


async def test_invoice_employee_paid_claim_does_not_cross_to_another_invoice(
    tmp_path: Path,
) -> None:
    import json

    from invoice_referee.workflow.evidence_assessment import build_evidence_assessment_input

    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    confirmation = {
        "id": "confirmation:ir-b",
        "tenant": TENANT,
        "root_id": root,
        "fact_key": "expense:IR-B:employee_paid",
        "value": "2000000",
        "actor": EMPLOYEE,
        "scope": ACTIVITY,
        "refs_json": json.dumps([_invoice_ref("source:ir-b", "IR-B").model_dump(mode="json")]),
        "reason": "Tôi trực tiếp thanh toán hóa đơn IR-B.",
        "observed_at": PILOT_CLOCK.isoformat(),
    }
    with wf.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_confirmations "
            "(id, tenant, root_id, fact_key, value, actor, scope, refs_json, reason, observed_at) "
            "VALUES (:id, :tenant, :root_id, :fact_key, :value, :actor, :scope, :refs_json, :reason, :observed_at)",
            confirmation,
        )
        assessment_input = build_evidence_assessment_input(
            cx, tenant=TENANT, root_id=root, report=_two_invoice_report(), as_of=PILOT_CLOCK
        )

    by_expense = {expense.id: expense for expense in assessment_input.expense_facts}
    assert by_expense["expense:1"].payments == ()
    assert [(payment.amount, payment.responsible_actor) for payment in by_expense["expense:2"].payments] == [
        (2_000_000, EMPLOYEE)
    ]


async def test_live_invoice_claim_requires_case_employee_and_activity_scope(
    tmp_path: Path,
) -> None:
    import json

    from invoice_referee.workflow.evidence_assessment import build_evidence_assessment_input

    wf = _workflow(tmp_path)
    root = await _seed_case(wf)
    confirmations = (
        {
            "id": "confirmation:wrong-actor",
            "tenant": TENANT,
            "root_id": root,
            "fact_key": "expense:IR-A:employee_paid",
            "value": "1000000",
            "actor": "employee:other",
            "scope": ACTIVITY,
            "refs_json": json.dumps([_invoice_ref("source:ir-a", "IR-A").model_dump(mode="json")]),
            "reason": "actor mismatch",
            "observed_at": PILOT_CLOCK.isoformat(),
        },
        {
            "id": "confirmation:wrong-scope",
            "tenant": TENANT,
            "root_id": root,
            "fact_key": "expense:IR-B:employee_paid",
            "value": "2000000",
            "actor": EMPLOYEE,
            "scope": "activity:other",
            "refs_json": json.dumps([_invoice_ref("source:ir-b", "IR-B").model_dump(mode="json")]),
            "reason": "scope mismatch",
            "observed_at": PILOT_CLOCK.isoformat(),
        },
    )
    with wf.db.transaction() as cx:
        for confirmation in confirmations:
            cx.execute(
                "INSERT INTO case_confirmations "
                "(id, tenant, root_id, fact_key, value, actor, scope, refs_json, reason, observed_at) "
                "VALUES (:id, :tenant, :root_id, :fact_key, :value, :actor, :scope, :refs_json, :reason, :observed_at)",
                confirmation,
            )
        assessment_input = build_evidence_assessment_input(
            cx, tenant=TENANT, root_id=root, report=_two_invoice_report(), as_of=PILOT_CLOCK
        )

    assert all(not expense.payments for expense in assessment_input.expense_facts)
    assert {
        issue.field_or_rule for issue in assessment_input.admission_issues
    } >= {
        "expense:IR-A:employee_paid",
        "expense:IR-B:employee_paid",
    }


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
