"""Literal offline inputs, not expected output injected into app."""
from invoice_referee.domain.case import CommandContext
from tests.conftest import TEST_PACKETS
async def scenario(f,monkeypatch,*,cost=9000000,advance=8000000,payer=True,coverage=True):
    facts=[{"field":"incurred","value":cost,"role":"INVOICE","quote":f"Chi phí {cost}"}]
    if payer:facts.append({"field":"paid_employee","value":cost,"role":"PAYMENT","quote":f"Nhân viên đã trả {cost}"})
    facts.append({"field":"advance","value":advance,"role":"ADVANCE","quote":f"Ứng {advance}"})
    if coverage:facts.append({"field":"coverage","value":1,"role":"LEDGER","quote":"Sổ đã đối chiếu đầy đủ"})
    monkeypatch.setitem(TEST_PACKETS,"card-scenario",{"facts":facts})
    return await f.submit_packet("card-scenario",mode="STUB")
def actor_context(f,view,*,persona="approver",actor="employee:approver",version=None,command_id=None):
    s=f.workflow.start_session(tenant="tenant:demo",persona=persona,actor_id=actor)
    return CommandContext(session_id=s.session_id,actor_id=actor,command_id=command_id or f.new_command_id(),expected_case_version=view.version if version is None else version)
