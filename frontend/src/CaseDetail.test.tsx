import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { CaseDetail } from './CaseDetail';
import { auditEvent, completedRun, needsInfoRun } from './testBuilders';

it('shows request creation separately from transfer', () => {
  render(<CaseDetail run={completedRun()} onStop={vi.fn()} />);
  expect(screen.getByText('Đã tạo đề nghị chi trả')).toBeTruthy();
  expect(screen.queryByText('Đã chuyển tiền')).toBeNull();
});

it('shows a Stop control only while a run is in flight', () => {
  const running = { ...completedRun(), status: 'RUNNING' as const, result: null };
  render(<CaseDetail run={running} onStop={vi.fn()} />);
  expect(screen.getByRole('button', { name: /dừng/i })).toBeTruthy();
});

it('renders a human question without a payment request', () => {
  const { container } = render(<CaseDetail run={needsInfoRun()} onStop={vi.fn()} />);
  const issue = container.querySelector('.issue');
  expect(issue?.textContent).toMatch(/chênh là khoản nào/);
  expect(screen.queryByText(/Đã tạo đề nghị chi trả/)).toBeNull();
});

it('shows the current pipeline stage while a run is in flight', () => {
  const running = { ...completedRun(), status: 'RUNNING' as const, stage: 'analyze:ev-1:before', result: null };
  render(<CaseDetail run={running} onStop={vi.fn()} />);
  expect(screen.getByText(/Đang trích xuất dữ kiện/)).toBeTruthy();
});

it('shows the audit timeline when history is provided', () => {
  render(
    <CaseDetail
      run={completedRun()}
      onStop={vi.fn()}
      history={[auditEvent({ kind: 'CASE_CREATED', reason: 'tao ho so' })]}
    />,
  );
  expect(screen.getByText(/Nhật ký kiểm toán/)).toBeTruthy();
  expect(screen.getByText('Tạo hồ sơ')).toBeTruthy();
});

it('shows source references for an issue', () => {
  const run = needsInfoRun();
  if (run.result) {
    run.result.decision.issues[0].refs = [
      { evidence_id: 'ev-1234567890', page_index: 0, block_id: 'b-1', locator: 'b-1-l6', raw_value: '20/09/2026' },
    ];
  }
  const { container } = render(<CaseDetail run={run} onStop={vi.fn()} />);
  const ref = container.querySelector('.source-refs');
  expect(ref?.textContent).toMatch(/b-1-l6/);
  expect(ref?.textContent).toMatch(/20\/09\/2026/);
});
