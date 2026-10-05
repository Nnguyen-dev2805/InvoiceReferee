import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { CaseDetail } from './CaseDetail';
import { completedRun, needsInfoRun } from './testBuilders';

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
