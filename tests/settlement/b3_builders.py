"""B3 verbal-intake test builders (b3-intake-v1).

Literals mirror the synthetic packet ``data/settlement/b3-verbal-v2``
(forms/native-form.json, company-context/context.json) but are written here as
independent literals: builders never call the engine under test to produce
expected values, and tests never feed expected data into a Reader.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from invoice_referee.settlement.models import (
    Observation,
    RunInput,
    SourceRecord,
    Submission,
)
from invoice_referee.settlement.b3 import B3CompanyContext

DEMO_CLOCK = datetime(2026, 10, 10, 9, 0, tzinfo=timezone(timedelta(hours=7)))

# Packet forms/native-form.json (WEB, confirmed) — independent literal.
NATIVE_FORM = {
    "schema_version": "b3-intake-v1",
    "intake_method": "WEB",
    "confirmed": True,
    "destination": "Hà Nội",
    "trip_start": "2026-10-12",
    "trip_end": "2026-10-13",
    "purpose": "Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án tại Hà Nội.",
    "assignment_note": None,
    "request_amount_vnd": 2_000_000,
    "settlement_due": "2026-10-16",
    "estimate_rows": [
        {
            "row_id": "flight",
            "description": "Vé máy bay khứ hồi",
            "basis": "1 vé khứ hồi",
            "company_vnd": 3_000_000,
            "employee_vnd": 0,
        },
        {
            "row_id": "hotel",
            "description": "Khách sạn",
            "basis": "1 đêm",
            "company_vnd": 0,
            "employee_vnd": 3_000_000,
        },
        {
            "row_id": "ground",
            "description": "Di chuyển tại Hà Nội",
            "basis": "Tổng chi phí di chuyển dự kiến",
            "company_vnd": 0,
            "employee_vnd": 1_000_000,
        },
        {
            "row_id": "meal",
            "description": "Bữa ăn phục vụ công việc",
            "basis": "Tổng chi phí bữa ăn dự kiến",
            "company_vnd": 0,
            "employee_vnd": 1_000_000,
        },
    ],
}

# Packet company-context/context.json — independent literal.
CONTEXT = {
    "schema_version": "b3-company-context-v1",
    "version": "synthetic-verbal-v2",
    "activated": True,
    "synthetic": True,
    "demo_clock": "2026-10-10T09:00:00+07:00",
    "people": [
        {"actor_ref": "NV-DEMO-01", "role": "EMPLOYEE", "name": "Nguyễn An",
         "department": "Kinh doanh"},
        {"actor_ref": "ACC-DEMO-01", "role": "ACCOUNTANT", "name": "Trần Bình",
         "department": "Kế toán"},
        {"actor_ref": "APR-DEMO-01", "role": "APPROVER", "name": "Lê Chi",
         "department": "Quản lý"},
    ],
    "routes": [
        {"employee_ref": "NV-DEMO-01", "accountant_ref": "ACC-DEMO-01",
         "approver_ref": "APR-DEMO-01"},
    ],
    "grants": [
        {"actor_ref": "APR-DEMO-01", "employee_ref": "NV-DEMO-01",
         "work_ref": None, "allow_work": True,
         "max_budget_vnd": 10_000_000, "max_advance_vnd": 5_000_000,
         "effective_from": "2026-10-01T00:00:00+07:00",
         "effective_to": "2026-10-31T23:59:59+07:00",
         "ref": "company:grant-01"},
    ],
    "coverage": [
        {"employee_ref": "NV-DEMO-01", "work_ref": None,
         "from": "2026-10-01T00:00:00+07:00",
         "to": "2026-10-10T09:00:00+07:00",
         "complete_prior_history": True,
         "groups": ["ADVANCE", "ADVANCE_RETURN", "ADVANCE_APPROVAL",
                    "PENDING_ADVANCE", "WORK_DECISION", "BUDGET_DECISION"],
         "methods": ["CASH", "BANK_TRANSFER", "OTHER_COMPANY_CHANNELS"],
         "missing_ranges": [],
         "owner_ref": "ACC-DEMO-01",
         "origin": ("Explicit synthetic company register covering all works "
                    "for this employee, including opening balances."),
         "ref": "company:coverage-01"},
    ],
    "history": [],
}


def make_b3_run(*, form: dict | None = None,
                context: dict | None = None) -> RunInput:
    """RunInput for a B3 v1 case: native form default, packet-like context."""
    return RunInput(
        case_id="C-B3-TEST", case_version=1, input_revision=1, control_epoch=1,
        submission=Submission(
            employee_ref="NV-DEMO-01", work_ref="WORK-TEST-0001", job="B3",
            money_as_of=DEMO_CLOCK, knowledge_cutoff=DEMO_CLOCK,
            form=form if form is not None else dict(NATIVE_FORM),
        ),
        sources=[],
        coverage=None,
        policy={"version": "settlement-demo-v0", "activated": True},
        authority=[],  # B3 v1 quyền đến từ context grants, không dùng legacy grant
        response_refs=[],
        config={"reader_mode": "FAKE_OR_REPLAY"},
        b3_context=B3CompanyContext.model_validate(
            context if context is not None else CONTEXT),
        snapshot_hash="snap-b3-test",
    )


def _paper_observation(fact_id: str, key: str, value, source_id: str,
                       page: int = 1, raw: str | None = None,
                       read_state: str = "READ") -> Observation:
    return Observation(
        fact_id=fact_id, key=key, raw=raw if raw is not None else str(value),
        read_state=read_state,  # type: ignore[arg-type]
        value=value, source_id=source_id, page=page,
        locator=f"page {page}", basis=f"fixture {source_id} page {page}",
    )


def make_b3_observations() -> list[Observation]:
    """Two employee papers (request + forecast) with independent refs."""
    request = "S-B3-REQ"
    forecast = "S-B3-FC"
    return [
        _paper_observation("REQ-1", "document.role", "ADVANCE_REQUEST", request),
        _paper_observation("REQ-2", "person.name", "Nguyễn An", request),
        _paper_observation("REQ-3", "trip.destination", "Hà Nội", request),
        _paper_observation("REQ-4", "trip.start", "2026-10-12", request),
        _paper_observation("REQ-5", "trip.end", "2026-10-13", request),
        _paper_observation("REQ-6", "trip.purpose",
                           "Khảo sát yêu cầu và thống nhất phạm vi triển khai "
                           "dự án tại Hà Nội.", request),
        _paper_observation("REQ-7", "advance.request.amount", 2_000_000, request),
        _paper_observation("REQ-8", "advance.request.amount_words",
                           "Hai triệu đồng", request, raw="Hai triệu đồng"),
        _paper_observation("REQ-9", "advance.request.amount_words_value",
                           2_000_000, request),
        _paper_observation("REQ-10", "advance.settlement_due", "2026-10-16",
                           request),
        _paper_observation("FC-1", "document.role", "FORECAST", forecast),
        _paper_observation("FC-2", "person.name", "Nguyễn An", forecast),
        _paper_observation("FC-3", "trip.destination", "Hà Nội", forecast),
        _paper_observation("FC-4", "trip.start", "2026-10-12", forecast),
        _paper_observation("FC-5", "trip.end", "2026-10-13", forecast),
        _paper_observation("FC-6", "trip.purpose",
                           "Khảo sát yêu cầu và thống nhất phạm vi triển khai "
                           "dự án tại Hà Nội.", forecast),
        _paper_observation("FC-7", "forecast.row.flight.description",
                           "Vé máy bay khứ hồi", forecast),
        _paper_observation("FC-8", "forecast.row.flight.company",
                           3_000_000, forecast),
        _paper_observation("FC-9", "forecast.row.flight.employee", 0, forecast),
        _paper_observation("FC-10", "forecast.row.hotel.description",
                           "Khách sạn", forecast),
        _paper_observation("FC-11", "forecast.row.hotel.company", 0, forecast),
        _paper_observation("FC-12", "forecast.row.hotel.employee",
                           3_000_000, forecast),
        _paper_observation("FC-13", "forecast.row.ground.description",
                           "Di chuyển tại Hà Nội", forecast),
        _paper_observation("FC-13b", "forecast.row.ground.company",
                           0, forecast),
        _paper_observation("FC-14", "forecast.row.ground.employee",
                           1_000_000, forecast),
        _paper_observation("FC-15", "forecast.row.meal.description",
                           "Bữa ăn phục vụ công việc", forecast),
        _paper_observation("FC-15b", "forecast.row.meal.company",
                           0, forecast),
        _paper_observation("FC-16", "forecast.row.meal.employee",
                           1_000_000, forecast),
        _paper_observation("FC-17", "forecast.company", 3_000_000, forecast),
        _paper_observation("FC-18", "forecast.employee", 5_000_000, forecast),
        _paper_observation("FC-19", "forecast.total", 8_000_000, forecast),
    ]


def b3_source_record(source_id: str) -> SourceRecord:
    return SourceRecord(
        id=source_id, case_id="C-B3-TEST",
        filename=f"{source_id}.pdf", media_type="application/pdf",
        sha256=f"hash-{source_id}", size_bytes=128, status="ACCEPTED",
        uploader_actor_id="NV-DEMO-01", received_at=DEMO_CLOCK,
        provenance={}, original_path=f"sources/{source_id}.pdf",
    )
