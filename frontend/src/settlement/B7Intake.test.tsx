import { fireEvent, render, screen } from '@testing-library/react';
import { B7IntakePanel } from './B7Intake';
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

test('employee thấy nút thêm khoản và xác nhận', () => {
  render(<B7IntakePanel view={makeView()} report={null} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.getByRole('button', { name: 'Thêm khoản chi' })).toBeInTheDocument();
  const confirm = screen.getByRole('button',
    { name: 'Xác nhận nộp và đối soát' }) as HTMLButtonElement;
  // No rows yet → cannot confirm.
  expect(confirm.disabled).toBe(true);
});

test('không prefill số forecast thành actual: số khai trống', () => {
  render(<B7IntakePanel view={makeView()} report={null} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  fireEvent.click(screen.getByRole('button', { name: 'Thêm khoản chi' }));
  const amount = screen.getAllByLabelText('Số khai (VND)')[0] as HTMLInputElement;
  expect(amount.value).toBe('');
});

test('thêm dòng rồi confirm bật khi có mô tả', () => {
  render(<B7IntakePanel view={makeView()} report={null} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  fireEvent.click(screen.getByRole('button', { name: 'Thêm khoản chi' }));
  const desc = screen.getAllByLabelText('Nội dung')[0];
  fireEvent.change(desc, { target: { value: 'Khách sạn' } });
  const confirm = screen.getByRole('button',
    { name: 'Xác nhận nộp và đối soát' }) as HTMLButtonElement;
  expect(confirm.disabled).toBe(false);
});

test('hiển thị link origin readonly', () => {
  render(<B7IntakePanel view={makeView()} report={null} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.getByTestId('b7-origin-link')).toHaveTextContent('C-parent');
});

test('người khác không thấy nút khai báo', () => {
  render(<B7IntakePanel view={makeView()} report={null} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button', { name: 'Thêm khoản chi' }))
    .not.toBeInTheDocument();
});
