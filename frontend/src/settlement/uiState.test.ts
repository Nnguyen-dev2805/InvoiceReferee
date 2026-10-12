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

  test('B3 draft with null trip fields says not-extracted, not employee omission', () => {
    // Extraction ran (report.b3 exists) but destination/purpose are null:
    // the UI must say the fields were NOT EXTRACTED from the document, not
    // imply the employee failed to declare them.
    const view = createCase();
    const run = createRun();
    const report = createReport(); // b3.intake.destination/purpose are null

    const summary = summarizeCase(view, run, report);
    expect(summary.description).toContain('Chưa trích được');
    expect(summary.description).toContain('từ tài liệu');
    expect(summary.description).not.toContain('thiếu');
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

  test('đã nhận ứng không bị report cũ đưa về chưa phê duyệt', () => {
    const base = createCase();
    const view = createCase({
      stage: 'AWAITING_WORK_SETTLEMENT',
      submission: { ...base.submission, form: { ...base.submission.form, confirmed: true } },
    });
    const baseReport = createReport();
    const report = createReport({ b3: { ...baseReport.b3!,
      intake: { ...baseReport.b3!.intake, confirmed: true } } });
    const summary = summarizeCase(view, createRun(), report,
      { role: 'EMPLOYEE', actorId: 'NV-01' });
    expect(summary.title).toBe('Đã nhận ứng — chờ nộp quyết toán');
    expect(summary.description).not.toContain('chưa phê duyệt');
    expect(summary.primaryTarget).toBe('prepare-settlement');
  });

  test('ứng đã duyệt nhưng chưa nhận đủ không nói đã nhận', () => {
    const view = createCase({
      stage: 'AWAITING_MONEY',
      b3_workflow: {
        status: 'APPROVED',
        presentation: null,
        decision: {
          id: 'D-1', case_id: 'C-01', kind: 'B3_ADVANCE', presentation_id: 'P-1',
          outcome: 'APPROVE', reason: 'ok', work_allowed: true, budget_vnd: 5_000_000,
          advance_vnd: 2_000_000, basis_report_id: 'R-01', basis_review_id: 'RV-1',
          basis_input_revision: 1, basis_control_epoch: 1, basis_signature: 's',
          context_signature: 'c', employee_ref: 'NV-01', work_ref: 'WORK-01',
          actor_id: 'APR-01', grant_ref: 'G-1', effective_at: '2026-10-10T09:00:00Z',
          created_at: '2026-10-10T09:00:00Z', idempotent_replay: false,
        },
        basis_current: true,
        decision_validity: 'VALID',
        blocked_reason: null,
        accountant_ref: 'ACC-01',
        approver_ref: 'APR-01',
        funding: {
          decision_id: 'D-1', approved_vnd: 2_000_000, recorded_received_vnd: null,
          fulfilled_vnd: null, remaining_vnd: null, pending_count: 0, unknown_count: 0,
          incidents: [], status: 'NOT_RECORDED', scope: 'DECISION', as_of: null,
        },
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'ACCOUNTANT', actorId: 'ACC-01' });
    expect(summary.title).toContain('chờ ghi nhận');
    expect(summary.title).not.toContain('Đã nhận');
    expect(summary.primaryTarget).toBe('advance-receipt');
  });

  test('report lịch sử không tạo current-success', () => {
    const view = createCase({
      current_run_id: 'R-02',
      stage: 'CHECKING',
      submission: {
        ...createCase().submission,
        form: { ...createCase().submission.form, confirmed: true },
      },
    });
    // report.run_id R-01 != current_run_id R-02 → historical.
    const report = createReport({ run_id: 'R-01' });
    const summary = summarizeCase(view, createRun({ id: 'R-02' }), report,
      { role: 'EMPLOYEE', actorId: 'NV-01' });
    expect(summary.title).not.toBe('Đủ thông tin để kế toán rà soát');
    expect(summary.title).toBe('Chưa kiểm tra hồ sơ');
  });

  test('ngữ cảnh công ty cũ chặn và hướng kế toán làm mới', () => {
    const view = createCase({
      job: 'B7',
      stage: 'CHECKING',
      linked_b7: {
        origin: { origin_case_id: 'C-00', employee_ref: 'NV-01', work_ref: 'WORK-01',
          created_at: '2026-10-10T09:00:00Z' },
        context_source_id: 'S-1', context_current: false, blocked_reasons: [],
        managed_advance_subtotal_vnd: 2_000_000,
      },
      b7_workflow: {
        status: 'NOT_PRESENTED', presentation: null, decision: null,
        basis_current: false, blocked_reasons: [], accountant_ref: 'ACC-01',
        approver_ref: 'APR-01',
      },
    });
    const summary = summarizeCase(view, null, null,
      { role: 'ACCOUNTANT', actorId: 'ACC-01' });
    expect(summary.title).toBe('Dữ liệu công ty đã cũ');
    expect(summary.primaryTarget).toBe('settlement-intake');
  });

  test('quyết toán đã duyệt chờ đối chiếu chi/thu', () => {
    const view = createCase({
      job: 'B7',
      stage: 'AWAITING_WORK_SETTLEMENT',
      linked_b7: {
        origin: { origin_case_id: 'C-00', employee_ref: 'NV-01', work_ref: 'WORK-01',
          created_at: '2026-10-10T09:00:00Z' },
        context_source_id: 'S-1', context_current: true, blocked_reasons: [],
        managed_advance_subtotal_vnd: 2_000_000,
      },
      b7_workflow: {
        status: 'APPROVED', presentation: null,
        decision: {
          id: 'D-7', case_id: 'C-01', kind: 'B7_SETTLEMENT', outcome: 'APPROVE',
          reason: 'ok', presentation_id: 'P-7', basis_report_id: 'R-7',
          basis_review_id: 'RV-7', employee_ref: 'NV-01', work_ref: 'WORK-01',
          actor_id: 'APR-01', effective_at: '2026-10-11T09:00:00Z',
          created_at: '2026-10-11T09:00:00Z', basis_input_revision: 1,
          control_epoch: 1, business_signature: 'b', parent_fingerprint: 'p',
          config_signature: 'c', authority_signature: 'a',
          target: { employee_cost_vnd: 5_000_000, total_work_cost_vnd: 5_000_000,
            budget_vnd: 5_000_000, signed_net_vnd: 3_000_000,
            direction: 'PAY_EMPLOYEE', amount_vnd: 3_000_000 },
          history_baseline: null, supersedes_decision_id: null,
          idempotent_replay: false,
        },
        basis_current: true, blocked_reasons: [], accountant_ref: 'ACC-01',
        approver_ref: 'APR-01',
        fulfillment: {
          decision_id: 'D-7', direction: 'PAY_EMPLOYEE', approved_vnd: 3_000_000,
          recorded_received_vnd: 0, fulfilled_vnd: 0, remaining_vnd: 3_000_000,
          known_remaining_vnd: 3_000_000, pending_count: 0, unknown_count: 0,
          incidents: [], status: 'PARTIAL', managed_scope: 'DECISION',
          as_of: '2026-10-11T09:00:00Z', knowledge_cutoff: '2026-10-11T09:00:00Z',
        },
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'ACCOUNTANT', actorId: 'ACC-01' });
    expect(summary.title).toBe('Quyết toán đã duyệt — chờ đối chiếu chi/thu');
    expect(summary.primaryTarget).toBe('settlement-receipt');
  });

  test('quyết toán cân bằng đủ điều kiện đóng', () => {
    const view = createCase({
      job: 'B7',
      stage: 'READY_TO_CLOSE',
      linked_b7: {
        origin: { origin_case_id: 'C-00', employee_ref: 'NV-01', work_ref: 'WORK-01',
          created_at: '2026-10-10T09:00:00Z' },
        context_source_id: 'S-1', context_current: true, blocked_reasons: [],
        managed_advance_subtotal_vnd: null,
      },
      b7_workflow: {
        status: 'APPROVED', presentation: null,
        decision: {
          id: 'D-7', case_id: 'C-01', kind: 'B7_SETTLEMENT', outcome: 'APPROVE',
          reason: 'ok', presentation_id: 'P-7', basis_report_id: 'R-7',
          basis_review_id: 'RV-7', employee_ref: 'NV-01', work_ref: 'WORK-01',
          actor_id: 'APR-01', effective_at: '2026-10-11T09:00:00Z',
          created_at: '2026-10-11T09:00:00Z', basis_input_revision: 1,
          control_epoch: 1, business_signature: 'b', parent_fingerprint: 'p',
          config_signature: 'c', authority_signature: 'a', target: null,
          history_baseline: null, supersedes_decision_id: null,
          idempotent_replay: false,
        },
        basis_current: true, blocked_reasons: [], accountant_ref: 'ACC-01',
        approver_ref: 'APR-01',
        fulfillment: {
          decision_id: 'D-7', direction: 'BALANCED', approved_vnd: 0,
          recorded_received_vnd: 0, fulfilled_vnd: 0, remaining_vnd: 0,
          known_remaining_vnd: 0, pending_count: 0, unknown_count: 0,
          incidents: [], status: 'BALANCED', managed_scope: 'DECISION',
          as_of: '2026-10-11T09:00:00Z', knowledge_cutoff: '2026-10-11T09:00:00Z',
        },
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'ACCOUNTANT', actorId: 'ACC-01' });
    expect(summary.title).toBe('Quyết toán đã đủ điều kiện đóng');
    expect(summary.primaryTarget).toBe('settlement-receipt');
  });

  test('đã đóng không bị report cũ hồi sinh tiến độ', () => {
    const view = createCase({
      stage: 'SETTLEMENT_CLOSED',
      submission: {
        ...createCase().submission,
        form: { ...createCase().submission.form, confirmed: true },
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'EMPLOYEE', actorId: 'NV-01' });
    expect(summary.title).toBe('Hồ sơ đã đóng');
  });

  test('Stop ưu tiên hơn mọi projection workflow', () => {
    const view = createCase({
      stop_active: true,
      stage: 'AWAITING_WORK_SETTLEMENT',
      b3_workflow: {
        status: 'APPROVED', presentation: null, decision: null,
        basis_current: true, decision_validity: 'VALID', blocked_reason: null,
        accountant_ref: 'ACC-01', approver_ref: 'APR-01',
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'EMPLOYEE', actorId: 'NV-01' });
    expect(summary.title).toBe('Hồ sơ đang tạm dừng xử lý');
    expect(summary.primaryTarget).toBeNull();
  });

  test('vai không phải owner không nhận CTA thao tác', () => {
    const view = createCase({
      stage: 'AWAITING_WORK_SETTLEMENT',
      submission: {
        ...createCase().submission,
        form: { ...createCase().submission.form, confirmed: true },
      },
    });
    const summary = summarizeCase(view, createRun(), createReport(),
      { role: 'APPROVER', actorId: 'APR-01' });
    expect(summary.title).toBe('Đã nhận ứng — chờ nộp quyết toán');
    expect(summary.primaryTarget).toBeNull();
    expect(summary.nextOwner).toBe('EMPLOYEE');
  });
});
