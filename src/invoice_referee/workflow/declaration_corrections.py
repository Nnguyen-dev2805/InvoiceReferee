"""Explicit employee declaration revisions; original read/PDF remains immutable."""
from __future__ import annotations
import json
import uuid
from invoice_referee.domain.common import EvidenceRef,parse_vnd
from invoice_referee.domain.issues import DeclarationCorrectionOption,DeclaredChange
from invoice_referee.reconciliation.authority import fingerprint
from invoice_referee.reconciliation.document_arithmetic import is_settlement_summary_row

def found(fields,name):
    f=next((f for f in fields if f.field==name and f.state=="FOUND"),None)
    return parse_vnd(f.value) if f is not None else None

def source_basis(report):
    # Only cost documents named by the paper bind the declaration revision.
    # A later company payout receipt does not invalidate an unchanged claim.
    papers=[d for d in report.documents if d.document_type=="SETTLEMENT_FORM"]
    refs=set()
    for p in papers:
        for line in p.line_items:
            c=next((f for f in line.fields if f.field=="invoice_refs" and f.state=="FOUND"),None)
            if c is not None:
                refs.update(c.value if isinstance(c.value,(tuple,list)) else (c.value,))
    docs=[d for d in report.documents if d.document_type=="SETTLEMENT_FORM" or any(f.field in ("document_number","transaction_reference") and f.state=="FOUND" and f.value in refs for f in d.fields)]
    return fingerprint({"reader":report.reader_identity,"documents":[d.model_dump(mode="json")for d in docs]})

def options(report,issue):
    papers=[d for d in report.documents if d.document_type=="SETTLEMENT_FORM" and d.profile_status=="CLEAR"]
    if len(papers)!=1:return ()
    paper=papers[0];changes=[]
    advance=found(paper.fields,"declared_advance");total=found(paper.fields,"printed_total")
    field={"expense:arithmetic:return":"printed_return","expense:arithmetic:reimburse":"printed_reimbursement"}.get(issue.field_or_rule)
    if field and advance is not None and total is not None:
        before=found(paper.fields,field)
        after=max(advance-total,0)if field=="printed_return" else max(total-advance,0)
        if before is not None and before!=after:changes=[DeclaredChange(field=field,before=before,after=after)]
    elif "allocation" in issue.field_or_rule:
        from invoice_referee.evidence.matching import cross_document_conflicts
        conflicts=cross_document_conflicts(paper,report.documents)
        conflict=next((c for c in conflicts if any(ref in issue.refs for ref in (*c.row_refs,*c.doc_refs))),None)
        if conflict is not None and len(conflict.item_ids)==1:
            row_id=conflict.item_ids[0]
            changes=[DeclaredChange(field="amount",row_id=row_id,before=conflict.paper_amount,after=conflict.document_total)]
            values=[]
            for i,line in enumerate(paper.line_items,1):
                desc=next((f.value for f in line.fields if f.field=="description" and f.state=="FOUND"),"")
                if is_settlement_summary_row(str(desc)):continue
                value=conflict.document_total if f"ITEM-{i:03d}"==row_id else found(line.fields,"amount")
                if value is None:return ()
                values.append(value)
            revised=sum(values)
            if total is None:return ()
            if total!=revised:changes.append(DeclaredChange(field="printed_total",before=total,after=revised))
            if advance is not None:
                for field,after in [("printed_return",max(advance-revised,0)),("printed_reimbursement",max(revised-advance,0))]:
                    before=found(paper.fields,field)
                    if before is not None and before!=after:changes.append(DeclaredChange(field=field,before=before,after=after))
    if not changes:return ()
    identifier="claim:"+fingerprint([c.model_dump(mode="json")for c in changes])
    return (DeclarationCorrectionOption(id=identifier,label="Điều chỉnh kê khai theo căn cứ đã đối chiếu",changes=tuple(changes)),)

def saved_corrections(cx,tenant,root):
    return tuple(json.loads(r["payload_json"])for r in cx.execute("SELECT payload_json FROM case_declaration_corrections WHERE tenant=? AND root_id=? ORDER BY observed_at,rowid",(tenant,root)))

