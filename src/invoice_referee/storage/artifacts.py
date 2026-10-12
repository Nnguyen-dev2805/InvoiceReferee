"""Compatibility shim: artifact IO now lives in ``shared.artifacts``.

Kept so legacy and current callers using ``invoice_referee.storage.artifacts``
keep resolving to the same functions.
"""
from __future__ import annotations

from invoice_referee.shared.artifacts import put_artifact, safe_name

__all__ = ["put_artifact", "safe_name"]
