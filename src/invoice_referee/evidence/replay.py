"""Exact provider-response replay. Synthetic fixtures are never real recordings."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from invoice_referee.domain.documents import OcrBlock,OcrPage,OcrSourceResult,OcrWord
from invoice_referee.domain.evidence import SourceRef

class MissingRecordingError(TimeoutError,RuntimeError):
    pass

def _load_data(target):
    if isinstance(target,dict): return target
    if target is not None and Path(target).is_file(): return json.loads(Path(target).read_text())
    return {}

def canonical_request(system: str,user: str,bindings: dict[str,str] | None=None) -> dict:
    def replace(text):
        for old,new in sorted((bindings or {}).items(),key=lambda p:len(p[0]),reverse=True):
            text=text.replace(old,new)
        return text
    system,user=replace(system),replace(user)
    try: payload=json.loads(user)
    except ValueError: payload=user
    return {"system":system,"user":payload}

def request_key(system: str,user: str,bindings: dict[str,str] | None=None) -> str:
    return hashlib.sha256(json.dumps(canonical_request(system,user,bindings),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def validate_recording(data: dict,*,reader_identity: str,source_digests: set[str]):
    meta=data.get("metadata",{})
    if meta.get("origin")!="LIVE_PROVIDER_CAPTURE" or meta.get("reader_identity")!=reader_identity:
        raise MissingRecordingError("NEEDS_RECORDING: compatible real provider capture unavailable")
    if not meta.get("captured_at") or not meta.get("llm_model") or not meta.get("ocr_model"):
        raise MissingRecordingError("NEEDS_RECORDING: incomplete provider metadata")
    if set(data.get("ocr",{}))!=source_digests or not isinstance(data.get("calls"),dict) or not data["calls"]:
        raise MissingRecordingError("NEEDS_RECORDING: source/call inventory mismatch")
    return data

class ReplayReader:
    def __init__(self,recording=None,*,bindings=None):
        self._data=_load_data(recording);self.bindings=bindings if bindings is not None else {}
        self.source_documents={}
    @property
    def tag(self): return "RECORDED_REPLAY"
    @property
    def provider_name(self): return self._data.get("metadata",{}).get("ocr_provider","UNKNOWN")
    @property
    def model(self): return self._data.get("metadata",{}).get("ocr_model","UNKNOWN")
    async def ocr_file(self,source: SourceRef,*,budget=None,artifacts=None,source_bytes=b"",expected_pages=None,root_id=""):
        if source_bytes and hashlib.sha256(source_bytes).hexdigest()!=source.digest:
            raise MissingRecordingError("NEEDS_RECORDING: source bytes/digest mismatch")
        recorded=self._data.get("ocr",{}).get(source.digest)
        if not isinstance(recorded,dict): raise MissingRecordingError(f"no OCR recording for {source.digest}")
        token=f"<SOURCE:{source.digest}>"
        self.bindings[source.id]=token
        self.bindings[source.storage_key]=f"<STORAGE:{source.digest}>"
        if root_id:self.bindings[root_id]="<ROOT>"
        pages=[]
        for p in recorded.get("pages",[]):
            blocks=tuple(OcrBlock(id=str(b.get("id") or b.get("block_id")),kind=str(b.get("kind") or b.get("type") or "text"),content=str(b.get("content", "")),bbox=b.get("bbox"),words=tuple(OcrWord(text=str(word.get("text","")),block_start=word.get("block_start"),block_end=word.get("block_end"),confidence=word.get("confidence"))for word in b.get("words",[]))) for b in p.get("blocks",[]))
            pages.append(OcrPage(page=int(p.get("page",1)),markdown=str(p.get("markdown","")),blocks=blocks))
        if not pages or (expected_pages is not None and len(pages)!=expected_pages):
            raise MissingRecordingError("NEEDS_RECORDING: incomplete OCR page inventory")
        self.source_documents[source.id]={"digest":source.digest,"pages":{str(p.page):p.markdown for p in pages}}
        return OcrSourceResult(source_id=source.id,source_digest=source.digest,provider="recorded-replay",model=self.model,pages=tuple(pages),complete=recorded.get("complete",False))
    async def ocr_page(self,source,page):
        for p in self._data.get("ocr",{}).get(source.digest,{}).get("pages",[]):
            if int(p.get("page",1))==page:return str(p.get("markdown",""))
        raise MissingRecordingError(f"no OCR recording for {source.digest}:{page}")

class ReplayClassifier:
    def __init__(self,recording=None,*,bindings=None):
        self._data=_load_data(recording);self.bindings=bindings if bindings is not None else {};self.calls=0
    @property
    def model(self):return self._data.get("metadata",{}).get("llm_model","UNKNOWN")
    @property
    def provider_name(self):return self._data.get("metadata",{}).get("llm_provider","UNKNOWN")
    @property
    def reasoning_effort(self):return self._data.get("metadata",{}).get("reasoning_effort")
    async def complete_json(self,*,system="",user="",budget=None):
        call=self._data.get("calls",{}).get(request_key(system,user,self.bindings))
        if not isinstance(call,dict) or call.get("request")!=canonical_request(system,user,self.bindings) or not isinstance(call.get("response"),dict):
            raise MissingRecordingError("NEEDS_RECORDING: no exact request/prompt/schema/source recording")
        self.calls+=1
        # Responses store canonical source placeholders; remap only registered IDs.
        text=json.dumps(call["response"],ensure_ascii=False)
        for actual,token in self.bindings.items():text=text.replace(token,actual)
        return json.loads(text)
