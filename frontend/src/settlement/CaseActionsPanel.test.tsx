import { render, screen } from '@testing-library/react';
import { ActionsPanel } from './Actions';
import type { AuditEntry, CaseView, MoneySummary } from './types';

function b3Workflow(overrides: Partial<CaseView['b3_workflow']> = {}) {
  return {
    status: 'NOT_PRESENTED' as const,
    presentation: null,
    decision: null,
    basis_current: false,
    decision_validity: null,
    blocked_reason: null,
    accountant_ref: null,
    approver_ref: null,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<MoneySummary> = {}): MoneySummary {
  return {
    approved_vnd: 3_000_000,
    received_vnd: 2_000_000,
    remaining_vnd: 1_000_000,
    pending_events: 0,
    incidents: [],
    ...overrides,
  };
}

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-t01',
    job: 'B7',
    case_version: 7,
    input_revision: 3,
    control_epoch: 1,
    stop_active: false,
    stage: 'AWAITING_MONEY',
    current_run_id: 'R-run01',
    submission: {
      employee_ref: 'NV-01',
      work_ref: 'CT-01',
      job: 'B7',
      money_as_of: '2026-10-08T11:00:00Z',
      knowledge_cutoff: '2026-10-08T11:00:00Z',
      form: {},
    },
    sources: [],
    allowed_actions: [],
    money_summary: makeSummary(),
    created_at: '2026-10-09T10:00:00Z',
    updated_at: '2026-10-09T10:00:00Z',
    ...overrides,
  };
}

const noop = async () => undefined;

test('hiển thị approved/received/remaining tách biệt; unknown giữ "—"', () => {
  render(<ActionsPanel view={makeView({
    money_summary: makeSummary({
      approved_vnd: null, received_vnd: null, remaining_vnd: null,
    }),
  })} role="ACCOUNTANT" actorId="ACC-01" decisionId={null}
    reportReady onAction={noop} />);
  const text = screen.getByTestId('money-summary').textContent ?? '';
  expect(text).toContain('Đã duyệt (approved): —');
  expect(text).toContain('Thực nhận (received): —');
  expect(text).toContain('Còn lại (remaining): —');
});

test('incidents OVERPAY/WRONG_RECIPIENT hiển thị, không clip gross', () => {
  render(<ActionsPanel view={makeView({
    money_summary: makeSummary({
      received_vnd: 4_000_000, remaining_vnd: 0,
      incidents: [
        { kind: 'OVERPAY', excess_vnd: 1_000_000, event_ref: null, payee_ref: null },
        { kind: 'WRONG_RECIPIENT', excess_vnd: null, event_ref: 'EV-9',
          payee_ref: 'NV-99' },
      ],
    }),
  })} role="ACCOUNTANT" actorId="ACC-01" decisionId={null}
    reportReady onAction={noop} />);
  const panel = screen.getByTestId('actions-panel').textContent ?? '';
  expect(panel).toContain('OVERPAY');
  expect(panel).toContain('1.000.000 VND');
  expect(panel).toContain('WRONG_RECIPIENT');
  expect(panel).toContain('NV-99');
});

test('vai không phải APPROVER thấy cảnh báo BEYOND_AUTHORITY', () => {
  render(<ActionsPanel view={makeView()} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByText(/BEYOND_AUTHORITY/)).toBeTruthy();
});

test('hồ sơ đã đóng chỉ còn thông báo đọc lại', () => {
  render(<ActionsPanel view={makeView({ stage: 'SETTLEMENT_CLOSED' })}
    role="ACCOUNTANT" actorId="ACC-01" decisionId="D-1"
    reportReady onAction={noop} />);
  const panel = screen.getByTestId('actions-panel');
  expect(panel.textContent).toContain('Hồ sơ đã kết thúc (SETTLEMENT_CLOSED)');
  expect(panel.textContent).not.toContain('Ghi quyết định');
});

