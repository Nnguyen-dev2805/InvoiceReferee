"""Synthetic Policy v0 constants (docs/POLICY.md).

SYNTHETIC: these values, especially the 50M authority threshold, are prototype
data for evaluation — not a real company policy or a legal rule.
"""

from __future__ import annotations

# Synthetic authority threshold in integer VND.
AUTHORITY_THRESHOLD_VND = 50_000_000

# Policy rule IDs P01–P15 with short descriptions (see docs/POLICY.md).
POLICY_RULES: dict[str, str] = {
    "P01": "PO must be identifiable",
    "P02": "Supplier must match PO",
    "P03": "Item must belong to PO",
    "P04": "Goods Receipt is required evidence",
    "P05": "Invoiced quantity must not exceed received quantity",
    "P06": "Unit price must match approved price",
    "P07": "Invoice total must not exceed approved amount",
    "P08": "Cumulative invoice total must not exceed PO",
    "P09": "Duplicate invoice must not be processed as new",
    "P10": "Paid/partially-paid invoice must not re-enter routine payment",
    "P11": "Unknown payment status must not be assumed",
    "P12": "Authority threshold",
    "P13": "Outside-policy transaction",
    "P14": "Conflicting evidence",
    "P15": "Suspicious / flagged input",
}

# Escalation targets (docs/POLICY.md §7).
TARGET_FINANCE_MANAGER = "Finance Manager"
TARGET_ACCOUNTING_OWNER = "Accounting / Finance owner"
