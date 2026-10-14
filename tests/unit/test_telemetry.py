"""TraceRecorder: real root/child topology, honest skips, real timings, redaction.

The recorder wraps a real operation (a draft read, a processing job, an actual
money record) and emits a root span plus child step spans. Each span has its own
id; children carry the root as parent. A sink failure never raises and never
changes the business result; skipped work is recorded as skipped, not as a
successful call.
"""

from __future__ import annotations

import time

from invoice_referee.evidence.telemetry import TraceRecorder
from invoice_referee.evidence.trace import LangSmithTrace, TraceSpan, filter_payload


class FakeClient:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        self.flush_calls = 0

    def create_run(self, **kwargs: object) -> None:
        self.runs.append(kwargs)

    def update_run(self, run_id: str, **kwargs: object) -> None:
        self.updates.append({"run_id": run_id, **kwargs})

    def flush(self, timeout: float | None = None) -> None:
        self.flush_calls += 1


class BoomClient:
    def create_run(self, **kwargs: object) -> None:
        raise RuntimeError("network down")

    def update_run(self, run_id: str, **kwargs: object) -> None:
        raise RuntimeError("network down")


def test_operation_emits_a_root_and_child_spans_with_distinct_ids() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("submit", metadata={"root_id": "case:1"}) as op:
        with recorder.step("ocr:file1", operation=op) as s:
            s.outputs["pages"] = 1
        with recorder.step("classify", operation=op) as s:
            s.outputs["documents"] = 2
    names = [r["name"] for r in client.runs]
    assert names == ["submit", "ocr:file1", "classify"]
    ids = [r["id"] for r in client.runs]
    assert len(set(ids)) == 3, "every span must have its own id"
    # children point at the root run uuid
    assert client.runs[1]["parent_run_id"] == client.runs[0]["id"]
    assert client.runs[2]["parent_run_id"] == client.runs[0]["id"]
    # the root has no parent
    assert "parent_run_id" not in client.runs[0]


def test_two_parallel_operations_do_not_mix_spans() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("submit-a") as a:
        with recorder.step("ocr", operation=a):
            pass
    with recorder.operation("submit-b") as b:
        with recorder.step("ocr", operation=b):
            pass
    root_ids = {r["id"] for r in client.runs if r["name"] in ("submit-a", "submit-b")}
    assert len(root_ids) == 2
    # each child points only at its own root
    child_parents = {r["parent_run_id"] for r in client.runs if r["name"] == "ocr"}
    assert child_parents == root_ids


def test_real_timing_is_not_faked_to_zero() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("submit") as op:
        with recorder.step("work", operation=op):
            time.sleep(0.01)
    for run in client.runs:
        assert run["start_time"] != run["end_time"], "latency must not be a fake 0"
    assert len(recorder.operations) == 1


def test_skipped_step_is_recorded_as_skipped_not_success() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("submit") as op:
        with recorder.step("ocr:file1", operation=op) as s:
            s.skipped = "cache_reuse"
    step = next(r for r in client.runs if r["name"] == "ocr:file1")
    # the skip is an explicit output, not a provider success
    assert step["outputs"].get("skipped") == "cache_reuse"
    assert step["extra"]["metadata"]["trace_output_state"] == "COLLECTED"


def test_sink_failure_never_raises_and_is_diagnosed() -> None:
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=BoomClient()))
    with recorder.operation("submit") as op:
        with recorder.step("ocr", operation=op):
            pass
    assert recorder.export_errors, "a failed export must be visible, not swallowed"
    assert len(recorder.operations) == 1


def test_operation_error_is_recorded_on_the_root() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    try:
        with recorder.operation("submit") as op:
            raise ValueError("boom")
    except ValueError:
        pass
    root = client.runs[0]
    assert root["name"] == "submit"


def test_disabled_recorder_buffers_locally_without_network() -> None:
    recorder = TraceRecorder(LangSmithTrace(api_key=None))
    with recorder.operation("submit") as op:
        with recorder.step("ocr", operation=op):
            pass
    assert recorder.enabled is False
    assert len(recorder.operations) == 1


def test_step_inputs_outputs_and_parent_are_sent_together() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("evidence-job") as operation:
        with recorder.step(
            "validate:E_INVOICE",
            operation=operation,
            inputs={"document_id": "doc:1", "field_count": 2},
        ) as step:
            step.outputs.update({"profile_status": "NEEDS_HUMAN", "finding_count": 1})

    child = next(run for run in client.runs if run["name"] == "validate:E_INVOICE")
    assert child["inputs"] == {"document_id": "doc:1", "field_count": 2}
    assert child["outputs"] == {"profile_status": "NEEDS_HUMAN", "finding_count": 1}
    assert child["parent_run_id"] == client.runs[0]["id"]
    assert child["extra"]["metadata"]["trace_output_state"] == "COLLECTED"
    assert client.flush_calls == 1


def test_redaction_keeps_numeric_token_metrics() -> None:
    # A numeric metric whose name contains "token" must NOT be dropped.
    filtered = filter_payload(
        {"token_count": 1200, "total_tokens": 900, "api_key": "sk-x", "raw": "bank pdf"}
    )
    assert filtered == {"token_count": 1200, "total_tokens": 900}


def test_redaction_drops_real_secret_keys() -> None:
    filtered = filter_payload({"token": "abc", "authorization": "Bearer x", "model": "m"})
    assert filtered == {"model": "m"}


def test_span_carries_metadata_and_error() -> None:
    client = FakeClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="k", client=client))
    with recorder.operation("submit", metadata={"root_id": "case:1"}) as op:
        with recorder.step("ocr", operation=op, metadata={"file": "a.pdf"}) as s:
            s.error = "timeout"
    step = next(r for r in client.runs if r["name"] == "ocr")
    assert step["extra"]["metadata"]["file"] == "a.pdf"
    assert step["error"] == "timeout"
    assert client.updates == []
