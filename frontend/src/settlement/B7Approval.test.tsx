import { fireEvent, render, screen } from '@testing-library/react';
import { B7ApprovalPanel } from './B7Approval';
import type { B7DecisionTarget, CaseView } from './types';

const B7_FORM = { schema_version: 'b7-linked-intake-v1', confirmed: true };

const TARGET: B7DecisionTarget = {
  employee_cost_vnd: 5_000_000, total_work_cost_vnd: 8_000_000,
  budget_vnd: 8_000_000, signed_net_vnd: 3_000_000,
  direction: 'PAY_EMPLOYEE', amount_vnd: 3_000_000,
};

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-child', job: 'B7', case_version: 6, input_revision: 3,
    control_epoch: 1, stop_active: false, stage: 'AWAITING_DECISION',
    current_run_id: 'R-run01',
    submission: {
      employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1', job: 'B7',
      money_as_of: '2026-10-14T02:00:00Z',
      knowledge_cutoff: '2026-10-14T02:00:00Z', form: B7_FORM,
    },
    sources: [], allowed_actions: [],
    money_summary: {
      approved_vnd: null, received_vnd: null, remaining_vnd: null,
      pending_events: 0, incidents: [],
    },
    linked_b7: {
      origin: {
        origin_case_id: 'C-parent', employee_ref: 'NV-DEMO-01',
        work_ref: 'WORK-1', created_at: '2026-10-14T02:00:00Z',
      },
      context_source_id: 'S-ctx', context_current: true, blocked_reasons: [],
      managed_advance_subtotal_vnd: 2_000_000,
    },
    b7_workflow: {
      status: 'NOT_PRESENTED', presentation: null, decision: null,
      basis_current: false, blocked_reasons: [], accountant_ref: null,
      approver_ref: null,
    },
    created_at: '2026-10-14T02:00:00Z',
    updated_at: '2026-10-14T02:00:00Z',
    ...overrides,
  };
}

function pendingView(overrides: Partial<CaseView> = {}): CaseView {
  return makeView({
    stage: 'AWAITING_DECISION',
    b7_workflow: {
      status: 'PENDING', decision: null, basis_current: true,
      blocked_reasons: [], accountant_ref: 'ACC-DEMO-01',
      approver_ref: 'APR-DEMO-01',
      presentation: {
        id: 'PR-1', case_id: 'C-child', employee_ref: 'NV-DEMO-01',
        work_ref: 'WORK-1', basis_report_id: 'R-run01',
        basis_review_id: 'RV-1', accountant_ref: 'ACC-DEMO-01',
        approver_ref: 'APR-DEMO-01', basis_input_revision: 3,
        control_epoch: 1, business_signature: 'b', parent_fingerprint: 'p',
        config_signature: 'c', target: TARGET,
        created_at: '2026-10-14T02:00:00Z', idempotent_replay: false,
      },
    },
    ...overrides,
  });
}

const noop = async () => undefined;

test('accountant thấy nút trình, không thấy form quyết định', () => {
  render(<B7ApprovalPanel view={makeView()} report={null} history={[]}
    role="ACCOUNTANT" actorId="ACC-DEMO-01" onAction={noop} />);
  expect(screen.getByRole('button',
    { name: 'Lưu rà soát và trình duyệt' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Phê duyệt quyết toán' }))
    .not.toBeInTheDocument();
});

test('approver pending: thấy target readonly và ba nút quyết định', () => {
  render(<B7ApprovalPanel view={pendingView()} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  expect(screen.getByText(/Số tiền công ty cần trả thêm/)).toBeInTheDocument();
  expect(screen.getByText(/3\.000\.000/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Phê duyệt quyết toán' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Yêu cầu làm rõ' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Từ chối đề nghị' })).toBeInTheDocument();
});

test('approver: nút quyết định cần lý do', () => {
  render(<B7ApprovalPanel view={pendingView()} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  const approve = screen.getByRole('button',
    { name: 'Phê duyệt quyết toán' }) as HTMLButtonElement;
  expect(approve.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Lý do'),
    { target: { value: 'Duyệt theo kết quả đã rà soát' } });
  expect(approve.disabled).toBe(false);
});

test('employee: không thấy nút quyết định', () => {
  render(<B7ApprovalPanel view={pendingView()} report={null} history={[]}
    role="EMPLOYEE" actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button', { name: 'Phê duyệt quyết toán' }))
    .not.toBeInTheDocument();
});

test('COLLECTION: hiển thị nhân viên cần hoàn lại', () => {
  const view = pendingView();
  view.b7_workflow!.presentation!.target = {
    ...TARGET, direction: 'COLLECT_FROM_EMPLOYEE', amount_vnd: 700_000,
    signed_net_vnd: -700_000,
  };
  render(<B7ApprovalPanel view={view} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  expect(screen.getByText(/Số tiền nhân viên cần hoàn lại/)).toBeInTheDocument();
});

test('BALANCED: không ghi "đã chi 0"', () => {
  const view = pendingView();
  view.b7_workflow!.presentation!.target = {
    ...TARGET, direction: 'BALANCED', amount_vnd: 0, signed_net_vnd: 0,
  };
  render(<B7ApprovalPanel view={view} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  expect(screen.getByText(/Quyết toán cân bằng/)).toBeInTheDocument();
  expect(screen.queryByText(/đã chi 0/i)).not.toBeInTheDocument();
});

test('approved: hiển thị chờ chi/thu và thực nhận chưa ghi', () => {
  const view = makeView({
    stage: 'AWAITING_MONEY',
    b7_workflow: {
      status: 'APPROVED', presentation: null, basis_current: true,
      blocked_reasons: [], accountant_ref: 'ACC-DEMO-01',
      approver_ref: 'APR-DEMO-01',
      decision: {
        id: 'B7D-1', case_id: 'C-child', kind: 'B7_SETTLEMENT',
        outcome: 'APPROVE', reason: 'Duyệt', presentation_id: 'PR-1',
        basis_report_id: 'R-run01', basis_review_id: 'RV-1',
        employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        actor_id: 'APR-DEMO-01', effective_at: '2026-10-14T09:00:00+07:00',
        created_at: '2026-10-14T02:00:00Z', basis_input_revision: 3,
        control_epoch: 1, business_signature: 'b', parent_fingerprint: 'p',
        config_signature: 'c', authority_signature: 'a', target: TARGET,
        history_baseline: { e: 5_000_000, a: 2_000_000, ra: 0, p: 0, rp: 0 },
        supersedes_decision_id: null, idempotent_replay: false,
      },
    },
  });
  render(<B7ApprovalPanel view={view} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  const panel = screen.getByTestId('b7-approval-panel');
  expect(panel).toHaveTextContent('Đã duyệt quyết toán — chờ chi/thu');
  expect(panel).toHaveTextContent('Thực nhận tiền mặt: Chưa ghi nhận');
});
