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
    ...overrides,
  };
}

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
