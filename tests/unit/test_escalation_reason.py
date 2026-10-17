from tests.tc18_shapes import _admit,_paper,_invoice,_acceptance,_transfer,_org,AS_OF
from invoice_referee.domain.evidence import ReadResult,Confirmation
from invoice_referee.reconciliation.admission import admit_evidence

def test_responsible_reason_confirmation_resolves_only_reason_fact():
    paper=_paper();docs=(_invoice(),_acceptance(),_transfer())
    initial=_admit(paper,docs)
    issue=next(i for i in initial.admission_issues if i.field_or_rule=="expense:2:exception_reason")
    answer=Confirmation(fact_key=issue.field_or_rule,value="Nhà cung cấp không xuất hóa đơn",actor="employee:a",scope="activity:1",refs=issue.refs,reason="Tôi chịu trách nhiệm về kê khai bổ sung",observed_at=AS_OF)
    kwargs=dict(scope=initial.scope,organization=_org(),ledger=(),coverage=None,read_set=initial.read_set,as_of=AS_OF)
    report=ReadResult(provider_mode="RECORDED_REPLAY",data_origin="RECORDED_REPLAY",documents=(paper,*docs))
    after=admit_evidence(report,confirmations=(answer,),**kwargs)
    assert not any(i.field_or_rule=="expense:2:exception_reason" for i in after.admission_issues)
    assert any(i.field_or_rule=="expense:2:party_mismatch" for i in after.admission_issues)
    stale=answer.model_copy(update={"actor":"employee:other"})
    rejected=admit_evidence(report,confirmations=(stale,),**kwargs)
    assert any(i.field_or_rule=="expense:2:exception_reason" for i in rejected.admission_issues)
