"""Presentation helpers for the Streamlit UI (pure functions, no Streamlit import).

Keeping these out of the Streamlit module lets them be unit-tested and keeps the
UI layer thin. No business rules live here — the UI only ever calls review().
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from invoice_referee.domain import models as m

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def format_vnd(value: Optional[int]) -> str:
    """Format integer VND with dot thousand separators, or an em dash if unknown."""
    if value is None or not isinstance(value, int) or isinstance(value, bool):
        return "—"
    return f"{value:,.0f}".replace(",", ".") + " ₫"


def list_sample_cases() -> list[str]:
    return sorted(p.stem for p in FIXTURES_DIR.glob("TC*.json"))


def load_sample(case_id: str) -> dict[str, Any]:
    with open(FIXTURES_DIR / f"{case_id}.json", encoding="utf-8") as f:
        return json.load(f)


def parse_json_input(text: str) -> dict[str, Any]:
    """Parse pasted/uploaded JSON into an evidence dict. Raises ValueError if invalid."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Transaction JSON must be an object at the top level.")
    return data


def evidence_summary(tx: m.Transaction) -> dict[str, bool]:
    return {
        "Purchase Order": tx.po is not None,
        "Goods Receipt": bool(tx.goods_receipts),
        "Invoice": tx.invoice is not None,
        "Payment History": bool(tx.payment_history),
        "Approvals": bool(tx.approvals),
    }


def decision_action_labels() -> list[str]:
    return [a.value for a in m.DecisionAction]
