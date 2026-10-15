# ADR0010 — Accountant-confirmed advance linkage and money-history coverage

## Status

Accepted — 15/10/2026

## Context

An accountant may add a received-advance voucher to an existing settlement root,
including a root whose activity is still `PROPOSED`. The opened root identifies
where the user is working; it is not, by itself, evidence that a separate voucher
belongs to that activity. A voucher records one money movement and cannot prove
that all advances, supplemental payments, returns, reversals, and unallocated
movements for the period have been reconciled.

The previous LIVE draft used transient source IDs, so its references were not
retrievable after restart. It also set the advance scope from the open root without
recording how the voucher was bound to the work. Generic `ledger:coverage` answers
were persisted as free text, while admission only consumed typed coverage from a
context snapshot. A proposed activity with no matching context snapshot also lost
tenant identity needed to check the company and employee.

## Decision

1. An advance voucher is attached to `case_sources` before OCR. The OCR report and
   the accountant-reviewed draft are stored against that source and root. A
   confirmation must name that stored draft; every persisted locator must still
   resolve to the same tenant, root, source and digest after restart.
2. The server first compares explicit references with the settlement and the
   tenant's activity-reference catalog. Exact, unique and consistent references
   may link automatically; a reference mapped elsewhere remains a conflict. If
   the voucher's reference is unregistered, a separate multi-field decision may
   link only when its source-backed employee, configured payer, specific work
   purpose, declared advance amount, chronology, transaction identity and
   tenant-wide uniqueness all agree (ADR0011). Otherwise the accountant confirms
   the specific work and records a reason tied to the source. An open page or
   generic purpose alone never auto-links.
3. Only a completed, source-clear, correctly scoped, accountant-confirmed advance
   may create `ActivityAcceptance`. This is a separate fact recording that the
   company accepted the work through the voucher, with employee/activity, actor,
   time, transaction identity, reason and source references. It does not change
   activity status, grant `AUTHORIZE_ACTIVITY`, recognize expenses, or grant
   payment/collection authority. A pending, failed, unclear, mismatched, or
   conflicting voucher cannot create it.
   For a complete and automatically linked draft, the authenticated accountant's
   source-bound record command is the confirmation; no repeated declaration text
   is required. The server derives the statement and records actor/time/source.
   Missing-field completion needs a reason; manual linkage uses its existing
   reason. Text cannot waive a conflicting source.
4. The accountant confirms coverage through a separate structured command. It
   records the employee/activity, period start, server-owned confirmation time,
   funds, all movement kinds, opening balance, unallocated event IDs, witness
   references, reason, actor and root ledger version. Admission consumes this
   `CoverageRecord`; a free-text answer does not.
5. A coverage record cannot be future-dated. It remains usable for the same
   accounting date only while the covered root ledger version is unchanged. A
   later or backdated event on that root makes it stale. An event in another root
   does not. A non-empty unallocated set cannot establish A/P/R zeros. Uploading
   an advance never creates coverage.
6. Context composition takes organization ID/name, people, policies and grants
   from tenant snapshots. It overlays the selected activity identity and only
   that activity's references, ledger, budgets and coverage. A new proposed
   activity therefore keeps company/employee identity without borrowing another
   activity's money history or becoming authorized.
7. New P/R receipts bind to the active same-root instruction and attached source.
   An employee uploads a return proof into a durable draft; this does not change
   R. Only an accountant's confirmation of a clear, completed, party-matched
   draft records `EMPLOYEE_RETURN`. A partial return leaves the COLLECT remainder
   active, and an overpayment is recorded with a blocking issue. Replaying the
   same transfer key is idempotent. The accountant's generic money form is shown
   only when a live PAY instruction exists and requires a real source and
   transaction reference.

## Consequences

- No activity-specific edit to `company-context.json` is needed to identify the
  company or employee on a new root.
- Event identity remains tenant-unique; an event already owned by another root is
  a conflict even when its amount and parties match.
- Database changes are additive (`case_advance_drafts`,
  `case_activity_acceptances`, and `case_coverage_records`). Existing user data is
  not rewritten by this implementation session.
- The accountant's coverage confirmation is an accountable business statement,
  not a bank integration or cryptographic verification. The UI preserves the
  source locator and actor/reason so the assertion can be reviewed.
- Existing action limits, grants, policy, arithmetic, payer binding, tenant
  isolation and Stop/Resume behavior remain separate gates.

## Rejected alternatives

- Reusing the generic answer string or changing an issue to `ANSWERED` would not
  give admission a typed, versioned history basis.
- Treating the current root, same employee, similar purpose, amount, or date as
  the activity link could attach money to one of two similar cases.
- Marking a proposed activity `AUTHORIZED` or inserting an activity grant would
  turn evidence of accepted work into financial authority.
- Inferring zero flows from one advance voucher would collapse A, B and C and
  permit a false balance.
