"""W06 evaluation harness: fixed-adapter oracle, None-strict money compare,
verdicts beyond net and honest denominators.

Oracle discipline: expected values in fixtures are computed by hand from the
Rulebook formula (S = E - (A - RA) - (P - RP)), never by running the engine.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement import evaluation as ev
from invoice_referee.settlement.evaluation import (
    compute_metrics,
    compare_money,
    expected_money_view,
    load_packet,
    run_suite,
)
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store

# Ledger giả lập: E=5tr, A=2tr đã ứng, RA/P/RP=0 → S = 5 - 2 = 3 triệu
# (tính tay theo Rulebook, không chạy engine để lấy expected).
LEDGER_ROUTINE = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "fact F7 history.advance.received 2000000\n"
    "fact F8 history.advance.returned 0\n"
    "fact F9 history.reimbursement.received 0\n"
    "fact F10 history.reimbursement.returned 0\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)
# Ledger thiếu history: E vẫn đọc được, A/RA/P/RP unknown → INCOMPLETE, không S.
LEDGER_NEEDS = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "fact F6 budget.approved 8000000\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


def _sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_packet(corpus: Path, case_id: str, *, job: str = "B7",
                 ledger: str, expected: dict) -> Path:
    packet = corpus / case_id
    (packet / "input").mkdir(parents=True)
    (packet / "expected").mkdir(parents=True)
    ledger_path = packet / "input" / "ledger.txt"
    ledger_path.write_text(ledger, encoding="utf-8")
    expected_path = packet / "expected" / "expected.json"
    expected_path.write_text(json.dumps(expected, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    manifest = {
        "evaluation_case_id": case_id,
        "job": job,
        "dataset_role": "DEVELOPMENT_ONLY",
        "family_id": "WORK_BUDGET_TEMPLATE_01",
        "business_story_id": "CT-EVAL-01",
        "as_of": "2026-10-08T11:00:00+00:00",
        "synthetic_only": True,
        "input_files": [{"path": "input/ledger.txt",
                         "sha256": _sha256(ledger_path)}],
        "expected_path": "expected/expected.json",
        "expected_sha256": _sha256(expected_path),
        "expected_is_input": False,
        "author_hints_removed": True,
        "independent_gold_validated": False,
        "policy_path_base": "..",
    }
    (packet / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return packet


def routine_expected(s: int | None = 3_000_000, **overrides) -> dict:
    expected = {
        "work": "CT-EVAL-01",
        "employee": "NV-EVAL-01",
        "as_of": "2026-10-08T11:00:00+00:00",
        "T": 5_000_000,
        "E": 5_000_000,
        "A": 2_000_000,
        "RA": 0,
        "P": 0,
        "RP": 0,
        "S": s,
        "direction": "COMPANY_TO_EMPLOYEE",
        "settlement_approved": False,
        "close_allowed": False,
        "requires_extra_fact_policy_authority_resolution": False,
        "routine_check_report_expected": True,
        "automatic_request_creation_allowed": False,
        "automatic_bank_execution_allowed": False,
        "duplicate_payment_allowed": False,
        "evidence_refs": {"advance": ["input/ledger.txt"]},
    }
    expected.update(overrides)
    return expected


@pytest.fixture
def service(tmp_path):
    from invoice_referee.settlement.models import AuthorityGrant

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    reader = StructuredLedgerReader(store.artifact_root)
    return Service(store, reader, config=ServiceConfig(authority=[
        AuthorityGrant(actor_ref="P-DEMO", work_ref=None,
                       max_settlement_vnd=100_000_000),
    ]))


# --- compare_money: None-strict, không skip, không first-non-null -------------

def test_expected_unknown_is_not_skipped_by_evaluator():
    verdict = compare_money({"proposed_net_vnd": None},
                            {"proposed_net_vnd": 3_000_000})
    assert verdict == "FAIL"


def test_compare_money_none_vs_none_and_missing_key():
    assert compare_money({"proposed_net_vnd": None},
                         {"proposed_net_vnd": None}) == "PASS"
    # actual thiếu key hoàn toàn → FAIL, không coi như khớp
    assert compare_money({"calculated_net_vnd": 3}, {}) == "FAIL"
    assert compare_money({"calculated_net_vnd": 3},
                         {"calculated_net_vnd": 3}) == "PASS"
    # một key sai là cả compare FAIL
    assert compare_money({"e": 5, "a": None}, {"e": 5, "a": 2}) == "FAIL"


def test_expected_money_view_fixed_shapes_no_first_non_null():
    flat = expected_money_view(routine_expected())
    assert flat["s"] == 3_000_000 and flat["e"] == 5_000_000 and flat["a"] == 2_000_000

    partial = expected_money_view({
        "known_partial_facts_vnd": {"B": 8_000_000, "T": 8_000_000,
                                    "A": 2_000_000, "RA": 0, "P": 0, "RP": 0},
        "E_vnd": None, "S_vnd": None,
    })
    assert partial["e"] is None and partial["s"] is None
    assert partial["b"] == 8_000_000 and partial["a"] == 2_000_000

    after = expected_money_view({
        "T_vnd": 8_000_000, "E_vnd": 5_000_000, "A_vnd": 2_000_000,
        "RA_vnd": 0, "P_vnd": 0, "RP_vnd": 0, "S_vnd": 3_000_000,
    })
    assert after["s"] == 3_000_000 and after["ra"] == 0

    # shape lạ → từ chối, không tự tìm key thay thế
    with pytest.raises(DomainError) as error:
        expected_money_view({"total": 5, "net": 3})
    assert error.value.code == "EXPECTED_SHAPE_UNKNOWN"
    # shape FLAT thiếu S → từ chối, không lấy first-non-null khác
    flat_without_s = {k: v for k, v in routine_expected().items() if k != "S"}
    with pytest.raises(DomainError) as error:
        expected_money_view(flat_without_s)
    assert error.value.code == "EXPECTED_SHAPE_UNKNOWN"


# --- end-to-end qua Service: oracle độc lập, verdict ngoài net ---------------

def test_run_suite_routine_pass_and_wrong_oracle_fail(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EP01", ledger=LEDGER_ROUTINE,
                 expected=routine_expected())  # oracle tay: S=3.000.000
    write_packet(corpus, "EP02", ledger=LEDGER_ROUTINE,
                 expected=routine_expected(s=4_000_000))  # oracle cố ý khác

    report = run_suite(corpus, service)
    assert report.mode == "FAKE_OR_REPLAY"
    assert report.source_hash and report.config_hash
    by_id = {r.case_id: r for r in report.results}
    assert by_id["EP01"].verdict == "PASS"
    ep01_money = [c for c in by_id["EP01"].checks if c.axis == "money"]
    assert ep01_money and ep01_money[0].ok
    # oracle 4 triệu không khớp engine 3 triệu → FAIL, không nới gold
    assert by_id["EP02"].verdict == "FAIL"
    metrics = report.metrics
    assert metrics["n_routine"] == 2 and metrics["n_needs"] == 0
    assert metrics["routine_completion"] == "1/2"


def test_run_suite_scores_critical_fact_and_relation_gold(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EPF1", ledger=LEDGER_ROUTINE,
                 expected=routine_expected(
                     critical_facts={
                         "expense.EXP-1.amount": 5_000_000,
                         "history.advance.received": 2_000_000,
                         "history.reimbursement.received": 0,
                     },
                     expected_relations=[{
                         "kind": "EXPENSE_PAYMENT",
                         "from": "EXP-1", "to": "PAY-1",
                         "portion_vnd": None,
                     }]))
    report = run_suite(corpus, service)
    result = report.results[0]
    axes = {c.axis: c for c in result.checks}
    assert result.verdict == "PASS"
    assert axes["facts"].ok and axes["relations"].ok
    assert axes["facts"].actual["expense.EXP-1.amount"] == 5_000_000

    # gold relation sai cặp + fact sai số → FAIL cả hai axis
    write_packet(corpus, "EPF2", ledger=LEDGER_ROUTINE,
                 expected=routine_expected(
                     critical_facts={"expense.EXP-1.amount": 9_000_000},
                     expected_relations=[{
                         "kind": "EXPENSE_PAYMENT",
                         "from": "EXP-1", "to": "PAY-9",
                         "portion_vnd": None,
                     }]))
    report = run_suite(corpus, service, packet_ids=["EPF2"])
    failed = {c.axis: c.ok for c in report.results[0].checks}
    assert failed.get("facts") is False and failed.get("relations") is False
    assert report.results[0].verdict == "FAIL"


def test_run_suite_counts_business_gold_coverage(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EPG1", ledger=LEDGER_ROUTINE, expected=routine_expected(
        critical_facts_business=[
            {"fact": "air_invoice_total_vnd", "value": 3_000_000,
             "refs": ["input/ledger.txt"]}],
        reconciliation_relations_business=[
            {"expense": "INV-AIR-001", "payment": "PAY-AIR-001",
             "kind": "EXPENSE_PAYMENT"}],
    ))
    report = run_suite(corpus, service)
    # gold business vocabulary được ghi nhận, không bị bỏ im lặng; chấm engine
    # chờ reader mapping (M1)
    assert report.metrics["gold_coverage"] == {
        "facts_business": 1, "relations_business": 1}
    assert any("business vocabulary" in note for note in report.notes)


def test_run_suite_needs_case_must_not_fabricate(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EP03", ledger=LEDGER_NEEDS, expected=routine_expected(
        s=None, A=None, RA=None, P=None, RP=None,
        requires_extra_fact_policy_authority_resolution=True,
        allowed_owner_roles=["ACCOUNTANT"], issue_type="FACT_HISTORY_UNKNOWN",
        evidence_refs={"coverage": ["input/ledger.txt"]}))
    report = run_suite(corpus, service)
    result = report.results[0]
    # needs case: không bịa S, issue đúng kiểu FACT, owner hợp lệ → PASS
    assert result.verdict == "PASS", [c.model_dump() for c in result.checks]
    metrics = report.metrics
    assert metrics["n_needs"] == 1 and metrics["fn"] == 0
    assert metrics["u_needs"] == 0


def test_run_suite_routine_with_extra_issue_counts_fp(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # expected nói routine/COMPLETE nhưng nguồn làm history unknown → FP
    write_packet(corpus, "EP04", ledger=LEDGER_NEEDS,
                 expected=routine_expected(s=None, A=None, RA=None, P=None, RP=None))
    report = run_suite(corpus, service)
    metrics = report.metrics
    assert metrics["n_routine"] == 1
    assert metrics["fp"] == 1
    assert metrics["fp_interval"] == [1.0, 1.0]


def test_technical_failure_stays_in_denominator(tmp_path):
    class BudgetOutReader(StructuredLedgerReader):
        def read(self, source, keys, budget):
            raise DomainError("BUDGET_EXHAUSTED", "run hết ngân sách; không bịa.")

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    service = Service(store, BudgetOutReader(store.artifact_root),
                       config=ServiceConfig())
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EP05", ledger=LEDGER_ROUTINE,
                 expected=routine_expected())
    report = run_suite(corpus, service)
    result = report.results[0]
    assert result.verdict == "INCONCLUSIVE"  # TIMED_OUT → trục kỹ thuật riêng
    assert result.technical is True
    metrics = report.metrics
    assert metrics["n_routine"] == 1
    assert metrics["u_routine"] == 1
    assert metrics["routine_completion"] == "0/1"  # U không rời mẫu số


def test_metrics_intervals_and_zero_denominator():
    metrics = compute_metrics([
        {"needs": True, "technical": False, "fn": True},
        {"needs": True, "technical": True, "fn": False},
        {"needs": False, "technical": False, "fn": False, "fp": False,
         "pass": True},
        {"needs": False, "technical": False, "fn": False, "fp": True,
         "pass": False},
    ])
    assert metrics["n_needs"] == 2 and metrics["fn"] == 1
    assert metrics["u_needs"] == 1
    assert metrics["fn_interval"] == [0.5, 1.0]
    assert metrics["n_routine"] == 2 and metrics["fp"] == 1
    assert metrics["fp_interval"] == [0.5, 0.5]
    assert metrics["routine_completion"] == "1/2"
    empty = compute_metrics([])
    assert empty["n_needs"] == 0
    assert empty["fn_interval"] is None  # N/A, không phải 0% hay 100%


# --- gold không bao giờ là input ----------------------------------------------

def test_expected_files_never_uploaded_as_sources(service, tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    packet = write_packet(corpus, "EP06", ledger=LEDGER_ROUTINE,
                          expected=routine_expected())
    run_suite(corpus, service)
    case_ids = [c.id for c in service.store.list_cases()]
    assert len(case_ids) == 1
    sources = service.store.get_case(case_ids[0]).sources
    # chỉ file input của manifest được upload; expected/manifest không vào nguồn
    assert [s.filename for s in sources] == ["ledger.txt"]
    assert packet.name not in {s.filename for s in sources}


# --- author hints: live mode cần dataset version đã gỡ hints -----------------

def test_live_mode_refuses_author_hint_sources(tmp_path):
    class LiveModeReader(StructuredLedgerReader):
        mode = "LIVE"

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")
    service = Service(store, LiveModeReader(store.artifact_root),
                       config=ServiceConfig())
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    write_packet(corpus, "EP07", ledger=LEDGER_ROUTINE,
                 expected=routine_expected())
    manifest = json.loads(((corpus / "EP07" / "manifest.json")).read_text())
    del manifest["author_hints_removed"]  # dataset cũ còn author hints
    (corpus / "EP07" / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(DomainError) as error:
        run_suite(corpus, service)
    assert error.value.code == "AUTHOR_HINTS_IN_PROMPT"


# --- packet loading gates ------------------------------------------------------

def test_load_packet_verifies_hashes_and_expected_not_input(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    packet = write_packet(corpus, "EP08", ledger=LEDGER_ROUTINE,
                          expected=routine_expected())
    loaded = load_packet(packet)
    assert loaded.case_id == "EP08"
    assert [p.name for p in loaded.input_files] == ["ledger.txt"]
    assert loaded.expected_initial["S"] == 3_000_000

    # hash lệch → từ chối dataset, không chạy cho có
    ledger = packet / "input" / "ledger.txt"
    ledger.write_text(LEDGER_ROUTINE + "fact F11 extra 1\n", encoding="utf-8")
    with pytest.raises(DomainError) as error:
        load_packet(packet)
    assert error.value.code == "DATASET_HASH_MISMATCH"


def test_load_packet_refuses_expected_marked_as_input(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    packet = write_packet(corpus, "EP09", ledger=LEDGER_ROUTINE,
                          expected=routine_expected())
    manifest_path = packet / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["expected_is_input"] = True
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(DomainError) as error:
        load_packet(packet)
    assert error.value.code == "EXPECTED_IS_INPUT"
