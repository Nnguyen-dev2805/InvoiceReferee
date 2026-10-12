"""Compatibility shim: the legacy application package moved to
``legacy/application``. Submodules are aliased so ``invoice_referee.application.X``
keeps resolving to the same module objects.
"""
from __future__ import annotations

import importlib
import sys

for _name in ("executor", "human", "pipeline", "service"):
    _mod = importlib.import_module(f"invoice_referee.legacy.application.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
