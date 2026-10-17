import json
from tests.unit.test_disputed_amount_admission import _paper,_invoice
from invoice_referee.domain.evidence import ReadResult
from invoice_referee.evidence.matching import match_paper_evidence
from invoice_referee.workflow.declaration_corrections import effective_report,source_basis

async def test_amount_revision_recomputes_allocation_without_reusing_old_dispute(app_fixture):
    created=await app_fixture.create(employee="employee:employee-a",activity="activity:travel-a")
    paper,invoice=_paper(),_invoice();invoice=invoice.model_copy(update={"fields":tuple(f.model_copy(update={"refs":tuple(r.model_copy(update={"source_id":invoice.source_id})for r in f.refs)})for f in invoice.fields)});matching=match_paper_evidence(paper,(invoice,))
    report=ReadResult(provider_mode="RECORDED_REPLAY",data_origin="RECORDED_REPLAY",documents=(paper,invoice),links=matching.links,row_matches=matching.rows,match_findings=matching.findings)
    assert report.links[0].status=="SUGGEST_LINK"
    entry={"id":"declaration:test","digest":"b"*64,"source_basis":source_basis(report),"reason":"Sửa khoản chi theo hóa đơn đã đối chiếu","changes":[{"field":"amount","row_id":"ITEM-001","before":3500000,"after":3240000},{"field":"printed_total","before":3500000,"after":3240000},{"field":"printed_return","before":500000,"after":760000}]}
    with app_fixture.db.transaction()as cx:
        cx.execute("INSERT INTO case_declaration_corrections(id,tenant,root_id,source_basis,payload_json,observed_at)VALUES(?,?,?,?,?,?)",(entry["id"],"tenant:demo",created.case_view.id,entry["source_basis"],json.dumps(entry),"2026-10-16"))
        row=cx.execute("SELECT *FROM cases WHERE id=?",(created.case_view.id,)).fetchone()
        revised=effective_report(cx,row,report)
    assert revised.links[0].status=="AUTO_LINK"
    assert revised.links[0].allocated_amount==3240000
    assert paper.line_items[0].fields[1].value=="3500000"
