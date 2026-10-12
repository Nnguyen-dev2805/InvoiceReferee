import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

// Stub the API module so the app renders with a controlled policy state.
vi.mock('./api', () => ({
  ApiError: class ApiError extends Error {},
  getPolicy: vi.fn(),
  getCase: vi.fn(),
  getRun: vi.fn(),
  getPaymentRequest: vi.fn(),
  listCases: vi.fn(),
  createCase: vi.fn(),
  startRun: vi.fn(),
  sendAction: vi.fn(),
  stopRun: vi.fn(),
  startVerifyRun: vi.fn(),
  getVerifyRun: vi.fn(),
}));

import * as api from './api';
import { App } from './App';
import { caseRecord, needsInfoRun } from './testBuilders';

const activePolicy = {
  version: 'demo-expense-v0.1-proposed',
  origin: 'proposed',
  activation_id: 'act-1',
  active: true,
  currency: 'VND',
  auto_approval_max: 2_000_000,
  inventory_date_gap_days: 7,
  comparison_money_tolerance: '1',
  normalized_unit_price_tolerance: '0',
  word_review_threshold: '0.85',
  threshold_version: 'demo-expense-v0.1-proposed',
};

beforeEach(() => {
  vi.clearAllMocks();
  // App loads the case list on mount; default to empty unless a test overrides it.
  (api.listCases as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (api.getPolicy as ReturnType<typeof vi.fn>).mockResolvedValue(activePolicy);
});

it('shows the role selector with only the three demo roles', async () => {
  render(<App />);
  const select = (await screen.findByLabelText(/vai trò/i)) as HTMLSelectElement;
  const values = Array.from(select.options).map((o) => o.value);
  expect(values).toEqual(['EMPLOYEE', 'REVIEWER', 'APPROVER']);
});

it('has no manual policy-activation control', async () => {
  render(<App />);
  await screen.findByLabelText(/vai trò/i);
  expect(screen.queryByText(/chưa được kích hoạt/i)).toBeNull();
});

it('filters the inbox by the selected role', async () => {
  const reviewCase = caseRecord({ id: 'case-r', open_owner_modes: ['REVIEWER'] });
  (api.listCases as ReturnType<typeof vi.fn>).mockResolvedValue([reviewCase]);
  (api.getRun as ReturnType<typeof vi.fn>).mockResolvedValue(needsInfoRun());
  render(<App />);
  // Default role EMPLOYEE: the REVIEWER case is not in "Việc của tôi".
  expect(await screen.findByRole('heading', { name: /hộp thư việc — nhân viên/i })).toBeTruthy();
  await userEvent.selectOptions(screen.getByLabelText(/vai trò/i), 'REVIEWER');
  expect(await screen.findByRole('heading', { name: /hộp thư việc — kế toán/i })).toBeTruthy();
  expect(screen.getByText('Công tác Hà Nội')).toBeTruthy();
});

it('hides the submit form for non-employee roles', async () => {
  render(<App />);
  expect(await screen.findByRole('heading', { name: /nộp hồ sơ hoàn ứng/i })).toBeTruthy();
  await userEvent.selectOptions(screen.getByLabelText(/vai trò/i), 'APPROVER');
  expect(screen.queryByRole('heading', { name: /nộp hồ sơ hoàn ứng/i })).toBeNull();
});
