"""Task 3: evaluate_b3_proposal regressions (acceptance matrix T01–T15).

Red-first: the proposal evaluator, rules dispatch and pipeline branch do not
exist yet. Expected values are independent literals (2M/3M/5M/8M) and packet
assertions — never values computed by the engine under test.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from invoice_referee.settlement.b3 import evaluate_b3_proposal
from invoice_referee.settlement.models import Issue
from invoice_referee.settlement.rules import evaluate as engine_evaluate
from tests.settlement.b3_builders import (
    CONTEXT,
    DEMO_CLOCK,
    NATIVE_FORM,
    make_b3_observations,
    make_b3_run,
)

WORK = "WORK-TEST-0001"


def evaluate(run_input, observations, technical=None):
    return evaluate_b3_proposal(
        run_input, observations, run_id="R-B3", mode="FAKE_OR_REPLAY",
        technical_issues=technical or [])


def check_of(report, rule):
    matches = [c for c in report.checks if c.rule == rule]
    assert matches, f"thiếu check {rule} trong { [c.rule for c in report.checks] }"
    return matches[0]


def issues_of(report, owner=None, type_=None):
    return [i for i in report.issues
            if (owner is None or i.owner == owner)
            and (type_ is None or i.type == type_)]


def import_form(**overrides) -> dict:
    form = dict(NATIVE_FORM)
    form["intake_method"] = "IMPORT"
    form.update(overrides)
    return form


def replace(observations, fact_id, **updates):
    return [o.model_copy(update=updates) if o.fact_id == fact_id else o
            for o in observations]


def context_with(**changes) -> dict:
    context = json.loads(json.dumps(CONTEXT))
    context.update(changes)
    return context


def history_event(event_ref, kind, status, amount, **overrides):
    event = {
        "event_ref": event_ref, "employee_ref": "NV-DEMO-01",
        "work_ref": WORK, "kind": kind, "amount_vnd": amount,
        "event_at": "2026-10-05T09:00:00+07:00",
        "known_at": "2026-10-05T09:30:00+07:00",
        "status": status, "ref": event_ref,
    }
    event.update(overrides)
    return event


def run_with_clock(run, clock):
    submission = run.submission.model_copy(
        update={"money_as_of": clock, "knowledge_cutoff": clock})
    return run.model_copy(update={"submission": submission})


# --- T01: native initial case --------------------------------------------------

def test_initial_request_does_not_require_current_approvals():
    report = evaluate(make_b3_run(), [])
    assert report.b3 is not None
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"
    assert report.b3.forecast_company_vnd == 3_000_000
    assert report.b3.forecast_employee_vnd == 5_000_000
    assert report.b3.forecast_total_vnd == 8_000_000
    assert report.components.b.value is None
    assert report.components.a.value == 0
    assert report.components.ra.value == 0
    assert report.b3.work_permission == "PENDING_DECISION"
    assert report.b3.advance_approval == "PENDING_DECISION"
    assert report.b3.accountant_ref == "ACC-DEMO-01"
    assert report.b3.approver_ref == "APR-DEMO-01"
    assert report.calculated_net_vnd is None
    assert report.proposed_net_vnd is None
    assert report.direction is None
    assert not report.issues
    assert report.completion == "COMPLETE"
    # Không đòi văn bản công tác/approval đang xin (R6): pending là next decision
    for slot in ("t", "e", "p", "rp"):
        assert getattr(report.components, slot).state == "NOT_APPLICABLE"


def test_t01_native_checks_pass_without_upload_demand():
    report = evaluate(make_b3_run(), [])
    assert check_of(report, "request_positive").status == "PASS"
    assert check_of(report, "estimate_arithmetic").status == "PASS"
    assert check_of(report, "request_forecast_consistency").status == "PASS"
    assert check_of(report, "proposal_relation").status == "PASS"
    assert check_of(report, "source_form_consistency").status == "PASS"
    assert check_of(report, "history_coverage").status == "PASS"
    assert check_of(report, "prior_advance_state").status == "PASS"
    assert check_of(report, "decision_route").status == "PASS"
    # native form không có số bằng chữ
    assert check_of(report, "amount_words_consistency").status == "NOT_APPLICABLE"


# --- T02: import confirm flow ---------------------------------------------------

def test_t02_import_confirmed_ready_with_refs():
    from tests.settlement.b3_builders import b3_source_record

    run = make_b3_run(form=import_form()).model_copy(update={
        "sources": [b3_source_record("S-B3-REQ"),
                    b3_source_record("S-B3-FC")]})
    report = evaluate(run, make_b3_observations())
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"
    assert report.b3.forecast_total_vnd == 8_000_000
    refs = report.b3.field_refs["request_amount_vnd"]
    assert any(ref.startswith("form:") for ref in refs)
    assert any("S-B3-REQ" in ref for ref in refs)
    row_refs = report.b3.field_refs["estimate_rows.hotel.employee_vnd"]
    assert any("S-B3-FC" in ref for ref in row_refs)
    assert report.source_refs == ["S-B3-FC", "S-B3-REQ"]


def test_t02_draft_always_requires_confirmation():
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    report = evaluate(make_b3_run(form=draft), make_b3_observations())
    assert report.b3.readiness == "DRAFT_CONFIRMATION_REQUIRED"
    assert report.completion == "INCOMPLETE"


def test_t02_draft_intake_carries_extracted_facts_for_ui_fill():
    # draft IMPORT: proposal.intake mang facts trích xuất để UI điền rồi confirm
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    report = evaluate(make_b3_run(form=draft), make_b3_observations())
    intake = report.b3.intake
    assert intake.confirmed is False
    assert intake.request_amount_vnd == 2_000_000
    assert intake.destination == "Hà Nội"
    assert intake.settlement_due is not None
    assert intake.trip_start is not None
    assert len(intake.estimate_rows) == 4
    assert sum(r.employee_vnd or 0 for r in intake.estimate_rows) == 5_000_000
    assert sum(r.company_vnd or 0 for r in intake.estimate_rows) == 3_000_000


def test_t02_words_consistent_passes():
    report = evaluate(make_b3_run(form=import_form()), make_b3_observations())
    assert check_of(report, "amount_words_consistency").status == "PASS"


def test_draft_keeps_destination_and_purpose_with_source_refs():
    # Regression: destination/purpose extracted from merged prose must reach
    # the draft AND keep their source refs (not just the request amount).
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    report = evaluate(make_b3_run(form=draft), make_b3_observations())
    intake = report.b3.intake
    assert intake.destination == "Hà Nội"
    assert intake.purpose == ("Khảo sát yêu cầu và thống nhất phạm vi triển khai "
                              "dự án tại Hà Nội.")
    assert any("S-B3-REQ" in ref
               for ref in report.b3.field_refs["destination"])
    assert any("S-B3-REQ" in ref
               for ref in report.b3.field_refs["purpose"])
    # Draft never auto-submits: still awaiting employee confirmation.
    assert report.b3.readiness == "DRAFT_CONFIRMATION_REQUIRED"
    assert intake.confirmed is False


def test_draft_trip_fields_are_not_hardcoded():
    # Different destination/purpose must flow through unchanged — proves the
    # pipeline does not hardcode "Hà Nội" or the sample sentence.
    observations = []
    for o in make_b3_observations():
        if o.key == "trip.destination":
            observations.append(o.model_copy(update={"value": "Đà Nẵng"}))
        elif o.key == "trip.purpose":
            observations.append(o.model_copy(
                update={"value": "Khảo sát nhà máy tại Đà Nẵng."}))
        else:
            observations.append(o)
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    report = evaluate(make_b3_run(form=draft), observations)
    assert report.b3.intake.destination == "Đà Nẵng"
    assert report.b3.intake.purpose == "Khảo sát nhà máy tại Đà Nẵng."


def test_conflicting_destination_across_sources_is_not_silently_picked():
    # Request says Hà Nội, forecast says Đà Nẵng → keep the contradiction.
    observations = replace(make_b3_observations(), "FC-3", value="Đà Nẵng")
    draft = {"schema_version": "b3-intake-v1", "intake_method": "IMPORT",
             "confirmed": False}
    report = evaluate(make_b3_run(form=draft), observations)
    assert report.b3.intake.destination is None  # no arbitrary pick
    assert check_of(report, "proposal_relation").status == "UNRESOLVED"
    assert issues_of(report, owner="EMPLOYEE")


# --- T03: words vs number -------------------------------------------------------

def test_t03_amount_words_mismatch_fails():
    observations = replace(make_b3_observations(), "REQ-9", value=3_000_000)
    report = evaluate(make_b3_run(form=import_form()), observations)
    check = check_of(report, "amount_words_consistency")
    assert check.status == "FAIL"
    assert issues_of(report, owner="EMPLOYEE")
    assert report.b3.readiness == "NEEDS_INFORMATION"
    # không clip về words hay number
    assert report.b3.intake.request_amount_vnd == 2_000_000


def test_t03_unclear_words_value_unresolved_not_guessed():
    observations = replace(make_b3_observations(), "REQ-9",
                          read_state="UNCLEAR", value=None)
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert check_of(report, "amount_words_consistency").status == "UNRESOLVED"
    assert report.b3.readiness == "NEEDS_INFORMATION"


# --- T04: printed total vs row sum ---------------------------------------------

def test_t04_printed_employee_total_conflicts_with_rows():
    observations = replace(make_b3_observations(), "FC-18", value=4_000_000)
    report = evaluate(make_b3_run(form=import_form()), observations)
    check = check_of(report, "estimate_arithmetic")
    assert check.status == "FAIL"
    assert "4.000.000" in check.reason or "4000000" in check.reason
    assert "5.000.000" in check.reason or "5000000" in check.reason
    assert report.b3.readiness == "NEEDS_INFORMATION"
    # không silently dùng printed hay sum
    assert report.b3.forecast_employee_vnd == 5_000_000  # giữ rows làm cơ sở, check giữ cả hai


# --- T05: request vượt employee forecast ----------------------------------------

def test_t05_request_above_forecast_needs_authorized_review():
    # native: nhân viên xin 6M so với dự toán employee 5M
    report = evaluate(make_b3_run(
        form=dict(NATIVE_FORM, request_amount_vnd=6_000_000)), [])
    assert report.b3.readiness == "NEEDS_AUTHORIZED_REVIEW"
    assert report.b3.intake.request_amount_vnd == 6_000_000  # giữ nguyên số
    authority = issues_of(report, owner="APPROVER", type_="AUTHORITY")
    assert len(authority) >= 2  # vượt forecast + vượt hạn mức ứng 5M là issue riêng
    assert check_of(report, "request_forecast_consistency").status == "FAIL"
    assert report.b3.advance_approval == "NEEDS_REVIEW"


# --- T06: form vs source conflict ------------------------------------------------

def test_t06_source_form_conflict_keeps_both_refs():
    observations = make_b3_observations()  # giấy ghi 2M
    report = evaluate(make_b3_run(form=import_form(request_amount_vnd=3_000_000)),
                      observations)
    check = check_of(report, "source_form_consistency")
    assert check.status == "FAIL"
    assert any(ref.startswith("form:") for ref in check.refs)
    assert any("S-B3-REQ" in ref for ref in check.refs)
    assert report.b3.readiness == "NEEDS_INFORMATION"
    assert issues_of(report, owner="EMPLOYEE")


# --- T07: row UNCLEAR ------------------------------------------------------------

def test_t07_unclear_row_keeps_null_no_partial_sum():
    observations = replace(make_b3_observations(), "FC-12",
                          read_state="UNCLEAR", value=None)
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert report.b3.forecast_employee_vnd is None
    assert report.b3.forecast_total_vnd is None
    check = check_of(report, "estimate_arithmetic")
    assert check.status != "PASS"
    quality = [i for i in report.issues if i.owner == "EMPLOYEE"]
    assert quality, "phải có issue EMPLOYEE kèm locator của dòng mờ"
    assert any("FC-12" in ref or "S-B3-FC" in ref
               for issue in quality for ref in issue.refs)
    assert report.b3.readiness == "NEEDS_INFORMATION"


# --- T08: thiếu coverage ----------------------------------------------------------

def test_t08_missing_coverage_keeps_history_unknown_accountant():
    report = evaluate(make_b3_run(context=context_with(coverage=[])), [])
    assert report.components.a.value is None
    assert report.components.ra.value is None
    assert report.components.a.state == "UNKNOWN"
    check = check_of(report, "history_coverage")
    assert check.status == "UNRESOLVED"
    assert issues_of(report, owner="ACCOUNTANT")
    # initial B/work vẫn pending, không đòi upload
    assert report.b3.work_permission == "PENDING_DECISION"
    assert report.components.b.value is None
    assert report.b3.readiness == "NEEDS_INFORMATION"
    assert not issues_of(report, owner="EMPLOYEE")


def test_t08_no_context_at_all_unknown():
    report = evaluate(make_b3_run(context={"schema_version":
                                           "b3-company-context-v1",
                                           "version": "none",
                                           "activated": False,
                                           "synthetic": False}), [])
    assert report.components.a.value is None
    assert report.b3.readiness == "NEEDS_INFORMATION"
    assert report.b3.accountant_ref is None
    assert report.b3.approver_ref is None


# --- T09: ngoài cửa sổ coverage --------------------------------------------------

def test_t09_as_of_after_coverage_window_unknown():
    late = datetime(2026, 10, 11, 9, 0, tzinfo=timezone(timedelta(hours=7)))
    run = run_with_clock(make_b3_run(), late)
    report = evaluate(run, [])
    assert report.components.a.value is None
    check = check_of(report, "history_coverage")
    assert check.status == "UNRESOLVED"
    assert issues_of(report, owner="ACCOUNTANT")
    assert report.b3.readiness == "NEEDS_INFORMATION"


def test_t09_coverage_for_other_employee_does_not_cover():
    coverage = [dict(CONTEXT["coverage"][0], employee_ref="NV-KHAC")]
    report = evaluate(make_b3_run(context=context_with(coverage=coverage)), [])
    assert report.components.a.value is None
    assert check_of(report, "history_coverage").status == "UNRESOLVED"


# --- T10: prior pending/actual/refused --------------------------------------------

def test_t10_prior_states_retained_routed_to_approver():
    history = [
        history_event("company:evt-adv", "ADVANCE", "RECEIVED", 1_000_000),
        history_event("company:evt-pending", "PENDING_ADVANCE", "PENDING",
                     2_000_000),
        history_event("company:evt-refused", "ADVANCE_APPROVAL", "REFUSED",
                     1_500_000),
    ]
    report = evaluate(make_b3_run(context=context_with(history=history)), [])
    assert report.components.a.value == 1_000_000  # chỉ RECEIVED trong scope
    assert report.components.ra.value == 0
    assert report.b3.readiness == "NEEDS_AUTHORIZED_REVIEW"
    authority = issues_of(report, owner="APPROVER", type_="AUTHORITY")
    assert len(authority) >= 2  # pending và refused là review riêng
    refs = {ref for issue in authority for ref in issue.refs}
    assert "company:evt-pending" in refs
    assert "company:evt-refused" in refs
    assert report.b3.advance_approval == "NEEDS_REVIEW"


def test_t10_out_of_window_events_not_summed():
    history = [history_event("company:evt-late", "ADVANCE", "RECEIVED",
                             9_000_000,
                             event_at="2026-10-11T09:00:00+07:00",
                             known_at="2026-10-11T09:00:00+07:00")]
    report = evaluate(make_b3_run(context=context_with(history=history)), [])
    assert report.components.a.value == 0  # event sau money_as_of không cộng


def test_t10_other_work_history_not_summed():
    history = [history_event("company:evt-other", "ADVANCE", "RECEIVED",
                             4_000_000, work_ref="WORK-KHAC")]
    report = evaluate(make_b3_run(context=context_with(history=history)), [])
    assert report.components.a.value == 0


# --- T11: budget authority insufficient -------------------------------------------

def test_t11_forecast_exceeds_budget_authority():
    grants = [dict(CONTEXT["grants"][0], max_budget_vnd=7_000_000)]
    report = evaluate(make_b3_run(context=context_with(grants=grants)), [])
    assert report.b3.forecast_total_vnd == 8_000_000
    assert report.b3.readiness == "NEEDS_AUTHORIZED_REVIEW"
    authority = issues_of(report, owner="APPROVER", type_="AUTHORITY")
    assert authority
    assert check_of(report, "decision_route").status != "PASS"


# --- T12: file của nhân viên không cấp quyền/absence -------------------------------

def test_t12_employee_history_file_not_trusted_as_coverage():
    # coverage bị drop; file SUPPORTING khai "history 0" không biến unknown thành 0
    observations = [
        o for o in make_b3_observations()
    ] + [
        # file nhân viên tự khai, không phải company-side
        _obs("T12-1", "document.role", "SUPPORTING", "S-B3-EMP"),
        _obs("T12-2", "history.advance.received", 0, "S-B3-EMP"),
    ]
    report = evaluate(make_b3_run(context=context_with(coverage=[]),
                                  form=import_form()), observations)
    assert report.components.a.value is None  # unknown, không phải 0


def test_t12_expired_grant_cannot_ready():
    grants = [dict(CONTEXT["grants"][0],
                   effective_to="2026-10-05T23:59:59+07:00")]
    report = evaluate(make_b3_run(context=context_with(grants=grants)), [])
    assert report.b3.readiness == "NEEDS_AUTHORIZED_REVIEW"
    assert report.b3.work_permission == "NEEDS_REVIEW"
    assert report.b3.advance_approval == "NEEDS_REVIEW"
    assert issues_of(report, owner="APPROVER", type_="AUTHORITY")


# --- T13: nhiều bản forecast -------------------------------------------------------

def _forecast_unit(source_id, person="Nguyễn An", total=8_000_000):
    base = [o for o in make_b3_observations() if o.source_id == "S-B3-FC"]
    unit = []
    for o in base:
        updates = {"source_id": source_id,
                   "fact_id": o.fact_id.replace("FC-", f"{source_id}-")}
        if o.key == "person.name":
            updates.update(value=person, raw=person)
        if o.key == "forecast.total":
            updates.update(value=total, raw=str(total))
        unit.append(o.model_copy(update=updates))
    return unit


def _request_unit(source_id="S-B3-REQ"):
    return [o for o in make_b3_observations() if o.source_id == source_id]


def test_t13_exact_duplicate_forecast_not_summed():
    observations = _request_unit() + _forecast_unit("S-B3-FC") \
        + _forecast_unit("S-B3-FC-COPY")
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert report.b3.forecast_employee_vnd == 5_000_000  # không 10M
    assert report.b3.forecast_total_vnd == 8_000_000
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"


def test_t13_conflicting_forecasts_unresolved_not_summed():
    observations = (_request_unit() + _forecast_unit("S-B3-FC")
                    + _forecast_unit("S-B3-FC-KHAC", person="Trần Khác",
                                      total=9_000_000))
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert report.b3.forecast_total_vnd is None
    check = check_of(report, "proposal_relation")
    assert check.status != "PASS"
    assert report.b3.readiness == "NEEDS_INFORMATION"


# --- T14: technical failure ---------------------------------------------------------

def test_t14_technical_failure_incomplete_but_keeps_clear_parts():
    technical = [Issue(issue_id="I-TECH-1", type="TECHNICAL",
                       owner="ACCOUNTANT",
                       message="Nguồn S-X không đọc được (PROVIDER_FAILED)",
                       refs=["S-X"], blocked="source", unresolved=True)]
    report = evaluate(make_b3_run(), [], technical=technical)
    assert report.completion == "INCOMPLETE"
    assert report.b3.readiness == "NEEDS_INFORMATION"
    assert report.b3.forecast_total_vnd == 8_000_000  # phần rõ vẫn giữ
    assert any(i.type == "TECHNICAL" for i in report.issues)


# --- T15: giấy v2 chỉ tên/bộ phận, gộp trip -----------------------------------------

def test_t15_v2_papers_name_only_identity_no_employee_ref_demand():
    observations = _request_unit() + [
        o for o in _forecast_unit("S-B3-FC")
        if o.key != "trip.destination" and o.key != "trip.start"
        and o.key != "trip.end"
    ]  # dự toán v2 gộp trip vào nội dung, không có trip fields riêng
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"
    assert not any("employee_ref" in issue.message for issue in report.issues)
    assert not any("giấy lệnh" in issue.message for issue in report.issues)
    assert report.b3.forecast_total_vnd == 8_000_000


def test_t15_person_name_mismatch_with_persona_asks_employee():
    observations = replace(make_b3_observations(), "REQ-2", value="Người Khác")
    report = evaluate(make_b3_run(form=import_form()), observations)
    assert report.b3.readiness == "NEEDS_INFORMATION"
    assert issues_of(report, owner="EMPLOYEE")
    assert check_of(report, "proposal_relation").status != "PASS"


# --- dispatch (rules) ---------------------------------------------------------------

def test_rules_dispatch_b3_v1_to_proposal():
    report = engine_evaluate(make_b3_run(), [], [], run_id="R-D",
                             mode="FAKE_OR_REPLAY")
    assert report.b3 is not None
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"


def test_rules_dispatch_legacy_b3_untouched():
    from tests.settlement import builders as b

    run_input, facts, relations = b.run_input(job="B3")
    report = engine_evaluate(run_input, facts, relations, run_id="R-L",
                             mode="FAKE_OR_REPLAY")
    assert report.b3 is None  # nhánh legacy giữ nguyên evaluator cũ
    assert report.job == "B3"


def _obs(fact_id, key, value, source_id, page=1):
    from invoice_referee.settlement.models import Observation

    return Observation(
        fact_id=fact_id, key=key, raw=str(value), read_state="READ",
        value=value, source_id=source_id, page=page,
        locator=f"page {page}", basis=f"fixture {source_id} page {page}")
