"""Compatibility entry for the legacy claim-processing API.

The implementation moved to ``legacy/api/app.py``. This thin module keeps the
public entry ``invoice_referee.api.app:create_runtime_app`` (and ``create_app``,
``load_repo_env``) importable for existing consumers/tests without duplicating
the implementation. Current settlement uses ``api/settlement.py``.
"""
from __future__ import annotations

from invoice_referee.env import load_repo_env  # noqa: F401  (re-export)
from invoice_referee.legacy.api.app import (  # noqa: F401  (re-export)
    create_app,
    create_runtime_app,
)

__all__ = ["create_app", "create_runtime_app", "load_repo_env"]