test('Stop đang bật: không cho Stop nữa, cho Resume', () => {
  render(<ActionsPanel view={makeView({ stop_active: true, stage: 'CHECKING' })}
    role="ACCOUNTANT" actorId="ACC-01" decisionId={null}
    reportReady onAction={noop} />);
  expect((screen.getByText(/Stop hồ sơ/) as HTMLButtonElement).disabled)
    .toBe(true);
  expect((screen.getByText(/Resume \(epoch/) as HTMLButtonElement).disabled)
    .toBe(false);
});

test('vai EMPLOYEE chỉ thấy tình trạng tiền và thông báo, không thấy form duyệt/chi', () => {
  render(<ActionsPanel view={makeView()} role="EMPLOYEE" actorId="NV-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByTestId('money-summary')).toBeTruthy();
  expect(screen.getByText(/Góc nhìn Nhân viên/)).toBeTruthy();
  expect(screen.queryByText('Quyết định (người duyệt)')).not.toBeInTheDocument();
  expect(screen.queryByText(/Rà soát kế toán/)).not.toBeInTheDocument();
  expect(screen.queryByText('Ghi sự kiện tiền')).not.toBeInTheDocument();
  expect(screen.queryByText('Stop hồ sơ')).not.toBeInTheDocument();
});

test('B3 chưa trình: kế toán thấy nút Lưu rà soát và trình duyệt; ẩn tình trạng tiền', () => {
  render(<ActionsPanel view={makeView({
    job: 'B3', b3_workflow: b3Workflow(),
    submission: { ...makeView().submission, job: 'B3',
      form: { schema_version: 'b3-intake-v1', confirmed: true } },
  })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByTestId('b3-approval-panel')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Lưu rà soát và trình duyệt' })).toBeInTheDocument();
  expect(screen.queryByTestId('money-summary')).not.toBeInTheDocument();
  expect(screen.queryByText(/B3_REPORT_ONLY/)).not.toBeInTheDocument();
});

test('B3 đã có review còn current: kế toán không phải nhập lại, thấy nút Trình người duyệt', () => {
  const historyEntry: AuditEntry = {
    id: 'H-01', case_id: 'C-t01', kind: 'REVIEW_RECORDED',
    operation: 'RECORD_REVIEW', actor_id: 'ACC-01',
    command_key: 'ck-rev-1', occurred_at: '2026-10-11T09:30:00Z',
    detail: { review: {
      id: 'RV-1', case_id: 'C-t01', report_id: 'R-run01',
      note: 'Đã đối chiếu bảng kê.', refs: [], actor_id: 'ACC-01',
      created_at: '2026-10-11T09:30:00Z' } },
  };
  render(<ActionsPanel view={makeView({
    job: 'B3', b3_workflow: b3Workflow(),
    submission: { ...makeView().submission, job: 'B3',
      form: { schema_version: 'b3-intake-v1', confirmed: true } },
  })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady history={[historyEntry]} onAction={noop} />);
  expect(screen.getByTestId('b3-saved-review')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Trình người duyệt' })).toBeInTheDocument();
  expect(screen.queryByLabelText('Ghi chú rà soát')).not.toBeInTheDocument();
});

test('B3 pending: approver thấy ba nút quyết định, employee không thấy', () => {
  const presented = {
    ...makeView(), job: 'B3' as const,
    stage: 'AWAITING_DECISION' as const,
    submission: { ...makeView().submission, job: 'B3' as const,
      form: { schema_version: 'b3-intake-v1', confirmed: true } },
    b3_workflow: b3Workflow({
      status: 'PENDING', basis_current: true,
      accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
      presentation: {
        id: 'PR-1', case_id: 'C-t01', basis_report_id: 'R-run01',
        review_id: 'RV-1', employee_ref: 'NV-01', work_ref: 'CT-01',
        accountant_ref: 'ACC-DEMO-01', approver_ref: 'APR-DEMO-01',
        basis_input_revision: 3, basis_control_epoch: 1,
        basis_signature: 'sig', context_signature: 'ctx',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    }),
  };
  const { unmount } = render(
    <ActionsPanel view={presented} role="APPROVER" actorId="APR-DEMO-01"
      decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByRole('button', { name: 'Phê duyệt tạm ứng' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Yêu cầu bổ sung' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Từ chối đề nghị' })).toBeInTheDocument();
  unmount();

  render(<ActionsPanel view={presented} role="EMPLOYEE" actorId="NV-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.queryByRole('button', { name: 'Phê duyệt tạm ứng' }))
    .not.toBeInTheDocument();
});

test('B3 approved: hiển thị chờ chi ứng và "Chưa ghi nhận", không có nút chi/đóng', () => {
  const approved = {
    ...makeView(), job: 'B3' as const, stage: 'AWAITING_MONEY' as const,
    submission: { ...makeView().submission, job: 'B3' as const,
      form: { schema_version: 'b3-intake-v1', confirmed: true } },
    b3_workflow: b3Workflow({
      status: 'APPROVED', basis_current: true,
      decision: {
        id: 'BD-1', case_id: 'C-t01', kind: 'B3_ADVANCE',
        presentation_id: 'PR-1', outcome: 'APPROVE', reason: 'Duyệt theo đề nghị',
        work_allowed: true, budget_vnd: 8_000_000, advance_vnd: 2_000_000,
        basis_report_id: 'R-run01', basis_review_id: 'RV-1',
        basis_input_revision: 3, basis_control_epoch: 1, basis_signature: 'sig',
        context_signature: 'ctx', employee_ref: 'NV-01', work_ref: 'CT-01',
        actor_id: 'APR-DEMO-01', grant_ref: 'company:grant-01',
        effective_at: '2026-10-10T09:00:00+07:00',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    }),
  };
  render(<ActionsPanel view={approved} role="APPROVER" actorId="APR-DEMO-01"
    decisionId={null} reportReady onAction={noop} />);
  const panel = screen.getByTestId('b3-approval-panel').textContent ?? '';
  expect(panel).toContain('Đã duyệt tạm ứng — chờ chi ứng');
  expect(panel).toContain('Thực nhận: Chưa ghi nhận');
  expect(screen.queryByText('Ghi sự kiện tiền')).not.toBeInTheDocument();
  expect(screen.queryByText('Đóng hồ sơ')).not.toBeInTheDocument();
});

test('B3 refused: employee thấy lý do, không có form mở lại', () => {
  const refused = {
    ...makeView(), job: 'B3' as const, stage: 'ADVANCE_REQUEST_REFUSED' as const,
    submission: { ...makeView().submission, job: 'B3' as const,
      form: { schema_version: 'b3-intake-v1', confirmed: true } },
    b3_workflow: b3Workflow({
      status: 'REFUSED', basis_current: true,
      decision: {
        id: 'BD-2', case_id: 'C-t01', kind: 'B3_ADVANCE',
        presentation_id: 'PR-1', outcome: 'REFUSE', reason: 'Chưa cấp ứng',
        work_allowed: null, budget_vnd: null, advance_vnd: null,
        basis_report_id: 'R-run01', basis_review_id: 'RV-1',
        basis_input_revision: 3, basis_control_epoch: 1, basis_signature: 'sig',
        context_signature: 'ctx', employee_ref: 'NV-01', work_ref: 'CT-01',
        actor_id: 'APR-DEMO-01', grant_ref: 'company:grant-01',
        effective_at: '2026-10-10T09:00:00+07:00',
        created_at: '2026-10-11T10:00:00Z', idempotent_replay: false,
      },
    }),
  };
  render(<ActionsPanel view={refused} role="EMPLOYEE" actorId="NV-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByText(/Đề nghị tạm ứng bị từ chối/)).toBeInTheDocument();
  expect(screen.getByText('Chưa cấp ứng')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Lưu rà soát và trình duyệt' }))
    .not.toBeInTheDocument();
});


// --- R2.4: linked B7 dùng dedicated actions, không generic lifecycle ---------

function linkedB7View(overrides: Partial<CaseView> = {}): CaseView {
  return makeView({
    job: 'B7',
    linked_b7: {
      origin: { origin_case_id: 'C-parent', employee_ref: 'NV-01',
                work_ref: 'CT-01', created_at: '2026-10-11T10:00:00Z' },
      context_source_id: 'S-1', context_current: true, blocked_reasons: [],
      managed_advance_subtotal_vnd: 2_000_000,
    },
    b7_workflow: {
      status: 'NOT_PRESENTED', presentation: null, decision: null,
      basis_current: false, blocked_reasons: [], accountant_ref: 'ACC-01',
      approver_ref: 'APR-01',
    },
    ...overrides,
  });
}

test('R2.4: linked B7 kế toán không thấy form quyết định/chi generic', () => {
  render(<ActionsPanel view={linkedB7View()} role="ACCOUNTANT" actorId="ACC-01"
    decisionId="D-1" reportReady onAction={noop} />);
  expect(screen.getByTestId('b7-approval-panel')).toBeInTheDocument();
  // Generic W05 forms are blocked by the backend for linked B7 → not rendered.
  expect(screen.queryByTestId('money-summary')).not.toBeInTheDocument();
  expect(screen.queryByText('Ghi sự kiện tiền')).not.toBeInTheDocument();
  expect(screen.queryByText('Quyết định (người duyệt)')).not.toBeInTheDocument();
  expect(screen.queryByText('Đóng hồ sơ')).not.toBeInTheDocument();
  expect(screen.queryByText(/Bàn giao thủ quỹ/)).not.toBeInTheDocument();
});

test('R2.4: legacy B7 (không link) vẫn giữ generic lifecycle', () => {
  render(<ActionsPanel view={makeView()} role="ACCOUNTANT" actorId="ACC-01"
    decisionId="D-1" reportReady onAction={noop} />);
  expect(screen.getByTestId('money-summary')).toBeInTheDocument();
  expect(screen.getByText('Ghi sự kiện tiền')).toBeInTheDocument();
});
