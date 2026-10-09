import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, afterEach } from 'vitest';
import * as api from './api';
import { VerifyPanel } from './Verify';
import type { VerifySuiteReport } from './types';

function makeReport(): VerifySuiteReport {
  return {
    suite: 'settlement-dev-2',
    timestamp: '2026-10-09T16:00:00Z',
    mode: 'FAKE_OR_REPLAY',
    source_hash: 'a'.repeat(64),
    config_hash: 'b'.repeat(64),
    results: [
      {
        case_id: 'EP01', job: 'B7', phase: 'INITIAL',
        family_id: 'F', dataset_role: 'DEVELOPMENT_ONLY',
        verdict: 'PASS', checks: [
          { axis: 'money', expected: { s: 3000000 }, actual: { s: 3000000 },
            ok: true, note: '' },
        ],
        run_id: 'R-1', run_status: 'SUCCEEDED', mode: 'FAKE_OR_REPLAY',
        needs_resolution_expected: false, technical: false,
        first_pass_routine_expected: true, timestamp: '2026-10-09T16:00:00Z',
      },
      {
        case_id: 'EP02', job: 'B7', phase: 'INITIAL',
        family_id: 'F', dataset_role: 'DEVELOPMENT_ONLY',
        verdict: 'FAIL', checks: [
          { axis: 'money', expected: null, actual: null, ok: false,
            note: 'Expected không theo shape cố định nào (FLAT/VND/PARTIAL)' },
          { axis: 'completion', expected: 'COMPLETE, không issue',
            actual: 'INCOMPLETE+1', ok: false, note: 'issue thừa là FP' },
        ],
        run_id: 'R-2', run_status: 'SUCCEEDED', mode: 'FAKE_OR_REPLAY',
        needs_resolution_expected: false, technical: false,
        first_pass_routine_expected: true, timestamp: '2026-10-09T16:00:00Z',
      },
      {
        case_id: 'EP03', job: 'B7', phase: 'INITIAL',
        family_id: 'F', dataset_role: 'DEVELOPMENT_ONLY',
        verdict: 'INCONCLUSIVE', checks: [],
        run_id: 'R-3', run_status: 'TIMED_OUT', mode: 'UNKNOWN',
        needs_resolution_expected: true, technical: true,
        first_pass_routine_expected: null, timestamp: '2026-10-09T16:00:00Z',
      },
    ],
    metrics: {
      n_routine: 2, n_needs: 1, fn: 0, fp: 1,
      u_routine: 0, u_needs: 1,
      fn_interval: [0, 1], fp_interval: [0.5, 0.5],
      routine_completion: '0/2',
    },
    notes: ['Corpus DEVELOPMENT_ONLY … không phải holdout độc lập.'],
  };
}

afterEach(() => vi.restoreAllMocks());

test('chạy suite và hiển thị metrics, verdict, axis sai và trục kỹ thuật',
  async () => {
    const report = makeReport();
    const spy = vi.spyOn(api, 'runSettlementVerify')
      .mockResolvedValue(report);
    render(<VerifyPanel />);
    await userEvent.click(screen.getByRole('button', { name: /Chạy Verify/ }));
    expect(spy).toHaveBeenCalledWith(null);
    const metrics = screen.getByTestId('verify-metrics').textContent ?? '';
    expect(metrics).toContain('first-pass routine completion 0/2');
    expect(metrics).toContain('U_needs 1');
    const results = screen.getByTestId('verify-results').textContent ?? '';
    expect(results).toContain('EP01');
    expect(results).toContain('PASS');
    // case FAIL nêu axis sai, không chỉ verdict
    expect(results).toContain('completion');
    expect(results).toContain('INCOMPLETE+1');
    // INCONCLUSIVE là trục kỹ thuật riêng, không bị bỏ
    expect(results).toContain('TIMED_OUT');
    expect(screen.getAllByText(/không phải holdout độc lập/).length)
      .toBeGreaterThan(0);
  });

test('lỗi chạy suite hiển thị thông báo, không bịa kết quả', async () => {
  vi.spyOn(api, 'runSettlementVerify')
    .mockRejectedValue(new Error('DATASET_HASH_MISMATCH: hash lệch'));
  render(<VerifyPanel />);
  await userEvent.click(screen.getByRole('button', { name: /Chạy Verify/ }));
  expect(screen.getByRole('alert').textContent)
    .toContain('DATASET_HASH_MISMATCH');
  expect(screen.queryByTestId('verify-results')).toBeNull();
});
