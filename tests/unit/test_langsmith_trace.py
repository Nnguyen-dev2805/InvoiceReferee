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

    def create_run(self, **kwargs: object) -> None:
        self.runs.append(kwargs)

    def update_run(self, run_id: str, **kwargs: object) -> None:
        self.updates.append({"run_id": run_id, **kwargs})


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
    update = next(u for u in client.updates if "end_time" in u)
    assert update["end_time"] == end
    assert update["run_id"] == client.runs[0]["id"]


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


def test_disabled_trace_never_calls_client() -> None:
    client = FakeClient()
    trace = LangSmithTrace(api_key=None, client=client)
    trace.record(_span())
    assert client.runs == []
    assert len(trace.local.spans) == 1
