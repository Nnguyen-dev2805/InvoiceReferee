"""Stable JSON + SHA256 fingerprint helpers (command idempotency basis)."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Stable JSON text: sorted keys, no padding — the fingerprint basis."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def fingerprint(operation: str, payload: dict[str, Any]) -> str:
    """SHA256 over the semantic payload of a command (key/version excluded)."""
    basis = canonical_json({"operation": operation, "payload": payload})
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
