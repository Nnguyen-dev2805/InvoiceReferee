# InvoiceReferee — Design Thinking Research & Sprint 1 Improvement Review

**Date:** 2026-09-20  
**Scope:** Challenge A — Escalation Referee, Sprint 1  
**Purpose:** Critique the current solution objectively and redesign the problem-solving approach from user need through input, decision, human intervention, audit, and evaluation.

This document does not claim that the synthetic Policy v0 represents a real company policy or Vietnamese law. External references below are design and control practices, not legal conclusions.

## 1. Executive finding

The current project has a coherent technical pipeline, but its design rationale is still mostly **solution-first**:

```text
challenge requirements
→ policy and test cases
→ schemas and checks
→ UI and Verify
```

What is still missing is an evidence-backed human-centered chain:

```text
observe the real AP workflow
→ identify the actual decision bottleneck
→ define what must remain human-owned
→ model evidence and uncertainty
→ prototype the resolution experience
→ measure both benefit and new burden
```

The product should not be framed primarily as “AI that checks invoices.” A more defensible problem statement is:

> Accounts Payable needs to reach a defensible next action from fragmented transaction evidence without repeatedly reconstructing the whole case, while retaining accountability for exceptions and payment review.

The best Sprint 1 product is therefore an **evidence-backed exception referee**, not an autonomous accountant and not a general invoice chatbot.

## 2. What the research changes

### 2.1 Design Thinking is evidence gathering, not a five-step slide

Stanford d.school describes five common modes—Empathize, Define, Ideate, Prototype, Test—but warns against treating design as one fixed linear process. IDEO similarly frames human-centered design around learning directly from people, making ideas tangible, and iterating with feedback.

Implication for InvoiceReferee:

- Do not present `Empathize → Define → Ideate → Prototype → Test` as work completed unless there is evidence for each stage.
- Repository specifications and synthetic cases are not empathy evidence.
- A working prototype is useful only when it tests a named assumption.
- User feedback must change either the problem definition, interaction, policy representation, or measurement plan—not merely validate the existing solution.

Primary references:

