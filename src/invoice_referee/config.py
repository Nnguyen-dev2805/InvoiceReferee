"""Application settings (plan T1).

Missing credentials are reported explicitly rather than defaulted, so a
LIVE run can never silently pretend to have a provider.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

LIVE_REQUIRED_SETTINGS: tuple[str, ...] = (
    "MISTRAL_API_KEY",
    "MISTRAL_OCR_MODEL",
    "XKIRO_API_KEY",
    "XKIRO_BASE_URL",
    "INVOICE_REFEREE_LLM_MODEL",
)


class Settings(BaseSettings):
    """Environment-backed configuration. Values are blank until supplied."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    mistral_api_key: str | None = None
    mistral_ocr_model: str | None = None
    xkiro_api_key: str | None = None
    xkiro_base_url: str | None = None
    invoice_referee_llm_model: str | None = None

    def missing_for_live(self) -> tuple[str, ...]:
        """The live-required settings that are absent or blank."""
        return tuple(
            name
            for name in LIVE_REQUIRED_SETTINGS
            if not getattr(self, name.lower(), None)
        )

    @property
    def live_ready(self) -> bool:
        return not self.missing_for_live()
