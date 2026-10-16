"""Provider telemetry + Kimi reasoning effort (RED first, 17/10/2026)."""

from __future__ import annotations

import json

import httpx


def _ok_body(*, model="moonshotai/Kimi-K3", with_model=True):
    body = {
        "choices": [{"message": {"content": '{"fields": [], "line_items": []}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    if with_model:
        body["model"] = model
    return body


def _transport(captured: dict, *, body=None, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content.decode())
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(status, json=body if body is not None else _ok_body())

    return httpx.MockTransport(handler)


def _operation():
    from invoice_referee.evidence.telemetry import TraceRecorder
    from invoice_referee.evidence.trace import LangSmithTrace

    recorder = TraceRecorder(LangSmithTrace(api_key=None))
    return recorder.operation("probe")


async def test_kimi_sends_reasoning_effort_and_labels_provider():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.trace import RunBudget

    captured: dict = {}
    client = KimiClient(
        token="t", secret="s", base_url="https://k/v1", transport=_transport(captured)
    )
    assert client.reasoning_effort == "low"
    with _operation() as op:
        from invoice_referee.evidence.telemetry import llm_trace_context

        with llm_trace_context(
            stage="extract",
            prompt_version="v",
            schema_version="s",
            attempt_kind="provider_call",
        ):
            await client.complete_json(system="sys", user="usr", budget=RunBudget())
    assert captured["json"]["reasoning_effort"] == "low"
    assert captured["json"]["temperature"] == 0.1
    assert captured["auth"].startswith("Bearer ") and ". " not in captured["auth"]
    span = next(s for s in op.spans if s.run_type == "llm")
    assert span.metadata["provider"] == "kimi"
    assert span.metadata["requested_model"] == "moonshotai/Kimi-K3"
    assert span.metadata["returned_model"] == "moonshotai/Kimi-K3"
    assert span.inputs["requested_effort"] == "low"
    assert span.outputs["observed_effort"] == "UNKNOWN"


async def test_xkiro_sends_no_effort_and_labels_provider():
    from invoice_referee.evidence.trace import RunBudget
    from invoice_referee.evidence.xkiro import XkiroClient

    captured: dict = {}
    client = XkiroClient(
        api_key="k",
        model="llm-1",
        base_url="https://x/v1",
        transport=_transport(captured),
    )
    with _operation():
        await client.complete_json(system="sys", user="usr", budget=RunBudget())
    assert "reasoning_effort" not in captured["json"]


async def test_kimi_rejection_surfaces_without_fallback():
    from invoice_referee.evidence.kimi import KimiClient, KimiTransportError
    from invoice_referee.evidence.trace import RunBudget

    captured: dict = {}
    client = KimiClient(
        token="t",
        secret="s",
        base_url="https://k/v1",
        transport=_transport(captured, status=400, body={}),
    )
    import pytest

    with pytest.raises(KimiTransportError):
        with _operation():
            await client.complete_json(system="s", user="u", budget=RunBudget())


async def test_missing_returned_model_stays_unknown():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.trace import RunBudget

    captured: dict = {}
    client = KimiClient(
        token="t",
        secret="s",
        base_url="https://k/v1",
        transport=_transport(captured, body=_ok_body(with_model=False)),
    )
    with _operation() as op:
        await client.complete_json(system="s", user="u", budget=RunBudget())
    span = next(s for s in op.spans if s.run_type == "llm")
    assert span.metadata["returned_model"] is None
    assert span.outputs["returned_model"] is None


def test_reader_identity_distinguishes_effort():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.prompts import role_aware_reader_identity

    class _Reader:
        provider_name = "mistral"
        model = "mistral-ocr-latest"

    class _OcrReader:
        provider = _Reader()

    low = KimiClient(
        token="t", secret="s", base_url="https://k/v1", reasoning_effort="low"
    )
    other = KimiClient(
        token="t", secret="s", base_url="https://k/v1", reasoning_effort="medium"
    )
    assert role_aware_reader_identity(
        reader=_OcrReader(), classifier=low, activity_profile=None
    ) != role_aware_reader_identity(
        reader=_OcrReader(), classifier=other, activity_profile=None
    )


async def test_repair_records_bounded_diagnostic_and_stays_finite():
    from invoice_referee.evidence.structured_output import complete_structured
    from invoice_referee.evidence.trace import RunBudget
    from invoice_referee.evidence.xkiro import XkiroSchemaError

    calls = {"n": 0}

    class FlakyLlm:
        max_input_chars = 120_000

        async def complete_json(self, *, system, user, budget):
            from invoice_referee.evidence.telemetry import llm_trace_context

            calls["n"] += 1
            budget.charge_llm()
            if "REPAIR" not in user:
                return {"fields": "not-an-array"}
            return {"fields": [], "lines": []}

    def validate(payload: dict) -> dict:
        if not isinstance(payload.get("fields"), list):
            raise XkiroSchemaError("fields must be an array")
        return payload

    budget = RunBudget()
    with _operation() as op:
        result = await complete_structured(
            FlakyLlm(),
            system="s",
            user="u",
            budget=budget,
            validate=validate,
            stage="extract",
            prompt_version="v",
            schema_version="s",
        )
    assert result == {"fields": [], "lines": []}
    assert calls["n"] == 2
    diagnostics = op.outputs.get("repair_diagnostics")
    assert isinstance(diagnostics, list) and len(diagnostics) == 1
    (entry,) = diagnostics
    assert entry["stage"] == "extract"
    assert entry["attempt"] == "primary"
    assert entry["error_code"] == "XkiroSchemaError"
    assert entry["field_path"] == ""
    assert entry["validation_category"] == "shape"
    assert "fields must be an array" in entry["summary"]


def test_repair_diagnostic_redacts_quoted_spans():
    from invoice_referee.evidence.telemetry import (
        TraceRecorder,
        record_repair_diagnostic,
    )
    from invoice_referee.evidence.trace import LangSmithTrace

    recorder = TraceRecorder(LangSmithTrace(api_key=None))
    with recorder.operation("probe") as op:
        record_repair_diagnostic(
            stage="extract",
            attempt="primary",
            error_code="XkiroSchemaError",
            field_path="field[3]",
            validation_category="value",
            summary='bad value "NGUYEN VAN A" at field[3]',
        )
    (entry,) = op.outputs["repair_diagnostics"]
    assert "NGUYEN VAN A" not in entry["summary"]
    assert entry["field_path"] == "field[3]"
    assert entry["validation_category"] == "value"


def test_classifier_maps_validator_messages_without_values():
    from invoice_referee.evidence.telemetry import classify_schema_error
    from invoice_referee.evidence.xkiro import XkiroSchemaError

    cases = [
        ("fields must be an array", ("XkiroSchemaError", "", "shape")),
        (
            "field[3].state is not a FieldState",
            ("XkiroSchemaError", "field[3]", "state"),
        ),
        (
            "field[1].page must be a positive integer",
            ("XkiroSchemaError", "field[1]", "page"),
        ),
        (
            "field[0] needs at least two well-formed alternatives",
            ("XkiroSchemaError", "field[0]", "alternatives"),
        ),
        (
            "assessments must cover all candidates exactly once",
            ("XkiroSchemaError", "", "coverage"),
        ),
        ("something entirely new", ("XkiroSchemaError", "", "other")),
    ]
    for message, expected in cases:
        assert classify_schema_error(XkiroSchemaError(message)) == expected


async def test_persistent_malformed_output_never_succeeds_and_respects_quota():
    from invoice_referee.evidence.structured_output import complete_structured
    from invoice_referee.evidence.trace import RunBudget
    from invoice_referee.evidence.xkiro import XkiroSchemaError

    import pytest

    class BadLlm:
        max_input_chars = 120_000

        async def complete_json(self, *, system, user, budget):
            budget.charge_llm()
            return {"fields": "not-an-array"}

    def validate(payload: dict) -> dict:
        if not isinstance(payload.get("fields"), list):
            raise XkiroSchemaError("fields must be an array")
        return payload

    budget = RunBudget()
    with _operation():
        with pytest.raises(XkiroSchemaError):
            await complete_structured(
                BadLlm(),
                system="s",
                user="u",
                budget=budget,
                validate=validate,
                stage="extract",
                prompt_version="v",
                schema_version="s",
            )
    # Primary + exactly one repair: the shared quota is finite.
    assert budget.llm_attempts == 2
    assert budget.schema_repairs == 1


def test_trace_usage_keeps_reasoning_and_cached_without_summing():
    from invoice_referee.evidence.kimi import _trace_usage

    usage = _trace_usage({
        "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
        "completion_tokens_details": {"reasoning_tokens": 30, "other": 1},
        "prompt_tokens_details": {"cached_tokens": 20},
    })
    assert usage["reasoning_tokens"] == 30
    assert usage["cached_tokens"] == 20
    assert usage["completion_tokens"] == 50, "never inflated with reasoning"
    assert usage["prompt_tokens"] == 100


def test_trace_usage_absent_means_missing_not_zero():
    from invoice_referee.evidence.xkiro import _trace_usage

    usage = _trace_usage({"prompt_tokens": 10, "completion_tokens": 5})
    assert "reasoning_tokens" not in usage
    assert "cached_tokens" not in usage


async def test_kimi_wire_has_no_extra_body_or_max_tokens():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.trace import RunBudget

    captured: dict = {}
    client = KimiClient(token="t", secret="s", base_url="https://k/v1",
                        transport=_transport(captured))
    with _operation():
        await client.complete_json(system="s", user="u", budget=RunBudget())
    assert "extra_body" not in captured["json"], "SDK syntax must not leak into raw HTTP"
    assert "max_tokens" not in captured["json"], "no copied cap without semantics"
