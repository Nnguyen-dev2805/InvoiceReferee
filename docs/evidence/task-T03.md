# Evidence — T03 (Policy, inventory/arithmetic, authority, decision reducer)

Mode: unit / synthetic-fake (builders). Does NOT prove live OCR quality,
deployment, or real-user acceptance.

## Commands and results

- RED (before implementation): `pytest tests/unit/test_expense_decisions.py tests/unit/test_inventory_arithmetic.py`
  → `ModuleNotFoundError: invoice_referee.policy.expenses` (expected).
- GREEN (T03 test files): `rtk proxy .venv/bin/python -m pytest tests/unit/test_expense_decisions.py tests/unit/test_inventory_arithmetic.py -q`
  → 47 passed (after review round 1).
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 147 passed
  (41 T01 + 59 T02 + 47 T03).
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.

## Review round 1 (Critical + Important + 3 minors), all addressed

1. Critical: `MappingProposal.conflicts` now consumed → INV-02 UNKNOWN, blocking
   CREATE_PAYMENT_REQUEST when a mapping conflict exists.
2. Important: matrix rules aggregated per `rule_id` (worst-status-wins) so each
   rule appears at most once per decision for multi-document bundles.
3. SRC-01 now fires only on declared-primary-absent (not on a non-BILL kind).
4. SCOPE-02 UNKNOWN (not PASS) when the currency fact is not usable.
5. Registry-less documents flagged UNKNOWN (not silently skipped).

## Scope note

`ITEMIZED_WITH_ADJUSTMENTS` compares `total` with `subtotal + tax + fees −
discount` using only the adjustment terms the model DECLARED present on the
document. A declared-present term that is unusable is UNKNOWN (no default-0); an
undeclared term contributes 0; a template that declares no term is UNKNOWN. When
item line amounts are usable, `sum(line_amount)` is also checked against
`subtotal`. The rulebook §4 wording was updated to match this B2 behaviour.
