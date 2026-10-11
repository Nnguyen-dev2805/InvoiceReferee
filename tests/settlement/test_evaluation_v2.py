"""B7 evaluation v2: packet/oracle/context versioned corpus (plan 2026-10-11).

Red-first (plan Task 1.1): the v2 corpus, ``PacketContextV2``/``ExpectedV2``
contracts and the schema-versioned loader do not exist yet. Expected values are
independent literals hand-computed from the packet sources and policy snapshot,
never produced by running the engine under test.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.evaluation import load_packet

V2 = Path("docs/discovery/eval_development_v2")


def test_v2_has_three_routine_two_resolution_cases():
    packets = [load_packet(V2 / name)
               for name in ("Q01", "Q03", "Q04", "Q11", "Q13")]
    assert [p.expected_initial["completion"] for p in packets] == [
        "COMPLETE", "COMPLETE", "COMPLETE", "INCOMPLETE", "INCOMPLETE"]
    assert all(p.context.submission.form.get("purpose") for p in packets)
    assert all(p.context.authority[0].work_ref ==
               p.context.submission.work_ref for p in packets)


def test_q03_total_includes_company_airfare():
    p = load_packet(V2 / "Q03")
    assert p.expected_initial["components"]["t"] == 6_300_000
    assert p.expected_initial["components"]["e"] == 3_300_000
    assert p.expected_initial["calculated_net_vnd"] == -700_000


def test_q04_current_reimbursement_is_three_million():
    p = load_packet(V2 / "Q04")
    assert p.expected_initial["components"]["p"] == 3_000_000
    assert p.expected_initial["external_basis_present"] is True
    assert "CREATE_DECISION" in p.expected_initial["forbidden_actions"]
    assert "CLOSE_CASE" in p.expected_initial["forbidden_actions"]


# --- step 1.3: strict loader negative tests (tmp copies only) -------------------

def _copy(packet: str) -> Path:
    import tempfile
    target = Path(tempfile.mkdtemp()) / packet
    shutil.copytree(V2 / packet, target)
    return target


def test_policy_tamper_is_refused():
    target = _copy("Q01")
    policy = target / "policy_bundle" / "R4_WORK_BUDGET_POLICY.md"
    policy.write_text(policy.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "DATASET_HASH_MISMATCH"


def test_context_tamper_is_refused():
    target = _copy("Q01")
    ctx = target / "context.json"
    data = json.loads(ctx.read_text(encoding="utf-8"))
    data["submission"]["work_ref"] = "CT-TAMPER"
    ctx.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "DATASET_HASH_MISMATCH"


def test_duplicate_json_keys_are_refused():
    target = _copy("Q01")
    ctx = target / "context.json"
    # two "synthetic" keys: object_pairs_hook must reject before dict overwrite.
    raw = ctx.read_text(encoding="utf-8")
    dup = raw.replace('"synthetic": true', '"synthetic": true,\n  "synthetic": false', 1)
    assert dup != raw
    ctx.write_text(dup, encoding="utf-8")
    # hash no longer matches, so fix the declared hash to isolate the dup check
    import hashlib
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["context_file"]["sha256"] = hashlib.sha256(
        ctx.read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "DATASET_CONTEXT_INVALID"


def test_orphan_anchor_in_expected_is_refused():
    target = _copy("Q11")
    exp = target / "expected" / "initial.json"
    data = json.loads(exp.read_text(encoding="utf-8"))
    data["issues"][0]["refs"] = ["input/payment_attempts.md#does-not-exist"]
    exp.write_text(json.dumps(data), encoding="utf-8")
    import hashlib
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["expected_files"]:
        if entry["path"].endswith("initial.json"):
            entry["sha256"] = hashlib.sha256(exp.read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "DATASET_CONTEXT_INVALID"


def test_expected_is_input_flag_is_refused():
    target = _copy("Q01")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["expected_is_input"] = True
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "EXPECTED_IS_INPUT"


def test_followup_mixed_into_initial_is_refused():
    target = _copy("Q11")
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["followup_is_initial_input"] = True
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainError) as err:
        load_packet(target)
    assert err.value.code == "FOLLOWUP_IS_INPUT"


def test_v2_authority_scope_is_specific_not_wildcard():
    # Every demo packet scopes the grant to its own employee/work with bounds.
    for name in ("Q01", "Q03", "Q04", "Q11", "Q13"):
        p = load_packet(V2 / name)
        grant = p.context.authority[0]
        assert grant.work_ref == p.context.submission.work_ref
        assert grant.employee_ref == p.context.submission.employee_ref
        assert grant.effective_from is not None
        assert grant.effective_until is not None
        assert grant.max_employee_cost_vnd is not None


def test_v2_expected_status_is_source_reviewed_development():
    for name in ("Q01", "Q03", "Q04", "Q11", "Q13"):
        p = load_packet(V2 / name)
        assert p.expected_v2.gold_status == \
            "SOURCE_REVIEWED_DEVELOPMENT_NOT_INDEPENDENT"


# --- Task 2: policy-replay through the application path ------------------------

def _replay_service(tmp_path):
    from invoice_referee.settlement.reader import StructuredLedgerReader
    from invoice_referee.settlement.service import Service, ServiceConfig
    from invoice_referee.settlement.store import Store

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    return Service(store, StructuredLedgerReader(store.artifact_root),
                   config=ServiceConfig())


def test_policy_replay_five_cases_match_expected_money(tmp_path):
    from invoice_referee.settlement.evaluation import run_suite

    service = _replay_service(tmp_path)
    report = run_suite(V2, service, packet_ids=["Q01", "Q03", "Q04", "Q11", "Q13"],
                       execution_mode="policy-replay")
    by_case = {(r.case_id, r.phase): r for r in report.results}
    for case_id in ("Q01", "Q03", "Q04"):
        r = by_case[(case_id, "INITIAL")]
        money = next(c for c in r.checks if c.axis == "money")
        assert money.ok, f"{case_id} money FAIL: {money.actual}"
        assert r.verdict == "PASS", f"{case_id} verdict {r.verdict}"
    # Q11 initial keeps A/S unknown, Q13 initial keeps final unknown.
    assert by_case[("Q11", "INITIAL")].needs_resolution_expected is True
    assert by_case[("Q13", "INITIAL")].needs_resolution_expected is True


def test_policy_replay_mode_is_not_live(tmp_path):
    from invoice_referee.settlement.evaluation import run_suite

    service = _replay_service(tmp_path)
    report = run_suite(V2, service, packet_ids=["Q01"],
                       execution_mode="policy-replay")
    assert report.results[0].mode == "POLICY_REPLAY"


def test_policy_replay_unknown_final_is_not_conditional(tmp_path):
    # Q13: final S must be None (exception undecided) and the accept-all
    # conditional (E6 -> +4M) recorded separately.
    from invoice_referee.settlement.evaluation import run_suite

    service = _replay_service(tmp_path)
    report = run_suite(V2, service, packet_ids=["Q13"],
                       execution_mode="policy-replay")
    money = next(c for c in report.results[0].checks if c.axis == "money")
    assert money.ok, money.actual
    assert money.actual["s"] is None


def test_replay_reader_binds_by_bytes_not_filename(tmp_path):
    # Renaming the packet folder / file name must not change replay outcome.
    import tempfile
    from invoice_referee.verify.settlement_replay import SourcedReplayReader

    target = Path(tempfile.mkdtemp()) / "RENAMED"
    shutil.copytree(V2 / "Q01", target)
    p = load_packet(target)
    assert p.case_id == "Q01"
    reader = SourcedReplayReader(tmp_path, p.replay_observations,
                                 p.replay_relations)
    assert reader.mode == "POLICY_REPLAY"


def test_replay_quote_not_in_source_is_refused(tmp_path):
    # A fabricated SOURCE_QUOTE that is not in the source fails closed.
    from invoice_referee.settlement.models import SourceRecord
    from invoice_referee.verify.settlement_replay import SourcedReplayReader
    import json as _json
    from datetime import datetime, timezone

    src = tmp_path / "src.txt"
    src.write_text("nothing relevant here", encoding="utf-8")
    obs = tmp_path / "obs.json"
    obs.write_text(_json.dumps([{
        "fact_id": "x", "key": "expense.X.amount", "value": 1, "raw": "999",
        "read_state": "READ", "basis": "SOURCE_QUOTE",
        "source_sha256": __import__("hashlib").sha256(
            src.read_bytes()).hexdigest(), "source_file": "src.txt",
    }]), encoding="utf-8")
    rel = tmp_path / "rel.json"
    rel.write_text("[]", encoding="utf-8")
    reader = SourcedReplayReader(tmp_path, obs, rel)
    record = SourceRecord(id="S1", case_id="C", filename="src.txt",
                          media_type="text/plain",
                          sha256=__import__("hashlib").sha256(
                              src.read_bytes()).hexdigest(),
                          size_bytes=len(src.read_bytes()), status="ACCEPTED",
                          uploader_actor_id="u", received_at=datetime.now(timezone.utc),
                          provenance={}, original_path="src.txt")
    from invoice_referee.settlement.models import RunBudget
    import time
    with pytest.raises(DomainError) as err:
        reader.read(record, [], RunBudget(deadline=time.monotonic() + 10,
                                          max_calls=5))
    assert err.value.code == "REPLAY_QUOTE_NOT_FOUND"


def test_replay_sidecar_missing_for_source_is_technical(tmp_path):
    # An uploaded source with no sidecar facts is a per-source technical gap.
    from invoice_referee.settlement.models import SourceRecord, RunBudget
    from invoice_referee.verify.settlement_replay import SourcedReplayReader
    import json as _json
    from datetime import datetime, timezone
    import time

    src = tmp_path / "src.txt"
    src.write_text("text", encoding="utf-8")
    obs = tmp_path / "obs.json"
    obs.write_text("[]", encoding="utf-8")
    rel = tmp_path / "rel.json"
    rel.write_text("[]", encoding="utf-8")
    reader = SourcedReplayReader(tmp_path, obs, rel)
    record = SourceRecord(id="S1", case_id="C", filename="src.txt",
                          media_type="text/plain", sha256="deadbeef",
                          size_bytes=4, status="ACCEPTED", uploader_actor_id="u",
                          received_at=datetime.now(timezone.utc),
                          provenance={}, original_path="src.txt")
    with pytest.raises(DomainError) as err:
        reader.read(record, [], RunBudget(deadline=time.monotonic() + 10,
                                          max_calls=5))
    assert err.value.code == "REPLAY_SOURCE_UNMATCHED"


def test_two_suite_runs_get_distinct_execution_ids(tmp_path):
    from invoice_referee.settlement.evaluation import run_suite

    service = _replay_service(tmp_path)
    first = run_suite(V2, service, packet_ids=["Q01"], execution_mode="policy-replay")
    second = run_suite(V2, service, packet_ids=["Q01"], execution_mode="policy-replay")
    assert first.execution_id and second.execution_id
    assert first.execution_id != second.execution_id
    # A fresh run per execution is a new run id, not a reused one.
    assert first.results[0].run_id != second.results[0].run_id


# --- Task 4: API verify mode (request override / env fallback / invalid) --------

def _verify_client(tmp_path, monkeypatch, env_mode=None):
    from fastapi.testclient import TestClient
    from invoice_referee.api.settlement import create_runtime_app

    monkeypatch.setenv("SETTLEMENT_EVAL_CORPUS", str(V2))
    if env_mode is None:
        monkeypatch.delenv("SETTLEMENT_EVAL_MODE", raising=False)
    else:
        monkeypatch.setenv("SETTLEMENT_EVAL_MODE", env_mode)
    monkeypatch.setenv("SETTLEMENT_VERIFY_DIR", str(tmp_path / "verify"))
    app = create_runtime_app(db_path=tmp_path / "cases.sqlite",
                             artifact_root=tmp_path / "artifacts")
    return TestClient(app)


def test_api_verify_mode_from_request_overrides_default(tmp_path, monkeypatch):
    client = _verify_client(tmp_path, monkeypatch)
    response = client.post("/api/verify/settlement/run",
                           json={"packets": ["Q01"], "mode": "policy-replay"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "POLICY_REPLAY"
    assert body["results"][0]["verdict"] == "PASS"


def test_api_verify_mode_from_env_fallback(tmp_path, monkeypatch):
    client = _verify_client(tmp_path, monkeypatch, env_mode="policy-replay")
    response = client.post("/api/verify/settlement/run", json={"packets": ["Q01"]})
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "POLICY_REPLAY"


def test_api_verify_invalid_mode_is_rejected(tmp_path, monkeypatch):
    client = _verify_client(tmp_path, monkeypatch, env_mode="not-a-mode")
    response = client.post("/api/verify/settlement/run", json={"packets": ["Q01"]})
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_INPUT"




