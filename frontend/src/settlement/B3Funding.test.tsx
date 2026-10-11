import { fireEvent, render, screen } from '@testing-library/react';
import { B3FundingPanel } from './B3Funding';
import type { CaseView } from './types';

const B3_FORM = { schema_version: 'b3-intake-v1', confirmed: true };

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-b3',
    job: 'B3',
    case_version: 6,
    input_revision: 1,
    control_epoch: 1,
    stop_active: false,
    stage: 'AWAITING_MONEY',
    current_run_id: 'R-run01',
    submission: {
      employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1', job: 'B3',
      money_as_of: '2026-10-10T02:00:00Z', knowledge_cutoff: '2026-10-10T02:00:00Z',
      form: B3_FORM,
    },
    sources: [],
    allowed_actions: [],
    money_summary: {
      approved_vnd: null, received_vnd: null, remaining_vnd: null,
      pending_events: 0, incidents: [],
    },
    b3_workflow: {
      status: 'APPROVED', presentation: null,
      decision: {
        id: 'BD-1', case_id: 'C-b3', kind: 'B3_ADVANCE',
        presentation_id: 'PR-1', outcome: 'APPROVE', reason: 'Duyệt',
        work_allowed: true, budget_vnd: 8_000_000, advance_vnd: 2_000_000,
        basis_report_id: 'R-run01', basis_review_id: 'RV-1',
        basis_input_revision: 1, basis_control_epoch: 1, basis_signature: 's',
        context_signature: 'c', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        actor_id: 'APR-DEMO-01', grant_ref: 'g',
        effective_at: '2026-10-10T09:00:00+07:00',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
      basis_current: true, decision_validity: null, blocked_reason: null,
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      funding: {
        decision_id: 'BD-1', approved_vnd: 2_000_000,
        recorded_received_vnd: null, fulfilled_vnd: null, remaining_vnd: null,
        pending_count: 0, unknown_count: 0, incidents: [],
        status: 'NOT_RECORDED', scope: 'decision:BD-1', as_of: null,
      },
      advance_events: [],
    },
    created_at: '2026-10-11T10:00:00Z',
    updated_at: '2026-10-11T10:00:00Z',
    ...overrides,
  };
}

const noop = async () => undefined;

test('kế toán: nút ghi bị disabled khi thiếu số/outcome/ghi chú', () => {
  render(<B3FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const btn = screen.getByRole('button',
    { name: 'Ghi nhận sự kiện ứng' }) as HTMLButtonElement;
  expect(btn.disabled).toBe(true);
});

test('kế toán: RECEIVED cần người nhận/namespace/ref', () => {
  render(<B3FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const btn = screen.getByRole('button',
    { name: 'Ghi nhận sự kiện ứng' }) as HTMLButtonElement;
  fireEvent.change(screen.getByLabelText('Số tiền nguồn ghi (VND)'),
    { target: { value: '2000000' } });
  fireEvent.change(screen.getByLabelText('Kết quả giao dịch (theo nguồn)'),
    { target: { value: 'RECEIVED' } });
  fireEvent.change(screen.getByLabelText('Ghi chú đối chiếu'),
    { target: { value: 'Đối chiếu đúng quyết định' } });
  // Missing payee/namespace/ref for RECEIVED.
  expect(btn.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Người nhận thực tế (đọc từ nguồn)'),
    { target: { value: 'NV-DEMO-01' } });
  fireEvent.change(screen.getByLabelText('Không gian giao dịch (namespace)'),
    { target: { value: 'BANK:DEMO-ACCOUNT' } });
  fireEvent.change(screen.getByLabelText('Mã giao dịch (event_ref)'),
    { target: { value: 'TX-1' } });
  expect(btn.disabled).toBe(false);
});

test('không mặc định người nhận theo nhân viên', () => {
  render(<B3FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const payee = screen.getByLabelText('Người nhận thực tế (đọc từ nguồn)');
  expect((payee as HTMLInputElement).value).toBe('');
});

test('nhân viên: readonly, không thấy nút ghi', () => {
  render(<B3FundingPanel view={makeView()} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button',
    { name: 'Ghi nhận sự kiện ứng' })).not.toBeInTheDocument();
});

test('hiển thị incidents khi có overpay', () => {
  const view = makeView();
  view.b3_workflow!.funding = {
    decision_id: 'BD-1', approved_vnd: 2_000_000,
    recorded_received_vnd: 3_000_000, fulfilled_vnd: 2_000_000,
    remaining_vnd: 0, pending_count: 0, unknown_count: 0,
    incidents: [{ kind: 'OVERPAY', event_ids: ['AE-1'], refs: [],
                 amount_vnd: 1_000_000, reason: 'Vượt số đã duyệt' }],
    status: 'NEEDS_RESOLUTION', scope: 'decision:BD-1', as_of: null,
  };
  render(<B3FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const incidents = screen.getByTestId('b3-funding-incidents');
  expect(incidents).toHaveTextContent('OVERPAY');
});

test('hiển thị từng sự kiện đã ghi', () => {
  const view = makeView();
  view.b3_workflow!.advance_events = [{
    id: 'AE-1', case_id: 'C-b3', kind: 'ADVANCE_TO_EMPLOYEE',
    decision_id: 'BD-1', event_namespace: 'BANK:DEMO-ACCOUNT',
    event_ref: 'TX-1', method: 'BANK_TRANSFER', gross_vnd: 2_000_000,
    payer_side: 'COMPANY', payee_ref: 'NV-DEMO-01',
    event_at: '2026-10-10T10:00:00+07:00', reported_status: 'RECEIVED',
    evidence: [], allocation_note: 'x', supersedes_event_id: null,
    employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
    classification: 'CONFIRMED_RECEIPT', actor_id: 'ACC-DEMO-01',
    created_at: '2026-10-11T10:00:00Z', after_money_cutoff: false,
    incidents: [], idempotent_replay: false,
  }];
  render(<B3FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const events = screen.getByTestId('b3-advance-events');
  expect(events).toHaveTextContent('AE-1');
  expect(events).toHaveTextContent('RECEIVED');
});

test('approved không tự thành received: chưa ghi thì recorded là null', () => {
  render(<B3FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const summary = screen.getByTestId('b3-funding-summary').textContent ?? '';
  expect(summary).toContain('Đã ghi nhận thực nhận: —');
  expect(summary).toContain('Số ứng đã duyệt: 2.000.000 đ');
});