- [Stanford d.school — Design Thinking Bootleg](https://dschool.stanford.edu/tools/design-thinking-bootleg)
- [Stanford d.school — How Might We Questions](https://dschool.stanford.edu/tools/how-might-we-questions)
- [IDEO Design Kit — Human-Centered Design](https://www.designkit.org/human-centered-design.html)
- [IDEO Design Kit — Interview](https://www.designkit.org/methods/2.html)
- [IDEO Design Kit — Rapid Prototyping](https://www.designkit.org/methods/rapid-prototyping.html)

### 2.2 The object being designed is a decision journey, not a document parser

Official Oracle and SAP documentation describes PO invoice processing as matching purchase order, receipt, and invoice facts within configured tolerances, with holds or exception reconciliation when facts do not agree. GAO guidance likewise emphasizes evidence of authorization, receipt/acceptance, invoice claim, duplicate controls, and separation of duties.

Implication:

- The central object is not `Invoice`; it is an **exception-resolution case** with linked evidence and ownership.
- Correct linkage is a prerequisite for comparison. A receipt belonging to another PO must never satisfy the current invoice.
- “Mismatch” should create a controlled exception or hold, not an accusation of fraud.
- Approval evidence must be bound to the exact PO, item, value, approver, status, and validity period it authorizes.
- Tolerances are policy configuration; exact equality is only one synthetic policy choice.

Primary references:

- [Oracle — Match Approval Level Options](https://docs.oracle.com/en/cloud/saas/procurement/25c/oapro/match-approval-level-options.html)
- [SAP — Blocking Invoices](https://help.sap.com/docs/PRODUCT_ID/af9ef57f504840d2b81be8667206d485/7870b6531de6b64ce10000000a174cb4.html)
- [SAP Ariba — Goods Receipt-Based Invoice Verification](https://help.sap.com/docs/buying-invoicing/invoicing-and-payment-process-guide/workflow-for-goods-receipt-based-invoice-verification-in-sap-ariba-buying-and-invoicing-aede7515ef3148f5a0f96e05d8670438)
- [GAO — Streamlining the Payment Process While Maintaining Effective Internal Control](https://www.gao.gov/assets/aimd-21.3.2.pdf)
- [GAO — The Green Book](https://www.gao.gov/greenbook)

### 2.3 Human oversight must be an operational role, not a button

NIST AI RMF asks teams to define human/AI roles, knowledge limits, oversight, feedback, measurement, and accountability throughout the lifecycle. Google PAIR recommends deciding explicitly between automation and augmentation, communicating limitations, supporting graceful failure, and giving users meaningful control.

Implication:

- “Human-in-the-loop” is incomplete unless the system defines who acts, what they see, what they can change, and what happens next.
- Stop, Override, Answer Request, Attach Evidence, and Approve Exception are different actions.
- The system should measure overrides, errors, response times, unresolved cases, and user burden.
- A generic explanation or confidence score does not establish accountability.

Primary references:

- [NIST — AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
- [NIST — AI RMF Playbook](https://airc.nist.gov/docs/AI_RMF_Playbook.pdf)
- [Google PAIR — User Needs and Defining Success](https://pair.withgoogle.com/chapter/user-needs/)
- [Google PAIR — Explainability and Trust](https://pair.withgoogle.com/chapter/explainability-trust)
- [Google PAIR — Feedback and Control](https://pair.withgoogle.com/chapter/feedback-controls/)
- [Google PAIR — Errors and Graceful Failure](https://pair.withgoogle.com/chapter/errors-failing/)

## 3. Proposed Design Thinking framing

### 3.1 Stakeholders to design with

| Role | Job in the workflow | Evidence they own | Risk if omitted |
| --- | --- | --- | --- |
| Accounts Payable reviewer | Decide the next safe processing step | Invoice, payment status, case history | Product optimizes checks but not daily review work |
| Procurement/Purchasing | Explain PO, vendor, item, and price changes | PO and amendment approval | Questions go to the wrong person |
| Receiver/Warehouse | Confirm delivery and quantities | Goods Receipt, returns, inspection state | Quantity logic uses incomplete or wrong receipts |
| Finance Manager/Approver | Decide beyond-authority exceptions | Approval, authority decision | Escalation is generated but not resolvable |
| Supplier | Correct invoice facts | Revised invoice/supporting documents | Requests are vague or disclose internal-only context |
| Internal audit/process owner | Reconstruct and test controls | Policy, logs, exception history | Audit becomes a UI table rather than evidence |

### 3.2 Research questions for three Sprint 1 interviews

Do not ask “Would you use this AI?” Ask about observed work:

1. Show me the last invoice that took unusually long. What made it hard?
2. Which documents or systems did you open, and in what order?
3. What facts make you comfortable moving a case forward?
4. When something is inconsistent, whom do you contact and what do you ask?
5. Which discrepancies are routine, and which require authority rather than more information?
6. What mistakes are costly enough that you always double-check them?
7. If a junior colleague handled this case, what evidence would you require in their explanation?
8. What part is repetitive but low-risk? What part must remain your responsibility?
9. What new burden would this tool create—extra checking, duplicate entry, interruptions, or loss of coordination?

Required evidence:

- direct quotes, not paraphrased approval;
- current workflow steps and approximate handling/waiting time;
- at least one real exception pattern per role;
- one observed negative effect or unresolved concern;
- consent and anonymization where required.

### 3.3 Current-state journey to validate

This is a hypothesis, not a claimed real workflow:

```text
Receive invoice
→ identify PO and supplier
→ locate receipt(s)
→ compare line items and totals
→ inspect previous invoices/payment state
→ search for amendment/approval
→ decide routine vs missing fact vs authority exception
→ contact the correct role
→ wait for response
→ reopen the case and reconstruct context
→ move to payment review or keep blocked
```

The likely bottleneck is not arithmetic. It is **reconstructing context and coordinating exception resolution** across evidence owners.

Use interviews and a journey map to test:

- time spent searching vs comparing vs waiting;
- number of document/system switches;
- repeated questions and reopened cases;
- handoff failures;
- cases where the reviewer cannot tell whether they need a fact or an approval.

Reference: [IDEO Design Kit — Journey Map](https://www.designkit.org/methods/journey-map.html)

### 3.4 Point of View and How Might We

Proposed Point of View:

> An AP reviewer handling many invoices needs a fast way to see whether the evidence supports the next processing step and who owns any unresolved exception, because reconstructing the transaction repeatedly is slow and makes accountability fragile.

Recommended HMW:

> How might we help an AP reviewer reach a defensible next action in under two minutes, without hiding missing evidence or taking away responsibility for exceptions and payment review?

Do not use a technology-first HMW such as “How might we use an LLM to automate invoice checking?” It presupposes both the solution and the role of AI.

## 4. End-to-end system design derived from the problem

### 4.1 Input should be an evidence contract, not a permissive dictionary

Each field needs more than a value:

```text
value
source document/reference
extraction method
parse status: PRESENT | MISSING | INVALID | AMBIGUOUS
verification status
confidence, only when produced by probabilistic extraction
```

The pipeline should preserve these distinctions:

```text
missing value       ≠ zero
invalid value       ≠ missing value
ambiguous extraction ≠ business mismatch
business mismatch   ≠ outside policy
```

Sprint 1 should reject malformed technical input separately and map valid business uncertainty to `REQUEST_INFO`.

### 4.2 Link evidence before running business checks

Add deterministic relationship validation:

- invoice `po_id` must equal the linked PO;
- every Goods Receipt used in matching must belong to that PO;
- prior invoices must be scoped to the same PO and stable invoice identity;
- payment records must bind to the current invoice;
- approvals must bind to the relevant PO/item/change/value;
- PO and receipt statuses must be usable under Policy v0.

If linkage is missing or conflicting, do not run a confident match and do not fill defaults that make comparisons pass.

### 4.3 Deterministic match engine should produce exception facts

Each check should return:

```text
check id
status: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
expected and actual facts
source references
policy/tolerance applied
exception owner
resolution evidence required
```

Checks should not merely state “mismatch.” They should identify the next resolvable fact, for example:

```text
CHECK_QUANTITY
received = 8
invoiced cumulative = 10
missing resolution evidence = additional receipt or approved quantity exception
owner = Warehouse / Procurement
```

### 4.4 Policy and authority are separate from matching

The current three-way match answers whether evidence agrees. Policy answers:

- whether this transaction type is supported;
- whether a variance can be tolerated;
- what approval is sufficient;
- which role can authorize an exception;
- whether the Agent may advance the case.

Keep Policy v0 synthetic and explicit. Do not present 50M VND, zero tolerance, or role names as industry or legal rules.

### 4.5 LLM should handle language and prioritization, not truth

The strongest Sprint 1 role for an LLM is narrow:

1. Explain verified facts in role-appropriate language.
2. Select one unresolved issue from an allow-listed set.
3. Generate a directly answerable question using exact values and evidence refs.
4. Summarize a human answer for re-evaluation, without directly changing facts.
5. Optionally map unstructured narrative into candidate fields that require confirmation.

Do not delegate to the LLM:

- money or quantity calculations;
- document linkage;
- duplicate identity;
- payment state;
- authority threshold;
- final action;
- approval creation;
- changing workflow state.

The LLM output contract must validate:

- proposed action against Guard outcome;
- `primary_check_id` exists **and is unresolved**;
- every policy rule ID exists in `PolicyContext`;
- every evidence ref exists and supports the cited check;
- a non-routine question contains the facts needed to answer it;
- no invented role, policy, approval, or source is accepted.

Because invoice text and uploaded documents are untrusted, document content must be isolated as data, not instructions. Schema validation and the deterministic Guard remain mandatory. These controls align with OWASP guidance on prompt injection, improper output handling, and excessive agency:

- [OWASP — Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [OWASP — Improper Output Handling](https://genai.owasp.org/llmrisk/llm052025-improper-output-handling/)
- [OWASP — Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)

### 4.6 Human interaction is a resolution loop

Replace the conceptual dead end:

```text
REQUEST_INFO → display question
```

with:

```text
REQUEST_INFO
→ owner answers or attaches evidence
→ system records actor/source/time
→ normalize and validate new evidence
→ rerun checks and Guard
→ preserve previous decision
→ issue the next decision
```

Define controls separately:

| Control | Meaning | Required result |
| --- | --- | --- |
| Stop | Pause workflow execution | Status changes; decision remains unchanged |
| Override | Human chooses a different effective action | Original and effective actions both visible |
| Answer request | Supply a missing fact | New evidence and re-evaluation |
| Approve exception | Exercise authority | Structured approval bound to the exception |
| Correct data | Fix extraction/linkage error | New version; old evidence remains traceable |

### 4.7 Audit should reconstruct a case, not only list events

One case history needs stable IDs across system and human actions. Every material event should retain:

- event ID and transaction ID;
- actor and role;
- timestamp;
- input/evidence refs;
- check/policy rule;
- previous state and new state;
- reason;
- LLM model/prompt/fallback where applicable;
- original Agent decision and current effective decision.

The judge-facing UI must expose these fields. Exporting a reduced table that removes actor, evidence refs, or details is not an adequate audit artifact.

## 5. Objective assessment of the current project

### 5.1 Problem-definition weaknesses

1. The primary persona and pain points are asserted in documents but not supported by observed user evidence.
2. The problem statement focuses on invoice review functionality rather than the cost of reconstructing and resolving exceptions.
3. There is no validated current-state journey, handoff map, waiting-time measurement, or evidence of which step causes the most burden.
4. Design Thinking artifacts are mostly absent: interview evidence, insight synthesis, competing concepts, tested assumptions, and iteration history.
5. The system risks demonstrating engineering completeness without demonstrating that it changes the right part of the work.

### 5.2 Input and evidence weaknesses confirmed by direct probes

The current implementation can return `AUTO_PROCESS` when:

- both PO and invoice vendor IDs are missing;
- all item IDs are missing;
- all quantities are missing;
- invoice number/series/tax code are missing;
- invoice date is invalid;
- invoice references a different PO;
- receipt belongs to a different PO;
- PO is `DRAFT` and receipt is `PENDING`.

Root issue: normalization converts several missing/invalid values to `""` or `0`, after which two invalid values can compare equal and pass.

This conflicts with the product’s own “unknown stays unknown” contract and is dangerous for the challenge’s unseen-input test.

### 5.3 Matching and approval weaknesses

1. PO/GR/invoice linkage is assumed from the supplied bundle instead of verified.
2. PO and receipt statuses are not enforced.
3. Quantity approval can resolve an overage without binding to the exact item/value.
4. Unit-price approval checks item identity but not whether `approved_value` equals the invoice value.
5. Prior invoice amounts that are unreadable can be omitted from cumulative calculations instead of making the result unknown.
6. Missing stable invoice identity can still pass duplicate checking.

### 5.4 LLM design weaknesses

1. The deterministic fallback already reproduces action and questions, so the unique value of the LLM is not yet demonstrated.
2. `policy_rule_ids` from the LLM are not validated.
3. `primary_check_id` only has to exist; it does not have to be unresolved.
4. Actual provider behavior is unverified in the current offline Verify run.
5. There is no prompt-injection test for untrusted invoice text.
6. There is no measured comparison of LLM question quality against deterministic templates or human-written questions.

For Sprint 1, do not add a larger agent framework. Either demonstrate that the LLM improves multi-issue triage/question quality, or describe it honestly as a replaceable communication layer protected by deterministic controls.

### 5.5 Human-control and audit weaknesses

1. Override creates a record but does not expose a distinct effective decision; the UI continues to display the original decision.
2. Human events are stored in a second `AuditStore`, causing duplicate event IDs when combined with review events.
3. The exported UI audit removes event ID, actor, input refs, and details.
4. `REQUEST_INFO` has no implemented answer/attach/re-evaluate loop.
5. Audit is in-memory and disappears outside the session; acceptable as a disclosed Sprint 1 limitation, not as production readiness.

### 5.6 Evaluation weaknesses

1. The 17 fixtures test known contracts well but are authored from the same policy and expected labels as the implementation design.
2. Current unseen tests mostly mutate valid fixtures; they do not stress malformed, contradictory, wrongly linked, or adversarial evidence.
3. Verify `all` repeats cases across Core and Escalation; 9 displayed rows do not represent 9 independent scenarios.
4. All current Verify evidence used deterministic fallback, not a real provider.
5. No real-user measurement exists yet.
6. README and Build Log report 181 tests while current execution reports 191.
7. A public Live URL is not documented in the repository.

## 6. Sprint 1 redesign: smallest credible vertical slice

### P0 — required before claiming robust unseen-input handling

1. **Fail-closed required-field validation**
   - Preserve missing/invalid critical fields as unknown.
   - Never convert absence to matching zero/empty defaults.
   - Add malformed-but-parseable business cases to Verify.

2. **Evidence linkage validation**
   - Validate PO IDs across invoice and receipts.
   - Exclude unrelated receipts/prior invoices/payment records.
   - Validate document status required by Policy v0.

3. **Approval binding**
   - Approval must match PO, item/change type, approved value/delta, status, and approver evidence.

4. **Coherent human decision state**
   - Preserve Agent decision separately from effective human decision.
   - Use one audit sequence/history for automated and human events.
   - Export full audit records.

5. **Strict LLM assessment validation**
   - Validate unresolved check, policy IDs, evidence refs, action compatibility, and question presence.

### P1 — improves the Design Thinking and judging story

1. Interview at least one AP reviewer, one Procurement/Receiver role, and one approver.
2. Create a current-state journey with handling time, waiting time, system switches, and repeated work.
3. Test a low-fidelity “exception card” before adding more backend features.
4. Implement one complete `REQUEST_INFO → answer/evidence → re-evaluate` journey.
5. Show an evidence comparison view instead of only a flat check table.
6. Add an explicit limitations/assumptions panel.
7. Record one product change caused by user evidence, not by developer preference.

### P2 — defer unless P0/P1 are complete

- OCR/PDF/image ingestion;
- RAG or vector database;
- multi-agent orchestration;
- learned escalation thresholds;
- broad service-invoice support;
- ERP/database integration;
- anomaly/fraud models;
- automatic payment or accounting entries.

## 7. Prototype plan for the remaining Sprint 1 story

Do not prototype the whole product again. Prototype the riskiest assumptions:

| Assumption | Cheapest prototype | Evidence of success |
| --- | --- | --- |
| Reviewer understands three actions | Paper/interactive decision cards | User predicts the next action without explanation from team |
| Question is directly answerable | Show five exception questions without source documents | Correct role can answer or identify the missing evidence immediately |
| Evidence comparison reduces reconstruction | Before/after timed task | Fewer document switches and no increase in missed discrepancies |
| Human control is clear | Role-play Stop vs Override vs Approve | User chooses the correct control and explains its effect |
| LLM adds value | Blind compare human/template/LLM questions | Users prefer LLM output for answerability without more hallucinated facts |
| Audit is reconstructable | Give audit export to another participant | They can explain what happened, on what evidence, and who changed the outcome |

Reference methods:

- [IDEO Design Kit — Role Play](https://www.designkit.org/methods/role-play.html)
- [IDEO Design Kit — Co-Creation Session](https://www.designkit.org/methods/co-creation-session.html)
- [IDEO Design Kit — Define Your Indicators](https://www.designkit.org/methods/define-your-indicators.html)

## 8. Measurement model

Do not optimize only for processing speed.

### Process indicators

- time to first defensible action;
- number of documents/systems opened;
- number of handoffs;
- time waiting for missing evidence;
- percentage of cases using fallback;
- LLM/Guard disagreement rate;
- percentage of questions answered without reopening the full file;
- override and correction rate.

### Outcome indicators

- missed-human-intervention rate;
- unnecessary-human-intervention rate;
- incorrect evidence-linkage rate;
- unresolved duplicate/payment-state rate;
- user ability to reconstruct the decision from audit;
- reviewer workload and interruption burden;
- evidence of automation bias or reduced peer coordination.

Use both quantitative and qualitative evidence. IDEO recommends separating process indicators (“implemented as planned?”) from outcome indicators (“achieving the intended result?”). NIST similarly emphasizes contextual testing, human feedback, oversight measurement, and tracking overrides/errors over time.

## 9. Recommended judge narrative

Avoid claiming:

> “We built an AI that automates invoice approval.”

Use:

> “We observed that the difficult part is not arithmetic; it is reconstructing transaction evidence and resolving exceptions with the right owner. InvoiceReferee deterministically links and checks evidence, uses an LLM only to communicate verified exceptions clearly, and keeps the final policy boundary and human authority outside the model. Sprint 1 demonstrates one narrow PO-goods workflow and exposes its limitations.”

The strongest demo sequence is:

1. routine case proceeds without human interruption;
2. malformed/wrongly linked evidence fails closed;
3. one factual unknown generates a specific question to the correct owner;
4. one authority case escalates with the exact policy boundary;
5. human supplies evidence or overrides;
6. complete audit reconstructs the original and effective decision;
7. Verify runs independent cases through the same production path.

## 10. Definition of Sprint 1 success

Sprint 1 is credible when:

- the system never turns absent/invalid evidence into a confident pass;
- document relationships are validated before matching;
- all arithmetic and authority decisions are deterministic;
- the LLM can only communicate or prioritize allow-listed verified issues;
- one complete human-resolution loop works;
- original and effective decisions remain reconstructable;
- Verify contains independent routine, factual-unknown, outside-policy, beyond-authority, malformed-input, and wrong-linkage cases;
- at least one design decision is supported by observed user evidence;
- limitations, synthetic policy, fallback use, and unverified claims are visible rather than hidden.

