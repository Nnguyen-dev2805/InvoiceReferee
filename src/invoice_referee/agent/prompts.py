"""Prompt construction for the LLM Agent (prompt v1).

The LLM receives only normalized facts, check results and policy context. It must
not perform authoritative arithmetic or rewrite facts; it selects one valid
unresolved check and returns traceable references.
"""

from __future__ import annotations

import json

from invoice_referee.domain import models as m

PROMPT_VERSION = "v1"

_SYSTEM = """\
You are InvoiceReferee's assessment agent for PO-based goods-purchase invoices.
You DO NOT compute numbers, change facts, or decide the final action. Deterministic
rules already produced the check results and policy context below.

Return ONLY a JSON object with these keys:
  proposed_uncertainty_type: one of FACTUAL_UNKNOWN | OUTSIDE_POLICY | BEYOND_AUTHORITY | null
  proposed_action: one of AUTO_PROCESS | REQUEST_INFO | ESCALATE
  primary_check_id: the id of ONE unresolved (FAIL/UNKNOWN) check to ask about, or null
  explanation: one or two sentences grounded only in the given facts
  question: a specific, directly-answerable question (empty for AUTO_PROCESS)
  target: the role who can answer/approve, or null
  policy_rule_ids: list of policy rule ids you relied on (must exist in the input)
  evidence_refs: list of evidence ids you cited (must exist in the input)

Rules:
- primary_check_id, policy_rule_ids and evidence_refs must reference items present
  in the input. Do not invent new checks, rules or evidence.
- For multiple issues, choose the single most important unresolved check.
- Never propose AUTO_PROCESS when any required check is unresolved or the amount
  is beyond authority.
"""


def _check_payload(c: m.CheckResult) -> dict:
    return {
        "check_id": c.check_id,
        "status": c.status.value,
        "policy_rule_id": c.policy_rule_id,
        "expected": c.expected,
        "actual": c.actual,
        "reason": c.reason,
        "evidence_refs": c.evidence_refs,
    }


def build_prompt(
    tx: m.Transaction, checks: list[m.CheckResult], ctx: m.PolicyContext
) -> str:
    payload = {
        "transaction_id": tx.transaction_id,
        "transaction_type": tx.transaction_type.value if tx.transaction_type else None,
        "declared_transaction_type": tx.declared_transaction_type,
        "invoice_amount": tx.invoice.total_amount if tx.invoice else None,
        "po_approved_total": tx.po.approved_total if tx.po else None,
        "checks": [_check_payload(c) for c in checks],
        "policy_context": {
            "scope_status": ctx.scope_status.value,
            "authority_threshold_vnd": ctx.authority_threshold_vnd,
            "applicable_rule_ids": ctx.applicable_rule_ids,
        },
    }
    return _SYSTEM + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
