"""Execution closure uses current version, scoped authority and source proof."""
import pytest
from invoice_referee.domain.commands import MarkExecution
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.workflow.service import UnsupportedCommandError, StaleCommandError

async def setup_case(app_fixture):
    v = await app_fixture.submit_packet("coverage-e6", mode="STUB")
    session = app_fixture.workflow.start_session(tenant="tenant:demo", persona="accountant", actor_id="employee:accountant-demo")
    with app_fixture.db.transaction() as cx:
        cx.execute("INSERT INTO context_grants (grant_id,tenant,version,actor,actions_json,scope,max_amount,effective_from,effective_to) VALUES (?,?,?,?,?,?,?,?,?)", ("grant:test-execution","tenant:demo","test","employee:accountant-demo",'["RECORD_ACTUAL"]',v.activity,20000000,"2026-01-01T00:00:00+00:00","2027-01-01T00:00:00+00:00"))
    return v, session

def ctx(f, s, v, version=None):
    from invoice_referee.domain.case import CommandContext
    return CommandContext(session_id=s.session_id, actor_id=s.actor_id, command_id=f.new_command_id(), expected_case_version=v.version if version is None else version)

async def test_execution_stale_is_rejected(app_fixture):
    v,s = await setup_case(app_fixture)
    with pytest.raises(StaleCommandError):
        await app_fixture.workflow.execute(ctx(app_fixture,s,v,0), MarkExecution(root_id=v.id,instruction_id=v.instructions[0].id,execution_state="OPEN",reason="Bắt đầu thực hiện"))

@pytest.mark.parametrize("bad", ["foreign-instruction", "no-proof", "unknown-source", "no-grant"])
async def test_execution_invalid_close_is_atomic(app_fixture,bad):
    v,s = await setup_case(app_fixture)
    if bad == "no-grant":
        s=app_fixture.workflow.start_session(tenant="tenant:demo",persona="accountant",actor_id="employee:ungranted")
    refs=() if bad=="no-proof" else (EvidenceRef(source_id="source:absent" if bad=="unknown-source" else v.sources[0].id,source_sha256=v.sources[0].digest,page=1,exact_quote="Đã hoàn tất"),)
    with pytest.raises(UnsupportedCommandError):
        await app_fixture.workflow.execute(ctx(app_fixture,s,v),MarkExecution(root_id=v.id,instruction_id="instruction:absent" if bad=="foreign-instruction" else v.instructions[0].id,execution_state="CLOSED_CONFIRMED",refs=refs,reason="Đã kiểm chứng thực hiện"))
    current=app_fixture.workflow.view(ctx(app_fixture,s,v),v.id)
    assert current.version==v.version
    assert current.instructions[0].execution_state=="NOT_STARTED"

async def test_mark_execution_route_requires_version(app_fixture):
    v,s = await setup_case(app_fixture)
    from invoice_referee.api.routes import SESSION_COOKIE
    client=app_fixture.fresh_client();client.cookies.set(SESSION_COOKIE,s.session_id)
    r=await client.post(f"/api/cases/{v.id}/mark-execution",json={"instruction_id":v.instructions[0].id,"execution_state":"OPEN","reason":"Bắt đầu thực hiện"},headers={"X-Command-Id":app_fixture.new_command_id()})
    assert r.status_code==400
    r=await client.post(f"/api/cases/{v.id}/mark-execution",json={"instruction_id":v.instructions[0].id,"execution_state":"OPEN","reason":"Bắt đầu thực hiện"},headers={"X-Command-Id":app_fixture.new_command_id(),"X-Expected-Version":str(v.version)})
    assert r.status_code==200,r.text
    assert r.json()["case_view"]["version"]>v.version


async def test_execution_close_persists_version_audit_and_idempotency(app_fixture):
    v,s=await setup_case(app_fixture)
    ref=EvidenceRef(source_id=v.sources[0].id,source_sha256=v.sources[0].digest,page=1,exact_quote="Chứng từ đã kiểm tra")
    command=MarkExecution(root_id=v.id,instruction_id=v.instructions[0].id,execution_state="CLOSED_CONFIRMED",refs=(ref,),reason="Đã kết thúc đợt thực hiện, phần chưa chi giữ theo lệnh")
    context=ctx(app_fixture,s,v)
    result=await app_fixture.workflow.execute(context,command)
    assert result.case_view.version>v.version
    assert result.case_view.instructions[0].execution_state=="CLOSED_CONFIRMED"
    assert result.case_view.instructions[0].remaining==4000000
    assert result.case_view.state!="SETTLED"
    replay=await app_fixture.workflow.execute(context,command)
    assert replay.duplicate_command
    assert replay.case_view.version==result.case_view.version


