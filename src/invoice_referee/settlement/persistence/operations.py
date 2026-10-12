"""Persisted operation codes and source-use tags.

These string values are the ``operation`` argument of ``fingerprint()`` and the
``audit_events.operation`` column, so they are part of the persisted wire
format. They are collected here so the lifecycle modules share one definition
instead of copying the same literals; the values must never change.

This module has no imports and no side effects: it is a plain constant table.
"""

# --- Case / run / source lifecycle (Store façade) ---------------------------
CREATE_CASE = "CREATE_CASE"
CREATE_B3_CASE = "CREATE_B3_CASE"
CREATE_STANDALONE_B7 = "CREATE_STANDALONE_B7"
REVISE_SUBMISSION = "REVISE_SUBMISSION"
ADD_SOURCE = "ADD_SOURCE"
START_RUN = "START_RUN"
RESPOND = "RESPOND"
DECIDE = "DECIDE"
REVIEW = "REVIEW"
RECORD_MONEY = "RECORD_MONEY"
CONTROL = "CONTROL"
HANDOFF = "HANDOFF"
CLOSE_CASE = "CLOSE_CASE"

# --- Advance (B3) lifecycle --------------------------------------------------
B3_PRESENT = "B3_PRESENT"
B3_DECIDE = "B3_DECIDE"
B3_ADD_ADVANCE_PROOF = "B3_ADD_ADVANCE_PROOF"
B3_RECORD_ADVANCE = "B3_RECORD_ADVANCE"

# --- Linked / settlement (B7) lifecycle --------------------------------------
PREPARE_LINKED_B7 = "PREPARE_LINKED_B7"
REVISE_LINKED_B7 = "REVISE_LINKED_B7"
B7_CONTEXT_REFRESH = "B7_CONTEXT_REFRESH"
B7_MONEY_CONTEXT_REFRESH = "B7_MONEY_CONTEXT_REFRESH"
B7_PRESENT = "B7_PRESENT"
B7_DECIDE = "B7_DECIDE"
B7_ADD_SETTLEMENT_PROOF = "B7_ADD_SETTLEMENT_PROOF"
B7_RECORD_MONEY = "B7_RECORD_MONEY"
B7_REVALIDATE = "B7_REVALIDATE"
B7_HANDOFF = "B7_HANDOFF"
B7_CLOSE = "B7_CLOSE"
B7_ADJUSTMENT = "B7_ADJUSTMENT"

# --- Source-use tags (distinguish proof origins in one case) ------------------
B3_ADVANCE_PROOF_USE = "B3_ADVANCE_PROOF"
B7_SETTLEMENT_PROOF_USE = "B7_SETTLEMENT_PROOF"
LINKED_B7_CONTEXT_USE = "LINKED_B7_CONTEXT"
