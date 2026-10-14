"""LangSmith integration: opt-in, filtered, never blocking (contracts §9).

Tracing is off unless explicitly enabled and keyed. The SDK client is injected
so no network is touched; a send carries the filtered payload and the local
span always survives.
"""

from __future__ import annotations

from invoice_referee.config import Settings
from invoice_referee.evidence.trace import LangSmithTrace, TraceSpan, build_trace


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


def _span() -> TraceSpan:
    return TraceSpan(
        name="read", run_id="run:1", model="m", basis="basis:1", prompt_version="p1"
    )


# -- Settings opt-in ----------------------------------------------------------


def test_langsmith_not_ready_without_tracing_flag(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "k")
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    settings = Settings(_env_file=None)
    assert settings.langsmith_ready is False


def test_langsmith_ready_when_enabled_and_keyed(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "k")
    settings = Settings(_env_file=None)
    assert settings.langsmith_ready is True


def test_langsmith_is_not_a_live_requirement(monkeypatch) -> None:
    from invoice_referee.config import LIVE_REQUIRED_SETTINGS

    assert not any("LANGSMITH" in name for name in LIVE_REQUIRED_SETTINGS)


# -- Adapter behavior ---------------------------------------------------------


def test_build_trace_off_when_not_ready() -> None:
    class S:
        langsmith_ready = False
        langsmith_api_key = "k"
        langsmith_project = "p"
        langsmith_endpoint = "e"
        langsmith_agent_id = None
        langsmith_agent_environment = None

    trace = build_trace(S())
    assert trace.enabled is False


def test_record_sends_filtered_payload_via_client() -> None:
    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    trace.record(
        _span(), payload={"run_id": "run:1", "raw": "bank pdf text", "model": "m"}
    )
    assert len(client.runs) == 1
    sent = client.runs[0]
    assert sent["inputs"] == {"run_id": "run:1", "model": "m"}  # "raw" filtered out
    assert sent["extra"]["basis"] == "basis:1"
    assert sent["extra"]["prompt_version"] == "p1"
    assert sent["extra"]["logical_run_id"] == "run:1"
    assert len(trace.local.spans) == 1


def test_completed_span_is_closed_with_its_own_end_time() -> None:
    # A span carrying real start/end is closed with those times; the adapter does
    # not fabricate start==end==now (which would report a fake latency 0).
    from datetime import UTC, datetime, timedelta

    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    start = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    end = start + timedelta(seconds=3)
    trace.record(TraceSpan(name="read", run_id="run:1", started_at=start, ended_at=end))
    assert client.runs[0]["start_time"] == start
    assert client.runs[0]["end_time"] == end
    assert client.runs[0]["start_time"] != client.runs[0]["end_time"]
    assert client.updates == []
    assert client.runs[0]["extra"]["metadata"]["trace_output_state"] == "NOT_COLLECTED"


def test_open_span_is_not_faked_closed() -> None:
    # With no end time the run stays open rather than being closed at `now`.
    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    trace.record(TraceSpan(name="read", run_id="run:1"))
    assert "end_time" not in client.runs[0]
    assert not [u for u in client.updates if "end_time" in u]


def test_sent_run_id_is_a_uuid() -> None:
    # LangSmith rejects a non-UUID run id; the logical id is kept as metadata.
    import uuid

    client = FakeClient()
    trace = LangSmithTrace(api_key="k", client=client)
    trace.record(_span())
    uuid.UUID(client.runs[0]["id"])  # raises if not a valid UUID
    assert client.runs[0]["extra"]["logical_run_id"] == "run:1"


def test_record_keeps_local_span_when_client_raises() -> None:
    class Boom:
        def create_run(self, **kwargs: object) -> None:
            raise RuntimeError("network down")

    trace = LangSmithTrace(api_key="k", client=Boom())
    trace.record(_span(), payload={"x": 1})  # must not raise
    assert len(trace.local.spans) == 1


def test_completed_run_sends_inputs_outputs_error_and_real_times_at_create() -> None:
    from datetime import UTC, datetime, timedelta

    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    start = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    end = start + timedelta(seconds=3)
    trace.record(
        TraceSpan(
            name="extract:E_INVOICE",
            run_id="run:extract",
            started_at=start,
            ended_at=end,
            inputs={"document_type": "E_INVOICE"},
            outputs={"field_count": 2},
            error="ValueError: provider response invalid",
            metadata={"safe": "ok", "nested": {"authorization": "Bearer private"}},
        )
    )

    run = client.runs[0]
    assert run["inputs"] == {"document_type": "E_INVOICE"}
    assert run["outputs"] == {"field_count": 2}
    assert run["error"] == "ValueError: provider response invalid"
    assert run["start_time"] == start and run["end_time"] == end
    assert run["extra"]["metadata"] == {
        "safe": "ok",
        "nested": {},
        "trace_output_state": "COLLECTED",
    }
    assert client.updates == []


def test_empty_outputs_are_distinct_from_not_collected_outputs() -> None:
    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    trace.record(
        TraceSpan(
            name="empty-result",
            run_id="run:empty",
            outputs={},
            output_state="EMPTY",
        )
    )
    trace.record(
        TraceSpan(
            name="missing-result",
            run_id="run:missing",
            outputs={},
            output_state="NOT_COLLECTED",
        )
    )

    empty, missing = client.runs
    assert empty["outputs"] == {}
    assert empty["extra"]["metadata"]["trace_output_state"] == "EMPTY"
    assert "outputs" not in missing
    assert missing["extra"]["metadata"]["trace_output_state"] == "NOT_COLLECTED"


def test_filter_payload_recursively_removes_secrets_and_keeps_metrics() -> None:
    from invoice_referee.evidence.trace import filter_payload

    filtered = filter_payload(
        {
            "stage": {
                "api_key": "sk-private",
                "token_count": 17,
                "content": "private document text",
                "details": {"authorization": "Bearer private", "status": "ok"},
            },
            "rows": [{"cookie": "session-private", "amount": 2500}],
        }
    )

    assert filtered == {
        "stage": {
            "token_count": 17,
            "details": {"status": "ok"},
        },
        "rows": [{"amount": 2500}],
    }


def test_stage_payload_uses_stage_allowlist_and_reports_truncation() -> None:
    from invoice_referee.evidence.trace import filter_payload, stage_payload

    stage = stage_payload(
        "extraction",
        {
            "document_id": "doc:1",
            "fields": [{"field": "employee_name", "state": "FOUND", "value": "PRIVATE_PERSON"}],
            "raw_prompt": "PRIVATE_PROMPT",
            "unknown_field": "must be dropped",
        },
    )
    assert "raw_prompt" not in stage and "unknown_field" not in stage
    assert stage["fields"][0]["value"] == "[REDACTED]"

    bounded = filter_payload({"rows": [{"item_id": f"row:{i}"} for i in range(45)]})
    assert len(bounded["rows"]) == 40
    assert bounded["truncated"] is True
    assert bounded["truncated_counts"]["items"] == 5


def test_record_flushes_buffered_client_once_after_create() -> None:
    client = FakeClient()
    trace = LangSmithTrace(api_key="k", project="p", client=client)
    trace.record(_span())
    trace.flush()
    assert client.flush_calls == 1


def test_disabled_trace_never_calls_client() -> None:
    client = FakeClient()
    trace = LangSmithTrace(api_key=None, client=client)
    trace.record(_span())
    assert client.runs == []
    assert len(trace.local.spans) == 1
