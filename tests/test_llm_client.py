"""Tests for the OpenAI-compatible LLM client and env-based configuration."""

import json
import urllib.error

import pytest

from invoice_referee.agent.llm_client import LLMError, LLMTimeout
from invoice_referee.agent import config as agent_config
from invoice_referee.agent.openai_client import OpenAICompatibleClient


def _fake_urlopen_factory(body: str):
    class _Resp:
        def read(self):
            return body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _open(req, timeout=None):
        return _Resp()

    return _open


def _chat_body(content: str) -> str:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})


def _client(urlopen):
    return OpenAICompatibleClient(
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        model="claude-opus-4.8",
        urlopen=urlopen,
    )


def test_complete_extracts_message_content():
    client = _client(_fake_urlopen_factory(_chat_body('{"ok": true}')))
    assert client.complete("hi") == '{"ok": true}'


def test_complete_builds_chat_completions_url_and_auth():
    captured = {}

    def _open(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode())

        class _R:
            def read(self):
                return _chat_body("{}").encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return _R()

    client = _client(_open)
    client.complete("hello")
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer sk-test"
    assert captured["body"]["model"] == "claude-opus-4.8"
    assert captured["body"]["messages"][0]["content"] == "hello"


def test_timeout_maps_to_llm_timeout():
    def _open(req, timeout=None):
        raise TimeoutError("slow")

    with pytest.raises(LLMTimeout):
        _client(_open).complete("x")


def test_http_error_maps_to_llm_error():
    def _open(req, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(LLMError):
        _client(_open).complete("x")


def test_unparseable_response_maps_to_llm_error():
    with pytest.raises(LLMError):
        _client(_fake_urlopen_factory("not json")).complete("x")


# --- .env loading ------------------------------------------------------------


def test_load_env_file_parses_pairs(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nLLM_BASE_URL=https://api.xkiro.com/v1\nLLM_API_KEY=\"sk-abc\"\n\nLLM_MODEL=deepseek-chat\n"
    )
    parsed = agent_config.load_env_file(str(env))
    assert parsed["LLM_BASE_URL"] == "https://api.xkiro.com/v1"
    assert parsed["LLM_API_KEY"] == "sk-abc"
    assert parsed["LLM_MODEL"] == "deepseek-chat"


def test_load_env_file_missing_returns_empty(tmp_path):
    assert agent_config.load_env_file(str(tmp_path / "nope.env")) == {}


def test_client_from_env_returns_none_without_api_key():
    assert agent_config.client_from_env(env={"LLM_MODEL": "x"}) is None


def test_client_from_env_builds_openai_compatible_client():
    client = agent_config.client_from_env(
        env={
            "LLM_BASE_URL": "https://api.xkiro.com/v1",
            "LLM_API_KEY": "sk-xyz",
            "LLM_MODEL": "claude-opus-4.8",
            "LLM_TIMEOUT": "12",
        }
    )
    assert isinstance(client, OpenAICompatibleClient)
    assert client.base_url == "https://api.xkiro.com/v1"
    assert client.model == "claude-opus-4.8"
    assert client.timeout == 12.0


def test_client_from_env_defaults_base_url_and_model():
    client = agent_config.client_from_env(env={"LLM_API_KEY": "sk-xyz"})
    assert client.base_url  # has a default
    assert client.model  # has a default
