"""Task 1 (b3-intake-v1): form/context/proposal contract regressions.

Red-first: these fail until ``settlement/b3.py`` records and the optional
``RunInput.b3_context`` / ``Report.b3`` fields exist. Money is strict integer
VND; ``None`` is unknown, never 0; IMPORT drafts may be partially empty while
confirmed submissions must be complete.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from invoice_referee.settlement.b3 import B3CompanyContext, B3Intake
from invoice_referee.settlement.models import Report, RunInput
from tests.settlement.b3_builders import (
    CONTEXT,
    NATIVE_FORM,
    make_b3_observations,
    make_b3_run,
)


def _form(**overrides) -> dict:
    form = dict(NATIVE_FORM)
    for key, value in overrides.items():
        if value is ...:
            form.pop(key, None)
        else:
            form[key] = value
    return form


def _rows(*rows) -> list[dict]:
    return [dict(row) for row in rows]


# --- draft vs confirmed -------------------------------------------------------

def test_import_draft_can_be_empty():
    draft = B3Intake(schema_version="b3-intake-v1", intake_method="IMPORT",
                    confirmed=False)
    assert draft.request_amount_vnd is None
    assert draft.estimate_rows == []
    assert draft.destination is None


def test_native_expected_split():
    run = make_b3_run()
    intake = B3Intake.model_validate(run.submission.form)
    assert sum(row.employee_vnd for row in intake.estimate_rows) == 5_000_000
    assert intake.request_amount_vnd == 2_000_000
    assert intake.schema_version == "b3-intake-v1"
    assert intake.confirmed is True


def test_confirmed_missing_destination_invalid():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(destination=..., confirmed=True))


def test_confirmed_missing_rows_invalid():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(estimate_rows=[]))


def test_confirmed_nonpositive_request_invalid():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(request_amount_vnd=0))
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(request_amount_vnd=None))


def test_confirmed_missing_deadline_invalid():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(settlement_due=...))


def test_confirmed_missing_dates_invalid():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(trip_start=..., trip_end=...))


def test_draft_partial_dates_allowed():
    draft = B3Intake.model_validate(
        _form(confirmed=False, request_amount_vnd=None, trip_end=...,
              estimate_rows=[]))
    assert draft.trip_start is not None
    assert draft.trip_end is None


# --- shape and money strictness ----------------------------------------------

@pytest.mark.parametrize("field", ["request_amount_vnd"])
def test_float_money_rejected(field):
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(**{field: 2_000_000.5}))


def test_bool_money_rejected():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(request_amount_vnd=True))


def test_negative_row_amount_rejected():
    rows = _rows(*NATIVE_FORM["estimate_rows"])
    rows[0]["employee_vnd"] = -1
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(estimate_rows=rows))


def test_row_bool_money_rejected():
    rows = _rows(*NATIVE_FORM["estimate_rows"])
    rows[0]["company_vnd"] = True
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(estimate_rows=rows))


def test_duplicate_row_id_rejected():
    rows = _rows(*NATIVE_FORM["estimate_rows"])
    rows[1]["row_id"] = rows[0]["row_id"]
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(estimate_rows=rows))


def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(trip_start="2026-10-13",
                                      trip_end="2026-10-12"))


def test_deadline_before_end_rejected():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(settlement_due="2026-10-12"))


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        B3Intake.model_validate(_form(approver_ref="APR-DEMO-01"))


def test_blank_text_is_unknown_not_invalid():
    # chuỗi rỗng (form chưa chạm) = null, không phải text rỗng hợp lệ
    draft = B3Intake.model_validate(_form(purpose="", confirmed=False,
                                          request_amount_vnd=None,
                                          estimate_rows=[]))
    assert draft.purpose is None
    with pytest.raises(ValidationError):
        # confirmed vẫn bắt buộc purpose khác None
        B3Intake.model_validate(_form(purpose="   "))


# --- company context ----------------------------------------------------------

def test_context_parses_packet_literal():
    context = B3CompanyContext.model_validate(CONTEXT)
    assert context.activated is True
    assert context.synthetic is True
    assert context.demo_clock is not None
    assert context.grants[0].max_budget_vnd == 10_000_000
    assert context.grants[0].max_advance_vnd == 5_000_000
    assert context.grants[0].allow_work is True
    assert context.coverage[0].complete_prior_history is True
    assert context.history == []


def test_context_demo_clock_requires_synthetic_activated():
    bad = dict(CONTEXT)
    bad["synthetic"] = False
    with pytest.raises(ValidationError):
        B3CompanyContext.model_validate(bad)


def test_context_not_activated_rejected_for_use():
    inactive = dict(CONTEXT)
    inactive["activated"] = False
    inactive["demo_clock"] = None
    context = B3CompanyContext.model_validate(inactive)
    assert context.activated is False


def test_history_amount_required_unless_work_decision():
    event = {
        "event_ref": "company:evt-1", "employee_ref": "NV-DEMO-01",
        "work_ref": "WORK-TEST-0001", "kind": "ADVANCE",
        "amount_vnd": None,
        "event_at": "2026-10-05T09:00:00+07:00",
        "known_at": "2026-10-05T09:00:00+07:00",
        "status": "RECEIVED", "ref": "company:evt-1",
    }
    with pytest.raises(ValidationError):
        B3CompanyContext.model_validate({**CONTEXT, "history": [event]})
    work = {**event, "kind": "WORK_DECISION", "status": "APPROVED"}
    context = B3CompanyContext.model_validate({**CONTEXT, "history": [work]})
    assert context.history[0].amount_vnd is None


def test_history_received_only_for_actual_money_kinds():
    base = {
        "employee_ref": "NV-DEMO-01", "work_ref": "WORK-TEST-0001",
        "amount_vnd": 2_000_000,
        "event_at": "2026-10-05T09:00:00+07:00",
        "known_at": "2026-10-05T09:00:00+07:00",
    }
    approved = {"event_ref": "company:evt-2", "kind": "ADVANCE_APPROVAL",
                "status": "RECEIVED", "ref": "company:evt-2", **base}
    with pytest.raises(ValidationError):
        B3CompanyContext.model_validate({**CONTEXT, "history": [approved]})
    pending = {"event_ref": "company:evt-3", "kind": "PENDING_ADVANCE",
               "status": "PENDING", "ref": "company:evt-3", **base}
    context = B3CompanyContext.model_validate({**CONTEXT, "history": [pending]})
    assert context.history[0].status == "PENDING"


def test_history_nonpositive_amount_rejected():
    event = {
        "event_ref": "company:evt-4", "employee_ref": "NV-DEMO-01",
        "work_ref": "WORK-TEST-0001", "kind": "ADVANCE",
        "amount_vnd": 0,
        "event_at": "2026-10-05T09:00:00+07:00",
        "known_at": "2026-10-05T09:00:00+07:00",
        "status": "RECEIVED", "ref": "company:evt-4",
    }
    with pytest.raises(ValidationError):
        B3CompanyContext.model_validate({**CONTEXT, "history": [event]})


def test_context_duplicate_person_rejected():
    people = [dict(p) for p in CONTEXT["people"]]
    people.append(dict(people[0]))
    with pytest.raises(ValidationError):
        B3CompanyContext.model_validate({**CONTEXT, "people": people})


# --- models integration (B7 compatibility) -----------------------------------

def test_run_input_roundtrips_b3_context():
    run = make_b3_run()
    dumped = run.model_dump(mode="json")
    restored = RunInput.model_validate(dumped)
    assert restored.b3_context is not None
    assert restored.b3_context.version == "synthetic-verbal-v2"


def test_b7_report_deserializes_without_b3_field():
    report = Report.model_validate({
        "run_id": "R-LEGACY", "job": "B7", "completion": "COMPLETE",
        "mode": "FAKE_OR_REPLAY", "generated_at": "2026-10-09T00:00:00Z",
        "components": {
            "t": {"value": 0, "state": "KNOWN", "refs": []},
            "b": {"value": None, "state": "UNKNOWN", "refs": []},
            "e": {"value": 0, "state": "KNOWN", "refs": []},
            "a": {"value": 0, "state": "KNOWN", "refs": []},
            "ra": {"value": 0, "state": "KNOWN", "refs": []},
            "p": {"value": 0, "state": "NOT_APPLICABLE", "refs": []},
            "rp": {"value": 0, "state": "NOT_APPLICABLE", "refs": []},
        },
        "calculated_net_vnd": 0, "proposed_net_vnd": 0,
        "next_step": "", "source_refs": [],
    })
    assert report.b3 is None


def test_builder_observations_carry_independent_refs():
    observations = make_b3_observations()
    fact_ids = [o.fact_id for o in observations]
    assert len(fact_ids) == len(set(fact_ids))
    amounts = {o.key: o.value for o in observations
               if o.key in {"advance.request.amount", "forecast.company",
                            "forecast.employee", "forecast.total"}}
    assert amounts == {
        "advance.request.amount": 2_000_000,
        "forecast.company": 3_000_000,
        "forecast.employee": 5_000_000,
        "forecast.total": 8_000_000,
    }
