// Synthetic fixtures for component tests. These build ledger-shaped records
// directly (no API call) so a test failure means the component is wrong, not
// that the fixture mirrored the backend.
import type { AuditEvent, CaseRecord, Decision, Issue, RunRecord } from './types';

export function routineDecision(): Decision {
  return {
    action: 'CREATE_PAYMENT_REQUEST',
    completion_basis: 'ROUTINE_AUTO',
    accepted_amount_vnd: 1_200_000,
    checks: [
      { rule_id: 'SRC-02', status: 'PASS', dependencies: [], refs: [], reason: 'Đủ trường bắt buộc', issue_ids: [] },
      { rule_id: 'AUTH-01', status: 'PASS', dependencies: [], refs: [], reason: 'Trong quyền tự động', issue_ids: [] },
    ],
    issues: [],
    reasons: ['Hồ sơ thường quy trong quyền tự động.'],
    technical_code: null,
  };
}

export function completedRun(): RunRecord {
  return {
    id: 'run-1',
    case_id: 'case-1',
    input_hash: 'abc123',
    case_version: 1,
    status: 'SUCCEEDED',
    stop_requested: false,
    stage: 'done',
    started_at: '2026-10-05T00:00:00+00:00',
    finished_at: '2026-10-05T00:00:01+00:00',
    policy_version: 'demo-expense-v0.1',
    threshold_version: 'threshold-b1-085',
    identities: [],
    result: {
      decision: routineDecision(),
      bundle: {},
      artifacts: ['raw-ocr.json'],
      identities: [],
      stage_durations_ms: { ocr: 120 },
      provider_calls: 1,
      repair_calls: 0,
    },
  };
}

export function humanIssue(): Issue {
  return {
    id: 'issue-1',
    stable_key: 'AMT-01:total',
    issue_class: 'FACTUAL_UNKNOWN',
    owner_mode: 'EMPLOYEE',
    question: 'Bill ghi 1.280.000đ, đề nghị 1.480.000đ. Phần 200.000đ chênh là khoản nào?',
    refs: [],
    blockers: ['AMT-01'],
    status: 'OPEN',
  };
}

export function infoDecision(): Decision {
  return {
    action: 'REQUEST_INFO',
    completion_basis: null,
    accepted_amount_vnd: null,
    checks: [],
    issues: [humanIssue()],
    reasons: ['Cần làm rõ phần chênh trước khi tạo đề nghị chi trả.'],
    technical_code: null,
  };
}

export function needsInfoRun(): RunRecord {
  const run = completedRun();
  run.result = run.result
    ? { ...run.result, decision: infoDecision() }
    : null;
  return run;
}

export function auditEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: 'evt-1',
    case_id: 'case-1',
    run_id: 'run-1',
    case_version: 1,
    timestamp: '2026-10-05T00:00:00+00:00',
    kind: 'CASE_CREATED',
    stage: 'created',
    reason: '',
    refs: [],
    payload: {},
    ...overrides,
  };
}

export function caseRecord(): CaseRecord {
  return {
    id: 'case-1',
    case_version: 1,
    claim: {
      employee_id: 'emp-1',
      profile: 'TRAVEL',
      purpose_type: 'BUSINESS',
      purpose: 'Công tác Hà Nội',
      trip: 'HN 01-02/10',
      requested_amount_vnd: 1_200_000,
      payer_type: 'PERSONAL',
      received_full: null,
    },
    current_run_id: 'run-1',
    workflow_state: 'REVIEWING',
    evidence: [],
  };
}
