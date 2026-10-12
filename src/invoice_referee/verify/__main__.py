"""Compatibility entry: ``python -m invoice_referee.verify`` (legacy harness).

The implementation moved to ``legacy/verify/__main__.py``. This shim keeps the
historical CLI entry working without duplicating the implementation.
"""
from __future__ import annotations

from invoice_referee.legacy.verify.__main__ import main

if __name__ == "__main__":
    main()
