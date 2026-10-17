"""Application settings (plan T1).

Missing credentials are reported explicitly rather than defaulted, so a
LIVE run can never silently pretend to have a provider.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

LIVE_REQUIRED_SETTINGS: tuple[str, ...] = (
    "MISTRAL_API_KEY",
    "MISTRAL_OCR_MODEL",
    "XKIRO_API_KEY",
    "XKIRO_BASE_URL",
    "INVOICE_REFEREE_LLM_MODEL",
    "KIMI_TOKEN",
    "KIMI_SECRET",
    "KIMI_BASE_URL",
    "KIMI_MODEL",
    "GROQ_API_KEY",
)

# Default LLM provider/model for local LIVE runs (16/10/2026 refinement).
# Groq is the default runtime; Kimi and xKiro remain explicit alternatives.
# The private endpoint URL is never hardcoded: KIMI_BASE_URL must come from
# local ignored config. The model id itself is not a secret.
DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_KIMI_MODEL = "moonshotai/Kimi-K3"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# The single dataset source root (plan R2), resolved relative to the project,
# not the cwd. Overridable for a temporary corpus.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = _PROJECT_ROOT / "data" / "kiem-thu"


class Settings(BaseSettings):
    """Environment-backed configuration. Values are blank until supplied."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    mistral_api_key: str | None = None
    mistral_ocr_model: str | None = None
    xkiro_api_key: str | None = None
    xkiro_base_url: str | None = None
    invoice_referee_llm_model: str | None = None
    kimi_token: str | None = None
    kimi_secret: str | None = None
    kimi_base_url: str | None = None
    kimi_model: str | None = None
    kimi_reasoning_effort: str = "low"
    groq_api_key: str | None = None
    groq_base_url: str = DEFAULT_GROQ_BASE_URL
    groq_model: str = DEFAULT_GROQ_MODEL
    groq_reasoning_effort: str = "low"
    llm_provider: str = DEFAULT_LLM_PROVIDER

    # The evaluation dataset root (plan R2). One value for the whole app.
    dataset_root: str = str(DEFAULT_DATASET_ROOT)

    # LangSmith tracing is opt-in: it is never a live-required setting, and a
    # missing/failed trace never blocks a business conclusion (contracts §9).
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "invoice-referee"
    langsmith_agent_id: str | None = None
    langsmith_agent_environment: str | None = None
    # RECORDED_REPLAY inputs (S6, 18/10/2026): a digest-keyed OCR recording and
    # an optional directory of canned LLM payloads (dev/test fixture transport
    # only — never production providers).
    replay_recording: str | None = None
    fake_llm_dir: str | None = None

    def missing_for_live(self) -> tuple[str, ...]:
        """The live-required settings that are absent or blank.

        Refinement 16/10/2026: provider-aware. Mistral OCR is always required;
        only the selected LLM provider's credentials are required. Kimi is the
        alternative; Groq is the default; xKiro stays usable when ``llm_provider="xkiro"``.
        """
        provider = (self.llm_provider or DEFAULT_LLM_PROVIDER).strip().lower()
        names: list[str] = ["MISTRAL_API_KEY", "MISTRAL_OCR_MODEL"]
        if provider == "groq":
            names += ["GROQ_API_KEY"]
        elif provider == "xkiro":
            names += ["XKIRO_API_KEY", "XKIRO_BASE_URL", "INVOICE_REFEREE_LLM_MODEL"]
        else:
            names += ["KIMI_TOKEN", "KIMI_SECRET", "KIMI_BASE_URL"]
        return tuple(name for name in names if not getattr(self, name.lower(), None))

    @property
    def live_ready(self) -> bool:
        return not self.missing_for_live()

    @property
    def langsmith_ready(self) -> bool:
        """Tracing is active only when explicitly enabled and keyed."""
        return bool(self.langsmith_tracing and self.langsmith_api_key)
