import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { VerifyPanel } from './VerifyPanel';
import type { VerifyJob } from './types';

vi.mock('./api', () => ({
  startVerifyRun: vi.fn(),
  getVerifyRun: vi.fn(),
}));

import * as api from './api';

const mockReportJob: VerifyJob = {
  id: 'vjob-1',
  status: 'SUCCEEDED',
  completed_count: 3,
  total_count: 3,
  report: {
    id: 'report-1',
    mode: 'replay',
    metrics: {},
    results: [
      {
        case_id: 'case-pass-1',
        run_id: 'run-1',
        verdict: 'PASS',
        mode: 'replay',
        elapsed_ms: 120,
        expected: { action: 'CREATE_PAYMENT_REQUEST', owners: [], reason: 'ok' },
        actual: { action: 'CREATE_PAYMENT_REQUEST' },
        timestamp: '2026-10-06T00:00:00Z',
      },
      {
        case_id: 'case-fail-1',
        run_id: 'run-2',
        verdict: 'FAIL',
        mode: 'replay',
        elapsed_ms: 250,
        expected: { action: 'REQUEST_INFO', owners: ['REVIEWER'], reason: 'mismatch' },
        actual: { action: 'REJECT' },
        timestamp: '2026-10-06T00:00:00Z',
      },
      {
        case_id: 'case-pass-2',
        run_id: 'run-3',
        verdict: 'PASS',
        mode: 'replay',
        elapsed_ms: 180,
        expected: { action: 'CREATE_PAYMENT_REQUEST', owners: [], reason: 'ok' },
        actual: { action: 'CREATE_PAYMENT_REQUEST' },
        timestamp: '2026-10-06T00:00:00Z',
      },
    ],
  },
};

describe('VerifyPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders verify controls and suites', () => {
    render(<VerifyPanel />);
    expect(screen.getByRole('heading', { name: /bộ kiểm thử tự động \(verify\)/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /chạy core/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /chạy escalation/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /chạy tất cả/i })).toBeTruthy();
  });

  it('filters results by failed cases and search query', async () => {
    (api.startVerifyRun as ReturnType<typeof vi.fn>).mockResolvedValue(mockReportJob);
    (api.getVerifyRun as ReturnType<typeof vi.fn>).mockResolvedValue(mockReportJob);

    render(<VerifyPanel />);
    await userEvent.click(screen.getByRole('button', { name: /chạy core/i }));

    // Initially "Tất cả (3)" is active: all 3 cases visible
    expect(await screen.findByText('case-pass-1')).toBeTruthy();
    expect(screen.getByText('case-fail-1')).toBeTruthy();
    expect(screen.getByText('case-pass-2')).toBeTruthy();

    // Click filter "Chỉ ca Thất bại (1)"
    const failFilterBtn = screen.getByRole('button', { name: /chỉ ca thất bại/i });
    await userEvent.click(failFilterBtn);

    // Only case-fail-1 should be in the document
    expect(screen.getByText('case-fail-1')).toBeTruthy();
    expect(screen.queryByText('case-pass-1')).toBeNull();
    expect(screen.queryByText('case-pass-2')).toBeNull();

    // Search input filter
    const searchInput = screen.getByLabelText(/tìm theo mã case/i);
    await userEvent.type(searchInput, 'non-existent');
    expect(screen.getByText('Không tìm thấy kết quả phù hợp với bộ lọc.')).toBeTruthy();

    // Clear search
    await userEvent.clear(searchInput);
    expect(screen.getByText('case-fail-1')).toBeTruthy();
  });
});