async def test_fulfilled_money_does_not_hide_open_execution(app_fixture):
    v,s=await setup_case(app_fixture)
    paid=await app_fixture.record_received(instruction_amount=4000000,received=4000000)
    assert paid.instructions[0].status=="FULFILLED"
    assert paid.actual_money.S.value==0
    unknown=await app_fixture.workflow.execute(ctx(app_fixture,s,paid),MarkExecution(root_id=paid.id,instruction_id=paid.instructions[0].id,execution_state="UNKNOWN",reason="Chưa xác minh đợt chi đã kết thúc"))
    assert unknown.case_view.state=="WAITING"
    ref=EvidenceRef(source_id=paid.sources[0].id,source_sha256=paid.sources[0].digest,page=1,exact_quote="Đã nhận đủ")
    closed=await app_fixture.workflow.execute(ctx(app_fixture,s,unknown.case_view),MarkExecution(root_id=paid.id,instruction_id=paid.instructions[0].id,execution_state="CLOSED_CONFIRMED",refs=(ref,),reason="Đã xác minh đợt chi kết thúc"))
    assert closed.case_view.state=="SETTLED"


async def test_dossier_recheck_preserves_record_scope_and_does_not_assert_opening(app_fixture):
    v,s=await setup_case(app_fixture)
    paid=await app_fixture.record_received(instruction_amount=4000000,received=4000000)
    from invoice_referee.workflow.money_history import record_dossier_history
    from datetime import datetime,UTC
    with app_fixture.db.transaction() as cx:
        row=cx.execute("SELECT * FROM cases WHERE id=?",(paid.id,)).fetchone()
        assert record_dossier_history(cx,row,actor=s.actor_id,now=datetime.now(UTC))
    from invoice_referee.api.routes import SESSION_COOKIE
    client=app_fixture.fresh_client();client.cookies.set(SESSION_COOKIE,s.session_id)
    r=await client.post(f"/api/cases/{paid.id}/money-history/recheck",json={"reason":"Đã đối chiếu các giao dịch đã ghi nhận cho hồ sơ"},headers={"X-Command-Id":app_fixture.new_command_id(),"X-Expected-Version":str(paid.version)})
    assert r.status_code==200,r.text
    import json
    saved=app_fixture.query_one("SELECT coverage_json FROM case_coverage_records ORDER BY rowid DESC LIMIT 1")
    coverage=json.loads(saved["coverage_json"])
    assert coverage["source"]=="DOSSIER_RECORDS"
    assert coverage.get("opening_balance") is None
    assert "ban đầu" not in coverage["reason"]
    assert r.json()["case_view"]["version"]>paid.version

async def test_dossier_recheck_requires_existing_dossier_checkpoint(app_fixture):
    v,s=await setup_case(app_fixture)
    from invoice_referee.api.routes import SESSION_COOKIE
    client=app_fixture.fresh_client();client.cookies.set(SESSION_COOKIE,s.session_id)
    r=await client.post(f"/api/cases/{v.id}/money-history/recheck",json={"reason":"Đã kiểm tra toàn bộ các khoản trong hồ sơ"},headers={"X-Command-Id":app_fixture.new_command_id(),"X-Expected-Version":str(v.version)})
    assert r.status_code==400,r.text


@pytest.mark.parametrize("guard", ["scope","profile","amount","expired"])
async def test_execution_grant_dimensions_are_enforced(app_fixture,guard):
    v,s=await setup_case(app_fixture)
    with app_fixture.db.transaction() as cx:
        changes={"scope":("scope","activity:other"),"profile":("allowed_profiles_json",'["OTHER"]'),"amount":("max_amount",1),"expired":("effective_to","2026-01-02T00:00:00+00:00")}
        column,value=changes[guard]
        cx.execute(f"UPDATE context_grants SET {column}=? WHERE grant_id='grant:test-execution'",(value,))
    with pytest.raises(UnsupportedCommandError,match="quyền"):
        await app_fixture.workflow.execute(ctx(app_fixture,s,v),MarkExecution(root_id=v.id,instruction_id=v.instructions[0].id,execution_state="OPEN",reason="Bắt đầu thực hiện"))

async def test_dossier_recheck_rejects_unresolved_events(app_fixture):
    v,s=await setup_case(app_fixture)
    paid=await app_fixture.record_received(instruction_amount=4000000,received=4000000)
    from invoice_referee.workflow.money_history import record_dossier_history
    from datetime import datetime,UTC
    import json
    with app_fixture.db.transaction() as cx:
        row=cx.execute("SELECT * FROM cases WHERE id=?",(paid.id,)).fetchone()
        assert record_dossier_history(cx,row,actor=s.actor_id,now=datetime.now(UTC))
        event=cx.execute("SELECT id,payload_json FROM money_events WHERE root_id=?",(paid.id,)).fetchone()
        payload=json.loads(event["payload_json"]);payload["verification_state"]="OBSERVED"
        cx.execute("UPDATE money_events SET payload_json=? WHERE id=?",(json.dumps(payload),event["id"]))
    from invoice_referee.api.routes import SESSION_COOKIE
    client=app_fixture.fresh_client();client.cookies.set(SESSION_COOKIE,s.session_id)
    r=await client.post(f"/api/cases/{paid.id}/money-history/recheck",json={"reason":"Đã kiểm tra các khoản trong hồ sơ"},headers={"X-Command-Id":app_fixture.new_command_id(),"X-Expected-Version":str(paid.version)})
    assert r.status_code==400,r.text
    assert "chưa xác minh" in r.json()["detail"]
