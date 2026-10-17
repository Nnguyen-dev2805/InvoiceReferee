import pytest
from invoice_referee.domain.commands import Decide,AnswerIssue
from invoice_referee.domain.issues import DecisionCommand,Answer
from invoice_referee.workflow.service import UnsupportedCommandError,StaleCommandError,NotFoundError
from tests.escalation_shapes import scenario,actor_context

def decision(card,amount=None):
    return DecisionCommand(issue_ids=tuple(a.issue_id for a in card.actions),basis_id=card.basis_id,actions=tuple(a.action for a in card.actions),effect_scope=card.scope,amount=amount,reason="Đủ căn cứ, chấp thuận trong quyền")

async def test_authority_approval_applies_and_survives_reassessment(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch)
    assert v.state=="WAITING" and not v.instructions
    issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    ctx=actor_context(app_fixture,v)
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    assert card.actions[0].amount==9000000 and card.actions[0].authorized
    result=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card,amount=9000000)))
    assert not any(i.kind=="AUTHORITY" for i in result.case_view.issues)
    assert result.case_view.instructions[0].direction=="PAY" and result.case_view.instructions[0].amount==1000000
    assert result.case_view.actual_money.P.value==0 and result.case_view.state!="SETTLED"
    with app_fixture.db.transaction() as cx:
        row=cx.execute("SELECT * FROM cases WHERE id=?",(v.id,)).fetchone()
        app_fixture.workflow._assess_and_commit(cx,app_fixture.workflow.session(ctx.session_id),row,app_fixture.workflow._now_iso())
    after=app_fixture.workflow.view(ctx,v.id)
    assert not after.issues and len(after.instructions)==1
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM case_authority_decisions")["n"]==1

async def test_compound_amount_is_derived_per_action(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch,advance=1000000)
    ctx=actor_context(app_fixture,v);issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    assert {a.action:a.amount for a in card.actions}=={"RECOGNIZE_COST":9000000,"ISSUE_PAYMENT":8000000}
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card,amount=1)))
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM case_authority_decisions")["n"]==0
    result=await app_fixture.workflow.execute(actor_context(app_fixture,v),Decide(root_id=v.id,decision=decision(card)))
    assert result.case_view.instructions[0].amount==8000000

async def test_fact_cannot_be_waived_by_decision(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch,payer=False)
    issue=next(i for i in v.issues if i.kind=="FACT")
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(actor_context(app_fixture,v),Decide(root_id=v.id,decision=DecisionCommand(issue_ids=(issue.id,),basis_id="fake",actions=("RECOGNIZE_COST",),effect_scope=v.activity,amount=1,reason="Đồng ý")))

async def test_authority_cannot_be_answered_as_a_fact(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch);issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(actor_context(app_fixture,v),AnswerIssue(root_id=v.id,answer=Answer(issue_id=issue.id,basis_id="fake",answer_kind="FACT",value="đồng ý",reason="duyệt")))

async def test_override_cannot_waive_fact(app_fixture,monkeypatch):
    from invoice_referee.domain.commands import Override
    v=await scenario(app_fixture,monkeypatch,payer=False);issue=next(i for i in v.issues if i.kind=="FACT")
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(actor_context(app_fixture,v),Override(root_id=v.id,supersedes_decision_id="decision:missing",decision=DecisionCommand(issue_ids=(issue.id,),basis_id="fake",actions=("EXCEPT_POLICY",),effect_scope=v.activity,reason="Đồng ý")))

