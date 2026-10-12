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


def iso(value: datetime) -> str:
    """Serialise an aware datetime to a UTC ISO-8601 string."""
    return value.astimezone(timezone.utc).isoformat()


def now_iso() -> str:
    """Current record time as a UTC ISO-8601 string.

    Resolves ``utcnow`` dynamically so monkeypatching ``clock.utcnow`` (the
    single record-clock owner) still pins persisted timestamps in tests.
    """
    return iso(utcnow())
