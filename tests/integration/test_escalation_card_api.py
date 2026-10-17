import pytest
from httpx import AsyncClient,ASGITransport
from invoice_referee.api.app import create_app
from invoice_referee.api.routes import SESSION_COOKIE
from tests.escalation_evidence import seed_input
from tests.escalation_shapes import scenario,actor_context

async def test_card_get_is_read_only_and_contains_tc06_values(tmp_path):
    wf,s,v,_=await seed_input(tmp_path)
    issue=next(i for i in v.issues if i.field_or_rule=="expense:arithmetic:return")
    def dump():
        with wf.db.connect()as cx:return tuple(cx.iterdump())
    before=dump()
    async with AsyncClient(transport=ASGITransport(app=create_app(wf,mode="RECORDED_REPLAY",frontend_dir=None)),base_url="http://test")as client:
        client.cookies.set(SESSION_COOKIE,s.session_id)
        r=await client.get(f"/api/cases/{v.id}/issues/{issue.id}/card")
        assert r.status_code==200,r.text
        card=r.json();text=str(card)
        for value in ("3800000","2970000","830000","770000","60000"):assert value in text.replace(".","")
        assert card["response_kind"]=="CORRECT_DECLARATION" and card["excerpt_refs"]
        assert dump()==before
        other=await client.get(f"/api/cases/{v.id}/issues/issue:foreign/card")
        assert other.status_code==404
        assert dump()==before

async def test_over_ceiling_card_explains_no_approval(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch,cost=25000000,advance=24000000)
    ctx=actor_context(app_fixture,v);i=next(i for i in v.issues if i.kind=="AUTHORITY")
    card=app_fixture.workflow.question_card(app_fixture.workflow.session(ctx.session_id),v.id,i.id)
    assert card.actions[0].amount==25000000 and card.actions[0].limit==20000000
    assert not card.actions[0].authorized and "cấp có quyền cao hơn" in card.actions[0].unavailable_reason
