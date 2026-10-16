"""Bounded isolated Verify runs. Gold stays outside workflow/provider inputs."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC,datetime
from pathlib import Path
from time import monotonic
from invoice_referee.config import Settings
from invoice_referee.domain.case import CommandContext
from invoice_referee.domain.commands import ActivityData,AttachSources,CreateDraft,Declaration,SourceUpload,Submit
from invoice_referee.evaluation.packets import load_input,load_gold,bind_sources,load_stub_readings
from invoice_referee.evaluation.runner import actual_from_view,EvaluationRunner
from invoice_referee.evaluation.scorer import ActualResult,IndependentScorer,ScoreRow
from invoice_referee.evaluation.suites import VERIFY_CORE,VERIFY_ESCALATION
from invoice_referee.evidence.reader import FileOcrReader
from invoice_referee.evidence.replay import ReplayReader,ReplayClassifier,MissingRecordingError,validate_recording
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow
PROJECT_ROOT=Path(__file__).resolve().parents[3]
DEFAULT_VERIFY_DATA_DIR=PROJECT_ROOT/"data/verify"
DEFAULT_RUNTIME_VERIFY_DIR=PROJECT_ROOT/".runtime/verify"
_RUN_LOCK=asyncio.Lock()

class DatasetError(ValueError): pass

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate_dataset(data_dir,ids):
    root=Path(data_dir).resolve()
    manifest=root/"manifest.json"
    if not manifest.is_file() or manifest.is_symlink():raise DatasetError("DATASET_INVALID: missing manifest")
    data=json.loads(manifest.read_text());files=data.get("files")
    if not isinstance(files,dict) or not files:raise DatasetError("DATASET_INVALID: missing locked file hashes")
    actual=set()
    for path in root.rglob("*"):
        if path.is_symlink():raise DatasetError("DATASET_INVALID: symlinks forbidden")
        if path.is_file() and path.name!="manifest.json":actual.add(path.relative_to(root).as_posix())
    if actual!=set(files):raise DatasetError("DATASET_INVALID: missing or extra files")
    for rel,sha in files.items():
        path=root/rel
        if not path.resolve().is_relative_to(root) or not path.is_file() or digest(path)!=sha:
            raise DatasetError("DATASET_INVALID: path or digest mismatch: "+rel)
    cases={}
    roots=set()
    for path in (root/"cases").iterdir():
        if not path.is_dir():continue
        cid=json.loads((path/"cau-hinh/kich-ban.json").read_text())["case_id"]
        packet=load_input(path,stage_id="ban-dau")
        roles=json.loads((path/"cau-hinh/kich-ban.json").read_text()).get("upload_roles",{})
        if set(roles)!={s.filename for s in packet.sources} or list(roles.values()).count("paper")!=1 or any(v not in ("paper","evidence") for v in roles.values()):raise DatasetError("DATASET_INVALID: upload roles incomplete")
        if cid in cases or packet.root_id in roots:raise DatasetError("DATASET_INVALID: duplicate member/root")
        roots.add(packet.root_id);cases[cid]=(path,packet.root_id)
    if set(cases)!=set(VERIFY_ESCALATION) or any(cid not in cases for cid in ids):
        raise DatasetError("DATASET_INVALID: suite membership mismatch")
    entry_roots=[entry["root_id"] for entry in data.get("entries",[])]
    if len(entry_roots)!=len(set(entry_roots)) or set(entry_roots)!=roots:
        raise DatasetError("DATASET_INVALID: manifest membership mismatch")
    return {cid:cases[cid]for cid in ids},digest(manifest)

class CaptureOcr:
    def __init__(self,provider):self.provider=provider;self.source_documents={}
    @property
    def model(self):return getattr(self.provider,"model",None)
    @property
    def provider_name(self):return getattr(self.provider,"provider_name",type(self.provider).__name__)
    async def ocr_file(self,source,**kwargs):
        result=await self.provider.ocr_file(source,**kwargs)
        self.source_documents[source.id]={"digest":source.digest,"pages":{str(p.page):p.markdown for p in result.pages}}
        return result

def code_version():
    return hashlib.sha256("".join(str(p.relative_to(PROJECT_ROOT))+digest(p) for p in sorted((PROJECT_ROOT/"src").rglob("*.py"))).encode()).hexdigest()

def safe_config(settings):
    return {key:getattr(settings,key,None)for key in ("llm_provider","kimi_model","kimi_reasoning_effort","mistral_ocr_model")}

async def _run_single_case(case_dir,*,mode,case_work_dir,scorer,settings=None):
    packet=load_input(case_dir,stage_id="ban-dau")
    db=Database(case_work_dir/"app.sqlite");db.migrate()
    as_of=datetime.fromisoformat(packet.organization.financial_as_of or "2026-10-16T12:00:00+07:00")
    workflow=CaseWorkflow(db,uploads_dir=case_work_dir/"uploads",clock=lambda:as_of)
    workflow.import_company_context(packet.organization,origin="SIMULATED")
    if mode=="STUB":
        packet=packet.model_copy(update={"transcription":load_stub_readings(case_dir,stage_id="ban-dau")})
        actual=await EvaluationRunner(workflow=workflow).run(packet,mode)
        return scorer.score(actual,load_gold(case_dir,stage_id="ban-dau"))
    if mode=="RECORDED_REPLAY":
        path=case_dir/"recordings/recording.json"
        if not path.is_file():raise MissingRecordingError("NEEDS_RECORDING: missing recording")
        data=json.loads(path.read_text());bindings={}
        provider=ReplayReader(data,bindings=bindings);llm=ReplayClassifier(data,bindings=bindings)
        from invoice_referee.evidence.prompts import role_aware_reader_identity
        # Recorded identity includes current prompts/profiles/schema and captured model config.
        identity=role_aware_reader_identity(reader=provider,classifier=llm,activity_profile=packet.profile)
        validate_recording(data,reader_identity=identity,source_digests={s.sha256 for s in packet.sources})
    elif mode=="LIVE":
        settings=settings or Settings()
        if settings.missing_for_live():raise ValueError("LIVE_SETTINGS_MISSING")
        from invoice_referee.runtime import build_llm_client
        from invoice_referee.evidence.live_reader import build_file_ocr_provider
        provider=build_file_ocr_provider(settings=settings);llm=build_llm_client(settings)
    else:raise ValueError("Unsupported verify mode")
    capture=CaptureOcr(provider)
    source_bytes={s.sha256:bind_sources(case_dir,packet,stage_id="ban-dau")(s)for s in packet.sources}
    workflow.enable_evidence_read(reader=FileOcrReader(provider=capture),classifier=llm,artifacts_root=case_work_dir/"artifacts",source_bytes=source_bytes,provider_mode=mode)
    session=workflow.start_session(tenant=packet.organization.tenant,actor_id=packet.submission.employee)
    def ctx(version):return CommandContext(session_id=session.session_id,actor_id=session.actor_id,command_id="verify:"+uuid.uuid4().hex,expected_case_version=version)
    start=monotonic()
    created=await workflow.execute(ctx(0),CreateDraft(activity_data=ActivityData(activity_id=packet.submission.activity,name=packet.submission.activity,occurred_at=as_of,declared_purpose=packet.submission.declared_purpose)))
    root=created.case_view.id
    uploads=[]
    roles=json.loads((case_dir/"cau-hinh/kich-ban.json").read_text())["upload_roles"]
    for s in packet.sources:
        role=roles[s.filename]
        key=f"{session.tenant}/{root}/{s.filename}"
        dest=workflow.uploads_dir/key;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(source_bytes[s.sha256])
        uploads.append(SourceUpload(filename=s.filename,media=s.media,digest=s.sha256,storage_key=key,upload_role=role))
    attached=await workflow.execute(ctx(created.case_view.version),AttachSources(root_id=root,uploads=tuple(uploads)))
    await workflow.execute(ctx(attached.case_view.version),Submit(root_id=root,declaration=Declaration(activity_id=packet.submission.activity,declared_purpose=packet.submission.declared_purpose)))
    await workflow.run_evidence_job_for(root)
    view=workflow.view(ctx(0),root)
    actual=actual_from_view(view,packet,mode=mode,elapsed_ms=(monotonic()-start)*1000,source_documents=capture.source_documents)
    (case_work_dir/"actual.json").write_text(actual.model_dump_json(indent=2))
    # Independent gold is loaded only after the actual output exists.
    return scorer.score(actual,load_gold(case_dir,stage_id="ban-dau"))

def _atomic_json(path,value):
    temp=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n")
    os.replace(temp,path)

async def run_isolated_verify(suite,mode="RECORDED_REPLAY",*,data_dir=None,runtime_dir=None,settings=None):
    # One bounded execution at a time per demo process, no unbounded queue.
    if _RUN_LOCK.locked():raise ValueError("VERIFY_BUSY: another run is active")
    async with _RUN_LOCK:
        suite=suite.strip().lower();mode=mode.upper()
        if mode=="LIVE":settings=settings or Settings()
        ids={"core":VERIFY_CORE,"escalation":VERIFY_ESCALATION}.get(suite)
        if ids is None or mode not in ("LIVE","RECORDED_REPLAY","STUB"):raise ValueError("Unknown verify suite/mode")
        runtime=Path(runtime_dir)if runtime_dir is not None else DEFAULT_RUNTIME_VERIFY_DIR
        runtime.mkdir(parents=True,exist_ok=True)
        started=datetime.now(UTC);run_id=f"vfy-{started.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        run_dir=runtime/("run-"+run_id);run_dir.mkdir()
        data_dir=Path(data_dir)if data_dir is not None else DEFAULT_VERIFY_DATA_DIR
        dataset_hash=None;preflight=None
        try:members,dataset_hash=validate_dataset(data_dir,ids)
        except (ValueError,KeyError,OSError) as error:members={};preflight="DATASET_INVALID: "+str(error)
        rows=[];attempted=0;completed=0;scorer=IndependentScorer();errors=[]
        expected_ids=tuple(members[cid][1]if cid in members else cid for cid in ids)
        report={"run_id":run_id,"started_at":started.isoformat(),"finished_at":None,"suite":suite,"mode":mode,"status":"RUNNING","planned":len(ids),"attempted":0,"completed":0,"passed":0,"release":False,"rows":[]}
        _atomic_json(run_dir/"report.json",report)
        start=monotonic()
        for cid in ids:
            path,root_id=members.get(cid,(None,cid))
            work=run_dir/cid.lower();work.mkdir()
            try:
                if preflight:raise DatasetError(preflight)
                attempted+=1
                row=await asyncio.wait_for(_run_single_case(path,mode=mode,case_work_dir=work,scorer=scorer,settings=settings),timeout=150)
                if row.root_id!=root_id:raise DatasetError("DATASET_INVALID: result root mismatch")
                if row.technical_failure:
                    errors.append("EXECUTION_ERROR")
                else:
                    completed+=1
            except Exception as error:
                code="NEEDS_RECORDING" if isinstance(error,MissingRecordingError) else "DATASET_INVALID" if isinstance(error,DatasetError) else "EXECUTION_ERROR"
                errors.append(code)
                row=ScoreRow(root_id=root_id,technical_failure=1,expected_route="UNKNOWN",actual_route="TECHNICAL",passed=False,failure_reasons=(f"{code}: {type(error).__name__}: {str(error)[:200]}",))
            rows.append(row)
            report.update(attempted=attempted,completed=completed,passed=sum(r.passed for r in rows),rows=[r.model_dump(mode="json")for r in rows])
            _atomic_json(run_dir/"report.json",report)
        gate=scorer.release_gate(rows,total_human=sum(r.expected_route in ("FACT","POLICY","AUTHORITY") for r in rows),expected_count=len(ids),expected_ids=expected_ids)
        report.update(finished_at=datetime.now(UTC).isoformat(),status="NEEDS_RECORDING" if errors and all(e=="NEEDS_RECORDING"for e in errors) else "ERROR" if errors else "COMPLETED",release=gate.release and completed==len(ids) and mode!="STUB",union_dangerous_miss=gate.union_dangerous_miss,dangerous_miss_rate=gate.dangerous_miss_rate,completion_rate=gate.completion_rate,elapsed_ms=(monotonic()-start)*1000,versions={"code":code_version(),"config":hashlib.sha256(json.dumps(safe_config(settings),sort_keys=True).encode()).hexdigest(),"dataset":dataset_hash,"recording":"exact-request-v2"},question_review="NOT_REVIEWED",models={"requested":getattr(settings,"kimi_model",None) if mode=="LIVE" else None,"returned":None,"effort_requested":getattr(settings,"kimi_reasoning_effort",None) if mode=="LIVE" else None,"effort_observed":None})
        _atomic_json(run_dir/"report.json",report);_atomic_json(runtime/"last.json",report)
        return report

def get_last_verify_report(runtime_dir=None):
    target=(Path(runtime_dir)if runtime_dir is not None else DEFAULT_RUNTIME_VERIFY_DIR)/"last.json"
    if not target.is_file():return None
    try:return json.loads(target.read_text())
    except (ValueError,OSError):return None
