# ADR0011 — Multi-field linking for accountant-uploaded advance vouchers

## Status

Accepted — 15/10/2026

## Context

TC01's original transfer voucher has the reference `TU-TC01`, but a new
settlement root may not have that code registered in its activity catalog. The
voucher and settlement report still contain independent, source-backed identity,
organization, purpose, amount and date facts. Seeding that reference into a
pre-created `activity:tc01` would bypass the case the workflow is meant to prove.

## Decision

1. Keep explicit, unique and consistent references as the strongest link. An
   unregistered reference printed only on the voucher is not a conflict and does
   not stop multi-field evaluation. A reference mapped to another activity, or a
   transaction already owned by another root, is a non-overridable conflict.
2. Add the named basis `MULTI_FIELD_MATCH` for the relationship between an
   accountant-uploaded advance voucher and a settlement root. It is not the weak
   settlement-to-dossier similarity route described by ADR0008.
3. Auto-link only when all required facts agree:
   - the voucher recipient and settlement declarant match the same unique
     tenant employee identity;
   - the payer matches a configured organization money source; context may not
     fill in an unreadable payer;
   - voucher purpose and settlement purpose have the same specific project core
     after removing known payment boilerplate, with at least three distinct
     anchor tokens; a generic purpose such as `tiếp khách` is insufficient;
   - actual transfer amount equals the settlement's declared advance, not the
     expense total;
   - source dates are present and chronologically plausible: the transaction
     does not postdate the settlement document date or a known work end date;
     an invoice date is not a work date, and no arbitrary window is added;
   - a namespaced transaction identity is available and no existing event or
     competing draft has assigned it to another root; and
   - all roots in the tenant have been checked and exactly one is compatible.
4. A missing or ambiguous required fact, generic/different purpose, amount
   mismatch, implausible chronology or competing candidate requires accountant
   confirmation. Wrong employee/company, a reference mapped elsewhere, or an
   event owned by another root is a conflict that a checkbox cannot override.
5. Persist matched/missing/ambiguous/conflicting field signals with source refs
   in the draft and `ActivityAcceptance`. Do not expose other roots' IDs or names
   in the response.
6. Auto-linking does not record money. The accountant still reviews the saved
   source-bound draft and confirms the actual transfer. It creates no coverage,
   authority, expense eligibility or instruction. Idempotency and transaction
   ownership remain enforced at record time.
7. The accountant UI explains a successful link and displays the voucher that
   produced the draft without a second link checkbox or reason field. Uncertain
   links retain the existing confirmation path.
8. Source dates share a strict calendar parser across extraction and linking.
   Vietnamese prose dates from saved reads are valid input; normalization retains
   the original quote. A reversed day/month, impossible day, invented year/time,
   or ambiguous multi-date quote cannot establish a known date. The saved-draft
   GET re-evaluates linkage without provider I/O or financial writes. Unmapped
   references on an otherwise successful link are shown in optional details.

## Decision table

| Outcome | Conditions |
| --- | --- |
| `LINKED` | One compatible tenant root; unique employee and configured payer match; specific project-purpose cores match; received amount equals the declared advance; source dates are present and plausible; transaction identity is available and unclaimed. A unique registered reference may be the basis; an unregistered voucher-only reference may proceed through `MULTI_FIELD_MATCH`. |
| `NEEDS_CONFIRMATION` | A required fact is absent or ambiguous; purpose is generic/different; amount or chronology does not establish a match; or another root/draft is a plausible competitor. The accountant resolves only the remaining question. |
| `CONFLICT` | Employee or company contradicts the configured identity; the reference points to another activity; or the transaction is already owned by another root. A generic checkbox cannot remove the conflict. |

## Consequences

- TC01 can be tested on a newly proposed settlement root without seeding
  `TU-TC01` into a reference catalog or using a pre-created `activity:tc01`.
- Link decisions are deterministic code decisions over source-backed facts; no
  confidence score or model-generated relationship is accepted as proof.
- The purpose rule is intentionally conservative: exact normalized project-core
  equality with three discriminative tokens. It may request human review for
  paraphrases until a separately evidenced semantic matcher is approved.
- The transaction link and accountant's later financial confirmation are
  separate facts with separate audit and authority boundaries.
