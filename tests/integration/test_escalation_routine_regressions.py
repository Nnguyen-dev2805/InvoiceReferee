import pytest
from tests.escalation_evidence import seed_input
from tests.escalation_shapes import scenario
@pytest.mark.parametrize("cid,direction,amount",[("tc01","COLLECT",760000),("tc02","PAY",400000),("vfy-bal-01",None,0)])
async def test_three_typed_admission_routines_have_no_escalation(tmp_path,cid,direction,amount):
    wf,session,v,report=await seed_input(tmp_path,cid)
    assert not v.issues,[(i.field_or_rule,i.basis)for i in v.issues]
    for axis in ("E","A","P","R","S"):assert getattr(v.actual_money,axis).state=="KNOWN"
    if direction:
        assert len(v.instructions)==1
        assert v.instructions[0].direction==direction and v.instructions[0].amount==amount
        assert v.state=="READY_TO_EXECUTE"
    else:assert v.state=="SETTLED" and not v.instructions

async def test_missing_payer_or_history_are_not_suppressed_for_routine_points(app_fixture,monkeypatch):
    v=await scenario(app_fixture,monkeypatch,cost=3240000,advance=4000000,payer=False,coverage=False)
    assert not v.instructions
    assert {"expense:payer","ledger:coverage"}.issubset({i.field_or_rule for i in v.issues})
