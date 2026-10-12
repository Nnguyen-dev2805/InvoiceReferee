"""Compatibility shim: Repository moved to ``legacy/storage/repository.py``.

Re-exports the public names (Repository + module constants) and the artifact
helpers, so existing ``invoice_referee.storage.repository`` imports (including
tests that monkeypatch ``put_artifact``) keep resolving.
"""
from __future__ import annotations

from invoice_referee.shared.artifacts import put_artifact, safe_name  # noqa: F401
from invoice_referee.legacy.storage.repository import (  # noqa: F401
    ALLOWED_EXT,
    SCHEMA_PATH,
    SCHEMA_VERSION,
    Repository,
)
