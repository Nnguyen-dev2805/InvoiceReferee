import { render, screen } from '@testing-library/react';
import { ReportPanel } from './Report';
import type { Report } from './types';

function slot(value: number | null, state: Report['components']['t']['state'],
              refs: string[] = []) {
  return { value, state, refs };
}

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    run_id: 'R-test01',
    job: 'B7',
    completion: 'INCOMPLETE',
    mode: 'FAKE_OR_REPLAY',
    generated_at: '2026-10-09T12:00:00+00:00',
    components: {
      t: slot(5_000_000, 'KNOWN', ['EXP-1']),
      b: slot(8_000_000, 'KNOWN', ['S-budget']),
      e: slot(5_000_000, 'KNOWN', ['EXP-1']),
      a: slot(null, 'UNKNOWN', []),
      ra: slot(0, 'KNOWN', ['S-history']),
      p: slot(0, 'KNOWN', ['S-history']),
      rp: slot(0, 'KNOWN', ['S-history']),
    },
    calculated_net_vnd: null,
    proposed_net_vnd: null,
    direction: null,
    conditional_results: [],
    expense_rows: [{
      expense_id: 'EXP-1',
      claimed_amount_vnd: 5_000_000,
      eligible_employee_vnd: 5_000_000,
      company_direct_vnd: 0,
      state: 'ELIGIBLE',
      refs: ['F1', 'S-bill'],
      reason: 'đủ căn cứ',
    }],
    checks: [{ rule: 'history_coverage', status: 'UNRESOLVED', refs: [], reason: 'thiếu A' }],
    issues: [{
      issue_id: 'I-HISTORY',
      type: 'FACT',
      owner: 'ACCOUNTANT',
      message: 'Thiếu lịch sử advance trong scope.',
      refs: ['S-history'],
      blocked: 'net',
      unresolved: true,
    }],
    next_step: 'Xử lý issue rồi chạy lại.',
    source_refs: ['S-bill', 'S-history', 'S-budget'],
    critical_facts: [],
    links: [],
    b3: null,
    ...overrides,
  };
}

test('chiều thu hiển thị khi S âm và mâu thuẫn fact không bị giấu', () => {
  render(<ReportPanel report={makeReport({
    completion: 'INCOMPLETE',
    calculated_net_vnd: -700_000,
    direction: 'EMPLOYEE_TO_COMPANY',
    critical_facts: [{
      key: 'history.advance.received', value: null, state: 'CONTRADICTED',
      refs: ['S-history'],
    }],
    links: [{
      relation_id: 'R1', kind: 'EXPENSE_PAYMENT', from_id: 'EXP-1',
      to_id: 'PAY-1', portion_vnd: null, status: 'PROPOSED',
    }],
  })} />);
  const panel = screen.getByTestId('report-panel');
  expect(panel.textContent).toContain('nhân viên hoàn lại công ty');
  const facts = screen.getByTestId('critical-facts').textContent ?? '';
  expect(facts).toContain('MÂU THUẪN');
  const links = screen.getByTestId('report-links').textContent ?? '';
  expect(links).toContain('PROPOSED');
  expect(links).toContain('chưa dùng làm căn cứ tiền');
});

test('hiển thị components, unknown giữ "—" không phải 0', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/A — ứng đã thực nhận/)).toBeTruthy();
  const reportPanel = screen.getByTestId('report-panel');
  expect(reportPanel.textContent).toContain('5.000.000 VND');
  expect(reportPanel.textContent).not.toContain('A — ứng đã thực nhận 0');
});

test('nhãn FAKE_OR_REPLAY hiển thị rõ là reader giả lập', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/FAKE_OR_REPLAY — reader giả lập\/offline/)).toBeTruthy();
});

test('issue nêu đúng owner kế toán và refs mở được nguồn', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/Kế toán: Thiếu lịch sử advance trong scope/)).toBeTruthy();
  const links = screen.getAllByRole('link', { name: 'S-history' });
  expect(links.length).toBeGreaterThan(0);
  expect(links[0].getAttribute('href')).toBe('/api/sources/S-history/content');
});

