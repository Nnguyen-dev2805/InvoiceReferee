"""Compatibility shim: the legacy policy package moved to ``legacy/policy``.
Submodules are aliased so ``invoice_referee.policy.X`` keeps resolving.
"""
from __future__ import annotations

import importlib
import sys

for _name in ("decision", "expenses", "inventory", "numeric", "quality"):
    _mod = importlib.import_module(f"invoice_referee.legacy.policy.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
