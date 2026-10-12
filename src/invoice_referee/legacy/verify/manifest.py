"""Verify manifest models (T11, master ledger).

A manifest is the frozen, content-addressed description of one suite: the cases,
their synthetic uploads, the expected business outcome, and the replay artifacts
(OCR + analyzed document + registry) used to drive the real pipeline without a
network call. The manifest hash excludes itself so the hash is stable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from invoice_referee.domain.models import Claim

EvaluationMode = Literal['POLICY_REPLAY', 'PIPELINE_FAKE_OR_REPLAY', 'LIVE_END_TO_END']
Verdict = Literal['PASS', 'FAIL', 'INCONCLUSIVE']


class _Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class FixtureUpload(_Record):
    path: str
    sha256: str
    role: str
    mime: str


class ExpectedOutcome(_Record):
    execution_status: str
    action: str
    completion_basis: str | None
    issue_classes: list[str]
    owners: list[str]
    required_rules: list[str]
    amount_vnd: int | None
    request_count: int
    reason: str


class VerifyCase(_Record):
    id: str
    description: str
    provenance: str
    claim: Claim
    uploads: list[FixtureUpload]
    mode: EvaluationMode
    policy_version: str
    expected: ExpectedOutcome
    reference_date: date
    raw_ground_truth_path: str
    replay_artifacts: dict[str, str]


class VerifyManifest(_Record):
    version: str
    suite: str
    mode: EvaluationMode
    policy_version: str
    cases: list[VerifyCase]
    sha256: str = ''

    def content_hash(self) -> str:
        payload = self.model_dump(mode='json', exclude={'sha256'})
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


class VerifyResult(_Record):
    case_id: str
    run_id: str | None
    input_hash: str | None
    timestamp: datetime
    expected: ExpectedOutcome
    actual: dict
    verdict: Verdict
    mode: EvaluationMode
    elapsed_ms: int
    trace_path: str | None


class VerifyReport(_Record):
    id: str
    manifest_hash: str
    policy_version: str
    threshold_version: str
    mode: EvaluationMode
    results: list[VerifyResult]
    metrics: dict
    started_at: datetime
    finished_at: datetime


class VerifyJob(_Record):
    id: str
    status: str
    completed_count: int
    total_count: int
    report: VerifyReport | None


def load_manifest(path: Path) -> VerifyManifest:
    """Load and validate a manifest from JSON, verifying its content hash."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    manifest = VerifyManifest.model_validate(data)
    expected = manifest.content_hash()
    if manifest.sha256 and manifest.sha256 != expected:
        raise ValueError(f'Manifest hash mismatch: {manifest.sha256} != {expected}')
    return manifest.model_copy(update={'sha256': expected})
