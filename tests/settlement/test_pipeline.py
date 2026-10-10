"""W03 pipeline: per-source technical failures keep partial output, run-level
budget exhaustion stops the run, checkpoint stages are recorded, and the
service persists stage + call trace on the run.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from invoice_referee.domain.models import DomainError
from invoice_referee.settlement.models import (
    CallTrace, Command, RunBudget, SourceRecord, Submission, Upload,
)
from invoice_referee.settlement.pipeline import process
from invoice_referee.settlement.reader import StructuredLedgerReader
from invoice_referee.settlement.service import Service, ServiceConfig
from invoice_referee.settlement.store import Store
from tests.settlement import builders as b

FIXTURES = Path(__file__).with_name("fixtures")

LEDGER = (
    "fact F1 expense.EXP-1.amount 5000000\n"
    "fact F2 expense.EXP-1.purpose BUSINESS\n"
    "fact F3 payment.PAY-1.amount 5000000\n"
    "fact F4 payment.PAY-1.payer EMPLOYEE\n"
    "fact F5 payment.PAY-1.status RECEIVED\n"
    "rel R1 EXPENSE_PAYMENT EXP-1 PAY-1\n"
)


def write_source(root: Path, source_id: str, name: str, content: bytes,
                 media_type: str) -> SourceRecord:
    (root / source_id).write_bytes(content)
    return SourceRecord(
        id=source_id, case_id="C-TEST", filename=name, media_type=media_type,
        sha256="h-" + source_id, size_bytes=len(content), status="ACCEPTED",
        uploader_actor_id="NV-01", received_at=datetime.now(timezone.utc),
        provenance={}, original_path=Path(source_id),
    )


def run_input_with(sources, job="B7"):
    run_input, facts, relations = b.run_input(job=job)
    return run_input.model_copy(update={"sources": list(sources)})


def checkpoint_spy():
    stages: list[str] = []

    def checkpoint(stage: str) -> None:
        stages.append(stage)

    return checkpoint, stages


def test_per_source_provider_failure_keeps_partial_and_incomplete(tmp_path):
    good = write_source(tmp_path, "S1", "hoa-don.txt", LEDGER.encode(), "text/plain")
    bad = write_source(tmp_path, "S2", "loi.png", (FIXTURES / "tiny.png").read_bytes(),
                       "image/png")
    run_input = run_input_with([good, bad])

    class ExplodingOnImageReader(StructuredLedgerReader):
        def read(self, source, keys, budget):
            if source.media_type == "image/png":
                raise DomainError("PROVIDER_FAILED", "OCR timeout (giả lập)")
            return super().read(source, keys, budget)

    reader = ExplodingOnImageReader(tmp_path)
    checkpoint, _ = checkpoint_spy()
    report = process(run_input, reader,
                     RunBudget(deadline=time.monotonic() + 30, max_calls=32),
                     checkpoint)
    assert report.completion == "INCOMPLETE"
    technical = [i for i in report.issues if i.type == "TECHNICAL"]
    assert technical and technical[0].refs == ["S2"]
    # nguồn lành mạnh vẫn được tính
    assert report.components.e.value == 5_000_000


def test_budget_exhaustion_stops_whole_run(tmp_path):
    sources = [write_source(tmp_path, f"S{i}", f"f{i}.txt",
                            (LEDGER + f"fact F9{i} budget.approved 8000000\n").encode(),
                            "text/plain") for i in range(1, 4)]
    run_input = run_input_with(sources)
    reader = StructuredLedgerReader(tmp_path)
    checkpoint, stages = checkpoint_spy()
    with pytest.raises(DomainError) as error:
        process(run_input, reader,
                RunBudget(deadline=time.monotonic() + 30, max_calls=2),
                checkpoint)
    assert error.value.code == "BUDGET_EXHAUSTED"
    assert stages == ["reading"]  # không giả tiếp stage sau khi hết budget


def test_process_records_all_stages(tmp_path):
    source = write_source(tmp_path, "S1", "hoa-don.txt", LEDGER.encode(),
                          "text/plain")
    run_input = run_input_with([source])
    reader = StructuredLedgerReader(tmp_path)
    checkpoint, stages = checkpoint_spy()
    process(run_input, reader,
            RunBudget(deadline=time.monotonic() + 30, max_calls=32),
            checkpoint)
    assert stages == ["reading", "matching", "evaluating", "publishing"]


def test_service_persists_stage_and_trace(tmp_path):
    from invoice_referee.settlement.models import Observation

    store = Store(tmp_path / "cases.sqlite", tmp_path / "artifacts")

    class TracingStubReader(StructuredLedgerReader):
        """Ledger reader + per-source trace để kiểm service persist trace."""

        def __init__(self, root):
            super().__init__(root)
            self._calls: list[CallTrace] = []

        def reset_trace(self):
            self._calls = []

        def trace_entries(self):
            return list(self._calls)

        def read(self, source, keys, budget):
            observations = super().read(source, keys, budget)
            self._calls.append(CallTrace(
                call_id=f"c{len(self._calls) + 1}", stage="read",
                source_id=source.id, requested_model=None,
                response_model=None, usage=None, ok=True, duration_ms=1))
            return observations

    reader = TracingStubReader(store.artifact_root)
    service = Service(store, reader, config=ServiceConfig())
    cutoff = datetime(2026, 10, 8, 11, tzinfo=timezone.utc)
    submission = Submission(employee_ref="NV-01", work_ref="CT-01", job="B7",
                            money_as_of=cutoff, knowledge_cutoff=cutoff,
                            form={"purpose": "Công tác A"})
    command = Command(key="c1", actor_id="NV-01", demo_role="EMPLOYEE",
                      expected_case_version=None, body={})
    case = service.submit(submission, command)
    service.add_source(case.id, Upload(filename="hoa-don.txt",
                                       content=LEDGER.encode()), Command(
        key="s1", actor_id="NV-01", demo_role="EMPLOYEE",
        expected_case_version=case.case_version, body={}))
    view = service.get_case(case.id)
    run = service.start(case.id, Command(key="r1", actor_id="NV-01",
                                         demo_role="EMPLOYEE",
                                         expected_case_version=view.case_version,
                                         body={}))
    ended = service.wait(run.id, timeout=10)
    assert ended.status == "SUCCEEDED"
    assert ended.stage in {"reading", "matching", "evaluating", "publishing"}
    assert ended.trace and ended.trace[0].source_id
    report = service.report(run.id)
    assert report.components.e.value == 5_000_000


def test_fake_reader_mode_is_explicit_not_live(tmp_path):
    reader = StructuredLedgerReader(tmp_path)
    assert reader.mode == "FAKE_OR_REPLAY"


# --- B3 v1 (b3-intake-v1): pipeline branch -------------------------------------

from tests.settlement import b3_builders as b3b  # noqa: E402

B3_REQUEST_LEDGER = (
    "fact B1 document.role ADVANCE_REQUEST\n"
    "fact B2 person.name Nguyễn_An\n"
    "fact B3 trip.destination Hà_Nội\n"
    "fact B4 trip.start 2026-10-12\n"
    "fact B5 trip.end 2026-10-13\n"
    "fact B6 trip.purpose Khảo_sát_yêu_cầu_và_thống_nhất_phạm_vi_triển_khai_dự_án_tại_Hà_Nội.\n"
    "fact B7 advance.request.amount 2000000\n"
    "fact B8 advance.request.amount_words Hai_triệu_đồng\n"
    "fact B9 advance.request.amount_words_value 2000000\n"
    "fact B10 advance.settlement_due 2026-10-16\n"
)
B3_FORECAST_LEDGER = (
    "fact C1 document.role FORECAST\n"
    "fact C2 person.name Nguyễn_An\n"
    "fact C3 trip.destination Hà_Nội\n"
    "fact C4 trip.start 2026-10-12\n"
    "fact C5 trip.end 2026-10-13\n"
    "fact C6 forecast.row.flight.description Vé_máy_bay\n"
    "fact C7 forecast.row.flight.company 3000000\n"
    "fact C8 forecast.row.flight.employee 0\n"
    "fact C9 forecast.row.hotel.description Khách_sạn\n"
    "fact C10 forecast.row.hotel.company 0\n"
    "fact C11 forecast.row.hotel.employee 3000000\n"
    "fact C12 forecast.row.ground.description Di_chuyển\n"
    "fact C13 forecast.row.ground.company 0\n"
    "fact C14 forecast.row.ground.employee 1000000\n"
    "fact C15 forecast.row.meal.description Bữa_ăn\n"
    "fact C16 forecast.row.meal.company 0\n"
    "fact C17 forecast.row.meal.employee 1000000\n"
    "fact C18 forecast.company 3000000\n"
    "fact C19 forecast.employee 5000000\n"
    "fact C20 forecast.total 8000000\n"
)


class SpyReader(StructuredLedgerReader):
    """Ghi lại keys nhận được và số lần match được gọi.

    Ledger giả lập không chứa dấu cách trong value; dấu gạch dưới được
    chuẩn hóa lại thành dấu cách để text khớp form như một reader thật.
    """

    def __init__(self, root):
        super().__init__(root)
        self.read_keys: list[list[str]] = []
        self.match_calls = 0

    def read(self, source, keys, budget):
        self.read_keys.append(list(keys))
        observations = super().read(source, keys, budget)
        return [o.model_copy(update={"value": o.value.replace("_", " ")})
                if isinstance(o.value, str) and o.key != "document.role"
                else o
                for o in observations]

    def match(self, run_input, candidates, budget):
        self.match_calls += 1
        return super().match(run_input, candidates, budget)


def _b3_import_run(sources):
    import json

    form = json.loads(json.dumps(b3b.NATIVE_FORM))
    form["intake_method"] = "IMPORT"
    return b3b.make_b3_run(form=form).model_copy(
        update={"sources": list(sources)})


def test_b3_v1_pipeline_skips_generic_matcher(tmp_path):
    sources = [
        write_source(tmp_path, "S-REQ", "de-nghi.txt",
                     B3_REQUEST_LEDGER.encode(), "text/plain"),
        write_source(tmp_path, "S-FC", "du-toan.txt",
                     B3_FORECAST_LEDGER.encode(), "text/plain"),
    ]
    run_input = _b3_import_run(sources)
    reader = SpyReader(tmp_path)
    checkpoint, stages = checkpoint_spy()
    report = process(run_input, reader,
                     RunBudget(deadline=time.monotonic() + 30, max_calls=32),
                     checkpoint)
    assert reader.match_calls == 0  # B3 v1 không gọi matcher B7
    assert stages == ["reading", "matching", "evaluating", "publishing"]
    assert report.b3 is not None
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"
    assert report.b3.forecast_total_vnd == 8_000_000


def test_b3_v1_reader_receives_b3_key_grammar(tmp_path):
    sources = [write_source(tmp_path, "S-REQ", "de-nghi.txt",
                            B3_REQUEST_LEDGER.encode(), "text/plain")]
    run_input = _b3_import_run(sources)
    reader = SpyReader(tmp_path)
    checkpoint, _ = checkpoint_spy()
    process(run_input, reader,
            RunBudget(deadline=time.monotonic() + 30, max_calls=32),
            checkpoint)
    assert reader.read_keys, "phải có ít nhất một lần read"
    for keys in reader.read_keys:
        assert "document.role" in keys
        assert any(key.startswith("forecast.") for key in keys)


def test_b3_v1_native_form_runs_without_sources_or_matcher(tmp_path):
    run_input = b3b.make_b3_run()  # WEB confirmed, không nguồn, không OCR
    reader = SpyReader(tmp_path)
    checkpoint, _ = checkpoint_spy()
    report = process(run_input, reader,
                     RunBudget(deadline=time.monotonic() + 30, max_calls=32),
                     checkpoint)
    assert reader.read_keys == []  # không nguồn: không gọi provider
    assert reader.match_calls == 0
    assert report.b3 is not None
    assert report.b3.readiness == "READY_FOR_ACCOUNTANT_REVIEW"


def test_b7_pipeline_still_calls_matcher(tmp_path):
    source = write_source(tmp_path, "S1", "hoa-don.txt", LEDGER.encode(),
                          "text/plain")
    run_input = run_input_with([source])
    reader = SpyReader(tmp_path)
    checkpoint, _ = checkpoint_spy()
    process(run_input, reader,
            RunBudget(deadline=time.monotonic() + 30, max_calls=32),
            checkpoint)
    assert reader.match_calls == 1  # B7 giữ nguyên đường match
