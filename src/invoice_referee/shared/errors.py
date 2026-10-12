"""Shared domain error, used by both current settlement and legacy slices.

There is exactly one ``DomainError`` class identity; ``domain.models``
re-exports these names so old imports keep resolving to the same class.
"""
from __future__ import annotations


class DomainError(Exception):
    """Machine-readable domain error: ``code`` stable, ``message`` friendly."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f'{code}: {message}')


class StoppedRun(DomainError):
    """Stop was acknowledged; no late business action may be applied."""

    def __init__(self, message: str = 'Run stopped; no late business action applied.') -> None:
        super().__init__('STOPPED', message)