def effective_report(cx,row,report):
    basis=source_basis(report)
    for entry in saved_corrections(cx,row["tenant"],row["id"]):
        if entry["source_basis"]!=basis:continue
        docs=[]
        for doc in report.documents:
            if doc.document_type!="SETTLEMENT_FORM":docs.append(doc);continue
            fields=doc.fields;lines=list(doc.line_items)
            for raw in entry["changes"]:
                change=DeclaredChange.model_validate(raw)
                target=fields if change.row_id is None else lines[int(change.row_id.split("-")[-1])-1].fields
                if found(target,change.field)!=change.before:continue
                quote=f"Nhân viên kê khai điều chỉnh {change.field}: {change.before} thành {change.after}. {entry['reason']}"
                ref=EvidenceRef(source_id=entry["id"],source_sha256=entry["digest"],record_key=change.row_id or change.field,exact_quote=quote)
                target=tuple(f.model_copy(update={"value":str(change.after),"refs":(ref,),"alternatives":()})if f.field==change.field else f for f in target)
                if change.row_id is None:fields=target
                else:
                    index=int(change.row_id.split("-")[-1])-1;lines[index]=lines[index].model_copy(update={"fields":target})
            docs.append(doc.model_copy(update={"fields":fields,"line_items":tuple(lines)}))
        report=report.model_copy(update={"documents":tuple(docs)})
        paper=next((d for d in report.documents if d.document_type=="SETTLEMENT_FORM"),None)
        if paper is not None:
            from invoice_referee.evidence.matching import match_paper_evidence
            matched=match_paper_evidence(paper,tuple(d for d in report.documents if d.document_type!="SETTLEMENT_FORM"))
            report=report.model_copy(update={"links":matched.links,"row_matches":matched.rows,"match_findings":matched.findings})
    return report

def persist_correction(wf,cx,session,context,row,command):
    from invoice_referee.workflow.service import UnsupportedCommandError
    from invoice_referee.workflow.question_cards import build_card
    from invoice_referee.domain.evidence import ReadResult
    wf._require_version(row,context.expected_case_version)
    if row["state"]=="STOPPED" or session.persona!="employee" or session.actor_id!=row["employee"]:
        raise UnsupportedCommandError("Chỉ nhân viên đứng tên hồ sơ đang hoạt động được sửa kê khai.")
    card=build_card(wf,cx,session,row,command.issue_id)
    if card.basis_id!=command.basis_id:raise UnsupportedCommandError("Căn cứ đã thay đổi. Hãy tải lại thẻ.")
    choice=next((c for c in card.corrections if c.id==command.correction_id),None)
    if choice is None:raise UnsupportedCommandError("Không có phương án điều chỉnh hợp lệ cho nguồn hiện tại.")
    raw=cx.execute("SELECT report_json FROM case_evidence_reports WHERE root_id=?",(row["id"],)).fetchone()
    report=ReadResult.model_validate_json(raw["report_json"])
    now=wf._now_iso();entry={"id":"declaration:"+uuid.uuid4().hex,"source_basis":source_basis(report),"changes":[c.model_dump(mode="json")for c in choice.changes],"actor":session.actor_id,"reason":command.reason,"observed_at":now}
    entry["digest"]=fingerprint(entry)
    cx.execute("INSERT INTO case_declaration_corrections(id,tenant,root_id,source_basis,payload_json,observed_at)VALUES(?,?,?,?,?,?)",(entry["id"],session.tenant,row["id"],entry["source_basis"],json.dumps(entry,ensure_ascii=False),now))
    previous=cx.execute("SELECT purpose,notes,draft_json FROM case_declarations WHERE root_id=? ORDER BY revision DESC LIMIT 1",(row["id"],)).fetchone()
    draft=json.loads(previous["draft_json"])if previous else {};draft["correction"]=entry
    cx.execute("INSERT INTO case_declarations(root_id,revision,purpose,notes,draft_json,created_at)VALUES(?,?,?,?,?,?)",(row["id"],wf._next_declaration_revision(cx,row["id"]),previous["purpose"]if previous else row["activity_name"],command.reason,json.dumps(draft,ensure_ascii=False),now))
    wf._bump(cx,row,now)
    # A real declaration revision, not an OCR re-read or a money event.
    wf._audit(cx,tenant=session.tenant,root_id=row["id"],session_id=session.session_id,actor=context.actor_id,action="CORRECT_DECLARATION",detail=json.dumps(entry,ensure_ascii=False))
