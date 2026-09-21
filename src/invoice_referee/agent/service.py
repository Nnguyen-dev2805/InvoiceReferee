"""Agent service — produce a structured AgentAssessment.

Normal path: call the configured LLM client, parse and validate strict structured
output. On any failure (no client, provider error/timeout, invalid JSON, or
references that do not exist in the input) it returns a deterministic fallback
assessment with ``fallback_used=True``. The fallback proposes the policy-correct
action and a specific question so the pipeline stays safe and operational.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from invoice_referee.domain import models as m
from invoice_referee.agent import prompts
from invoice_referee.agent.llm_client import LLMClient, LLMError
from invoice_referee.policy import config
from invoice_referee.policy.engine import resolve_action
from invoice_referee.decision import fallback_questions


def _string_list(value: Any, field_name: str) -> list[str]:
    """Coerce a provider field to ``list[str]`` or raise ValueError.

    Providers occasionally emit a scalar or an object where a list is expected;
    a wrong type must degrade to the deterministic fallback, never crash.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be strings")
    return list(value)


def _optional_str(value: Any, field_name: str) -> Optional[str]:
    """Coerce a provider field to ``Optional[str]`` or raise ValueError."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    return value


def _valid_check_ids(checks: list[m.CheckResult]) -> set[str]:
    return {c.check_id for c in checks}


def _valid_evidence_ids(tx: m.Transaction, checks: list[m.CheckResult]) -> set[str]:
    ids: set[str] = set()
    if tx.po:
        ids.add(tx.po.po_id)
    for gr in tx.goods_receipts:
        ids.add(gr.receipt_id)
    if tx.invoice:
        ids.add(tx.invoice.invoice_id)
    for pi in tx.prior_invoices:
        ids.add(pi.invoice_id)
    for c in checks:
        ids.update(c.evidence_refs)
    return ids


def _extract_json_object(body: str) -> str:
    """Return the JSON object text from a model reply.

    Models often wrap JSON in ```json ... ``` fences or add a little prose. Strip
    fences and, failing that, slice from the first ``{`` to the last ``}`` so the
    normal LLM path is not forced into the fallback by cosmetic formatting.
    """
    text = body.strip()
    if text.startswith("```"):
        # Drop the opening fence line (``` or ```json) and any closing fence.
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_and_validate(
    body: str, tx: m.Transaction, checks: list[m.CheckResult], model: Optional[str], prompt_version: str
) -> m.AgentAssessment:
    """Parse strict structured output. Raises ValueError if invalid/untraceable."""
    data = json.loads(_extract_json_object(body))
    if not isinstance(data, dict):
        raise ValueError("assessment is not a JSON object")

    action = m.DecisionAction(data["proposed_action"])
    raw_uncertainty = data.get("proposed_uncertainty_type")
    uncertainty = m.UncertaintyType(raw_uncertainty) if raw_uncertainty else None

    primary = data.get("primary_check_id")
    if primary is not None and primary not in _valid_check_ids(checks):
        raise ValueError(f"primary_check_id {primary} not in checks")

    evidence_refs = _string_list(data.get("evidence_refs"), "evidence_refs")
    valid_evidence = _valid_evidence_ids(tx, checks)
    for ref in evidence_refs:
        if ref not in valid_evidence:
            raise ValueError(f"evidence_ref {ref} not present in input")

    explanation = data.get("explanation")
    if not explanation:
        raise ValueError("explanation is required")

    question = _optional_str(data.get("question"), "question")
    target = _optional_str(data.get("target"), "target")
    policy_rule_ids = _string_list(data.get("policy_rule_ids"), "policy_rule_ids")
    unknown_rules = [r for r in policy_rule_ids if r not in config.POLICY_RULES]
    if unknown_rules:
        raise ValueError(f"policy_rule_ids {unknown_rules} are not known policy rules")

    return m.AgentAssessment(
        proposed_uncertainty_type=uncertainty,
        proposed_action=action,
        explanation=explanation,
        primary_check_id=primary,
        question=question,
        target=target,
        policy_rule_ids=policy_rule_ids,
        evidence_refs=list(evidence_refs),
        model=model,
        prompt_version=prompt_version,
        fallback_used=False,
    )


def _fallback_assessment(
    tx: m.Transaction, checks: list[m.CheckResult], ctx: m.PolicyContext, prompt_version: str
) -> m.AgentAssessment:
    outcome = resolve_action(tx, checks, ctx)
    question = fallback_questions.build_question(outcome, tx, checks)
    return m.AgentAssessment(
        proposed_uncertainty_type=outcome.uncertainty_type,
        proposed_action=outcome.action,
        explanation=outcome.reason,
        primary_check_id=outcome.primary_check_id,
        question=question or None,
        target=outcome.target,
        policy_rule_ids=list(outcome.policy_rule_ids),
        evidence_refs=[c.evidence_refs[0] for c in checks if c.evidence_refs][:1],
        model=None,
        prompt_version=prompt_version,
        fallback_used=True,
    )


def assess(
    tx: m.Transaction,
    checks: list[m.CheckResult],
    ctx: m.PolicyContext,
    client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    prompt_version: str = prompts.PROMPT_VERSION,
) -> m.AgentAssessment:
    if client is None:
        return _fallback_assessment(tx, checks, ctx, prompt_version)

    prompt = prompts.build_prompt(tx, checks, ctx)
    try:
        body = client.complete(prompt)
        return _parse_and_validate(body, tx, checks, model, prompt_version)
    except (LLMError, ValueError, KeyError, json.JSONDecodeError):
        return _fallback_assessment(tx, checks, ctx, prompt_version)
