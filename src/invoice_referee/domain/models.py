"""Compatibility shim: the T01 contract models now live in
``legacy/domain/models.py`` (historical claim-processing contracts). Current
settlement code should import the error class from ``shared.errors``; this shim
keeps existing ``invoice_referee.domain.models`` imports resolving, including
``DomainError`` (same class identity via ``shared.errors``).
"""
from __future__ import annotations

from invoice_referee.legacy.domain.models import *  # noqa: F401,F403
from invoice_referee.legacy.domain.models import (  # noqa: F401
    DomainError,
    StoppedRun,
)

__all__ = [name for name in dir() if not name.startswith("_")]
