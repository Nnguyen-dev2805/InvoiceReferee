import { fireEvent, render, screen } from '@testing-library/react';
import { B7FundingPanel } from './B7Funding';
import type { B7DecisionTarget, CaseView } from './types';

function target(overrides: Partial<B7DecisionTarget> = {}): B7DecisionTarget {
  return {
    employee_cost_vnd: 5_000_000, total_work_cost_vnd: 8_000_000,
    budget_vnd: 8_000_000, signed_net_vnd: 3_000_000,
    direction: 'PAY_EMPLOYEE', amount_vnd: 3_000_000, ...overrides,
  };
}

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-b7',
    job: 'B7',
    case_version: 9,
    input_revision: 4,
    control_epoch: 1,
    stop_active: false,
    stage: 'AWAITING_MONEY',
    current_run_id: 'R-run01',
    submission: {
      employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1', job: 'B7',
      money_as_of: '2026-10-14T02:00:00Z', knowledge_cutoff: '2026-10-14T02:00:00Z',
      form: { schema_version: 'b7-linked-intake-v1' },
    },
    sources: [],
    allowed_actions: [],
    money_summary: {
      approved_vnd: null, received_vnd: null, remaining_vnd: null,
      pending_events: 0, incidents: [],
    },
    b7_workflow: {
      status: 'APPROVED', basis_current: true, blocked_reasons: [],
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      presentation: null,
      decision: {
        id: 'B7D-1', case_id: 'C-b7', kind: 'B7_SETTLEMENT', outcome: 'APPROVE',
        reason: 'Duyệt', presentation_id: 'PR-1', basis_report_id: 'R-run01',
        basis_review_id: 'RV-1', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        actor_id: 'APR-DEMO-01', effective_at: '2026-10-14T09:00:00+07:00',
        created_at: '2026-10-14T02:00:00Z', basis_input_revision: 4,
        control_epoch: 1, business_signature: 's', parent_fingerprint: 'p',
        config_signature: 'c', authority_signature: 'a', target: target(),
        history_baseline: { e: 5_000_000, a: 2_000_000, ra: 0, p: 0, rp: 0 },
        supersedes_decision_id: null, idempotent_replay: false,
      },
      fulfillment: {
        decision_id: 'B7D-1', direction: 'PAY_EMPLOYEE', approved_vnd: 3_000_000,
        recorded_received_vnd: null, fulfilled_vnd: 0, remaining_vnd: 3_000_000,
        known_remaining_vnd: 3_000_000, pending_count: 0, unknown_count: 0,
        incidents: [], status: 'WAITING', managed_scope: 'decision:B7D-1',
        as_of: '2026-10-14T09:00:00+07:00',
        knowledge_cutoff: '2026-10-14T09:00:00+07:00',
      },
      revalidation: null, current_handoff: null, closure: null,
    },
    created_at: '2026-10-14T02:00:00Z',
    updated_at: '2026-10-14T02:00:00Z',
    ...overrides,
  };
}

const noop = async () => undefined;

