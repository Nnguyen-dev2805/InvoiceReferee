"""Provider selection: Groq default, Kimi/xKiro explicit, no silent fallback (16/10/2026)."""

from __future__ import annotations


def _settings(**kwargs):
    from invoice_referee.config import Settings

    base = dict(_env_file=None, llm_provider="kimi")
    base.update(kwargs)
    return Settings(**base)  # type: ignore[call-arg]


def test_groq_is_default_provider():
    from invoice_referee.config import Settings
    from invoice_referee.evidence.groq import GroqClient
    from invoice_referee.runtime import build_llm_client
    settings = Settings(_env_file=None, groq_api_key="fake")
    assert settings.llm_provider == "groq"
    client = build_llm_client(settings)
    assert isinstance(client, GroqClient)
    assert client.model == "openai/gpt-oss-20b"
    assert client.reasoning_effort == "low"


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
        llm_provider="kimi", kimi_token="t", kimi_secret="s", kimi_base_url="https://k/v1",
        kimi_reasoning_effort="ultra", _env_file=None,  # type: ignore[call-arg]
    )
    with pytest.raises(ValueError, match="KIMI_REASONING_EFFORT"):
        build_llm_client(settings)


def test_default_effort_is_low():
    from invoice_referee.runtime import build_llm_client
    from invoice_referee.config import Settings

    settings = Settings(
        llm_provider="kimi", kimi_token="t", kimi_secret="s", kimi_base_url="https://k/v1",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert build_llm_client(settings).reasoning_effort == "low"


def test_groq_is_selected_when_configured():
    from invoice_referee.evidence.groq import GroqClient
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        llm_provider="groq",
        groq_api_key="gsk-test",
    )
    client = build_llm_client(settings)
    assert isinstance(client, GroqClient)
    assert client.provider_name == "groq"
    assert client.model == "openai/gpt-oss-20b"
    assert client.reasoning_effort == "low"
    assert client.base_url == "https://api.groq.com/openai/v1"


def test_groq_explicit_model_and_effort_kept():
    from invoice_referee.evidence.groq import GroqClient
    from invoice_referee.runtime import build_llm_client

    settings = _settings(
        llm_provider="groq",
        groq_api_key="gsk-test",
        groq_model="openai/gpt-oss-20b",
        groq_reasoning_effort="medium",
        groq_base_url="https://custom.groq.internal/v1",
    )
    client = build_llm_client(settings)
    assert isinstance(client, GroqClient)
    assert client.model == "openai/gpt-oss-20b"
    assert client.reasoning_effort == "medium"
    assert client.base_url == "https://custom.groq.internal/v1"


def test_groq_missing_api_key_raises():
    from invoice_referee.runtime import build_llm_client
    import pytest

    settings = _settings(llm_provider="groq")
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_llm_client(settings)


def test_groq_invalid_reasoning_effort_rejected():
    from invoice_referee.runtime import build_llm_client
    import pytest

    settings = _settings(
        llm_provider="groq",
        groq_api_key="gsk-test",
        groq_reasoning_effort="max",
    )
    with pytest.raises(ValueError, match="GROQ_REASONING_EFFORT"):
        build_llm_client(settings)


def test_groq_missing_for_live_is_provider_aware():
    groq_only = _settings(
        llm_provider="groq",
        mistral_api_key="m",
        mistral_ocr_model="ocr",
        groq_api_key="gsk-test",
    )
    assert groq_only.missing_for_live() == ()
    assert groq_only.live_ready

    groq_missing_key = _settings(
        llm_provider="groq",
        mistral_api_key="m",
        mistral_ocr_model="ocr",
    )
    assert groq_missing_key.missing_for_live() == ("GROQ_API_KEY",)
    assert not groq_missing_key.live_ready


def test_reader_identity_distinguishes_groq():
    from invoice_referee.evidence.groq import GroqClient
    from invoice_referee.evidence.kimi import KimiClient
    from invoice_referee.evidence.prompts import evidence_reader_identity

    class _Reader:
        provider_name = "mistral"
        model = "mistral-ocr-latest"

    class _OcrReader:
        provider = _Reader()

    kimi = KimiClient(
        token="t", secret="s", base_url="https://k/v1", model="moonshotai/Kimi-K3"
    )
    groq = GroqClient(api_key="gsk-test", model="openai/gpt-oss-20b", reasoning_effort="low")

    id_kimi = evidence_reader_identity(reader=_OcrReader(), classifier=kimi, activity_profile=None)
    id_groq = evidence_reader_identity(reader=_OcrReader(), classifier=groq, activity_profile=None)
    assert id_kimi != id_groq



def test_reader_cache_identity_tracks_line_normalization_version(monkeypatch):
    import invoice_referee.evidence.prompts as prompts
    class Provider:
        provider_name="mistral"; model="ocr"
    class Reader:
        provider=Provider()
    class Llm:
        provider_name="groq";model="openai/gpt-oss-20b";reasoning_effort="low"
    for identity in (prompts.evidence_reader_identity,prompts.role_aware_reader_identity):
        old=identity(reader=Reader(),classifier=Llm(),activity_profile=None)
        with monkeypatch.context() as patch:
            patch.setattr(prompts,"LINE_NORMALIZATION_VERSION","different-parser")
            assert old!=identity(reader=Reader(),classifier=Llm(),activity_profile=None)
