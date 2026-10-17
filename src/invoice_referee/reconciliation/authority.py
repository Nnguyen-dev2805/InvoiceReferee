"""Pure per-action authority decision checks. No global grant mutation."""
from __future__ import annotations
import hashlib
import json

def fingerprint(value):
    if hasattr(value,"model_dump"):value=value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),default=str).encode()).hexdigest()

def authorization_basis(input,action):
    cost={"scope":input.scope.model_dump(mode="json"),"expenses":[e.model_dump(mode="json",exclude={"incurred_at"})for e in input.expense_facts],"policy":[p.model_dump(mode="json")for p in input.policy],"category":[p.model_dump(mode="json")for p in input.category_policy],"epoch":input.read_set.control_epoch}
    if action in ("ISSUE_PAYMENT","ISSUE_COLLECTION"):
        # Confirmed instruction-bound receipts fulfill the approved obligation;
        # they do not authorize a new obligation or change cost recognition.
        cost["obligation_events"]=[e.model_dump(mode="json",exclude={"event_at","recorded_at"})for e in input.ledger if not (e.kind in ("REIMBURSEMENT_RECEIVED","EMPLOYEE_RETURN") and e.instruction_id)]
    return fingerprint(cost)

def grants_for(input,actor,action,amount=None):
    return tuple(g for g in input.grants if g.actor==actor and action in g.actions and g.scope in (input.scope.activity,input.scope.tenant) and (not g.allowed_profiles or input.scope.profile in g.allowed_profiles) and g.effective_from<=input.as_of and (g.effective_to is None or input.as_of<=g.effective_to) and (amount is None or amount<=g.max_amount))

def approved(input,action,amount):
    for decision in reversed(input.authorizations):
        if decision.action!=action or decision.activity!=input.scope.activity or decision.amount<amount or decision.basis!=authorization_basis(input,action):continue
        for grant in input.grants:
            if grant.id!=decision.grant_ref or fingerprint(grant)!=decision.grant_fingerprint or grant.actor!=decision.actor or action not in grant.actions or grant.scope not in (input.scope.activity,input.scope.tenant) or (grant.allowed_profiles and input.scope.profile not in grant.allowed_profiles) or amount>grant.max_amount:
                continue
            valid_at_decision=grant.effective_from<=decision.decided_at and (grant.effective_to is None or decision.decided_at<=grant.effective_to)
            current=grant.effective_from<=input.as_of and (grant.effective_to is None or input.as_of<=grant.effective_to)
            # Natural expiry does not erase authority for an already issued,
            # unchanged obligation. Deleted/revised grants still fail fingerprint.
            issued=decision.issued_at is not None and decision.decided_at<=decision.issued_at and (grant.effective_to is None or decision.issued_at<=grant.effective_to)
            remaining_covers=action=="RECOGNIZE_COST" or (decision.remaining_issued is not None and amount<=decision.remaining_issued)
            if valid_at_decision and (current or (issued and remaining_covers)):
                return decision
    return None
