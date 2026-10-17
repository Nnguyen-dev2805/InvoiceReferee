"""Offline question-card rehearsal; isolated DBs only, no provider capture claim."""
from __future__ import annotations
import asyncio,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.escalation_evidence import seed_input
from tests.escalation_shapes import scenario,actor_context
from tests.conftest import AppFixture
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.documents import FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.domain.commands import AttachSources,SourceUpload
class FixtureMap:
 def setitem(self,d,k,v):d[k]=v
OUT=ROOT/".runtime/escalation-answerability/browser"
async def main():
 OUT.mkdir(parents=True,exist_ok=True);manifest={}
 for name,cid in [("fact","tc06"),("collect","tc01"),("pay","tc02"),("balanced","vfy-bal-01")]:
  folder=OUT/name;folder.mkdir(exist_ok=True)
  wf,s,v,report=await seed_input(folder,cid)
  manifest[name]={"root_id":v.id,"db":str(folder/"app.sqlite"),"mode":"RECORDED_REPLAY","session":s.session_id}
 for name,cost,advance in [("authority",9000000,8000000),("compound",9000000,1000000),("over",25000000,24000000)]:
  folder=OUT/name;folder.mkdir(exist_ok=True);f=AppFixture(folder)
  v=await scenario(f,FixtureMap(),cost=cost,advance=advance)
  # Materialize literal STUB source bytes so the PDF viewer has real input.
  from reportlab.pdfgen import canvas
  from reportlab.pdfbase import pdfmetrics
  from reportlab.pdfbase.ttfonts import TTFont
  pdfmetrics.registerFont(TTFont("NotoFixture",str(ROOT/"assets/fonts/NotoSans-Regular.ttf")))
  path=f.workflow.uploads_dir/v.sources[0].storage_key;path.parent.mkdir(parents=True,exist_ok=True)
  c=canvas.Canvas(str(path));c.setFont("NotoFixture",14)
  for i,text in enumerate(["MÔ PHỎNG: kiểm thử thẻ quyết định",f"Chi phí {cost}",f"Nhân viên đã trả {cost}",f"Ứng {advance}","Sổ đã đối chiếu đầy đủ"]):c.drawString(50,780-i*35,text)
  c.showPage();c.save();digest=hashlib.sha256(path.read_bytes()).hexdigest()
  ctx=actor_context(f,v)
  with f.db.transaction()as cx:
   cx.execute("UPDATE case_sources SET digest=? WHERE root_id=?",(digest,v.id))
   row=cx.execute("SELECT *FROM cases WHERE id=?",(v.id,)).fetchone()
   f.workflow._assess_and_commit(cx,f.workflow.session(ctx.session_id),row,f.workflow._now_iso())
  s=f.workflow.start_session(tenant="tenant:demo",persona="approver",actor_id="employee:approver")
  manifest[name]={"root_id":v.id,"db":str(folder/"app.sqlite"),"mode":"STUB","session":s.session_id}
  await f.close()
 (OUT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 print(json.dumps(manifest,indent=2))
if __name__=="__main__":asyncio.run(main())
