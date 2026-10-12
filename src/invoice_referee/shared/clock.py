"""Shared runtime clock: record time (aware UTC), not business time.

Records call ``clock.utcnow()`` for the timestamp of a persisted record. This is
distinct from business time (``effective_b3_time``/``effective_b7_time``), which
decides authority/eligibility and may be pinned by a synthetic demo clock. Tests
monkeypatch ``clock.utcnow`` on this owner, not on the Store façade.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
