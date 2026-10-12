"""Compatibility shim: config moved to ``legacy/config.py``."""
from __future__ import annotations

from invoice_referee.legacy.config import *  # noqa: F401,F403
from invoice_referee.legacy.config import (  # noqa: F401
    activate_demo_policy,
    load_policy,
    snapshot_hash,
)
