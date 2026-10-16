"""Provider selection: Kimi default, xKiro explicit, no silent fallback (16/10/2026)."""

from __future__ import annotations


def _settings(**kwargs):
    from invoice_referee.config import Settings

    base = dict(_env_file=None)
    base.update(kwargs)
    return Settings(**base)  # type: ignore[call-arg]


def test_kimi_is_default_provider():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        mistral_api_key="m",
        mistral_ocr_model="ocr",
        kimi_token="t",
        kimi_secret="s",
        kimi_base_url="https://kimi.test/v1",
    )
    client = build_llm_client(settings)
    assert isinstance(client, KimiClient)
    assert client.provider_name == "kimi"
    assert client.model == "moonshotai/Kimi-K3"


def test_kimi_explicit_model_kept():
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        llm_provider="kimi",
        kimi_token="t",
        kimi_secret="s",
        kimi_base_url="https://kimi.test/v1",
        kimi_model="moonshotai/Kimi-K3",
    )
    assert build_llm_client(settings).model == "moonshotai/Kimi-K3"


def test_xkiro_explicit_still_works():
    from invoice_referee.evidence.xkiro import XkiroClient
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        llm_provider="xkiro",
        xkiro_api_key="k",
        xkiro_base_url="https://x.test/v1",
        invoice_referee_llm_model="llm-1",
    )
    client = build_llm_client(settings)
    assert isinstance(client, XkiroClient)
    assert client.provider_name == "xkiro"


def test_kimi_missing_does_not_fallback_to_xkiro():
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        xkiro_api_key="k",
        xkiro_base_url="https://x.test/v1",
        invoice_referee_llm_model="llm-1",
    )
    try:
        build_llm_client(settings)
    except ValueError as error:
        assert "KIMI_TOKEN" in str(error) or "KIMI_SECRET" in str(error)
    else:
        raise AssertionError("missing Kimi creds must raise, never fallback to xKiro")


def test_unknown_provider_rejected():
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        llm_provider="other",
        kimi_token="t",
        kimi_secret="s",
        kimi_base_url="https://kimi.test/v1",
    )
    try:
        build_llm_client(settings)
    except ValueError as error:
        assert "llm_provider" in str(error)
    else:
        raise AssertionError("unknown provider must raise")


def test_reader_identity_distinguishes_provider_model_pipeline():
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.prompts import evidence_reader_identity
    from invoice_referee.evidence.xkiro import XkiroClient

    class _Reader:
        provider_name = "mistral"
        model = "mistral-ocr-latest"

    class _OcrReader:
        provider = _Reader()

    kimi = KimiClient(
        token="t", secret="s", base_url="https://k/v1", model="moonshotai/Kimi-K3"
    )
    xkiro = XkiroClient(api_key="k", model="llm-1", base_url="https://x/v1")
    a = evidence_reader_identity(
        reader=_OcrReader(), classifier=kimi, activity_profile=None
    )
    b = evidence_reader_identity(
        reader=_OcrReader(), classifier=xkiro, activity_profile=None
    )
    assert a != b


def test_missing_for_live_is_provider_aware():
    kimi_only = _settings(
        mistral_api_key="m",
        mistral_ocr_model="ocr",
        kimi_token="t",
        kimi_secret="s",
        kimi_base_url="https://kimi.test/v1",
    )
    assert kimi_only.missing_for_live() == ()
    assert kimi_only.live_ready


def test_invalid_reasoning_effort_is_rejected_loudly():
    from invoice_referee.runtime import build_llm_client
    from invoice_referee.config import Settings
    import pytest

    settings = Settings(
        kimi_token="t", kimi_secret="s", kimi_base_url="https://k/v1",
        kimi_reasoning_effort="ultra", _env_file=None,  # type: ignore[call-arg]
    )
    with pytest.raises(ValueError, match="KIMI_REASONING_EFFORT"):
        build_llm_client(settings)


def test_default_effort_is_low():
    from invoice_referee.runtime import build_llm_client
    from invoice_referee.config import Settings

    settings = Settings(
        kimi_token="t", kimi_secret="s", kimi_base_url="https://k/v1",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_llm_client(settings).reasoning_effort == "low"
