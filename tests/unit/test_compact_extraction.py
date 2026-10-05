"""Compact wire output must retain facts, provenance and fail-closed gates."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from invoice_referee.domain.models import AnalysisRequest, DomainError, SourceBlock, SourceRegistry, SourceWord
from invoice_referee.extraction.providers import LiveProviders, analysis_payload, _http_client
from invoice_referee.extraction.compact import source_catalog
from tests.builders import routine_snapshot, text_registry


def request(*, score='0.99', amount='1200000'):
    return AnalysisRequest(evidence=routine_snapshot().evidence[0],
        registry=text_registry(evidence_id='e-1', score=score, amount=amount),
        required_fields=['merchant','date','currency','total'], threshold_version='test-085')


def field(raw, source, *, reading='READABLE', verify=False):
    return {'raw':raw,'src':[source],'reading':reading,'verify':verify}


def wire(*, amount='1200000', template='TOTAL_ONLY'):
    # IDs correspond to the independent fixture's four header and five item loci.
    return {'kind':'BILL','template':template,
        'fields':{'merchant':field('Nhà cung cấp Demo','r1'),
                  'date':field('2026-10-01','r2'), 'currency':field('VND','r3'),
                  'total':field(amount,'r4')},
        'items':[], 'covered_item_regions':[], 'adjustment_terms':[]}


class Client:
    def __init__(self, responses):
        self.responses=iter(responses)
        self.calls=[]
    def post(self, path, json):
        self.calls.append(json)
        content=next(self.responses)
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'choices':[{'message':{'content':content}}]}
        return Response()


def analyze(value, req=None):
    encoded=json.dumps(value,ensure_ascii=False)
    return LiveProviders(chat_client=Client([encoded,encoded])).analyze(req or request())


def test_compact_output_builds_domain_fact_and_owned_source():
    result=analyze(wire())
    total=result.fields['total']
    assert total.normalized_value=='1200000'
    assert total.usability=='USABLE'
    assert total.source_kind=='DOCUMENT'
    assert total.refs[0].evidence_id=='e-1'
    assert (total.refs[0].page_index,total.refs[0].block_id)==(0,'b-1')
    assert total.refs[0].raw_value=='1200000'
    assert total.normalization_trace


def test_payload_uses_unique_source_ids_even_for_repeated_locator_names():
    req=request()
    duplicate=req.registry.blocks[0].model_copy(update={'block_id':'other',
        'words':[SourceWord(id='other-word',text='other merchant',score='0.99')],
        'locators':{'merchant':['other-word']},'text':'other merchant'})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[*req.registry.blocks,duplicate]})})
    payload=analysis_payload(req)
    refs=payload['sources']
    assert len({r['id'] for r in refs})==len(refs)
    assert sum(r['text']=='other merchant' for r in refs)==1
    assert all(set(r)=={'id','text','tokens'} for r in refs)
    assert payload['schema_version']=='compact-document-v1'


@pytest.mark.parametrize('score',[None,'0.50'])
def test_compact_clear_reading_never_waives_missing_or_low_scores(score):
    assert analyze(wire(),request(score=score)).fields['total'].usability=='UNCERTAIN'


def test_compact_unknown_reading_is_retained_as_uncertain():
    value=wire()
    value['fields']['total']=field('1200000','r4',reading='UNKNOWN',verify=True)
    assert analyze(value).fields['total'].usability=='UNCERTAIN'


def test_required_field_omitted_is_missing_not_zero():
    value=wire();del value['fields']['total']
    result=analyze(value)
    assert result.fields['total'].usability=='MISSING'
    assert result.fields['total'].normalized_value is None


def test_ambiguous_number_is_not_normalized_to_a_favorable_value():
    result=analyze(wire(amount='1.234'),request(amount='1.234'))
    assert result.fields['total'].usability=='UNCERTAIN'
    assert result.fields['total'].normalized_value is None


def test_compact_adjustment_terms_are_carried_onto_the_document():
    value=wire();value['adjustment_terms']=['subtotal','tax']
    result=analyze(value)
    assert result.declared_adjustment_terms==['subtotal','tax']


@pytest.mark.parametrize('terms',[['vat'],['tax','tax']])
def test_compact_rejects_unknown_or_duplicate_adjustment_terms(terms):
    value=wire();value['adjustment_terms']=terms
    with pytest.raises(DomainError) as exc:analyze(value)
    assert exc.value.code=='INVALID_ANALYSIS'


@pytest.mark.parametrize('mutation',[
    lambda v:v['fields']['total'].update(src=['foreign-id']),
    lambda v:v['fields']['total'].update(reading='UNKNOWN',verify=False),
    lambda v:v['fields']['total'].update(usability='USABLE'),
])
def test_unknown_refs_and_quality_bypass_output_fail_closed(mutation):
    value=wire();mutation(value)
    with pytest.raises(DomainError) as exc:analyze(value)
    assert exc.value.code=='INVALID_ANALYSIS'


def table_request():
    req=request()
    rows=[('row1','| Item A | 2 | 100 | 200 |'),('row2','| Item B | 3 | 100 | 300 |')]
    block=SourceBlock(evidence_id='e-1',page_index=0,block_id='table',
        text='| Name | SL | ĐG | TT |\n|---|---|---|---|\n'+ '\n'.join(v for _,v in rows),
        words=[SourceWord(id=f'{k}-{i}',text=cell.strip(),score='0.99')
               for k,v in rows for i,cell in enumerate(v.strip('|').split('|'))],
        locators={k:[f'{k}-{i}' for i in range(4)] for k,_ in rows})
    return req.model_copy(update={'registry':req.registry.model_copy(update={
        'blocks':[req.registry.blocks[0],block],'uncovered_item_regions':['table']})})


def line(name,source,quantity='2',amount='200'):
    return {'name':field(name,source),'quantity':field(quantity,source),'unit':None,
            'unit_price':field('100',source),'line_amount':field(amount,source)}


def test_compact_itemized_output_cannot_drop_a_recognized_source_row():
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[line('Item A','r5')]
    with pytest.raises(DomainError) as exc:analyze(value,table_request())
    assert exc.value.code=='INVALID_ANALYSIS'


def test_compact_items_keep_rows_and_reject_duplicate_row_claims():
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[line('Item A','r5'),line('Item B','r6','3','300')]
    result=analyze(value,table_request())
    assert len(result.items)==2
    assert result.items[1].line_amount.normalized_value=='300'
    value['items']=[line('Item A','r5'),line('Item A','r5'),line('Item B','r6','3','300')]
    with pytest.raises(DomainError):analyze(value,table_request())


def test_repair_keeps_schema_and_previous_output_and_budget():
    valid=json.dumps(wire(),ensure_ascii=False)
    client=Client(['{"bad":"wire"}',valid])
    provider=LiveProviders(chat_client=client)
    result=provider.analyze(request())
    assert result.fields['total'].normalized_value=='1200000'
    second=client.calls[1]
    assert second['messages'][0]['content'].startswith(client.calls[0]['messages'][0]['content'])
    assert any(m['role']=='assistant' and m['content']=='{"bad":"wire"}' for m in second['messages'])
    assert provider.repair_calls==1
    assert all(0<c['max_tokens']<=8192 for c in client.calls)


def test_transport_deadline_bounds_worker_without_network(monkeypatch):
    import httpx
    class SlowClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):await asyncio.sleep(0.08)
    class SlowSyncClient:
        def __init__(self,**kwargs):pass
        def post(self,*args,**kwargs):time.sleep(0.08)
    monkeypatch.setattr(httpx,'AsyncClient',SlowClient)
    monkeypatch.setattr(httpx,'Client',SlowSyncClient)
    client=_http_client('test-key','https://invalid.example/v1',0.02)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(client.post,'/chat/completions',json={})
        with pytest.raises(TimeoutError):future.result(timeout=0.5)


def test_truncated_response_is_not_accepted_or_repaired():
    class LimitedClient(Client):
        def post(self, path, json):
            self.calls.append(json)
            class Response:
                def raise_for_status(self):pass
                def json(self):return {'choices':[{'finish_reason':'length',
                    'message':{'content':__import__('json').dumps(wire(),ensure_ascii=False)}}],
                    'usage':{'completion_tokens':8192}}
            return Response()
    client=LimitedClient([])
    provider=LiveProviders(chat_client=client)
    with pytest.raises(DomainError) as exc:provider.analyze(request())
    assert exc.value.code=='INVALID_ANALYSIS'
    assert len(client.calls)==1
    assert provider.repair_calls==0


def test_fractional_output_budget_is_rejected():
    with pytest.raises(DomainError):LiveProviders(max_output_tokens=1.5)


def test_quantity_and_price_parse_from_source_grounded_vi_format():
    req=table_request()
    block=req.registry.blocks[-1]
    text='| Gà | 1,65 | 255.000 | 420.750 |'
    block=block.model_copy(update={'text':'| Name | SL | ĐG | TT |\n|---|---|---|---|\n'+text,
        'words':[SourceWord(id=f'one-row-{i}',text=cell.strip(),score='0.99') for i,cell in enumerate(text.strip('|').split('|'))],
        'locators':{'one-row':[f'one-row-{i}' for i in range(4)]}})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={
        'blocks':[req.registry.blocks[0],block]})})
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[{'name':field('Gà','r5'),'quantity':field('1,65','r5'),'unit':None,
                    'unit_price':field('255.000','r5'),'line_amount':field('420.750','r5')}]
    result=analyze(value,req)
    assert result.items[0].quantity.normalized_value=='1.65'
    assert result.items[0].unit_price.normalized_value=='255000'
    assert result.items[0].line_amount.normalized_value=='420750'


def test_compact_source_values_remain_subject_to_arithmetic_gate():
    from invoice_referee.policy.decision import evaluate
    from invoice_referee.domain.models import EvidenceBundle
    req=table_request()
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[line('Item A','r5'),line('Item B','r6','3','300')]
    result=analyze(value,req)
    decision=evaluate(routine_snapshot(),EvidenceBundle(documents=[result],registries={'e-1':req.registry}))
    # Two lines total 500, requested/primary total 1200000: cannot auto-approve.
    assert decision.action=='REQUEST_INFO'
    assert any(c.rule_id=='AMT-02' and c.status=='FAIL' for c in decision.checks)


def test_total_only_cannot_hide_a_table_when_native_regions_are_missing():
    req=table_request()
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'uncovered_item_regions':[]})})
    with pytest.raises(DomainError) as exc:analyze(wire(),req)
    assert exc.value.code=='INVALID_ANALYSIS'


def test_word_source_disambiguates_equal_price_and_line_values_without_fake_scores():
    req=table_request()
    block=req.registry.blocks[-1]
    text='| Item A | 1 | 100 | 100 |'
    words=[SourceWord(id=f'cell-{i}',text=t,score='0.20' if i==3 else '0.99')
           for i,t in enumerate(('Item A','1','100','100'))]
    block=block.model_copy(update={'text':'| Name | SL | ĐG | TT |\n|---|---|---|---|\n'+text,
                                  'words':words,'locators':{'row':['cell-0','cell-1','cell-2','cell-3']}})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[req.registry.blocks[0],block]})})
    tokens=next(row['tokens'] for row in analysis_payload(req)['sources'] if row['id']=='r5')
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[{'name':field('Item A',tokens[0]['id']),'quantity':field('1',tokens[1]['id']),
        'unit':None,'unit_price':field('100',tokens[2]['id']),'line_amount':field('100',tokens[3]['id'])}]
    result=analyze(value,req)
    assert result.items[0].unit_price.usability=='USABLE'
    assert result.items[0].line_amount.usability=='UNCERTAIN'
    assert result.items[0].line_amount.refs[0].raw_value=='100'


def test_invalid_or_zero_quantity_rows_cannot_be_silently_dropped():
    req=table_request()
    block=req.registry.blocks[-1]
    text='| Item A | 0 | 100 | 100 |\n| Item B | 3 | 100 | 300 |'
    values=('Item A','0','100','100','Item B','3','100','300')
    block=block.model_copy(update={'text':'| Name | SL | ĐG | TT |\n|---|---|---|---|\n'+text,
        'words':[SourceWord(id=f'cell-{i}',text=value,score='0.99') for i,value in enumerate(values)],
        'locators':{'row1':[f'cell-{i}' for i in range(4)],'row2':[f'cell-{i}' for i in range(4,8)]}})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[req.registry.blocks[0],block]})})
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table']
    value['items']=[line('Item B','r6','3','300')]
    with pytest.raises(DomainError):analyze(value,req)


@pytest.mark.parametrize('source',['1 2','1|2'])
def test_source_digits_are_not_concatenated_into_a_new_number(source):
    req=request()
    header=req.registry.blocks[0]
    words=[w.model_copy(update={'text':source}) if w.id=='w-total' else w for w in header.words]
    header=header.model_copy(update={'words':words})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[header,*req.registry.blocks[1:]]})})
    result=analyze(wire(amount='12'),req)
    assert result.fields['total'].usability=='UNCERTAIN'
    assert result.fields['total'].normalized_value is None


def test_low_quality_or_out_of_scope_numeric_hint_cannot_resolve_total_locale():
    req=request(amount='1.234')
    block=SourceBlock(evidence_id='e-1',page_index=0,block_id='hint',text='1,2',
        words=[SourceWord(id='hint-word',text='1,2',score='0.01')],locators={'hint':['hint-word']})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[*req.registry.blocks,block]})})
    value=wire(amount='1.234')
    value['fields']['quantity']=field('1,2','r10',reading='UNKNOWN',verify=True)
    result=analyze(value,req)
    assert result.fields['total'].usability=='UNCERTAIN'
    assert result.fields['total'].normalized_value is None


def test_unknown_quantity_item_row_cannot_be_dropped():
    req=table_request()
    block=req.registry.blocks[-1]
    rows=['| Item A | 2 | 100 | 200 |','| Item B | ? | 100 | 300 |']
    words=[SourceWord(id=f'r{r}-c{c}',text=value.strip(),score='0.99')
           for r,line_text in enumerate(rows) for c,value in enumerate(line_text.strip('|').split('|'))]
    block=block.model_copy(update={'text':'| Name | SL | ĐG | TT |\n|---|---|---|---|\n'+'\n'.join(rows),
        'words':words,'locators':{f'row{r+1}':[f'r{r}-c{c}' for c in range(4)] for r in range(2)}})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[req.registry.blocks[0],block]})})
    value=wire(template='SIMPLE_ITEMIZED');value['covered_item_regions']=['table'];value['items']=[line('Item A','r5')]
    with pytest.raises(DomainError):analyze(value,req)


def test_dns_does_not_extend_worker_request_deadline(monkeypatch):
    import socket
    def slow_dns(*args,**kwargs):
        time.sleep(0.4)
        raise OSError('synthetic resolver failure')
    monkeypatch.setattr(socket,'getaddrinfo',slow_dns)
    client=_http_client('test-key','https://invalid.example/v1',0.02)
    with ThreadPoolExecutor(max_workers=1) as pool:
        started=time.monotonic()
        future=pool.submit(client.post,'/chat/completions',json={})
        with pytest.raises(TimeoutError):future.result(timeout=1)
        assert time.monotonic()-started<0.25


def _two_line_header(line1, line2, loc1='merchant', loc2='merchant2'):
    # Two ADJACENT OCR lines, as a wrapped legal name produces on a real bill.
    req=request()
    header=req.registry.blocks[0]
    words=[]
    for w in header.words:
        if w.id=='w-merchant':
            words.append(w.model_copy(update={'text':line1}))
            words.append(SourceWord(id='w-extra',text=line2,score='0.99'))
        else:
            words.append(w)
    header=header.model_copy(update={'words':words,
        'locators':{**header.locators,loc2:['w-extra']}})
    req=req.model_copy(update={'registry':req.registry.model_copy(update={'blocks':[header,*req.registry.blocks[1:]]})})
    ids={ref.raw_value:key for key,ref in source_catalog(req).items()}
    return req,ids


def test_value_wrapped_across_two_cited_lines_still_grounds():
    # A legal name wrapped across two OCR lines cites both; the value must ground
    # against their COMBINED words and normalize, not fail as UNCERTAIN.
    req,ids=_two_line_header('CÔNG TY',' SEN NAM BỘ')
    value=wire();value['fields']['merchant']={'raw':'CÔNG TY SEN NAM BỘ',
        'src':[ids['CÔNG TY'],ids[' SEN NAM BỘ']],'reading':'READABLE','verify':False}
    result=analyze(value,req)
    assert result.fields['merchant'].usability=='USABLE'
    assert result.fields['merchant'].normalized_value=='CÔNG TY SEN NAM BỘ'


def test_wrapped_value_cannot_join_digits_across_the_two_lines():
    # Grounding against combined sources must STILL refuse digit concatenation.
    req,ids=_two_line_header('1','2',loc1='total',loc2='total2')
    value=wire(amount='12');value['fields']['total']={'raw':'12',
        'src':[ids['1'],ids['2']],'reading':'READABLE','verify':False}
    result=analyze(value,req)
    assert result.fields['total'].usability=='UNCERTAIN'
    assert result.fields['total'].normalized_value is None
