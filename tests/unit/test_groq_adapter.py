"""Tests for Groq LLM adapter (GroqClient)."""

from __future__ import annotations

import json
import httpx
import pytest

from invoice_referee.evidence.groq import (
    GroqClient,
    GroqError,
    GroqSchemaError,
    GroqTransportError,
    _clean_json_content,
)
from invoice_referee.evidence.trace import RunBudget


def test_clean_json_content_strips_think_tags_and_fences():
    raw_with_think = "<think>Here is some chain of thought</think>{\"key\": \"value\"}"
    assert _clean_json_content(raw_with_think) == '{"key": "value"}'

    raw_unclosed_think = "<think>Cutoff thought... {\"key\": \"value\"}"
    # If the whole string starts with <think> and is unclosed
    assert _clean_json_content(raw_unclosed_think) == ""

    raw_fence = "```json\n{\"foo\": 123}\n```"
    assert _clean_json_content(raw_fence) == '{"foo": 123}'


@pytest.mark.asyncio
async def test_groq_client_successful_complete_json():
    captured_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        req_body = json.loads(request.content)
        assert req_body["model"] == "openai/gpt-oss-20b"
        assert req_body["reasoning_effort"] == "low"
        assert req_body["reasoning_format"] == "parsed"
        assert req_body["response_format"] == {"type": "json_object"}
        assert req_body["messages"][0]["role"] == "system"
        assert req_body["messages"][1]["role"] == "user"

        res_body = {
            "id": "chatcmpl-test",
            "model": "openai/gpt-oss-20b",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"status": "ok", "count": 42}',
                        "reasoning": "Quick reasoning here",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "completion_tokens_details": {
                    "reasoning_tokens": 20
                }
            }
        }
        return httpx.Response(200, json=res_body)

    transport = httpx.MockTransport(mock_handler)
    client = GroqClient(
        api_key="gsk-mock-key",
        transport=transport,
    )
    budget = RunBudget()

    result = await client.complete_json(
        system="You are a classifier.",
        user="Classify document.",
        budget=budget,
    )
    assert result == {"status": "ok", "count": 42}
    assert len(captured_requests) == 1
    assert captured_requests[0].headers["Authorization"] == "Bearer gsk-mock-key"


@pytest.mark.asyncio
async def test_groq_client_http_error_raises_transport_error():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_handler)
    client = GroqClient(
        api_key="gsk-mock-key",
        transport=transport,
        max_rate_limit_retries=0,
    )
    budget = RunBudget()

    with pytest.raises(GroqTransportError, match="LLM HTTP 500"):
        await client.complete_json(system="sys", user="usr", budget=budget)


@pytest.mark.asyncio
async def test_groq_client_retries_on_429_and_succeeds():
    attempts = 0

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0.01"},
                json={"error": {"message": "Rate limit exceeded"}},
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"retry": "success"}'}}],
                "usage": {"total_tokens": 10},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = GroqClient(
        api_key="gsk-mock-key",
        transport=transport,
        max_rate_limit_retries=2,
    )
    budget = RunBudget()
    res = await client.complete_json(system="sys", user="usr", budget=budget)
    assert res == {"retry": "success"}
    assert attempts == 2


@pytest.mark.asyncio
async def test_groq_client_non_json_raises_schema_error():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "This is definitely not JSON"}}]
        })

    transport = httpx.MockTransport(mock_handler)
    client = GroqClient(
        api_key="gsk-mock-key",
        transport=transport,
    )
    budget = RunBudget()

    with pytest.raises(GroqSchemaError, match="LLM returned non-JSON output") as exc_info:
        await client.complete_json(system="sys", user="usr", budget=budget)
    assert exc_info.value.raw == "This is definitely not JSON"


@pytest.mark.asyncio
async def test_groq_client_budget_exhausted():
    client = GroqClient(api_key="gsk-mock-key")
    budget = RunBudget(max_llm_attempts=0)

    with pytest.raises(GroqError, match="LLM budget exhausted"):
        await client.complete_json(system="sys", user="usr", budget=budget)


