"""Trace adapter: opt-in telemetry, sensitive payload filtered (contracts §9).

Local audit must work with telemetry off or failing; sensitive keys are removed
before anything is sent.
"""

from __future__ import annotations

from invoice_referee.evidence.trace import (
    LangSmithTrace,
    LocalTrace,
    TraceSpan,
    filter_payload,
)


def _span() -> TraceSpan:
    return TraceSpan(name="read", run_id="run:1", model="m", basis="basis:1")


def test_filter_payload_drops_sensitive_keys() -> None:
    filtered = filter_payload(
        {"run_id": "run:1", "raw": "bank pdf text", "api_key": "sk-x", "model": "m"}
    )
    assert filtered == {"run_id": "run:1", "model": "m"}


def test_local_trace_records_without_telemetry() -> None:
    local = LocalTrace()
    local.record(_span())
    assert len(local.spans) == 1


def test_langsmith_disabled_still_keeps_local_span() -> None:
    trace = LangSmithTrace(api_key=None)
    assert trace.enabled is False
    trace.record(_span(), payload={"raw": "secret"})
    assert len(trace.local.spans) == 1


def test_langsmith_send_failure_does_not_raise() -> None:
    trace = LangSmithTrace(api_key="k")
    trace._send = lambda span, payload: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
    trace.record(_span(), payload={"raw": "x"})  # must not raise
    assert len(trace.local.spans) == 1