async def test_revoked_authority_suspends_old_instruction(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    result=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    assert result.case_view.instructions[0].status=="ISSUED"
    with app_fixture.db.transaction() as cx:
        cx.execute("DELETE FROM context_grants WHERE tenant='tenant:demo' AND actor='employee:approver'")
        row=cx.execute("SELECT * FROM cases WHERE id=?",(v.id,)).fetchone()
        app_fixture.workflow._assess_and_commit(cx,app_fixture.workflow.session(ctx.session_id),row,app_fixture.workflow._now_iso())
    after=app_fixture.workflow.view(ctx,v.id)
    assert any(i.kind=="AUTHORITY" for i in after.issues)
    assert not any(i.status in ("ISSUED","PARTIAL") for i in after.instructions)
    assert app_fixture.query_one("SELECT status FROM instructions WHERE root_id=?",(v.id,))["status"]=="SUSPENDED"

@pytest.mark.parametrize("failure",["stale_version","basis","scope","empty","wrong_action","missing_grant","expired_grant","profile","stopped","cross_root"])
async def test_decision_guards_leave_no_partial_authorization(app_fixture,monkeypatch,failure):
    from invoice_referee.domain.commands import Control
    v=await scenario(app_fixture,monkeypatch,advance=1000000)
    ctx=actor_context(app_fixture,v);issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    cmd=decision(card)
    if failure=="stale_version":ctx=ctx.model_copy(update={"expected_case_version":0})
    if failure=="basis":cmd=cmd.model_copy(update={"basis_id":"stale"})
    if failure=="scope":cmd=cmd.model_copy(update={"effect_scope":"activity:other"})
    if failure=="empty":cmd=cmd.model_copy(update={"issue_ids":()})
    if failure=="wrong_action":cmd=cmd.model_copy(update={"actions":("EXCEPT_POLICY",)})
    if failure=="cross_root":cmd=cmd.model_copy(update={"issue_ids":("issue:other",)})
    if failure in ("missing_grant","expired_grant","profile"):
        with app_fixture.db.transaction()as cx:
            if failure=="missing_grant":cx.execute("UPDATE context_grants SET actions_json=? WHERE actor='employee:approver'",('["RECOGNIZE_COST"]',))
            if failure=="expired_grant":cx.execute("UPDATE context_grants SET effective_to='2026-01-01T00:00:00+00:00' WHERE actor='employee:approver'")
            if failure=="profile":cx.execute("UPDATE context_grants SET allowed_profiles_json=? WHERE actor='employee:approver'",('["OTHER"]',))
    if failure=="stopped":
        await app_fixture.workflow.execute(ctx,Control(root_id=v.id,action="STOP",reason="Dừng để kiểm tra"))
        ctx=actor_context(app_fixture,v)  # Fresh command identity, deliberately stale case version.
    with pytest.raises((UnsupportedCommandError,StaleCommandError,NotFoundError)):await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=cmd))
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM case_authority_decisions")["n"]==0
    assert app_fixture.query_one("SELECT COUNT(*) AS n FROM money_events")["n"]==0

async def test_approval_needs_no_more_permission_on_same_basis_after_restart(app_fixture,monkeypatch):
    from invoice_referee.workflow.service import CaseWorkflow
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    first=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    duplicate=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    assert duplicate.duplicate_command and duplicate.case_view.version==first.case_view.version
    restarted=CaseWorkflow(app_fixture.db,uploads_dir=app_fixture.workflow.uploads_dir)
    with restarted.db.transaction()as cx:
        row=cx.execute("SELECT * FROM cases WHERE id=?",(v.id,)).fetchone()
        restarted._assess_and_commit(cx,restarted.session(ctx.session_id),row,restarted._now_iso())
    after=restarted.view(ctx,v.id)
    assert not after.issues and len(after.instructions)==1 and after.instructions[0].amount==1000000

async def test_changed_cost_invalidates_prior_approval(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    changed=await scenario(app_fixture,monkeypatch,cost=10000000,advance=8000000)
    assert any(i.kind=="AUTHORITY" for i in changed.issues)
    assert not any(i.status in ("ISSUED","PARTIAL") for i in changed.instructions)

async def test_confirmed_partial_receipt_does_not_require_cost_approval_again(app_fixture,monkeypatch):
    from datetime import datetime,UTC
    from invoice_referee.domain.commands import RecordActual
    from invoice_referee.domain.finance import RecordMoneyInput
    from invoice_referee.domain.common import EvidenceRef
    v=await scenario(app_fixture,monkeypatch,advance=1000000);ctx=actor_context(app_fixture,v)
    issue=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,issue.id)
    approved=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    view=approved.case_view;source=view.sources[0];inst=view.instructions[0]
    ctx=actor_context(app_fixture,view,persona="accountant",actor="employee:accountant-demo")
    result=await app_fixture.workflow.execute(ctx,RecordActual(root_id=v.id,money=RecordMoneyInput(external_key="bank:APPROVED-PART-01",claimed_kind="REIMBURSEMENT_RECEIVED",claimed_scope=v.activity,payer="company:demo",payee=v.employee,amount=1000000,event_at=datetime.now(UTC),completion_claim="Kế toán đã đối chiếu và xác nhận khoản công ty chi",refs=(EvidenceRef(source_id=source.id,source_sha256=source.digest,page=1,exact_quote="Đã chuyển 1000000"),),instruction_id=inst.id,reason="Ghi nhận tiền thực tế theo lệnh đã được duyệt")))
    assert not result.case_view.issues
    assert result.case_view.actual_money.P.value==1000000 and result.case_view.actual_money.S.value==7000000
    assert len(result.case_view.instructions)==1 and result.case_view.instructions[0].id==inst.id
    assert result.case_view.instructions[0].remaining==7000000
    assert app_fixture.query_one("SELECT COUNT(*)AS n FROM case_authority_decisions")["n"]==2

