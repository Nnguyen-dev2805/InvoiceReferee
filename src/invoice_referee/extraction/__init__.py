"""Compatibility shim: the legacy extraction package moved to
``legacy/extraction``. Submodules are aliased so ``invoice_referee.extraction.X``
keeps resolving to the same module objects.
"""
from __future__ import annotations

import importlib
import sys

for _name in ("compact", "providers", "validation"):
    _mod = importlib.import_module(f"invoice_referee.legacy.extraction.{_name}")
    sys.modules[f"{__name__}.{_name}"] = _mod
