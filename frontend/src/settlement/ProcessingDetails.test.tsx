import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ProcessingDetails } from './ProcessingDetails';
import type { RunView } from './types';

const RUN: RunView = {
  id: 'R-01', case_id: 'C-01', status: 'SUCCEEDED', mode: 'FAKE_OR_REPLAY',
  input_revision: 1, control_epoch: 1, stage: 'read',
  created_at: '2026-10-10T02:00:00Z', updated_at: '2026-10-10T02:00:00Z',
  detail: null, completion: 'COMPLETE', trace: [], idempotent_replay: false,
};

test('không có run thì không render', () => {
  const { container } = render(<ProcessingDetails run={null} report={null} />);
  expect(container.firstChild).toBeNull();
});

test('raw run id/status/stage nằm trong details truy vết', () => {
  render(<ProcessingDetails run={RUN} report={null} />);
  const details = screen.getByTestId('processing-details');
  expect(details.textContent).toContain('R-01');
  expect(details.textContent).toContain('SUCCEEDED');
  expect(details.textContent).toContain('read');
});
