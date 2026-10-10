import { describe, expect, test } from 'vitest';
import { summarizeCase } from './uiState';
import type { CaseView, Report, RunView } from './types';

function createCase(overrides?: Partial<CaseView>): CaseView {
  return {
    id: 'C-01',
    job: 'B3',
    case_version: 1,
    input_revision: 1,
    control_epoch: 1,
    stop_active: false,
    stage: 'CHECKING',
    current_run_id: 'R-01',
    submission: {
      employee_ref: 'NV-01',
      work_ref: 'WORK-01',
      job: 'B3',
      money_as_of: '2026-10-10T09:00:00Z',
      knowledge_cutoff: '2026-10-10T09:00:00Z',
      form: {
        confirmed: false,
        destination: null,
        purpose: null,
        request_amount_vnd: 2_000_000,
        settlement_due: '2026-10-16',
      },
    },
    sources: [],
    allowed_actions: [],
    money_summary: {
      approved_vnd: null,
      received_vnd: null,
      remaining_vnd: null,
      pending_events: 0,
      incidents: [],
    },
    created_at: '2026-10-10T09:00:00Z',
    updated_at: '2026-10-10T09:00:00Z',
    ...overrides,
  };
}

function createRun(overrides?: Partial<RunView>): RunView {
  return {
    id: 'R-01',
    case_id: 'C-01',
    status: 'SUCCEEDED',
    mode: 'FAKE_OR_REPLAY',
    input_revision: 1,
    control_epoch: 1,
    stage: null,
    created_at: '2026-10-10T09:00:00Z',
    updated_at: '2026-10-10T09:00:00Z',
    detail: null,
    completion: 'COMPLETE',
    trace: [],
    idempotent_replay: false,
    ...overrides,
  };
}

function createReport(overrides?: Partial<Report>): Report {
  return {
    run_id: 'R-01',
    job: 'B3',
    completion: 'COMPLETE',
    mode: 'FAKE_OR_REPLAY',
    generated_at: '2026-10-10T09:00:00Z',
    components: {
      t: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      b: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      e: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      a: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      ra: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      p: { value: null, state: 'NOT_APPLICABLE', refs: [] },
      rp: { value: null, state: 'NOT_APPLICABLE', refs: [] },
    },
    calculated_net_vnd: null,
    proposed_net_vnd: null,
    direction: null,
    conditional_results: [],
    expense_rows: [],
    checks: [],
    issues: [],
    critical_facts: [],
    links: [],
    b3: {
      readiness: 'READY_FOR_ACCOUNTANT_REVIEW',
      intake: {
        schema_version: 'b3-intake-v1',
        intake_method: 'IMPORT',
        confirmed: false,
        destination: null,
        trip_start: null,
        trip_end: null,
        purpose: null,
        assignment_note: null,
        request_amount_vnd: 2_000_000,
        settlement_due: '2026-10-16',
        estimate_rows: [],
      },
      forecast_company_vnd: 3_000_000,
      forecast_employee_vnd: 5_000_000,
      forecast_total_vnd: 8_000_000,
      work_permission: 'PENDING_DECISION',
      advance_approval: 'PENDING_DECISION',
      accountant_ref: 'ACC-01',
      approver_ref: 'APR-01',
      field_refs: {},
    },
    next_step: 'chờ rà soát',
    source_refs: [],
    ...overrides,
  };
}

describe('uiState - summarizeCase', () => {
  test('B3 draft unconfirmed identifies missing fields and directs to draft editor', () => {
    const view = createCase();
    const run = createRun();
    const report = createReport();

    const summary = summarizeCase(view, run, report);
    expect(summary.title).toBe('Kiểm tra bản nháp trước khi gửi');
    expect(summary.missingFields).toEqual(['Nơi đến', 'Mục đích công tác']);
    expect(summary.primaryTarget).toBe('draft-editor');
    expect(summary.tone).toBe('warning');
  });

  test('stopped case prioritizes Stop status', () => {
    const view = createCase({ stop_active: true });
    const run = createRun();
    const report = createReport();

    const summary = summarizeCase(view, run, report);
    expect(summary.title).toBe('Hồ sơ đang tạm dừng xử lý');
    expect(summary.tone).toBe('warning');
    expect(summary.primaryTarget).toBeNull();
  });

  test('run failure points to run check retry', () => {
    const view = createCase();
    const run = createRun({ status: 'FAILED' });

    const summary = summarizeCase(view, run, null);
    expect(summary.title).toBe('Chưa kiểm tra xong do lỗi xử lý');
    expect(summary.tone).toBe('error');
    expect(summary.primaryTarget).toBe('run-check');
  });

  test('check UNRESOLVED with issues empty warns that items need verification', () => {
    const view = createCase({
      submission: {
        ...createCase().submission,
        form: { ...createCase().submission.form, confirmed: true },
      },
    });
    const run = createRun();
    const report = createReport({
      checks: [
        {
          rule: 'trip_context',
          status: 'UNRESOLVED',
          refs: [],
          reason: 'Chưa đủ căn cứ nơi đến',
        },
      ],
      issues: [],
    });

    const summary = summarizeCase(view, run, report);
    expect(summary.title).toBe('Kết quả còn điểm cần kiểm tra');
    expect(summary.tone).toBe('warning');
    expect(summary.primaryTarget).toBe('issues');
  });

  test('ready for review states ready without claiming approved', () => {
    const view = createCase({
      submission: {
        ...createCase().submission,
        form: { ...createCase().submission.form, confirmed: true },
      },
    });
    const run = createRun();
    const report = createReport({
      checks: [
        {
          rule: 'trip_context',
          status: 'PASS',
          refs: [],
          reason: 'Đủ nơi đến',
        },
      ],
      issues: [],
    });

    const summary = summarizeCase(view, run, report);
    expect(summary.title).toBe('Đủ thông tin để kế toán rà soát');
    expect(summary.tone).toBe('info');
    expect(summary.primaryTarget).toBeNull();
  });
});
