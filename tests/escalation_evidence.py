"""Synthetic typed admission fixtures from frozen input only; no provider claims."""
import json,hashlib
from pathlib import Path
from datetime import datetime
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow
from invoice_referee.domain.commands import CreateDraft,ActivityData,AttachSources,SourceUpload
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.domain.documents import DocumentAnalysis,DocumentLine,FieldCandidate
from invoice_referee.domain.common import EvidenceRef
from invoice_referee.domain.evidence import ReadResult
ROOT=Path(__file__).resolve().parents[1]
async def seed_input(tmp_path,cid="tc06"):
    folder=ROOT/"data/verify/cases"/cid
    org=OrganizationContext.model_validate_json((folder/"cau-hinh/to-chuc.json").read_text())
    db=Database(tmp_path/"app.sqlite");db.migrate();asof=datetime.fromisoformat(org.financial_as_of)
    wf=CaseWorkflow(db,uploads_dir=tmp_path/"uploads",clock=lambda:asof)
    wf.enable_evidence_read(reader=object(),classifier=object(),artifacts_root=tmp_path/"artifacts")
    wf.import_company_context(org,origin="SIMULATED")
    s=wf.start_session(tenant=org.tenant,persona="employee",actor_id="employee:employee-a")
    counter=0
    def ctx(version):
        nonlocal counter;counter+=1
        return CommandContext(session_id=s.session_id,actor_id=s.actor_id,command_id=f"cmd:fixture:{counter}",expected_case_version=version)
    v=(await wf.execute(ctx(0),CreateDraft(activity_data=ActivityData(activity_id=org.activity["activity_id"],name=org.activity["name"],occurred_at=asof,declared_purpose=org.activity["purpose"])))).case_view
    uploads=[]
    for f in sorted((folder/"dau-vao/01-nop-ban-dau").glob("*.pdf")):
        key=f"fixture/{f.name}";dest=wf.uploads_dir/key;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(f.read_bytes())
        uploads.append(SourceUpload(filename=f.name,media="PDF",digest=hashlib.sha256(f.read_bytes()).hexdigest(),storage_key=key,upload_role="paper" if "report" in f.name else "evidence"))
    v=(await wf.execute(ctx(v.version),AttachSources(root_id=v.id,uploads=tuple(uploads)))).case_view
    synthetic=json.loads((folder/"recordings/recording.json").read_text())
    docs=[]
    for source in v.sources:
        role="paper" if "report" in source.filename else "evidence";raw=synthetic["extractions"][role];dtype="SETTLEMENT_FORM" if role=="paper" else raw["document_type"]
        def fields(raw_fields):
            result=[]
            for f in raw_fields:
                refs=(EvidenceRef(source_id=source.id,source_sha256=source.digest,page=f.get("page",1),exact_quote=f.get("quote","")),)if f["state"]=="FOUND" else ()
                payload={"field":f["field"],"state":f["state"],"value":f.get("value"),"refs":[r.model_dump(mode="json")for r in refs]}
                result.append(FieldCandidate.model_validate_json(json.dumps(payload)))
            return tuple(result)
        docs.append(DocumentAnalysis(source_id=source.id,document_id=source.id+":"+dtype,document_type=dtype,roles=("SETTLEMENT_DECLARATION" if role=="paper" else "ORIGINAL_EXPENSE_EVIDENCE",),page_range=(1,1),fields=fields(raw["fields"]),line_items=tuple(DocumentLine(id=f"ITEM-{i:03d}",fields=fields(l["fields"]))for i,l in enumerate(raw.get("line_items",[]),1)),confidence_status="ASSESSED",profile_status="CLEAR"))
    report=ReadResult(provider_mode="RECORDED_REPLAY",data_origin="RECORDED_REPLAY",documents=tuple(docs))
    with wf.db.transaction() as cx:
        wf._publish_evidence_report(cx,tenant=org.tenant,root_id=v.id,report=report)
        row=cx.execute("SELECT * FROM cases WHERE id=?",(v.id,)).fetchone();wf._assess_and_commit(cx,s,row,wf._now_iso())
    return wf,s,wf.view(ctx(0),v.id),report
