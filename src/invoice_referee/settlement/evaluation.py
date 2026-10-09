"""Settlement evaluation harness (W06): packets, fixed-adapter oracle, honest metrics.

Discipline baked in (Evaluation §E2/E3):

- Expected lives in the packet, hash-verified, and is **never** an input: the
  runner uploads only manifest input files; followup files only enter in the
  assisted phase; tampered datasets are refused, not run.
- The money adapter uses **fixed shapes** declared by the packet structure —
  no first-non-null fallback, and ``None`` expected means the actual must be
  ``None`` (``compare_money`` fails a value where gold says unknown).
- Verdicts go beyond net: completion/issues (FN/FP discipline), source
  coverage and post-run state are separate axes; technical failures stay in
  the denominators as ``U`` and never silently become business results.
- The corpus here is DEVELOPMENT_ONLY from one template family: it tunes the
  system and is never reported as an independent holdout.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    Command,
    ResponsePayload,
    Submission,
    Upload,
)
from invoice_referee.settlement.service import Service

Verdict = Literal["PASS", "FAIL", "INCONCLUSIVE"]

# Corpus packets of the WORK_BUDGET_TEMPLATE_01 family share this employee;
# a per-employee field in expected overrides it.
DEFAULT_EMPLOYEE_REF = "NV-DEMO-01"
EVAL_ACTOR = "EVAL-RUNNER"
_EVAL_ROLE = "EMPLOYEE"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- records ------------------------------------------------------------------

class Check(BaseModel):
    """One comparison axis: expected vs actual with a visible note."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    axis: str
    expected: Any = None
    actual: Any = None
    ok: bool
    note: str = ""


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    job: str
    phase: str  # INITIAL | AFTER_FOLLOWUP
    family_id: str
    dataset_role: str
    verdict: Verdict
    checks: list[Check] = []
    run_id: str | None = None
    run_status: str | None = None
    mode: str
    needs_resolution_expected: bool
    technical: bool = False
    first_pass_routine_expected: bool | None = None
    timestamp: str


class SuiteReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite: str
    timestamp: str
    mode: str
    source_hash: str
    config_hash: str
    results: list[CaseResult]
    metrics: dict[str, Any]
    notes: list[str]


@dataclass
class Packet:
    directory: Path
    manifest: dict[str, Any]
    case_id: str
    job: str
    family_id: str
    dataset_role: str
    as_of: str
    input_files: list[Path] = field(default_factory=list)
    followup_files: list[Path] = field(default_factory=list)
    expected_initial: dict[str, Any] = field(default_factory=dict)
    expected_after: dict[str, Any] | None = None
    gold_status: str | None = None


# --- packet loading ------------------------------------------------------------

def _verify_entry(entry: Mapping[str, Any], packet_dir: Path) -> Path:
    path = packet_dir / str(entry["path"])
    if not path.is_file():
        raise DomainError(
            "DATASET_HASH_MISMATCH",
            f"Packet {packet_dir.name}: thiếu file {entry['path']} đã đóng băng.",
        )
    actual = _sha256_bytes(path.read_bytes())
    if actual != str(entry["sha256"]):
        raise DomainError(
            "DATASET_HASH_MISMATCH",
            f"Packet {packet_dir.name}: hash {entry['path']} không khớp bản đóng "
            f"băng ({actual} != {entry['sha256']}); từ chối chạy dataset.",
        )
    return path


