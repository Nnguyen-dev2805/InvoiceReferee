import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { B3ApprovalPanel } from './B3Approval';
import * as api from './api';
import type { AuditEntry, CaseView } from './types';

const B3_FORM = { schema_version: 'b3-intake-v1', confirmed: true };

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-b3',
    job: 'B3',
    case_version: 4,
    input_revision: 1,
    control_epoch: 1,
    stop_active: false,
    stage: 'CHECKING',
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
      status: 'NOT_PRESENTED', presentation: null, decision: null,
      basis_current: false, decision_validity: null, blocked_reason: null,
      accountant_ref: null, approver_ref: null,
    },
    created_at: '2026-10-11T10:00:00Z',
    updated_at: '2026-10-11T10:00:00Z',
    ...overrides,
  };
}

const noop = async () => undefined;

test('kế toán chưa có review: nút trình disabled khi note trắng, mở khi có note', () => {
  render(<B3ApprovalPanel view={makeView()} report={null} history={[]}
    role="ACCOUNTANT" actorId="ACC-DEMO-01" onAction={noop} />);
  const btn = screen.getByRole('button',
    { name: 'Lưu rà soát và trình duyệt' }) as HTMLButtonElement;
  expect(btn.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Ghi chú rà soát'),
    { target: { value: 'Đã đối chiếu bảng kê.' } });
  expect(btn.disabled).toBe(false);
});

test('kế toán có review còn current: không bắt nhập lại, submit dùng review_id', async () => {
  const history: AuditEntry[] = [{
    id: 'H-1', case_id: 'C-b3', kind: 'REVIEW_RECORDED',
    operation: 'RECORD_REVIEW', actor_id: 'ACC-DEMO-01',
    command_key: 'k', occurred_at: '2026-10-11T09:00:00Z',
    detail: { review: {
      id: 'RV-9', case_id: 'C-b3', report_id: 'R-run01',
      note: 'Đã đối chiếu.', refs: [], actor_id: 'ACC-DEMO-01',
      created_at: '2026-10-11T09:00:00Z' } },
  }];
  const spy = vi.spyOn(api, 'presentB3').mockResolvedValue({} as never);
  const onAction = async (_label: string, run: () => Promise<unknown>) => {
    await run();
  };
  render(<B3ApprovalPanel view={makeView()} report={null} history={history}
    role="ACCOUNTANT" actorId="ACC-DEMO-01" onAction={onAction} />);
  expect(screen.queryByLabelText('Ghi chú rà soát')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Trình người duyệt' }));
  await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
  expect(spy.mock.calls[0][1]).toMatchObject({ review_id: 'RV-9' });
  spy.mockRestore();
});

test('approver pending: phê duyệt cần allow-work + hai số > 0 + lý do', () => {
  const view = makeView({
    stage: 'AWAITING_DECISION',
    b3_workflow: {
      status: 'PENDING', basis_current: true,
      decision: null, decision_validity: null, blocked_reason: null,
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      presentation: {
        id: 'PR-1', case_id: 'C-b3', basis_report_id: 'R-run01',
        review_id: 'RV-1', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
        basis_input_revision: 1, basis_control_epoch: 1,
        basis_signature: 's', context_signature: 'c',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    },
  });
  render(<B3ApprovalPanel view={view} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  const approve = screen.getByRole('button',
    { name: 'Phê duyệt tạm ứng' }) as HTMLButtonElement;
  expect(approve.disabled).toBe(true);
  fireEvent.click(screen.getByLabelText('Cho phép thực hiện công việc'));
  fireEvent.change(screen.getByLabelText('Ngân sách duyệt (VND)'),
    { target: { value: '8000000' } });
  fireEvent.change(screen.getByLabelText('Số ứng duyệt (VND)'),
    { target: { value: '2000000' } });
  fireEvent.change(screen.getByLabelText('Lý do'),
    { target: { value: 'Duyệt theo đề nghị' } });
  expect(approve.disabled).toBe(false);
});

test('approver pending: RETURN/REFUSE chỉ cần lý do, không gửi approved fields', async () => {
  const view = makeView({
    stage: 'AWAITING_DECISION',
    b3_workflow: {
      status: 'PENDING', basis_current: true,
      decision: null, decision_validity: null, blocked_reason: null,
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      presentation: {
        id: 'PR-1', case_id: 'C-b3', basis_report_id: 'R-run01',
        review_id: 'RV-1', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
        basis_input_revision: 1, basis_control_epoch: 1,
        basis_signature: 's', context_signature: 'c',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    },
  });
  render(<B3ApprovalPanel view={view} report={null} history={[]}
    role="APPROVER" actorId="APR-DEMO-01" onAction={noop} />);
  const ret = screen.getByRole('button',
    { name: 'Yêu cầu bổ sung' }) as HTMLButtonElement;
  expect(ret.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Lý do'),
    { target: { value: 'Cần sửa dự toán' } });
  expect(ret.disabled).toBe(false);
});

test('employee pending: không thấy nút quyết định', () => {
  const view = makeView({
    stage: 'AWAITING_DECISION',
    b3_workflow: {
      status: 'PENDING', basis_current: true,
      decision: null, decision_validity: null, blocked_reason: null,
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      presentation: {
        id: 'PR-1', case_id: 'C-b3', basis_report_id: 'R-run01',
        review_id: 'RV-1', employee_ref: 'NV-DEMO-01', work_ref: 'WORK-1',
        accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
        basis_input_revision: 1, basis_control_epoch: 1,
        basis_signature: 's', context_signature: 'c',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    },
  });
  render(<B3ApprovalPanel view={view} report={null} history={[]}
    role="EMPLOYEE" actorId="NV-DEMO-01" onAction={noop} />);
  expect(screen.queryByRole('button', { name: 'Phê duyệt tạm ứng' }))
    .not.toBeInTheDocument();
  expect(screen.getByText(/Chờ người duyệt tạm ứng/)).toBeInTheDocument();
});
