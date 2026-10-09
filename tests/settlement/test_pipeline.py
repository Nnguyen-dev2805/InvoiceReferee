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
