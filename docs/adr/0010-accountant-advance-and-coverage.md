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
4. Superseding user correction on 15/10/2026: no initial-history checkbox or
   separate confirmation action in the ordinary UI. Confirming a valid source-bound
   advance records A once and enables `DOSSIER_RECORDS` reconciliation atomically.
   Its universe is the dossier's recorded money, not all external bank history.
   No actor statement of complete prior history, fake zero opening, fund or absence
   quote is generated. Unconfirmed uploads/declarations do not become actual money.
5. Completed source-bound advances and active-instruction-bound P/R update the
   dossier tracking, while unknown/unallocated/conflicting money remains blocking.
   Employee proof upload leaves R unchanged; only accountant confirmation records
   receipt. A confirmed imported advance may start tracking when the accountant
   records a source-bound P/R. Legacy coverage APIs and payloads remain readable;
   `MANAGED_HISTORY` is compatibility data, never an extra UI requirement.
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
- Dossier tracking is not a bank integration or a complete-history assertion.
  Positive money events retain source locators and responsible accountant audit.
  No one receipt proves all external history.
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
