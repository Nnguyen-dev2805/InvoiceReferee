# Evidence — T07 (Human action validation, closure, input revision)

Mode: unit / synthetic-fake (builders). Validator + repository scope; full
end-to-end service closure is T08. Does NOT prove live quality, deployment, or
real-user acceptance.

## Commands and results

- RED (before implementation): `ModuleNotFoundError` for `application.human`;
  base `snapshot()` wrongly marked `PROPOSE_CORRECTION` active.
- GREEN (T07 + repository): `rtk proxy .venv/bin/python -m pytest tests/unit/test_human_actions.py tests/integration/test_repository.py -q`
  → 90 passed (after review round 1).
- Full suite: `rtk proxy .venv/bin/python -m pytest tests/ -q` → 306 passed.
- `rtk proxy .venv/bin/python -m pip check` → No broken requirements found.

## Review round 1 (2 Important + 4 minors), all addressed

1. OVERRIDE wrapper now keyset-validates the wrapped operation for all ops
   (incl. DENY/CLASSIFY_PROFILE); extra keys → INVALID_ACTION.
2. Deep ref-resolution / full mapping coverage / non-ambiguous-unit checks are
   documented as T08-owned (T07's signature has no bundle); not claimed enforced.
3. Numeric confirmations accept canonical `str` only (int/float rejected).
4. SUPPLY_DECLARATION value type-check → INVALID_ACTION (not pydantic).
5. `PROPOSE_CORRECTION` excluded from both hashed `confirmations` and
   `active_action_ids` (a proposal no longer changes the recomputed hash).
6. Added coverage tests: positive CONFIRM_MAPPING, OVERRIDE role-rejection,
   inclusive 5,000,000 boundary.

## Carried to T08 (documented requirements)

- Deep ref resolution + full-coverage mapping + non-ambiguous units.
- CONFIRM_FIELD field-path vs `quality._confirmation_matches`; wire
  confirmations through `process()`.
- ADD_EVIDENCE atomic evidence linkage.
- `create_run` active set should include `STOP_REQUESTED`.
- Route STOP via `Repository.request_stop`, not `apply_human_action`.
