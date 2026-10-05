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
  createCase: vi.fn(),
  startRun: vi.fn(),
  sendAction: vi.fn(),
  stopRun: vi.fn(),
  activatePolicy: vi.fn(),
  startVerifyRun: vi.fn(),
  getVerifyRun: vi.fn(),
}));

import * as api from './api';
import { App } from './App';

const inactivePolicy = {
  version: 'demo-expense-v0.1-proposed',
  origin: 'proposed',
  activation_id: null,
  active: false,
  currency: 'VND',
  auto_approval_max: 2_000_000,
  standard_policy_max: 5_000_000,
  inventory_date_gap_days: 7,
  comparison_money_tolerance: '1',
  normalized_unit_price_tolerance: '0',
  word_review_threshold: '0.85',
  threshold_version: 'demo-expense-v0.1-proposed',
};

beforeEach(() => {
  vi.clearAllMocks();
});

it('shows a policy activation control before any run when policy is inactive', async () => {
  (api.getPolicy as ReturnType<typeof vi.fn>).mockResolvedValue(inactivePolicy);
  render(<App />);
  expect(await screen.findByText('Policy demo chưa được kích hoạt.')).toBeTruthy();
  expect(screen.getByRole('button', { name: /kích hoạt policy demo/i })).toBeTruthy();
});

it('requires a reason before activating', async () => {
  (api.getPolicy as ReturnType<typeof vi.fn>).mockResolvedValue(inactivePolicy);
  render(<App />);
  await screen.findByText('Policy demo chưa được kích hoạt.');
  await userEvent.click(screen.getByRole('button', { name: /kích hoạt policy demo/i }));
  expect(api.activatePolicy).not.toHaveBeenCalled();
  expect(screen.getByText(/cần lý do/i)).toBeTruthy();
});

it('hides the activation control once the policy is active', async () => {
  (api.getPolicy as ReturnType<typeof vi.fn>).mockResolvedValue({ ...inactivePolicy, active: true });
  render(<App />);
  await screen.findByText(/đã kích hoạt/);
  expect(screen.queryByText('Policy demo chưa được kích hoạt.')).toBeNull();
});
