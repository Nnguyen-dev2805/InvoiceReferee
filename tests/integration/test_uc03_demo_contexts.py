"""Real demo inputs are scoped financial fixtures, never expected outcomes."""
from datetime import datetime
import json
from pathlib import Path

from invoice_referee.config import Settings
from invoice_referee.domain.organization import OrganizationContext
from invoice_referee.runtime import build_workflow
from invoice_referee.workflow.context_records import load_context, context_ledger, context_coverage
from invoice_referee.workflow.db import Database
from invoice_referee.workflow.service import CaseWorkflow

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "data/demo"
AS_OF = datetime.fromisoformat("2026-10-16T12:00:00+07:00")
ADVANCES = [4_000_000,5_000_000,4_320_000,85_000_000,4_000_000,
            4_000_000,4_000_000,4_000_000,4_000_000,4_000_000,
            6_000_000,4_000_000,3_000_000,120_000_000,3_000_000,
            12_000_000,6_000_000,5_000_000,4_000_000,2_000_000,
            15_000_000,9_000_000,9_000_000,3_000_000,5_000_000]


def _manifest():
    return json.loads((DEMO / "manifest.json").read_text())


def test_demo_common_contains_only_current25_without_answer_transcriptions(tmp_path):
    common = OrganizationContext.model_validate_json((DEMO / "company-context.json").read_bytes())
    assert common.company_tax_id == "0319999996"
    assert {a["activity_id"] for a in common.activities} == {f"activity:tc{i:02d}" for i in range(1,26)}
    assert len(common.ledger)==25 and common.coverage is None and not common.budgets
    assert len(common.coverages)==25
    assert "transcription" not in common.model_dump_json()
    wf = build_workflow(Settings(_env_file=None), "STUB", db=Database(tmp_path/"common.sqlite"),
                        uploads_dir=tmp_path/"uploads", context_path=DEMO/"company-context.json",
                        clock=lambda: AS_OF)
    assert len(wf.catalog()) ==25


def test_shared_app_has_all25_advances_with_independent_history_after_restart(tmp_path):
    kwargs=dict(settings=Settings(_env_file=None),mode="STUB",db=Database(tmp_path/"all.sqlite"),
                uploads_dir=tmp_path/"up",context_path=DEMO/"company-context.json",clock=lambda:AS_OF)
    build_workflow(**kwargs)
    wf=build_workflow(**kwargs)
    with wf.db.connect() as cx:
        for index,amount in enumerate(ADVANCES,1):
            activity=f"activity:tc{index:02d}"
            ctx=load_context(cx,"tenant:demo",activity,AS_OF)
            events=context_ledger(ctx,digest="a"*64)
            history=context_coverage(ctx,digest="a"*64)
            assert len(events)==1 and events[0].amount==amount
            assert events[0].scope==activity and events[0].payee=="employee:employee-a"
            assert history is not None and history.scope==activity
            assert history.opening_balance.value==0 and history.as_of==AS_OF
            assert len(ctx.coverages)==1
            assert {g["scope"] for g in ctx.grants}=={"tenant:demo"}
        assert load_context(cx,"tenant:demo","activity:unrelated",AS_OF) is None


