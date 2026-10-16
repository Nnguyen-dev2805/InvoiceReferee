"""S6 exception persistence + no-advance conflict at the workflow boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import Decide, RefuseException
from invoice_referee.domain.evidence import Confirmation, ReadResult
from invoice_referee.domain.issues import DecisionCommand
from invoice_referee.workflow.service import UnsupportedCommandError
from tests.s6_seeding import (
    ACCOUNTANT,
    ACTIVITY,
    AS_OF,
    EMPLOYEE,
    TENANT,
    _context,
    _issues,
    _report,
    _seed,
    _workflow,
)
from tests.tc18_shapes import _acceptance, _invoice, _paper, _transfer


async def test_accept_persists_and_clears_on_reassess(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root, _ = await _seed(wf, consistent=True)
    issue = next(
        i
        for i in _issues(wf, root)
        if i["field_or_rule"] == "expense:2:missing_evidence"
    )
    acct = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    result = await wf.execute(
        CommandContext(
            session_id=acct.session_id,
            actor_id=ACCOUNTANT,
            command_id="cmd:d1",
            expected_case_version=0,
        ),
        Decide(
            root_id=root,
            decision=DecisionCommand(
                issue_ids=(issue["id"],),
                basis_id="b:1",
                actions=("EXCEPT_POLICY",),
                effect_scope=ACTIVITY,
                amount=1_500_000,
                reason="Chấp nhận nghiệm thu + chuyển khoản thay hóa đơn",
            ),
        ),
    )
    assert result.case_view.version >= 0
    remaining = [
        i
        for i in _issues(wf, root)
        if i["field_or_rule"] == "expense:2:missing_evidence"
    ]
    assert remaining == [], "accepted exception stays cleared after reassess"
    with wf.db.connect() as cx:
        rows = cx.execute(
            "SELECT * FROM case_exception_decisions WHERE root_id = ?", (root,)
        ).fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "ACCEPTED"
    assert rows[0]["grant_ref"] == "g:except-sim"


async def test_refuse_keeps_issue_open(tmp_path: Path) -> None:
    wf = _workflow(tmp_path)
    root, _ = await _seed(wf, consistent=True)
    issue = next(
        i
        for i in _issues(wf, root)
        if i["field_or_rule"] == "expense:2:missing_evidence"
    )
    acct = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    await wf.execute(
        CommandContext(
            session_id=acct.session_id,
            actor_id=ACCOUNTANT,
            command_id="cmd:r1",
            expected_case_version=0,
        ),
        RefuseException(
            root_id=root,
            issue_ids=(issue["id"],),
            reason="Chưa đủ căn cứ, bổ sung thêm",
        ),
    )
    assert any(
        i["field_or_rule"] == "expense:2:missing_evidence" for i in _issues(wf, root)
    )
    with wf.db.connect() as cx:
        rows = cx.execute(
            "SELECT * FROM case_exception_decisions WHERE root_id = ?", (root,)
        ).fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "REFUSED"


async def test_accept_without_grant_is_blocked(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, except_max=None)
    root, _ = await _seed(wf, consistent=True)
    issue = next(
        i
        for i in _issues(wf, root)
        if i["field_or_rule"] == "expense:2:missing_evidence"
    )
    acct = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=acct.session_id,
                actor_id=ACCOUNTANT,
                command_id="cmd:d1",
                expected_case_version=0,
            ),
            Decide(
                root_id=root,
                decision=DecisionCommand(
                    issue_ids=(issue["id"],),
                    basis_id="b:1",
                    actions=("EXCEPT_POLICY",),
                    effect_scope=ACTIVITY,
                    amount=1_500_000,
                    reason="Tự cấp quyền",
                ),
            ),
        )
    assert any(
        i["field_or_rule"] == "expense:2:missing_evidence" for i in _issues(wf, root)
    )


async def test_accept_over_grant_ceiling_is_blocked(tmp_path: Path) -> None:
    wf = _workflow(tmp_path, except_max=100_000)
    root, _ = await _seed(wf, consistent=True)
    issue = next(
        i
        for i in _issues(wf, root)
        if i["field_or_rule"] == "expense:2:missing_evidence"
    )
    acct = wf.start_session(tenant=TENANT, persona="accountant", actor_id=ACCOUNTANT)
    with pytest.raises(UnsupportedCommandError):
        await wf.execute(
            CommandContext(
                session_id=acct.session_id,
                actor_id=ACCOUNTANT,
                command_id="cmd:d1",
                expected_case_version=0,
            ),
            Decide(
                root_id=root,
                decision=DecisionCommand(
                    issue_ids=(issue["id"],),
                    basis_id="b:1",
                    actions=("EXCEPT_POLICY",),
                    effect_scope=ACTIVITY,
                    amount=1_500_000,
                    reason="Vượt hạn mức",
                ),
            ),
        )


def test_no_advance_assertion_with_recorded_advance_conflicts() -> None:
    import json as _json

    from invoice_referee.domain.case import CaseScope, ReadSet
    from invoice_referee.domain.evidence import ReadResult
    from invoice_referee.domain.organization import OrganizationContext
    from invoice_referee.reconciliation.admission import admit_evidence

    confirmation = Confirmation(
        fact_key="settlement:no_advance",
        value="asserted",
        actor="employee:a",
        scope="activity:1",
        refs=(),
        reason="Tự chi",
        observed_at=datetime(2026, 10, 10, 11, 0, tzinfo=UTC),
    )
    report = ReadResult(
        provider_mode="LIVE",
        data_origin="LIVE_READ",
        documents=(_paper(), _invoice(), _acceptance(), _transfer()),
    )
    org = OrganizationContext.model_validate_json(_json.dumps(_context()))
    inp2 = admit_evidence(
        report,
        scope=CaseScope(
            tenant=TENANT, employee=EMPLOYEE, activity=ACTIVITY, profile="WORK_EXPENSE"
        ),
        organization=org,
        confirmations=(confirmation,),
        ledger=(),
        coverage=None,
        read_set=ReadSet(
            input_revision=1,
            control_epoch=0,
            context_version=1,
            ledger_version=1,
            usage_version=0,
        ),
        as_of=AS_OF,
    )
    assert any(
        i.field_or_rule == "advance:type_conflict" for i in inp2.admission_issues
    )
