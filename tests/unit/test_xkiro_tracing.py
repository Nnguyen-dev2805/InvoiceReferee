from __future__ import annotations

import json

import httpx
import pytest

from invoice_referee.evidence.extraction import _call_with_one_repair
from invoice_referee.evidence.telemetry import TraceRecorder
from invoice_referee.evidence.trace import LangSmithTrace, RunBudget
from invoice_referee.evidence.xkiro import XkiroClient


class FakeLangSmithClient:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []

    def create_run(self, **kwargs: object) -> None:
        self.runs.append(kwargs)


class RepairTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls == 1:
            content = "invalid JSON PRIVATE_PERSON"
        else:
            content = json.dumps(
                {
                    "fields": [
                        {"field": "employee_name", "value": "Alice Example"},
                        {"field": "total_amount", "value": "100"},
                    ],
                    "line_items": [],
                }
            )
        return httpx.Response(
            200,
            json={
                "model": "returned-model-v1",
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                "choices": [{"message": {"content": content}}],
            },
            request=request,
        )


@pytest.mark.asyncio
async def test_actual_xkiro_repair_calls_emit_llm_spans_without_prompt_or_private_values() -> None:
    langsmith = FakeLangSmithClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="test-key", client=langsmith))
    transport = RepairTransport()
    llm = XkiroClient(
        api_key="provider-test-key",
        model="requested-model-v1",
        base_url="https://provider.invalid/v1",
        transport=transport,
    )
    budget = RunBudget()
    system = "system prompt containing PRIVATE_PERSON"
    user = "source text containing PRIVATE_PERSON"

    with recorder.operation("evidence-job"):
        result = await _call_with_one_repair(
            llm, system=system, user=user, budget=budget
        )

    runs = [run for run in langsmith.runs if run["run_type"] == "llm"]
    assert len(runs) == 2
    assert transport.calls == budget.llm_attempts == 2
    assert [run["inputs"]["attempt_index"] for run in runs] == [1, 2]
    assert [run["inputs"]["attempt_kind"] for run in runs] == ["primary", "repair"]
    assert all(run["inputs"]["prompt_version"] == "document-extraction-v3" for run in runs)
    assert all(run["inputs"]["schema_version"] == "document-fields-and-line-items-json-v1" for run in runs)
    assert all(run["inputs"]["system_sha256"] and run["inputs"]["user_sha256"] for run in runs)
    assert all("PRIVATE_PERSON" not in str(run["inputs"]) for run in runs)
    assert all("PRIVATE_PERSON" not in str(run["outputs"]) for run in runs)
    assert runs[0]["outputs"]["status"] == "FAILED"
    assert runs[1]["outputs"]["parsed_json_summary"]["top_level_keys"] == [
        "fields", "line_items"
    ]
    assert runs[1]["outputs"]["parsed_json_summary"]["list_counts"]["fields"] == 2
    assert len(runs[1]["outputs"]["parsed_json_sha256"]) == 64
    assert runs[1]["extra"]["metadata"]["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert all(run["parent_run_id"] == langsmith.runs[0]["id"] for run in runs)


@pytest.mark.asyncio
async def test_primary_attempt_index_restarts_for_each_document_stage() -> None:
    class ValidTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "returned-model-v1",
                    "choices": [{"message": {"content": '{"fields": []}'}}],
                },
                request=request,
            )

    langsmith = FakeLangSmithClient()
    recorder = TraceRecorder(LangSmithTrace(api_key="test-key", client=langsmith))
    llm = XkiroClient(
        api_key="provider-test-key",
        model="requested-model-v1",
        base_url="https://provider.invalid/v1",
        transport=ValidTransport(),
    )
    with recorder.operation("evidence-job") as operation:
        for document_type in ("E_INVOICE", "SETTLEMENT_FORM"):
            with recorder.step(f"extract:{document_type}", operation=operation):
                from invoice_referee.evidence.telemetry import llm_trace_context

                with llm_trace_context(
                    stage="extract",
                    prompt_version="document-extraction-v1",
                    schema_version="document-fields-and-line-items-json-v1",
                    attempt_kind="primary",
                ):
                    await llm.complete_json(
                        system="system", user=document_type, budget=RunBudget()
                    )

    runs = [run for run in langsmith.runs if run["run_type"] == "llm"]
    assert [run["inputs"]["attempt_index"] for run in runs] == [1, 1]
    assert [run["extra"]["metadata"]["stage_instance"] for run in runs] == [
        "extract:E_INVOICE",
        "extract:SETTLEMENT_FORM",
    ]
