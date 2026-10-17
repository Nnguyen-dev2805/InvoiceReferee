import json
import pytest
from tests.escalation_evidence import seed_input
from invoice_referee.domain.case import CommandContext
from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from httpx import AsyncClient,ASGITransport

async def test_tc06_correction_is_declaration_revision_not_pdf_overwrite(tmp_path):
    wf,s,v,report=await seed_input(tmp_path)
    issue=next(i for i in v.issues if i.field_or_rule=="expense:arithmetic:return")
    card=wf.question_card(s,v.id,issue.id)
    assert card.corrections[0].changes[0].after==830000
    original=report.model_dump_json()
    app=create_app(wf,mode="RECORDED_REPLAY",frontend_dir=None)
    async with AsyncClient(transport=ASGITransport(app),base_url="http://test")as client:
        client.cookies.set(SESSION_COOKIE,s.session_id)
        r=await client.post(f"/api/cases/{v.id}/issues/{issue.id}/corrections",json={"basis_id":card.basis_id,"correction_id":card.corrections[0].id,"reason":"Tôi sửa số hoàn kê khai thành 830000 theo số ứng và chi đã đối chiếu"},headers={"X-Expected-Version":str(v.version),"X-Command-Id":"cmd:correct"})
        assert r.status_code==200,r.text
        after=r.json()["case_view"]
        assert not any(i["field_or_rule"]=="expense:arithmetic:return" for i in after["issues"])
        assert after["actual_money"]["R"]["value"]==0
        assert after["instructions"][0]["direction"]=="COLLECT" and after["instructions"][0]["amount"]==830000
        reloaded=await client.get(f"/api/cases/{v.id}")
        assert reloaded.json()["declaration_corrections"]
    with wf.db.connect()as cx:
        raw=cx.execute("SELECT report_json FROM case_evidence_reports WHERE root_id=?",(v.id,)).fetchone()[0]
        assert json.loads(raw)==json.loads(original)
        assert cx.execute("SELECT COUNT(*)FROM case_declaration_corrections").fetchone()[0]==1

async def test_correction_idempotency_and_stale_source_do_not_rewrite_pdf(tmp_path):
    from invoice_referee.domain.commands import CorrectDeclaration
    wf,s,v,report=await seed_input(tmp_path)
    issue=next(i for i in v.issues if i.field_or_rule=="expense:arithmetic:return")
    card=wf.question_card(s,v.id,issue.id)
    context=CommandContext(session_id=s.session_id,actor_id=s.actor_id,command_id="cmd:revision",expected_case_version=v.version)
    command=CorrectDeclaration(root_id=v.id,issue_id=issue.id,basis_id=card.basis_id,correction_id=card.corrections[0].id,reason="Sửa số hoàn theo ứng và chi phí đã đối chiếu")
    first=await wf.execute(context,command);second=await wf.execute(context,command)
    assert second.duplicate_command and first.case_view.version==second.case_view.version
    assert len(second.case_view.declaration_corrections)==1
    # A changed effective input does not inherit an old claim correction.
    paper=report.documents[1] if report.documents[1].document_type=="SETTLEMENT_FORM" else report.documents[0]
    changed=paper.model_copy(update={"document_id":paper.document_id+":new"})
    updated=report.model_copy(update={"documents":tuple(changed if d.document_type=="SETTLEMENT_FORM"else d for d in report.documents)})
    with wf.db.transaction()as cx:
        wf._publish_evidence_report(cx,tenant=s.tenant,root_id=v.id,report=updated)
        row=cx.execute("SELECT *FROM cases WHERE id=?",(v.id,)).fetchone();wf._assess_and_commit(cx,s,row,wf._now_iso())
    after=wf.view(context,v.id)
    assert any(i.field_or_rule=="expense:arithmetic:return" for i in after.issues)
    assert not any(i.status in ("ISSUED","PARTIAL")for i in after.instructions)

async def test_exception_cannot_store_client_forged_source_refs(tmp_path):
    from tests.s6_seeding import _workflow,_seed,_issues,TENANT,ACCOUNTANT,ACTIVITY
    from invoice_referee.domain.commands import Decide
    from invoice_referee.domain.issues import DecisionCommand
    from invoice_referee.domain.common import EvidenceRef
    from invoice_referee.workflow.service import UnsupportedCommandError
    wf=_workflow(tmp_path);root,_=await _seed(wf,consistent=True)
    issue=next(i for i in _issues(wf,root)if i["field_or_rule"]=="expense:2:missing_evidence")
    actor=wf.start_session(tenant=TENANT,persona="accountant",actor_id=ACCOUNTANT)
    card=wf.question_card(actor,root,issue["id"])
    context=CommandContext(session_id=actor.session_id,actor_id=actor.actor_id,command_id="cmd:bad-ref",expected_case_version=card.case_version)
    command=Decide(root_id=root,decision=DecisionCommand(issue_ids=(issue["id"],),basis_id=card.basis_id,actions=("EXCEPT_POLICY",),effect_scope=ACTIVITY,amount=1500000,reason="Đồng ý ngoại lệ có căn cứ",refs=(EvidenceRef(source_id="source:foreign",source_sha256="b"*64,page=1,exact_quote="Không phải căn cứ hiện hành"),)))
    with pytest.raises(UnsupportedCommandError):await wf.execute(context,command)
    with wf.db.connect()as cx:assert cx.execute("SELECT COUNT(*)FROM case_exception_decisions").fetchone()[0]==0

async def test_accountant_cannot_apply_employee_declaration_correction(tmp_path):
    """Valid employee correction tokens do not confer the employee's identity."""
    wf,employee,view,report=await seed_input(tmp_path)
    issue=next(i for i in view.issues if i.field_or_rule=="expense:arithmetic:return")
    card=wf.question_card(employee,view.id,issue.id)
    accountant=wf.start_session(tenant=employee.tenant,persona="accountant",actor_id="employee:accountant-demo")
    def snapshot():
        with wf.db.connect() as cx:
            return {table:[tuple(r)for r in cx.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                    for table in ("cases","case_declarations","case_declaration_corrections",
                                  "case_evidence_reports","case_issues","instructions","money_events")}
    before=snapshot()
    app=create_app(wf,mode="RECORDED_REPLAY",frontend_dir=None)
    async with AsyncClient(transport=ASGITransport(app),base_url="http://test")as client:
        client.cookies.set(SESSION_COOKIE,accountant.session_id)
        response=await client.post(f"/api/cases/{view.id}/issues/{issue.id}/corrections",json={
            "basis_id":card.basis_id,"correction_id":card.corrections[0].id,
            "reason":"Kế toán thử điều chỉnh số hoàn thay cho nhân viên đứng tên hồ sơ"},
            headers={"X-Expected-Version":str(view.version),"X-Command-Id":"cmd:accountant-cannot-revise-employee"})
    assert response.status_code==400,response.text
    assert response.json()["code"]=="UNSUPPORTED_COMMAND"
    assert "Chỉ nhân viên đứng tên" in response.text
    assert snapshot()==before