test('proposed khác calculated: proposed null giữ "—"', () => {
  render(<ReportPanel report={makeReport({
    calculated_net_vnd: 3_000_000,
    proposed_net_vnd: null,
  })} />);
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Calculated:');
  expect(text).toContain('3.000.000 VND');
  expect(text).toContain('Proposed (chưa duyệt, chưa chi): —');
});

// --- B3 v1 proposal (Task 4) ---------------------------------------------------

function makeB3Report(): Report {
  return makeReport({
    job: 'B3',
    b3: {
      readiness: 'READY_FOR_ACCOUNTANT_REVIEW',
      intake: {
        schema_version: 'b3-intake-v1',
        intake_method: 'WEB',
        confirmed: true,
        destination: 'Hà Nội',
        trip_start: '2026-10-12',
        trip_end: '2026-10-13',
        purpose: 'Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án.',
        assignment_note: null,
        request_amount_vnd: 2_000_000,
        settlement_due: '2026-10-16',
        estimate_rows: [
          {row_id: 'flight', description: 'Vé máy bay khứ hồi', basis: '1 vé',
           company_vnd: 3_000_000, employee_vnd: 0},
          {row_id: 'hotel', description: 'Khách sạn', basis: '1 đêm',
           company_vnd: 0, employee_vnd: 3_000_000},
        ],
      },
      forecast_company_vnd: 3_000_000,
      forecast_employee_vnd: 5_000_000,
      forecast_total_vnd: 8_000_000,
      work_permission: 'PENDING_DECISION',
      advance_approval: 'PENDING_DECISION',
      accountant_ref: 'ACC-DEMO-01',
      approver_ref: 'APR-DEMO-01',
      field_refs: {request_amount_vnd: ['form:1:request_amount_vnd']},
    },
  });
}

test('report B3 dùng section proposal, không dùng bảng S; pending không là issue', () => {
  render(<ReportPanel report={makeB3Report()} />);
  expect(screen.queryByText(/S = E/)).not.toBeInTheDocument();
  expect(screen.getAllByText(/Đang chờ quyết định/).length).toBeGreaterThan(0);
  expect(screen.getByText(/2[.,]000[.,]000/)).toBeInTheDocument();
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Tổng dự toán');
  expect(text).toContain('8.000.000 VND');
  expect(text).toContain('kế toán ACC-DEMO-01');
  expect(text).toContain('người duyệt APR-DEMO-01');
  expect(text).toContain('dự toán không phải ngân sách đã duyệt');
  expect(text).toContain('Complete nghĩa là đủ căn cứ rà soát, không nghĩa đã duyệt');
});

test('report B3 với company context hiển thị grants/coverage và nhãn mô phỏng', () => {
  render(<ReportPanel report={makeB3Report()} b3Context={{
    version: 'synthetic-verbal-v2',
    synthetic: true,
    demo_clock: '2026-10-10T09:00:00+07:00',
    grants: [{
      actor_ref: 'APR-DEMO-01', employee_ref: 'NV-DEMO-01', work_ref: null,
      allow_work: true, max_budget_vnd: 10_000_000,
      max_advance_vnd: 5_000_000,
      effective_from: '2026-10-01T00:00:00+07:00',
      effective_to: '2026-10-31T23:59:59+07:00',
      ref: 'company:grant-01',
    }],
    coverage: [{
      employee_ref: 'NV-DEMO-01', work_ref: null,
      from: '2026-10-01T00:00:00+07:00', to: '2026-10-10T09:00:00+07:00',
      complete_prior_history: true, groups: ['ADVANCE'], methods: ['CASH'],
      missing_ranges: [], owner_ref: 'ACC-DEMO-01',
      origin: 'synthetic register', ref: 'company:coverage-01',
    }],
    history: [],
  }} />);
  const context = screen.getByTestId('b3-run-context').textContent ?? '';
  expect(context).toContain('company:grant-01');
  expect(context).toContain('mô phỏng');
  expect(context).toContain('gồm mở sổ/tồn trước kỳ');
  expect(context).toContain('Lịch sử company-side: trống');
});

test('report B7 không có section B3 proposal', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.queryByTestId('b3-proposal')).not.toBeInTheDocument();
  expect(screen.getByText(/S = E/)).toBeInTheDocument();
});
