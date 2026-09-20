"""Verify manifest — expected labels and suite membership.

This lives with the Verify harness (the judge path), never inside production
``review()`` code. Production logic must not read expected labels.
"""

from __future__ import annotations

# Ground-truth expected action per documented case (docs/TEST_CASES.md).
EXPECTED: dict[str, str] = {
    "TC01": "AUTO_PROCESS",
    "TC02": "AUTO_PROCESS",
    "TC03": "AUTO_PROCESS",
    "TC04": "REQUEST_INFO",
    "TC05": "REQUEST_INFO",
    "TC06": "REQUEST_INFO",
    "TC07": "REQUEST_INFO",
    "TC08": "REQUEST_INFO",
    "TC09": "REQUEST_INFO",
    "TC10": "REQUEST_INFO",
    "TC11": "REQUEST_INFO",
    "TC12": "REQUEST_INFO",
    "TC13": "ESCALATE",
    "TC14": "ESCALATE",
    "TC15": "REQUEST_INFO",
    "TC16": "REQUEST_INFO",
    "TC17": "REQUEST_INFO",
}

# Core Verify — 4 cases covering routine / request-info / escalation.
CORE = ["TC01", "TC07", "TC13", "TC14"]

# Challenge A (escalation) Verify — 3 routine + 1 request-info + 1 escalate.
ESCALATION = ["TC01", "TC02", "TC03", "TC07", "TC13"]

SUITES: dict[str, list[str]] = {
    "core": CORE,
    "escalation": ESCALATION,
}
