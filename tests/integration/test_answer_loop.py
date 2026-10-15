"""Human-in-the-loop closes: an answer changes the basis (§3, §5, §6).

A correct answer from the issue's owner must persist as a responsible
confirmation and feed the re-assessment, so the issue resolves and the workflow
continues. Marking a card ANSWERED without applying its value leaves the loop
open (the issue is recomputed and returns OPEN).
"""

from __future__ import annotations

from invoice_referee.domain.issues import Answer


async def test_payer_answer_resolves_issue_and_enables_progress(app_fixture):
    # missing-payer: incurred 5m, coverage ok, no payer -> E UNKNOWN -> FACT
    # owned by the employee. The employee confirms they paid; E is established
    # and the FACT is resolved.
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    issue = next(i for i in v.issues if i.field_or_rule == "expense:payer")
    assert v.actual_money.E.state == "UNKNOWN"

    after = await app_fixture.answer(
        v.id,
        Answer(
            issue_id=issue.id,
            basis_id="basis:payer",
            answer_kind="FACT",
            value="employee:employee-a",
            reason="Tôi đã trả khoản này bằng thẻ cá nhân.",
        ),
        actor="employee:employee-a",
    )
    assert not any(i.field_or_rule == "expense:payer" for i in after.issues)
    assert after.actual_money.E.state == "KNOWN"
    assert after.actual_money.E.value == 5_000_000


async def test_answer_persists_a_confirmation(app_fixture):
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    issue = next(i for i in v.issues if i.field_or_rule == "expense:payer")
    await app_fixture.answer(
        v.id,
        Answer(
            issue_id=issue.id,
            basis_id="basis:payer",
            answer_kind="FACT",
            value="employee:employee-a",
            reason="Tôi đã trả.",
        ),
        actor="employee:employee-a",
    )
    row = app_fixture.query_one(
        "SELECT value, actor, scope FROM case_confirmations "
        "WHERE root_id = ? AND fact_key = 'expense:payer'",
        (v.id,),
    )
    assert row is not None
    assert row["value"] == "employee:employee-a"
    assert row["actor"] == "employee:employee-a"


async def test_wrong_owner_answer_is_not_applied(app_fixture):
    # The payer issue is owned by the employee; an accountant answer must not
    # apply (and must not create a confirmation).
    v = await app_fixture.submit_packet("missing-payer", mode="STUB")
    issue = next(i for i in v.issues if i.field_or_rule == "expense:payer")
    import pytest

    with pytest.raises(Exception):
        await app_fixture.answer(
            v.id,
            Answer(
                issue_id=issue.id,
                basis_id="basis:payer",
                answer_kind="FACT",
                value="employee:employee-a",
                reason="trả lời sai vai trò",
            ),
            actor="employee:accountant-demo",
        )
    assert (
        app_fixture.query_one(
            "SELECT COUNT(*) AS n FROM case_confirmations WHERE root_id = ?", (v.id,)
        )["n"]
        == 0
    )


async def test_reassessment_closes_legacy_budget_issue_without_losing_case_history(app_fixture):
    # Seed one persisted issue as an older release would have stored it. The
    # behavior under test still runs through the real employee answer command.
    v = await app_fixture.submit_packet(
        "missing-payer-no-history", mode="STUB", activity="activity:unknown-z"
    )
    payer_issue = next(i for i in v.issues if i.field_or_rule == "expense:payer")
    assert any(i.field_or_rule == "ledger:coverage" for i in v.issues)
    source_ids_before = [source.id for source in v.sources]
    audit_before = app_fixture.audit_actions()
    with app_fixture.db.transaction() as cx:
        cx.execute(
            "INSERT INTO case_issues (id, tenant, root_id, kind, field_or_rule, owner, "
            "status, recovery_key, payload_json, created_at, updated_at) "
            "VALUES (?, ?, ?, 'FACT', 'budget:B', 'org-data', 'OPEN', 'FACT:budget:B', ?, ?, ?)",
            (
                "issue:legacy-budget",
                v.sources[0].tenant if v.sources else "tenant:demo",
                v.id,
                '{"id":"issue:legacy-budget","kind":"FACT","field_or_rule":"budget:B",'
                '"owner":"org-data","status":"OPEN","basis":"Legacy B issue",'
                '"question":"Legacy B question","refs":[]}',
                "2026-10-05T09:00:00+00:00",
                "2026-10-05T09:00:00+00:00",
            ),
        )

    events_before = app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (v.id,)
    )["n"]
    after = await app_fixture.answer(
        v.id,
        Answer(
            issue_id=payer_issue.id,
            basis_id="basis:payer",
            answer_kind="FACT",
            value="employee:employee-a",
            reason="Tôi đã thanh toán khoản chi này.",
        ),
        actor="employee:employee-a",
    )

    assert not any(i.field_or_rule == "budget:B" for i in after.issues)
    assert not any(i.field_or_rule == "expense:payer" for i in after.issues)
    assert any(i.field_or_rule == "ledger:coverage" for i in after.issues)
    assert [source.id for source in after.sources] == source_ids_before
    assert app_fixture.query_one(
        "SELECT COUNT(*) AS n FROM money_events WHERE root_id = ?", (v.id,)
    )["n"] == events_before
    audit_after = app_fixture.audit_actions()
    for action in ("CREATE_DRAFT", "ATTACH_SOURCES", "ASSESS"):
        assert action in audit_before and action in audit_after
    assert audit_after.count("ANSWER_ISSUE") == audit_before.count("ANSWER_ISSUE") + 1
