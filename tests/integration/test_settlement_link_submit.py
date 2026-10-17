"""Settlement submit via backend dossier linking (task 14/10/2026).

The employee uploads, reviews the draft and confirms — the BACKEND binds the
dossier. No standing-activity choice in the normal flow.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import (
    ActivityData,
    AttachSources,
    CreateDraft,
    Declaration,
    SourceUpload,
    Submit,
)
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.documents import DocumentAnalysis, FieldCandidate
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import (
    CaseWorkflow,
    CommandConflictError,
    UnsupportedCommandError,
)

TENANT = "tenant:link-submit"
EMPLOYEE = "employee:employee-a"
SHA = "a" * 64
CLOCK = datetime(2026, 10, 10, 18, 0, tzinfo=timezone(timedelta(hours=7)))


def _ref(quote: str = "q") -> EvidenceRef:
    return EvidenceRef(
        source_id="source:1", source_sha256=SHA, page=1, exact_quote=quote
    )


def _found(field: str, value: object, quote: str = "q") -> FieldCandidate:
    return FieldCandidate(field=field, state="FOUND", value=value, refs=(_ref(quote),))  # type: ignore[arg-type]


def _paper(*fields: FieldCandidate) -> DocumentAnalysis:
    return DocumentAnalysis(
        source_id="source:1",
        document_id="source:1:1-1:SETTLEMENT_FORM",
        document_type="SETTLEMENT_FORM",
        roles=("SETTLEMENT_DECLARATION",),  # type: ignore[arg-type]
        page_range=(1, 1),
        fields=tuple(fields),
        confidence_status="ASSESSED",
        profile_status="CLEAR",
    )


def _report(*fields: FieldCandidate) -> ReadResult:
    return ReadResult(
        provider_mode="LIVE", data_origin="LIVE_READ", documents=(_paper(*fields),)
    )


def _context(tenant: str) -> object:
    from invoice_referee.domain.organization import OrganizationContext

    interval = ["2026-10-01T00:00:00+07:00", "2026-12-31T23:59:59+07:00"]
    return OrganizationContext.model_validate_json(
        json.dumps(
            {
                "organization_id": tenant,
                "tenant": tenant,
                "profile": "WORK_EXPENSE",
                "activity": {
                    "activity_id": "activity:adv-1",
                    "name": "Tạm ứng 1",
                    "occurred_at": "2026-10-05T09:00:00+07:00",
                    "purpose": "Tạm ứng công tác",
                    "profile": "WORK_EXPENSE",
                    "authorization": {"id": "auth:1"},
                },
                "activities": [
                    {
                        "activity_id": "activity:adv-1",
                        "name": "Tạm ứng 1",
                        "occurred_at": "2026-10-05T09:00:00+07:00",
                        "purpose": "Tạm ứng công tác",
                        "profile": "WORK_EXPENSE",
                        "authorization": {"id": "auth:1"},
                    },
                    {
                        "activity_id": "activity:adv-2",
                        "name": "Tạm ứng 2",
                        "occurred_at": "2026-10-06T09:00:00+07:00",
                        "purpose": "Tạm ứng công tác",
                        "profile": "WORK_EXPENSE",
                        "authorization": {"id": "auth:1"},
                    },
                ],
                "people": ({"id": EMPLOYEE, "name": "Nguyễn An"},),
                "budgets": (),
                "grants": (
                    {
                        "id": "g:r",
                        "version": "v1",
                        "actor": "system:referee",
                        "actions": ["RECOGNIZE_COST"],
                        "scope": "activity:adv-1",
                        "max_amount": 8_000_000,
                        "effective_from": interval[0],
                        "effective_to": interval[1],
                        "allowed_profiles": ["WORK_EXPENSE"],
                    },
                    {
                        "id": "g:i",
                        "version": "v1",
                        "actor": "system:referee",
                        "actions": ["ISSUE_PAYMENT", "ISSUE_COLLECTION"],
                        "scope": "activity:adv-1",
                        "max_amount": 4_000_000,
                        "effective_from": interval[0],
                        "effective_to": interval[1],
                        "allowed_profiles": ["WORK_EXPENSE"],
                    },
                ),
                "ledger": (),
                "coverage": None,
            }
        )
    )


def _workflow(tmp_path: Path, tenant: str = TENANT) -> CaseWorkflow:
    db = Database(tmp_path / f"{tenant.replace(':', '-')}.sqlite")
    db.migrate()
    wf = CaseWorkflow(db, uploads_dir=tmp_path / "up", clock=lambda: CLOCK)
    wf.enable_evidence_read(
        reader=object(), classifier=object(), artifacts_root=tmp_path / "art"
    )
    wf.import_company_context(_context(tenant), origin="SIMULATED")
    # The catalog knows adv-1 by its dossier reference (server-owned).
    with wf.db.transaction() as cx:
        cx.execute(
            "UPDATE context_activities SET references_json = ? WHERE tenant = ? AND activity_id = ?",
            (json.dumps(["TU-2026-001"]), tenant, "activity:adv-1"),
        )
        cx.execute(
            "UPDATE context_activities SET references_json = ? WHERE tenant = ? AND activity_id = ?",
            (json.dumps(["TU-2026-002"]), tenant, "activity:adv-2"),
        )
    return wf


_TAG = itertools.count(1)


async def _draft_root(wf: CaseWorkflow, tenant: str = TENANT) -> str:
    tag = next(_TAG)
    session = wf.start_session(tenant=tenant, persona="employee", actor_id=EMPLOYEE)
    created = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id=f"cmd:1:{tag}",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:proposed:draft1",
                name="Hồ sơ quyết toán chi phí",
                occurred_at="2026-10-10T09:00:00+07:00",
                declared_purpose="Quyết toán chi phí công việc",
            )
        ),
    )
    root = created.case_view.id
    digest = hashlib.sha256(b"pdf").hexdigest()
    await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id=f"cmd:2:{root[-6:]}",
            expected_case_version=created.case_view.version,
        ),
        AttachSources(
            root_id=root,
            uploads=(
                SourceUpload(
                    filename="quyet-toan.pdf",
                    media="PDF",
                    digest=digest,
                    storage_key=f"{tenant}/{root}/quyet-toan.pdf",
                ),
            ),
        ),
    )
    return root


def _publish(wf: CaseWorkflow, tenant: str, root: str, report: ReadResult) -> None:
    digest = hashlib.sha256(b"pdf").hexdigest()
    with wf.db.transaction() as cx:
        wf._store_evidence_report(
            cx,
            tenant=tenant,
            root_id=root,
            report=report,
            basis={"sources": [digest], "case_version": 2},
        )


async def _submit(
    wf: CaseWorkflow,
    tenant: str,
    root: str,
    *,
    confirmed: str | None = None,
    **dec_kwargs,
):
    session = wf.start_session(tenant=tenant, persona="employee", actor_id=EMPLOYEE)
    version = int(
        wf._query_one("SELECT version FROM cases WHERE id = ?", (root,))["version"]
    )
    payload = {
        "declared_purpose": "Quyết toán tạm ứng",
        "confirmed_activity_id": confirmed,
    }
    payload.update(dec_kwargs)
    return await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id=f"cmd:submit:{root[-6:]}:{confirmed or 'auto'}",
            expected_case_version=version,
        ),
        Submit(
            root_id=root,
            declaration=Declaration(**payload),
        ),
    )


async def test_printed_reference_rebinds_without_activity_choice(
    tmp_path: Path,
) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    _publish(
        wf,
        TENANT,
        root,
        _report(
            _found("purpose", "Quyết toán tạm ứng"),
            _found("advance_reference", "TU-2026-001", quote="Số tạm ứng TU-2026-001"),
        ),
    )
    result = await _submit(wf, TENANT, root)
    view = result.case_view
    assert view.activity == "activity:adv-1"


async def test_weak_basis_asks_employee_then_confirmed_submits(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    _publish(wf, TENANT, root, _report(_found("purpose", "Tạm ứng công tác")))
    with pytest.raises(UnsupportedCommandError, match="khoản tạm ứng nào"):
        await _submit(wf, TENANT, root)
    result = await _submit(wf, TENANT, root, confirmed="activity:adv-2")
    assert result.case_view.activity == "activity:adv-2"


async def test_rebind_to_existing_dossier_conflicts(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    # An existing dossier already owns (employee, adv-1).
    session = wf.start_session(tenant=TENANT, persona="employee", actor_id=EMPLOYEE)
    first = await wf.execute(
        CommandContext(
            session_id=session.session_id,
            actor_id=EMPLOYEE,
            command_id="cmd:first",
            expected_case_version=0,
        ),
        CreateDraft(
            activity_data=ActivityData(
                activity_id="activity:adv-1",
                name="Tạm ứng 1",
                occurred_at="2026-10-05T09:00:00+07:00",
                declared_purpose="Tạm ứng công tác",
            )
        ),
    )
    root = await _draft_root(wf)
    _publish(
        wf,
        TENANT,
        root,
        _report(
            _found("purpose", "Quyết toán tạm ứng"),
            _found("advance_reference", "TU-2026-001", quote="Số tạm ứng TU-2026-001"),
        ),
    )
    with pytest.raises(CommandConflictError, match="đã tồn tại"):
        await _submit(wf, TENANT, root)
    # The old dossier is untouched.
    assert first.case_view.id != root


async def test_unknown_reference_stays_independent_without_fabricated_budget(
    tmp_path: Path,
) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    _publish(
        wf,
        TENANT,
        root,
        _report(
            _found("purpose", "Quyết toán tạm ứng"),
            _found("advance_reference", "TU-9999-001", quote="Số tạm ứng TU-9999-001"),
        ),
    )
    # Unknown reference: accepted as an independent draft, never a wrong link.
    result = await _submit(wf, TENANT, root)
    assert result.case_view.activity == "activity:proposed:draft1"


async def test_unlinked_dossier_creates_no_budget_or_grant(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    _publish(wf, TENANT, root, _report(_found("purpose", "Việc đột xuất không trong danh mục")))
    result = await _submit(wf, TENANT, root)
    assert result.case_view.activity == "activity:proposed:draft1"
    with wf.db.transaction() as cx:
        row = cx.execute(
            "SELECT status, budget_amount FROM context_activities "
            "WHERE tenant = ? AND activity_id = ?",
            (TENANT, "activity:proposed:draft1"),
        ).fetchone()
        assert row["status"] != "AUTHORIZED"
        assert row["budget_amount"] is None
        grants = cx.execute(
            "SELECT COUNT(*) AS n FROM context_grants WHERE tenant = ? AND scope = ?",
            (TENANT, "activity:proposed:draft1"),
        ).fetchone()
        assert int(grants["n"]) == 0
 
 
async def test_employee_reimbursement_submits_without_advance_even_when_weak_candidates_exist(
    tmp_path: Path,
) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    # The paper's purpose matches catalog activities, which produces NEEDS_CONFIRMATION
    _publish(wf, TENANT, root, _report(_found("purpose", "Tạm ứng công tác")))

    # An employee submitting an EMPLOYEE_REIMBURSEMENT asserts no advance.
    # It must NOT be forced to confirm an advance!
    result = await _submit(
        wf,
        TENANT,
        root,
        settlement_type="EMPLOYEE_REIMBURSEMENT",
        no_advance_asserted=True,
        no_advance_reason="Tự thanh toán không nhận tạm ứng",
    )
    # Since catalog has 2 authorized activities (adv-1, adv-2) and none was confirmed,
    # it stays as an independent PROPOSED dossier:
    assert result.case_view.activity == "activity:proposed:draft1"


async def test_employee_reimbursement_submits_without_no_advance_reason(
    tmp_path: Path,
) -> None:
    wf = _workflow(tmp_path)
    root = await _draft_root(wf)
    _publish(wf, TENANT, root, _report(_found("purpose", "Tự chi công việc đột xuất")))

    # Submitting an EMPLOYEE_REIMBURSEMENT without providing a no_advance_reason
    # should NOT be rejected with "Khai không nhận tạm ứng cần có lý do."
    result = await _submit(
        wf,
        TENANT,
        root,
        settlement_type="EMPLOYEE_REIMBURSEMENT",
        no_advance_asserted=True,
        no_advance_reason=None,
    )
    assert result.case_view.activity == "activity:proposed:draft1"
    with wf.db.transaction() as cx:
        conf = cx.execute(
            "SELECT reason FROM case_confirmations WHERE root_id = ? AND fact_key = ?",
            (root, "settlement:no_advance"),
        ).fetchone()
        assert conf is not None
        assert conf["reason"] == "Nhân viên tự chi, không nhận tạm ứng"