async def test_retry_does_not_send_after_attempt_budget(monkeypatch):
    import invoice_referee.evidence.groq as module
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(429, headers={"retry-after":"1"})
    async def no_wait(_): pass
    monkeypatch.setattr(module.asyncio, "sleep", no_wait)
    budget = RunBudget(max_llm_attempts=1)
    with pytest.raises(GroqError):
        await GroqClient(api_key="fake", transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=budget)
    assert len(requests) == budget.llm_attempts == 1


async def test_retry_does_not_send_after_sleep_expires_deadline(monkeypatch):
    import time
    import invoice_referee.evidence.groq as module
    budget = RunBudget(processing_deadline_s=3)
    requests = []
    def handler(req):
        requests.append(req)
        if len(requests)==1: return httpx.Response(429,headers={"retry-after":"1"})
        return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
    async def expire(_): budget.started_at=time.monotonic()-5
    monkeypatch.setattr(module.asyncio,"sleep",expire)
    with pytest.raises(GroqError):
        await GroqClient(api_key="fake",transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=budget)
    assert len(requests)==budget.llm_attempts==1


@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls"])
async def test_provider_incomplete_finish_is_not_json_success(reason):
    def handler(req):return httpx.Response(200,json={"choices":[{"finish_reason":reason,"message":{"content":"{\"fields\":[],\"line_items\":[]}"}}]})
    with pytest.raises(GroqTransportError):
        await GroqClient(api_key="fake",transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=RunBudget())


async def test_refusal_is_not_json_success():
    def handler(req):return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":"{}","refusal":"Not supported"}}]})
    with pytest.raises(GroqTransportError):
        await GroqClient(api_key="fake",transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=RunBudget())


async def test_each_http_retry_is_charged_and_traced(monkeypatch):
    import invoice_referee.evidence.groq as module
    import invoice_referee.evidence.telemetry as telemetry
    traces=[];requests=[]
    monkeypatch.setattr(telemetry,"record_llm_call",lambda **kwargs:traces.append(kwargs))
    async def no_wait(_):pass
    monkeypatch.setattr(module.asyncio,"sleep",no_wait)
    def handler(req):
        requests.append(req)
        if len(requests)==1:return httpx.Response(429,headers={"retry-after":"1"})
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]})
    budget=RunBudget()
    await GroqClient(api_key="fake",transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=budget)
    assert len(requests)==budget.llm_attempts==len(traces)==2
    assert traces[0]["error"] and not traces[1]["error"]


def test_cleaner_preserves_think_tags_inside_json_values():
    raw='{ "note": "<think>source text</think>" }'
    assert _clean_json_content(raw)==raw


async def test_request_timeout_is_bounded_by_remaining_run_deadline():
    import asyncio
    async def handler(req):
        await asyncio.sleep(.1)
        return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
    budget=RunBudget(processing_deadline_s=.01)
    with pytest.raises(GroqTransportError,match="timeout"):
        await GroqClient(api_key="fake",timeout_s=60,transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=budget)
    assert budget.llm_attempts==1


async def test_rate_limit_longer_than_run_deadline_does_not_sleep(monkeypatch):
    import invoice_referee.evidence.groq as module
    waits=[]
    async def sleep(seconds): waits.append(seconds)
    monkeypatch.setattr(module.asyncio,"sleep",sleep)
    def handler(req):return httpx.Response(429,headers={"retry-after":"120"})
    with pytest.raises(GroqTransportError):
        await GroqClient(api_key="fake",transport=httpx.MockTransport(handler)).complete_json(system="s",user="u",budget=RunBudget(processing_deadline_s=3))
    assert not waits


async def test_groq_schema_repair_is_shared_and_limited_to_one_slot():
    from invoice_referee.evidence.structured_output import complete_structured
    count=0
    def handler(req):
        nonlocal count;count+=1
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":"invalid JSON"}}]})
    client=GroqClient(api_key="fake",transport=httpx.MockTransport(handler))
    budget=RunBudget()
    for _ in range(2):
        with pytest.raises(GroqSchemaError):
            await complete_structured(client,system="s",user="u",budget=budget,validate=lambda d:d,
                stage="extract",prompt_version="test",schema_version="test")
    assert budget.schema_repairs==1 and budget.llm_attempts==count==3