async def test_stop_resume_invalidates_stored_authority_approval(app_fixture,monkeypatch):
    from invoice_referee.domain.commands import Control
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    i=next(i for i in v.issues if i.kind=="AUTHORITY");card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,i.id)
    approved=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    stopped=await app_fixture.workflow.execute(actor_context(app_fixture,approved.case_view),Control(root_id=v.id,action="STOP",reason="Dừng rà soát"))
    resumed=await app_fixture.workflow.execute(actor_context(app_fixture,stopped.case_view),Control(root_id=v.id,action="RESUME",reason="Tiếp tục sau rà soát"))
    assert any(i.kind=="AUTHORITY"for i in resumed.case_view.issues)
    assert not any(i.status in ("ISSUED","PARTIAL")for i in resumed.case_view.instructions)

async def test_reapproval_rebinds_instruction_to_current_authority(app_fixture,monkeypatch):
    import json
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    i=next(i for i in v.issues if i.kind=="AUTHORITY");card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,i.id)
    first=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    oldrefs=first.case_view.instructions[0].authority_refs
    with app_fixture.db.transaction()as cx:
        cx.execute("UPDATE context_grants SET version='revoked-old' WHERE actor='employee:approver'")
        row=cx.execute("SELECT *FROM cases WHERE id=?",(v.id,)).fetchone();app_fixture.workflow._assess_and_commit(cx,app_fixture.workflow.session(ctx.session_id),row,app_fixture.workflow._now_iso())
    current=app_fixture.workflow.view(ctx,v.id);ctx=actor_context(app_fixture,current)
    i=next(i for i in current.issues if i.kind=="AUTHORITY");card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,i.id)
    second=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    refs=second.case_view.instructions[0].authority_refs
    assert refs!=oldrefs
    assert len([r for r in refs if r.startswith("decision:")])==1
    assert app_fixture.query_one("SELECT COUNT(*)AS n FROM money_events")["n"]==0

@pytest.mark.parametrize("received",[500000,1000000])
async def test_receipt_after_natural_grant_expiry_does_not_reopen_cost_approval(app_fixture,monkeypatch,received):
    from datetime import datetime,UTC,timedelta
    from invoice_referee.domain.commands import RecordActual
    from invoice_referee.domain.finance import RecordMoneyInput
    from invoice_referee.domain.common import EvidenceRef
    start=datetime(2026,10,16,12,tzinfo=UTC)
    app_fixture.workflow._clock=lambda:start
    with app_fixture.db.transaction()as cx:cx.execute("UPDATE context_grants SET effective_to=? WHERE actor='employee:approver'",((start+timedelta(hours=1)).isoformat(),))
    v=await scenario(app_fixture,monkeypatch);ctx=actor_context(app_fixture,v)
    i=next(i for i in v.issues if i.kind=="AUTHORITY");card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,i.id)
    approved=await app_fixture.workflow.execute(ctx,Decide(root_id=v.id,decision=decision(card)))
    app_fixture.workflow._clock=lambda:start+timedelta(hours=2)
    src=approved.case_view.sources[0];inst=approved.case_view.instructions[0]
    result=await app_fixture.workflow.execute(actor_context(app_fixture,approved.case_view,persona="accountant",actor="employee:accountant-demo"),RecordActual(root_id=v.id,money=RecordMoneyInput(external_key=f"bank:EXPIRY-{received}",claimed_kind="REIMBURSEMENT_RECEIVED",claimed_scope=v.activity,payer="company:demo",payee=v.employee,amount=received,event_at=start+timedelta(hours=2),completion_claim="Đã chi và nhân viên đã nhận theo chứng từ",instruction_id=inst.id,refs=(EvidenceRef(source_id=src.id,source_sha256=src.digest,page=1,exact_quote=f"Đã nhận {received}"),),reason="Xác nhận giao dịch thực tế sau thời điểm phát hành")))
    assert not result.case_view.issues
    assert result.case_view.actual_money.P.value==received
    assert result.case_view.state==("SETTLED"if received==1000000 else"READY_TO_EXECUTE")
