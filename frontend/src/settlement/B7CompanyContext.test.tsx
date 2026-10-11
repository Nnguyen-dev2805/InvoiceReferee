import { fireEvent, render, screen } from '@testing-library/react';
import { B7CompanyContextPanel } from './B7CompanyContext';
import type { CaseView } from './types';

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-child',
    job: 'B7',
    case_version: 2,
    input_revision: 1,
    control_epoch: 1,
    stop_active: false,
    stage: 'CHECKING',
    current_run_id: null,
    submission: {
      employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1', job: 'B7',
      money_as_of: '2026-10-10T02:00:00Z',
      knowledge_cutoff: '2026-10-10T02:00:00Z',
      form: { schema_version: 'b7-linked-intake-v1', confirmed: false,
              expense_rows: [], note: null },
    },
    sources: [],
    allowed_actions: [],
    money_summary: {
      approved_vnd: null, received_vnd: null, remaining_vnd: null,
      pending_events: 0, incidents: [],
    },
    linked_b7: {
      origin: {
        origin_case_id: 'C-parent', employee_ref: 'NV-DEMO-01',
        work_ref: 'WORK-1', created_at: '2026-10-11T10:00:00Z',
      },
      context_source_id: null, context_current: false, blocked_reasons: [],
      managed_advance_subtotal_vnd: 2_000_000,
    },
    created_at: '2026-10-11T10:00:00Z',
    updated_at: '2026-10-11T10:00:00Z',
    ...overrides,
  };
}

const noop = async () => undefined;

test('accountant thấy textarea + nút ghi company context', () => {
  render(<B7CompanyContextPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  expect(screen.getByLabelText(/Company packet/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Ghi company context' }))
    .toBeInTheDocument();
});

test('employee không thấy editor', () => {
  render(<B7CompanyContextPanel view={makeView()} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button', { name: 'Ghi company context' }))
    .not.toBeInTheDocument();
});

test('hiển thị trạng thái coverage và ứng đã ghi nhận', () => {
  render(<B7CompanyContextPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const status = screen.getByTestId('b7-context-status');
  expect(status).toHaveTextContent('Chưa có / cần làm mới');
  expect(status).toHaveTextContent('2.000.000 đ');
});

test('JSON sai không gọi API', () => {
  let called = 0;
  const onAction = async () => { called += 1; };
  render(<B7CompanyContextPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={onAction} />);
  fireEvent.change(screen.getByLabelText(/Company packet/),
    { target: { value: '{ not json' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ghi company context' }));
  expect(called).toBe(0);
});