def test_each_case_has_scoped_advance_and_a_separate_unrecorded_ui_start(tmp_path):
    entries = _manifest()["cases"]
    assert [e["case_id"] for e in entries] == [f"TC{i:02d}" for i in range(1,26)]
    for index, entry in enumerate(entries):
        ctx=OrganizationContext.model_validate_json((DEMO/entry["context"]).read_bytes())
        ui=OrganizationContext.model_validate_json((DEMO/entry["context_ui"]).read_bytes())
        activity=f"activity:tc{index+1:02d}"
        assert ctx.activity["activity_id"] == activity
        assert not ctx.activities and not ctx.budgets
        assert ctx.company_tax_id == "0319999996"
        assert len(ctx.ledger)==1
        event=ctx.ledger[0]
        assert event["amount"]==ADVANCES[index]
        assert event["scope"]==activity and event["payee"]=="employee:employee-a"
        assert event["verification_state"]=="CONFIRMED"
        assert event["kind"]=="ADVANCE_RECEIVED"
        assert ctx.coverage["activity"]==activity
        assert ctx.financial_as_of==AS_OF.isoformat()
        assert not ui.ledger and ui.coverage is None
        assert ui.activity==ctx.activity
        assert "expected" not in ctx.model_dump_json() and "transcription" not in ctx.model_dump_json()
        grants={g["actor"]+":"+g["actions"][0]:g for g in ctx.grants}
        assert grants["system:referee:RECOGNIZE_COST"]["max_amount"]==8_000_000
        assert grants["system:referee:ISSUE_PAYMENT"]["max_amount"]==4_000_000
        assert grants["employee:approver:AUTHORIZE_ACTIVITY"]["max_amount"]==20_000_000
        wf=build_workflow(Settings(_env_file=None),"STUB",db=Database(tmp_path/f"{index}.sqlite"),
                          uploads_dir=tmp_path/f"up-{index}",context_path=DEMO/entry["context"],
                          clock=lambda:AS_OF)
        with wf.db.connect() as cx:
            stored=load_context(cx,"tenant:demo",activity,AS_OF)
        assert stored is not None and stored.company_tax_id=="0319999996"
        assert [e.amount for e in context_ledger(stored,digest="f"*64)]==[ADVANCES[index]]


def test_public_import_entry_accepts_typed_context_and_restart_keeps_scope(tmp_path):
    entries=_manifest()["cases"]
    wf=CaseWorkflow(Database(tmp_path/"app.sqlite"),uploads_dir=tmp_path/"up",clock=lambda:AS_OF)
    wf.db.migrate()
    for entry in entries[:2]:
        wf.import_demo_context(DEMO/entry["context"])
    restarted=CaseWorkflow(Database(tmp_path/"app.sqlite"),uploads_dir=tmp_path/"up",clock=lambda:AS_OF)
    with restarted.db.connect() as cx:
        one=load_context(cx,"tenant:demo","activity:tc01",AS_OF)
        two=load_context(cx,"tenant:demo","activity:tc02",AS_OF)
        absent=load_context(cx,"tenant:demo","activity:travel-a",AS_OF)
    assert one.company_tax_id==two.company_tax_id=="0319999996"
    assert [e.amount for e in context_ledger(one,digest="a"*64)]==[4_000_000]
    assert [e.amount for e in context_ledger(two,digest="b"*64)]==[5_000_000]
    assert context_coverage(one,digest="a"*64).opening_balance.value==0
    assert absent is None


def test_manifest_does_not_invent_duplicate_usage_or_modify_source_pdfs():
    import hashlib
    manifest=_manifest()
    tc12=manifest["cases"][11]
    assert tc12["requires_predecessor"]=="TC01"
    for entry in manifest["cases"]:
        for source in entry["sources"]:
            path=ROOT/source["path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==source["sha256"]
        ctx=json.loads((DEMO/entry["context"]).read_text())
        assert not any('duplicate' in key or 'expected' in key for key in ctx)


def test_context_generator_is_repeatable_and_does_not_write_into_other_folders(tmp_path):
    import pytest
    from scripts.sinh_context_uc03 import generate
    output=tmp_path/"contexts"
    generate(output)
    before={p.relative_to(output):p.read_bytes() for p in output.rglob('*.json')}
    generate(output)
    assert before=={p.relative_to(output):p.read_bytes() for p in output.rglob('*.json')}
    unmanaged=tmp_path/"unmanaged"
    unmanaged.mkdir(); (unmanaged/"keep.txt").write_text("keep")
    with pytest.raises(ValueError,match="unmanaged"):
        generate(unmanaged)
    link=tmp_path/"link"
    link.symlink_to(output,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        generate(link)
    assert (unmanaged/"keep.txt").read_text()=="keep"
