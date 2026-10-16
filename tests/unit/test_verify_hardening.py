import pytest
from invoice_referee.evaluation.scorer import ActualResult,ActualIssue,ActualInstruction,IndependentScorer
from invoice_referee.evaluation.packets import load_gold
from pathlib import Path
from invoice_referee.domain.common import EvidenceRef
import hashlib
D=Path(__file__).resolve().parents[2]/"data/verify/cases"
def gold(case):return load_gold(D/case,stage_id="ban-dau")
def routine(**overrides):
 data=dict(root_id="activity:tc01",mode="RECORDED_REPLAY",state="READY_TO_EXECUTE",instructions=(ActualInstruction(direction="COLLECT",amount=760000,owner="employee:employee-a"),))
 sha=hashlib.sha256((D/"tc01/dau-vao/01-nop-ban-dau/hoa_don_dien_tu.pdf").read_bytes()).hexdigest()
 data.update(money_refs=(EvidenceRef(source_id="invoice",source_sha256=sha,page=1,exact_quote="3.240.000"),),source_documents={"invoice":{"digest":sha,"pages":{"1":"3.240.000"}}})
 data.update(money_states={k:"KNOWN"for k in ("E","A","P","R","S")},money_values={"E":3240000,"A":4000000,"P":0,"R":0,"S":-760000})
 data.update(overrides);return ActualResult(**data)
def test_missing_beneficiary_fails():
 assert not IndependentScorer().score(routine(instructions=(ActualInstruction(direction="COLLECT",amount=760000),)),gold("tc01")).passed
def test_blocking_issue_with_expected_instruction_fails():
 assert not IndependentScorer().score(routine(issues=(ActualIssue(kind="FACT",owner="employee"),)),gold("tc01")).passed
def test_balanced_unknown_R_S_fails():
 a=ActualResult(root_id="b",mode="STUB",state="WAITING",conclusion_status="BALANCED",money_states={"A":"KNOWN","P":"KNOWN","R":"UNKNOWN","S":"UNKNOWN"})
 assert not IndependentScorer().score(a,gold("vfy-bal-01")).passed
def test_duplicate_rows_are_not_four_cases():
 sc=IndependentScorer();row=sc.score(routine(),gold("tc01"))
 assert not sc.release_gate([row]*4,total_human=0,expected_count=4).release
def test_wrong_question_and_extra_issue_fails():
 a=ActualResult(root_id="tc06",mode="STUB",state="WAITING",issues=(ActualIssue(kind="FACT",owner="employee",question="Bạn khỏe không?",field_or_rule="unrelated"),ActualIssue(kind="POLICY",owner="approver",question="Duyệt đi")))
 assert not IndependentScorer().score(a,gold("tc06")).passed

def test_balanced_known_zero_and_clean_execution_passes():
 a=ActualResult(root_id="b",mode="STUB",state="SETTLED",conclusion_status="BALANCED",money_states={k:"KNOWN"for k in ("E","A","P","R","S")},money_values={"S":0})
 g=gold("vfy-bal-01");g=g.model_copy(update={"allowed":g.allowed.model_copy(update={"money_source_digests":(),"expected_money":{}})})
 assert IndependentScorer().score(a,g).passed
 assert not IndependentScorer().score(a.model_copy(update={"pending_execution":True}),g).passed

def test_structured_question_checks_two_source_quotes_and_all_issues():
 from invoice_referee.evaluation.models import GoldPacket
 from invoice_referee.domain.common import EvidenceRef
 g=GoldPacket.model_validate_json('{"latent":{"facts":{}},"observable":{"facts":{}},"allowed":{"route":"FACT","owner":"employee","question_required":true,"expected_issues":[{"kind":"FACT","owner":"employee","field_or_rule":"amount:dispute","question_values":["900000","700000","200000"],"source_digests":["'+('a'*64)+'","'+('b'*64)+'"],"required_quotes":["900000","700000"]}]}}')
 refs=(EvidenceRef(source_id="p",source_sha256="a"*64,page=1,exact_quote="Khai 900000"),EvidenceRef(source_id="r",source_sha256="b"*64,page=1,exact_quote="Thu 700000"))
 issue=ActualIssue(kind="FACT",owner="employee",field_or_rule="amount:dispute",question="Giấy 900.000, chứng từ 700.000, lệch 200.000; xác nhận khoản đúng?",refs=refs)
 a=ActualResult(root_id="x",mode="STUB",state="WAITING",issues=(issue,),source_documents={"p":{"digest":"a"*64,"pages":{"1":"Khai 900000"}},"r":{"digest":"b"*64,"pages":{"1":"Thu 700000"}}})
 sc=IndependentScorer();assert sc.score(a,g).passed
 assert not sc.score(a.model_copy(update={"source_documents":{}}),g).passed
 assert not sc.score(a.model_copy(update={"issues":(issue.model_copy(update={"refs":(refs[0],)}),)}),g).passed
 assert not sc.score(a.model_copy(update={"issues":(issue,issue)}),g).passed

