import json,shutil
from pathlib import Path
import pytest
from invoice_referee.evaluation.service import run_isolated_verify,DEFAULT_VERIFY_DATA_DIR
@pytest.mark.asyncio
async def test_missing_manifest_cannot_execute(tmp_path):
 data=tmp_path/"data";shutil.copytree(DEFAULT_VERIFY_DATA_DIR,data);(data/"manifest.json").unlink()
 r=await run_isolated_verify("core",data_dir=data,runtime_dir=tmp_path/"run")
 assert not r["release"] and r["completed"]==0
 assert all("DATASET_INVALID" in str(row["failure_reasons"]) for row in r["rows"])
@pytest.mark.asyncio
async def test_synthetic_recordings_report_needs_recording(tmp_path):
 r=await run_isolated_verify("core",runtime_dir=tmp_path)
 assert not r["release"] and r["completed"]==0
 assert all("NEEDS_RECORDING" in str(row["failure_reasons"]) for row in r["rows"])
@pytest.mark.asyncio
async def test_modified_gold_or_symlink_is_blocked(tmp_path):
 data=tmp_path/"data";shutil.copytree(DEFAULT_VERIFY_DATA_DIR,data)
 p=data/"cases/tc01/dap-an/ket-qua-hop-le.json";p.write_text(p.read_text()+" ")
 r=await run_isolated_verify("core",data_dir=data,runtime_dir=tmp_path/"run")
 assert not r["release"] and r["attempted"]==0

@pytest.mark.asyncio
async def test_api_preserves_nonempty_app_database_without_network(app_fixture,tmp_path,monkeypatch):
 import socket
 import invoice_referee.evaluation.service as service
 monkeypatch.setattr(service,"DEFAULT_RUNTIME_VERIFY_DIR",tmp_path/"verify")
 await app_fixture.create(employee="employee:employee-a",activity="activity:travel-a")
 def database():
  cx=app_fixture.db.connect()
  try:return tuple(cx.iterdump())
  finally:cx.close()
 before=database()
 def blocked(*args,**kwargs):raise AssertionError("Replay attempted network")
 monkeypatch.setattr(socket.socket,"connect",blocked)
 r=await app_fixture.client.post("/api/verify",json={"suite":"core","mode":"RECORDED_REPLAY"})
 assert r.status_code==200,r.text
 assert r.json()["status"]=="NEEDS_RECORDING"
 assert not r.json()["release"]
 assert database()==before
 loaded=await app_fixture.client.get("/api/verify/last")
 assert loaded.json()["run_id"]==r.json()["run_id"]
 second=await app_fixture.client.post("/api/verify",json={"suite":"core","mode":"RECORDED_REPLAY"})
 assert second.json()["run_id"]!=r.json()["run_id"]
 assert len(list((tmp_path/"verify").glob("run-*/report.json")))==2
 assert database()==before

@pytest.mark.asyncio
async def test_missing_middle_member_and_duplicate_identity_are_invalid(tmp_path):
 import invoice_referee.evaluation.service as service
 data=tmp_path/"data";shutil.copytree(DEFAULT_VERIFY_DATA_DIR,data)
 shutil.rmtree(data/"cases/tc02")
 r=await service.run_isolated_verify("core",data_dir=data,runtime_dir=tmp_path/"run")
 assert r["attempted"]==0 and not r["release"]
 assert [row["root_id"]for row in r["rows"]]==["TC01","TC02","VFY-BAL-01","TC06"]
