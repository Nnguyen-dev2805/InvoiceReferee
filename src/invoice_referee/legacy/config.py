"""Policy config loading, explicit demo activation, and snapshot hashing (T01).

Design rulings (recorded at T01):

- ``config/demo-policy.json`` holds the PROPOSED rulebook values
  (2,000,000 / 5,000,000 / 7 days / tolerances / 0.85) but starts **inactive**
  (``active=false``, ``origin='proposed'``). Proposed demo parameters are not
  active company policy.
- ``activate_demo_policy`` is the only path to an active demo policy: it returns
  a NEW config with ``active=true``, a fresh UUID ``activation_id``, and
  ``origin='developer_activated_demo'``. Runtime does not implicitly activate a
  fixture; T09 persists the activation event.
- ``snapshot_hash`` is SHA256 over canonical (sorted-key, compact) JSON of the
  snapshot with ``input_hash`` excluded, so the same logical snapshot always
  hashes identically.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from invoice_referee.domain.models import CaseSnapshot, DomainError, PolicyConfig

DEMO_ACTIVATED_ORIGIN = 'developer_activated_demo'


def load_policy(path: Path) -> PolicyConfig:
    """Load and validate a policy config file (does not activate it)."""
    raw = Path(path).read_text(encoding='utf-8')
    return PolicyConfig.model_validate_json(raw)


def activate_demo_policy(policy: PolicyConfig, reason: str) -> PolicyConfig:
    """Return a new, active demo policy with a recorded activation identity.

    The original ``policy`` is not mutated (records are frozen). A non-empty
    reason is required; blank reasons are rejected as invalid input.
    """
    if not reason or not reason.strip():
        raise DomainError('INVALID_INPUT', 'Cần lý do để kích hoạt policy demo.')
    return policy.model_copy(
        update={
            'active': True,
            'activation_id': str(uuid.uuid4()),
            'origin': DEMO_ACTIVATED_ORIGIN,
        }
    )


def snapshot_hash(snapshot: CaseSnapshot) -> str:
    """SHA256 of the canonical snapshot payload, excluding ``input_hash`` itself."""
    payload = snapshot.model_dump(mode='json', exclude={'input_hash'})
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