def test_valid_money_requires_real_source_reference_not_boolean():
 sc=IndependentScorer();a=routine();assert sc.score(a,gold("tc01")).passed
 assert not sc.score(a.model_copy(update={"money_refs":()}),gold("tc01")).passed
 assert not sc.score(a.model_copy(update={"source_documents":{}}),gold("tc01")).passed

def test_unexecuted_draft_is_not_successful_unsupported_outcome():
 from tests.factories import _gold
 a=ActualResult(root_id="x",mode="STUB",state="DRAFT")
 assert not IndependentScorer().score(a,_gold("UNSUPPORTED")).passed

def test_nonzero_balanced_gold_rejects_all_zero_projection_with_valid_quote():
 g=gold("vfy-bal-01")
 sha=g.allowed.money_source_digests[0]
 a=ActualResult(root_id="b",mode="STUB",state="SETTLED",conclusion_status="BALANCED",money_states={k:"KNOWN"for k in ("E","A","P","R","S")},money_values={k:0 for k in ("E","A","P","R","S")},money_refs=(EvidenceRef(source_id="invoice",source_sha256=sha,page=1,exact_quote="2.160.000"),),source_documents={"invoice":{"digest":sha,"pages":{"1":"2.160.000"}}})
 assert not IndependentScorer().score(a,g).passed
 correct=a.model_copy(update={"money_values":{"E":2160000,"A":2160000,"P":0,"R":0,"S":0}})
 assert IndependentScorer().score(correct,g).passed

def test_contract_human_rule_ids_are_in_oracle():
 assert gold("tc06").allowed.expected_issues[0].field_or_rule=="expense:arithmetic:return"
 assert gold("tc04").allowed.expected_issues[0].field_or_rule=="RECOGNIZE_COST"

def test_runner_rejects_nonexistent_authority_reference():
 from types import SimpleNamespace as N
 from invoice_referee.evaluation.runner import actual_from_view
 from invoice_referee.evaluation.packets import load_input
 packet=load_input(D/"tc01",stage_id="ban-dau")
 money=N(**{k:N(state="KNOWN",value=v)for k,v in {"E":3240000,"A":4000000,"P":0,"R":0,"S":-760000}.items()})
 view=N(state="READY_TO_EXECUTE",employee="employee:employee-a",activity="activity:tc01",issues=[],actual_money=money,conclusion=N(status="OUTSTANDING"),instructions=[N(direction="COLLECT",amount=760000,authority_refs=("grant:DOES-NOT-EXIST",),execution_state="NOT_STARTED")])
 actual=actual_from_view(view,packet,mode="STUB",elapsed_ms=0)
 assert actual.instructions[0].refs_ok is False

def test_authority_reference_matches_action_scope_and_amount():
 from types import SimpleNamespace as N
 from invoice_referee.evaluation.runner import _instruction_authority_valid
 from invoice_referee.evaluation.packets import load_input
 import copy
 packet=load_input(D/"tc01",stage_id="ban-dau")
 grant=next(g for g in packet.organization.grants if g["actor"]=="system:referee" and "ISSUE_COLLECTION" in g["actions"])
 inst=N(direction="COLLECT",amount=760000,authority_refs=(grant["id"],))
 view=N(activity="activity:tc01")
 assert _instruction_authority_valid(inst,view,packet)
 for over in [{"scope":"activity:other"},{"actions":["RECOGNIZE_COST"]},{"max_amount":1},{"effective_to":"2026-10-01T00:00:00+07:00"}]:
  altered=copy.deepcopy(grant);altered.update(over)
  bad=packet.model_copy(update={"organization":packet.organization.model_copy(update={"grants":(altered,)})})
  assert not _instruction_authority_valid(inst,view,bad)

def test_actual_arithmetic_card_matches_independent_tc06_oracle():
 from tests.unit.test_document_arithmetic import _paper
 from invoice_referee.reconciliation.document_arithmetic import check_document_arithmetic
 g=gold("tc06");finding=check_document_arithmetic(_paper(declared_advance="3800000",printed_total="2970000",printed_return="770000"))[0]
 digest=g.allowed.expected_issues[0].source_digests[0]
 refs=tuple(ref.model_copy(update={"source_sha256":digest})for ref in finding.refs)
 issue=ActualIssue(kind="FACT",owner="employee",field_or_rule=finding.field_or_rule,question=finding.question,basis=finding.basis,refs=refs)
 a=ActualResult(root_id="tc06",mode="STUB",state="WAITING",issues=(issue,),source_documents={"s":{"digest":digest,"pages":{"1":"3800000 2970000 770000"}}})
 assert IndependentScorer().score(a,g).passed
 wrong=issue.model_copy(update={"question":"Số tiền khác?","basis":"Không có số liệu"})
 assert not IndependentScorer().score(a.model_copy(update={"issues":(wrong,)}),g).passed
