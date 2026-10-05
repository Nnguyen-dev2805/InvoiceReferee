"""Root test configuration.

Tests must be hermetic: they must not depend on a developer's local `.env`
(real provider keys, model names, endpoints). ``create_runtime_app`` loads the
repo `.env` into ``os.environ`` for real deployments; that must never leak into
the test process and change assertions.

This autouse fixture removes the provider/config variables before every test so a
test that exercises ``create_runtime_app`` cannot pollute a later test, and tests
that set their own values (via ``monkeypatch``) still work.
"""
from __future__ import annotations

import pytest

# Provider + runtime config that a `.env` could set and that tests assert on.
_ENV_VARS = (
    'DATA_ROOT',
    'PROVIDER_MODE',
    'MISTRAL_API_KEY',
    'MISTRAL_OCR_MODEL',
    'MISTRAL_BASE_URL',
    'KIMI_API_KEY',
    'KIMI_TOKEN',
    'KIMI_SECRET',
    'KIMI_MODEL',
    'KIMI_BASE_URL',
    'OCR_WORD_REVIEW_THRESHOLD',
)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