def load_packet(packet_dir: Path) -> Packet:
    manifest_path = Path(packet_dir) / "manifest.json"
    if not manifest_path.is_file():
        raise DomainError("PACKET_NOT_FOUND",
                          f"Không tìm thấy manifest trong {packet_dir}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("expected_is_input"):
        raise DomainError(
            "EXPECTED_IS_INPUT",
            f"Packet {packet_dir.name}: expected không được phép là input; "
            f"gold phải tách khỏi nguồn nạp vào engine.",
        )
    if manifest.get("followup_is_initial_input"):
        raise DomainError(
            "FOLLOWUP_IS_INPUT",
            f"Packet {packet_dir.name}: followup phải là phase riêng, không "
            f"trộn vào input ban đầu.",
        )
    input_entries = (manifest.get("initial_input_files")
                     or manifest.get("input_files") or [])
    input_files = [_verify_entry(entry, Path(packet_dir))
                   for entry in input_entries]
    followup_files = [_verify_entry(entry, Path(packet_dir))
                      for entry in manifest.get("followup_input_files") or []]

    expected_after: dict[str, Any] | None = None
    expected_initial: dict[str, Any]
    if manifest.get("expected_files"):
        expected_files = {Path(e["path"]).name: _verify_entry(e, Path(packet_dir))
                          for e in manifest["expected_files"]}
        if "before.json" in expected_files:
            before_path = expected_files["before.json"]
        elif len(expected_files) == 1:
            before_path = next(iter(expected_files.values()))
        else:
            raise DomainError(
                "EXPECTED_SHAPE_UNKNOWN",
                f"Packet {packet_dir.name}: expected_files phải khai báo "
                f"before.json (initial) và after.json (assisted, tùy chọn).",
            )
        expected_initial = json.loads(before_path.read_text(encoding="utf-8"))
        if "after.json" in expected_files:
            expected_after = json.loads(
                expected_files["after.json"].read_text(encoding="utf-8"))
    elif manifest.get("expected_path"):
        expected_path = _verify_entry(
            {"path": manifest["expected_path"],
             "sha256": manifest["expected_sha256"]}, Path(packet_dir))
        expected_initial = json.loads(expected_path.read_text(encoding="utf-8"))
    else:
        raise DomainError(
            "EXPECTED_SHAPE_UNKNOWN",
            f"Packet {packet_dir.name}: manifest không khai báo expected.",
        )

    as_of = (manifest.get("as_of") or manifest.get("as_of_money")
             or expected_initial.get("as_of")
             or expected_initial.get("as_of_money"))
    if not as_of:
        raise DomainError(
            "EXPECTED_SHAPE_UNKNOWN",
            f"Packet {packet_dir.name}: không có mốc tiền as_of để dựng case.",
        )
    return Packet(
        directory=Path(packet_dir), manifest=manifest,
        case_id=str(manifest["evaluation_case_id"]), job=str(manifest["job"]),
        family_id=str(manifest["family_id"]),
        dataset_role=str(manifest.get("dataset_role", "UNKNOWN")),
        as_of=str(as_of), input_files=input_files,
        followup_files=followup_files, expected_initial=expected_initial,
        expected_after=expected_after,
        gold_status=expected_initial.get("gold_status")
        or expected_initial.get("status"),
    )


def discover_packets(corpus_dir: Path) -> list[Packet]:
    corpus = Path(corpus_dir)
    packets = []
    for manifest_path in sorted(corpus.rglob("manifest.json")):
        packets.append(load_packet(manifest_path.parent))
    packets.sort(key=lambda p: p.case_id)
    return packets


# --- oracle: fixed-shape money view and None-strict compare -------------------

_FLAT_KEYS = ("T", "E", "A", "RA", "P", "RP", "S")
_VND_KEYS = ("T_vnd", "E_vnd", "A_vnd", "RA_vnd", "P_vnd", "RP_vnd", "S_vnd")


def expected_money_view(expected: Mapping[str, Any]) -> dict[str, int | None]:
    """Map packet money fields to component slots — fixed shapes, no fallback.

    Three shapes are recognised, exactly as the corpus declares them; anything
    else (or a missing key inside a shape) is refused with
    ``EXPECTED_SHAPE_UNKNOWN`` instead of guessing a substitute key.
    """
    if all(k in expected for k in _FLAT_KEYS):
        return {"t": expected["T"], "e": expected["E"], "a": expected["A"],
                "ra": expected["RA"], "p": expected["P"], "rp": expected["RP"],
                "s": expected["S"]}
    if all(k in expected for k in _VND_KEYS):
        return {"t": expected["T_vnd"], "e": expected["E_vnd"],
                "a": expected["A_vnd"], "ra": expected["RA_vnd"],
                "p": expected["P_vnd"], "rp": expected["RP_vnd"],
                "s": expected["S_vnd"]}
    partial = expected.get("known_partial_facts_vnd")
    if isinstance(partial, Mapping) and "E_vnd" in expected and "S_vnd" in expected:
        return {"t": partial.get("T"), "b": partial.get("B"),
                "a": partial.get("A"), "ra": partial.get("RA"),
                "p": partial.get("P"), "rp": partial.get("RP"),
                "e": expected["E_vnd"], "s": expected["S_vnd"]}
    raise DomainError(
        "EXPECTED_SHAPE_UNKNOWN",
        "Expected không theo shape cố định nào (FLAT/VND/PARTIAL); từ chối "
        "first-non-null.",
    )


def compare_money(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> Verdict:
    """Strict per-key compare: expected None demands actual None (never skip)."""
    for key in sorted(expected):
        want = expected[key]
        if key not in actual:
            return "FAIL"
        got = actual[key]
        if want is None or got is None:
            if want is not got:
                return "FAIL"
        elif want != got:
            return "FAIL"
    return "PASS"


def _requires_resolution(expected: Mapping[str, Any]) -> bool:
    if "requires_extra_resolution" in expected:
        return bool(expected["requires_extra_resolution"])
    return bool(expected.get("requires_extra_fact_policy_authority_resolution"))


def _evidence_files(expected: Mapping[str, Any]) -> set[str]:
    """Basenames of gold evidence files (refs point into packet input paths)."""
    refs = expected.get("evidence_refs") or []
    values: list[str] = []
    if isinstance(refs, Mapping):
        for group in refs.values():
            values.extend(group or [])
    else:
        values.extend(refs)
    return {Path(str(ref).split("#")[0]).name for ref in values}


# --- metrics -------------------------------------------------------------------

def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """FN/FP/U over fixed denominators with conservative intervals (§E3)."""
    needs = [r for r in rows if r["needs"]]
    routine = [r for r in rows if not r["needs"]]
    u_needs = sum(1 for r in needs if r["technical"])
    u_routine = sum(1 for r in routine if r["technical"])
    fn = sum(1 for r in needs if not r["technical"] and r["fn"])
    fp = sum(1 for r in routine if not r["technical"] and r["fp"])
    passed_routine = sum(1 for r in routine
                         if not r["technical"] and r.get("pass"))
    return {
        "n_needs": len(needs), "n_routine": len(routine),
        "fn": fn, "fp": fp, "u_needs": u_needs, "u_routine": u_routine,
        "fn_interval": ([fn / len(needs), (fn + u_needs) / len(needs)]
                        if needs else None),
        "fp_interval": ([fp / len(routine), (fp + u_routine) / len(routine)]
                        if routine else None),
        "routine_completion": (f"{passed_routine}/{len(routine)}"
                               if routine else "N/A"),
    }


# --- suite runner ---------------------------------------------------------------

def _command(case_id: str, phase: str, action: str, version: int | None) -> Command:
    return Command(key=f"eval-{case_id}-{phase}-{action}",
                   actor_id=EVAL_ACTOR, demo_role=_EVAL_ROLE,
                   expected_case_version=version, body={})


def _author_hint_guard(service: Service, packets: list[Packet]) -> None:
    if "live" not in service.reader.mode.lower():
        return
    stale = [p.case_id for p in packets
             if not p.manifest.get("author_hints_removed")]
    if stale:
        raise DomainError(
            "AUTHOR_HINTS_IN_PROMPT",
            f"Packets {stale} còn author hints trong nguồn; live prompt cần "
            f"dataset version mới đã gỡ hints, giữ nguyên source/expected cũ.",
        )


def _actual_money(report) -> dict[str, Any]:
    components = report.components
    return {"t": components.t.value, "b": components.b.value,
            "e": components.e.value, "a": components.a.value,
            "ra": components.ra.value, "p": components.p.value,
            "rp": components.rp.value, "s": report.calculated_net_vnd,
            "proposed_net_vnd": report.proposed_net_vnd}


def _run_case(service: Service, packet: Packet, phase: str,
              files: list[Path]) -> tuple[str, Any, Any]:
    """Submit + upload + run one phase through the real Service path."""
    expected = (packet.expected_initial if phase == "INITIAL"
                else packet.expected_after or {})
    submission = Submission(
        employee_ref=str(expected.get("employee") or DEFAULT_EMPLOYEE_REF),
        work_ref=str(expected.get("work")
                     or packet.manifest.get("business_story_id")
                     or packet.case_id),
        job=packet.job,  # type: ignore[arg-type]
        money_as_of=datetime.fromisoformat(packet.as_of),
        knowledge_cutoff=datetime.fromisoformat(packet.as_of),
        form={"purpose": f"Evaluation packet {packet.case_id} ({phase})",
              "scope": "eval"},
    )
    case = service.submit(submission, _command(packet.case_id, phase,
                                                "create", None))
    version = case.case_version
    for index, path in enumerate(files):
        record = service.add_source(
            case.id, Upload(filename=path.name, content=path.read_bytes()),
            _command(packet.case_id, phase, f"source-{index}", version))
        version = service.get_case(case.id).case_version
        assert record.case_id == case.id
    run = service.start(case.id, _command(packet.case_id, phase, "run", version))
    final = service.wait(run.id)
    report = None
    if final.status == "SUCCEEDED":
        try:
            report = service.report(run.id)
        except DomainError:
            report = None
    return case.id, final, report


def _compare_initial(service: Service, packet: Packet, case_id: str,
                     run, report) -> CaseResult:
    expected = packet.expected_initial
    needs = _requires_resolution(expected)
    checks: list[Check] = []

    # axis money: fixed adapter, None-strict; B3 chấm completion/state riêng.
    view = None
    if packet.job != "B3":
        try:
            view = expected_money_view(expected)
        except DomainError as error:
            checks.append(Check(axis="money", ok=False,
                                expected=None, actual=None, note=error.message))
    if view is not None:
        actual = _actual_money(report)
        money_verdict = compare_money(view, {k: actual[k] for k in view})
        checks.append(Check(
            axis="money", expected=dict(view),
            actual={k: actual[k] for k in view},
            ok=money_verdict == "PASS",
            note="S = E - (A - RA) - (P - RP); None là unknown, không phải 0.",
        ))

    unresolved = [issue for issue in report.issues if issue.unresolved]
    if needs:
        ok = report.completion == "INCOMPLETE" and len(unresolved) > 0
        note = "Cần material issue thật, không bịa số và không tự complete."
        owners = expected.get("allowed_owner_roles")
        if owners:
            questions = service.questions(case_id)
            bad_owners = [q.id for q in questions
                          if q.status == "OPEN" and q.owner not in owners]
            ok = ok and not bad_owners
            note += f" Owner hợp lệ: {owners}."
        issue_type = expected.get("issue_type")
        if issue_type:
            prefix = str(issue_type).split("_")[0]
            ok = ok and any(i.type == prefix for i in unresolved)
            note += f" Issue type kỳ vọng: {issue_type}."
        checks.append(Check(axis="completion", expected="INCOMPLETE+issues",
                            actual=f"{report.completion}+{len(unresolved)}",
                            ok=ok, note=note))
    else:
        checks.append(Check(
            axis="completion", expected="COMPLETE, không issue",
            actual=f"{report.completion}+{len(unresolved)}",
            ok=report.completion == "COMPLETE" and len(unresolved) == 0,
            note="Routine phải ra report hoàn chỉnh; issue thừa là FP.",
        ))

    # axis links: mọi file evidence của gold phải được nạp và report tham chiếu.
    view_after = service.get_case(case_id)
    by_name = {s.filename: s.id for s in view_after.sources}
    wanted = _evidence_files(expected)
    missing = {name for name in wanted
               if name not in by_name
               or by_name[name] not in set(report.source_refs)}
    checks.append(Check(
        axis="links", expected=sorted(wanted),
        actual=sorted(by_name),
        ok=not missing, note=f"File chưa nạp/tham chiếu: {sorted(missing)}.",
    ))

    # axis state: không tự duyệt/đóng/tạo request sau run.
    allowed_true = [key for key in (
        "settlement_approved", "close_allowed", "request_creation_allowed",
        "automatic_request_creation_allowed", "bank_execution_allowed",
        "automatic_bank_execution_allowed", "duplicate_payment_allowed",
        "financial_approval_allowed",
    ) if expected.get(key) is True]
    state_ok = (view_after.money_summary["approved_vnd"] is None
                and not service.closed(case_id)
                and not allowed_true)
    checks.append(Check(
        axis="state",
        expected="không approval/closure/request tự sinh",
        actual={"approved_vnd": view_after.money_summary["approved_vnd"],
                "stage": view_after.stage},
        ok=state_ok,
        note="Hệ thống không tự phê duyệt/đóng/chi; con người quyết định.",
    ))

    verdict: Verdict = "PASS" if all(c.ok for c in checks) else "FAIL"
    return CaseResult(
        case_id=packet.case_id, job=packet.job, phase="INITIAL",
        family_id=packet.family_id, dataset_role=packet.dataset_role,
        verdict=verdict, checks=checks, run_id=run.id, run_status=run.status,
        mode=report.mode, needs_resolution_expected=needs, technical=False,
        first_pass_routine_expected=bool(expected.get("routine_first_pass")
                                         or expected.get("routine_check_report_expected")),
        timestamp=utcnow().isoformat(),
    )


def _compare_followup(service: Service, packet: Packet, case_id: str,
                      run, report) -> CaseResult:
    expected = packet.expected_after or {}
    needs = _requires_resolution(expected)
    checks: list[Check] = []
    try:
        view = expected_money_view(expected)
        actual = _actual_money(report)
        checks.append(Check(
            axis="money", expected=dict(view),
            actual={k: actual[k] for k in view},
            ok=compare_money(view, {k: actual[k] for k in view}) == "PASS",
            note="Phase assisted sau followup hợp lệ; first-pass giữ nhãn cũ.",
        ))
    except DomainError as error:
        checks.append(Check(axis="money", ok=False, note=error.message))
    unresolved = [issue for issue in report.issues if issue.unresolved]
    checks.append(Check(
        axis="completion", expected="COMPLETE sau re-check",
        actual=f"{report.completion}+{len(unresolved)}",
        ok=report.completion == "COMPLETE" and len(unresolved) == 0,
        note="Re-check với nguồn đủ mới resolve; không đổi nhãn first-pass.",
    ))
    view_after = service.get_case(case_id)
    checks.append(Check(
        axis="state", expected="không approval/closure tự sinh",
        actual={"approved_vnd": view_after.money_summary["approved_vnd"],
                "stage": view_after.stage},
        ok=view_after.money_summary["approved_vnd"] is None
        and not service.closed(case_id),
    ))
    verdict: Verdict = "PASS" if all(c.ok for c in checks) else "FAIL"
    return CaseResult(
        case_id=packet.case_id, job=packet.job, phase="AFTER_FOLLOWUP",
        family_id=packet.family_id, dataset_role=packet.dataset_role,
        verdict=verdict, checks=checks, run_id=run.id, run_status=run.status,
        mode=report.mode, needs_resolution_expected=needs, technical=False,
        first_pass_routine_expected=bool(expected.get("first_pass_routine")),
        timestamp=utcnow().isoformat(),
    )


def _technical_result(packet: Packet, phase: str, run) -> CaseResult:
    return CaseResult(
        case_id=packet.case_id, job=packet.job, phase=phase,
        family_id=packet.family_id, dataset_role=packet.dataset_role,
        verdict="INCONCLUSIVE", checks=[], run_id=run.id, run_status=run.status,
        mode="UNKNOWN", needs_resolution_expected=_requires_resolution(
            packet.expected_initial if phase == "INITIAL"
            else packet.expected_after or {}),
        technical=True, timestamp=utcnow().isoformat(),
    )


def run_suite(corpus_dir: Path, service: Service,
              packet_ids: list[str] | None = None) -> SuiteReport:
    """Sequential suite over the real Service; expected never enters inputs."""
    packets = discover_packets(Path(corpus_dir))
    _author_hint_guard(service, packets)
    if packet_ids is not None:
        wanted = set(packet_ids)
        packets = [p for p in packets if p.case_id in wanted]
    results: list[CaseResult] = []
    metric_rows: list[dict[str, Any]] = []

    for packet in packets:
        case_id, run, report = _run_case(service, packet, "INITIAL",
                                        packet.input_files)
        if report is None:
            result = _technical_result(packet, "INITIAL", run)
            results.append(result)
            metric_rows.append({"needs": result.needs_resolution_expected,
                                "technical": True, "fn": False, "fp": False,
                                "pass": False})
            continue
        result = _compare_initial(service, packet, case_id, run, report)
        results.append(result)
        unresolved = int(str(
            [c for c in result.checks if c.axis == "completion"][0].actual
        ).split("+")[-1])
        metric_rows.append({
            "needs": result.needs_resolution_expected, "technical": False,
            "fn": (result.needs_resolution_expected
                   and report.completion == "COMPLETE"),
            "fp": (not result.needs_resolution_expected and unresolved > 0),
            "pass": result.verdict == "PASS",
        })

        if packet.followup_files and packet.expected_after:
            followup_result = _run_followup(service, packet, case_id)
            results.append(followup_result)

    notes = [
        "Corpus DEVELOPMENT_ONLY từ một template family (clones không phải "
        "cases độc lập): dùng để thiết kế/tune, KHÔNG phải holdout độc lập.",
        "Gold hiện là draft single-author (chưa adjudication độc lập); "
        "mọi con số là baseline trung thực, chưa phải chất lượng đã chứng minh.",
    ]
    if "live" not in service.reader.mode.lower():
        notes.append(
            "Chế độ fake/replay không chứng minh chất lượng OCR/LLM live; "
            "sources dạng narrative của corpus không đọc được bằng structured "
            "ledger reader nên kết quả money/links phản ánh capability reader."
        )
    if any(p.job == "B3" for p in packets):
        notes.append(
            "B3 được chấm riêng theo trục completion/state; adapter money của "
            "harness v0 chỉ cover components B7."
        )
    return SuiteReport(
        suite=f"settlement-dev-{len(packets)}",
        timestamp=utcnow().isoformat(), mode=service.reader.mode,
        source_hash=_dataset_hash(discover_packets(Path(corpus_dir))),
        config_hash=_config_hash(service),
        results=results, metrics=compute_metrics(metric_rows), notes=notes,
    )


def _run_followup(service: Service, packet: Packet, case_id: str) -> CaseResult:
    """Assisted re-check: answer the open question with the followup source."""
    questions = service.questions(case_id)
    allowed = packet.expected_initial.get("allowed_owner_roles")
    open_questions = [q for q in questions if q.status == "OPEN"
                      and (not allowed or q.owner in allowed)]
    if not open_questions:
        return CaseResult(
            case_id=packet.case_id, job=packet.job, phase="AFTER_FOLLOWUP",
            family_id=packet.family_id, dataset_role=packet.dataset_role,
            verdict="INCONCLUSIVE", checks=[], mode=service.reader.mode,
            needs_resolution_expected=False, technical=False,
            first_pass_routine_expected=False, timestamp=utcnow().isoformat(),
        )
    question = open_questions[0]
    version = service.get_case(case_id).case_version
    source_ids = []
    for index, path in enumerate(packet.followup_files):
        record = service.add_source(
            case_id, Upload(filename=path.name, content=path.read_bytes()),
            Command(key=f"eval-{packet.case_id}-followup-source-{index}",
                    actor_id=EVAL_ACTOR, demo_role=_EVAL_ROLE,
                    expected_case_version=version, body={}))
        version = service.get_case(case_id).case_version
        source_ids.append(record.id)
    service.respond(
        question.id,
        ResponsePayload(content="Nguồn bổ sung theo followup của packet.",
                        source_ids=source_ids),
        Command(key=f"eval-{packet.case_id}-followup-respond",
                actor_id=f"EVAL-{question.owner}", demo_role=question.owner,
                expected_case_version=version, body={}))
    version = service.get_case(case_id).case_version
    run = service.start(case_id, _command(packet.case_id, "followup", "run",
                                          version))
    final = service.wait(run.id)
    if final.status != "SUCCEEDED":
        return _technical_result(packet, "AFTER_FOLLOWUP", final)
    report = service.report(run.id)
    return _compare_followup(service, packet, case_id, final, report)


def _dataset_hash(packets: list[Packet]) -> str:
    basis = [{"case_id": p.case_id,
              "manifest": _sha256_bytes((p.directory / "manifest.json")
                                        .read_bytes()),
              "inputs": [str(f) for f in p.input_files]}
             for p in packets]
    return _sha256_bytes(_dump(basis).encode("utf-8"))


def _config_hash(service: Service) -> str:
    basis = {
        "service": service.config.model_dump(mode="json"),
        "policy": service.policy,
        "reader_mode": service.reader.mode,
    }
    return _sha256_bytes(_dump(basis).encode("utf-8"))