test('kế toán: nút ghi disabled khi thiếu số/outcome/purpose/ghi chú', () => {
  render(<B7FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const btn = screen.getByRole('button',
    { name: 'Ghi nhận kết quả thực tế' }) as HTMLButtonElement;
  expect(btn.disabled).toBe(true);
});

test('kế toán: RECEIVED cần payer/payee/namespace/ref', () => {
  render(<B7FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const btn = screen.getByRole('button',
    { name: 'Ghi nhận kết quả thực tế' }) as HTMLButtonElement;
  fireEvent.change(screen.getByLabelText('Số tiền nguồn ghi (VND)'),
    { target: { value: '2000000' } });
  fireEvent.change(screen.getByLabelText('Kết quả giao dịch (theo nguồn)'),
    { target: { value: 'RECEIVED' } });
  fireEvent.change(screen.getByLabelText('Nguồn nghĩa vụ'),
    { target: { value: 'REIMBURSEMENT_RECEIVED' } });
  fireEvent.change(screen.getByLabelText('Ghi chú đối chiếu'),
    { target: { value: 'Đối chiếu đúng quyết định' } });
  expect(btn.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Bên trả (đọc từ nguồn)'),
    { target: { value: 'COMPANY' } });
  fireEvent.change(screen.getByLabelText('Bên nhận (đọc từ nguồn)'),
    { target: { value: 'NV-DEMO-01' } });
  fireEvent.change(screen.getByLabelText('Không gian giao dịch (namespace)'),
    { target: { value: 'BANK:DEMO-ACCOUNT' } });
  fireEvent.change(screen.getByLabelText('Mã giao dịch (event_ref)'),
    { target: { value: 'TX-1' } });
  expect(btn.disabled).toBe(false);
});

test('không mặc định bên nhận theo nhân viên', () => {
  render(<B7FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const payee = screen.getByLabelText('Bên nhận (đọc từ nguồn)');
  expect((payee as HTMLInputElement).value).toBe('');
});

test('nhân viên: readonly, không thấy nút ghi/đóng', () => {
  render(<B7FundingPanel view={makeView()} role="EMPLOYEE"
    actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button',
    { name: 'Ghi nhận kết quả thực tế' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button',
    { name: 'Đóng hồ sơ quyết toán' })).not.toBeInTheDocument();
});

test('người duyệt: không thấy form ghi tiền', () => {
  render(<B7FundingPanel view={makeView()} role="APPROVER"
    actorId="APR-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button',
    { name: 'Ghi nhận kết quả thực tế' })).not.toBeInTheDocument();
});

test('approved không tự thành received: chưa ghi thì recorded là —', () => {
  render(<B7FundingPanel view={makeView()} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const summary = screen.getByTestId('b7-fulfillment-summary').textContent ?? '';
  expect(summary).toContain('Đã đối chiếu thực nhận: —');
  expect(summary).toContain('Đã duyệt: 3.000.000 đ');
});

test('collection: nhãn Công ty đã nhận, không P', () => {
  const view = makeView();
  view.b7_workflow!.decision!.target = target({
    direction: 'COLLECT_FROM_EMPLOYEE', signed_net_vnd: -700_000,
    amount_vnd: 700_000, employee_cost_vnd: 1_300_000 });
  view.b7_workflow!.fulfillment = {
    decision_id: 'B7D-1', direction: 'COLLECT_FROM_EMPLOYEE', approved_vnd: 700_000,
    recorded_received_vnd: null, fulfilled_vnd: 0, remaining_vnd: 700_000,
    known_remaining_vnd: 700_000, pending_count: 0, unknown_count: 0,
    incidents: [], status: 'WAITING', managed_scope: 'decision:B7D-1',
    as_of: '2026-10-14T09:00:00+07:00',
    knowledge_cutoff: '2026-10-14T09:00:00+07:00',
  };
  render(<B7FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const summary = screen.getByTestId('b7-fulfillment-summary').textContent ?? '';
  expect(summary).toContain('Công ty đã nhận');
  expect(summary).toContain('Còn phải thu từ nhân viên');
});

test('hiển thị incident OVERPAY', () => {
  const view = makeView();
  view.b7_workflow!.fulfillment = {
    decision_id: 'B7D-1', direction: 'PAY_EMPLOYEE', approved_vnd: 3_000_000,
    recorded_received_vnd: 4_000_000, fulfilled_vnd: 3_000_000, remaining_vnd: null,
    known_remaining_vnd: 0, pending_count: 0, unknown_count: 0,
    incidents: [{ code: 'OVERPAY', event_ids: ['BM-1'], excess_vnd: 1_000_000,
                 refs: [], reason: 'Vượt số đã duyệt' }],
    status: 'BLOCKED', managed_scope: 'decision:B7D-1',
    as_of: '2026-10-14T09:00:00+07:00',
    knowledge_cutoff: '2026-10-14T09:00:00+07:00',
  };
  render(<B7FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  const incidents = screen.getByTestId('b7-fulfillment-incidents');
  expect(incidents).toHaveTextContent('OVERPAY');
});

test('closed: banner readonly + nút tạo điều chỉnh cho kế toán', () => {
  const view = makeView();
  view.stage = 'SETTLEMENT_CLOSED';
  view.b7_workflow!.closure = {
    id: 'BC-1', case_id: 'C-b7', decision_id: 'B7D-1',
    current_report_id: 'R-run01', actor_id: 'ACC-DEMO-01',
    kind: 'SETTLEMENT_COMPLETE', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
    close_as_of: '2026-10-14T09:00:00+07:00',
    knowledge_cutoff: '2026-10-14T09:00:00+07:00',
    created_at: '2026-10-14T02:00:00Z', input_revision: 4, control_epoch: 1,
    business_signature: 's', receipt_history_signature: 'r',
    parent_fingerprint: 'p', source_refs: [], event_ids: [],
    original_decision_id: 'B7D-1', revalidation_ref: 'R-run01',
    reason: 'Đủ căn cứ', idempotent_replay: false,
  };
  render(<B7FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  expect(screen.getByRole('button',
    { name: 'Tạo hồ sơ điều chỉnh' })).toBeInTheDocument();
  expect(screen.queryByRole('button',
    { name: 'Đóng hồ sơ quyết toán' })).not.toBeInTheDocument();
});

test('BALANCED: không có nút ghi tiền (không chi/thu)', () => {
  const view = makeView();
  view.b7_workflow!.decision!.target = target({
    direction: 'BALANCED', signed_net_vnd: 0, amount_vnd: 0 });
  view.b7_workflow!.fulfillment = {
    decision_id: 'B7D-1', direction: 'BALANCED', approved_vnd: 0,
    recorded_received_vnd: null, fulfilled_vnd: 0, remaining_vnd: 0,
    known_remaining_vnd: 0, pending_count: 0, unknown_count: 0,
    incidents: [], status: 'BALANCED', managed_scope: 'decision:B7D-1',
    as_of: '2026-10-14T09:00:00+07:00',
    knowledge_cutoff: '2026-10-14T09:00:00+07:00',
  };
  render(<B7FundingPanel view={view} role="ACCOUNTANT"
    actorId="ACC-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button',
    { name: 'Ghi nhận kết quả thực tế' })).not.toBeInTheDocument();
});
