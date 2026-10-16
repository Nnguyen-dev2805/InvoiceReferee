import pytest
from invoice_referee.evidence.replay import ReplayReader,ReplayClassifier,MissingRecordingError
from invoice_referee.domain.evidence import SourceRef
@pytest.mark.asyncio
async def test_missing_ocr_confidence_stays_unknown():
 s=SourceRef(id="s",digest="a"*64,tenant="t",media="PDF",storage_key="x")
 r=await ReplayReader({"ocr":{"a"*64:{"pages":[{"page":1,"markdown":"amount 999","blocks":[]}]}}}).ocr_file(s)
 assert not any(w.confidence is not None for b in r.pages[0].blocks for w in b.words)
@pytest.mark.asyncio
async def test_role_only_recording_is_not_valid_llm_replay():
 with pytest.raises(MissingRecordingError):
  await ReplayClassifier({"extractions":{"evidence":{"document_type":"E_INVOICE"}}}).complete_json(system="changed",user='{"upload_role": "evidence"}')

@pytest.mark.asyncio
async def test_exact_replay_two_sources_and_changed_prompt():
 from invoice_referee.evidence.replay import request_key,canonical_request
 bindings={"source:old":"<SOURCE:a>","source:other":"<SOURCE:b>"}
 calls={}
 for source,amount in [("source:old",100),("source:other",200)]:
  user='{"source_id": "'+source+'", "upload_role": "evidence"}'
  calls[request_key("schema-v2",user,bindings)]={"request":canonical_request("schema-v2",user,bindings),"response":{"amount":amount}}
 replay=ReplayClassifier({"calls":calls},bindings={"source:new":"<SOURCE:a>","source:second":"<SOURCE:b>"})
 assert (await replay.complete_json(system="schema-v2",user='{"source_id": "source:new", "upload_role": "evidence"}'))["amount"]==100
 assert (await replay.complete_json(system="schema-v2",user='{"source_id": "source:second", "upload_role": "evidence"}'))["amount"]==200
 with pytest.raises(MissingRecordingError):await replay.complete_json(system="schema-v3",user='{"source_id": "source:new", "upload_role": "evidence"}')
