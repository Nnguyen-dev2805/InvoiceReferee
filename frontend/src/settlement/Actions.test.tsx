import { fireEvent, render, screen } from '@testing-library/react';
import { ActionsPanel } from './Actions';
import type { AuditEntry, CaseView, MoneySummary } from './types';

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

test('vai ACCOUNTANT trên hồ sơ B3 thấy form rà soát kế toán và nút Lưu kết quả rà soát', () => {
  render(<ActionsPanel view={makeView({ job: 'B3' })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady onAction={noop} />);
  expect(screen.getByText('Rà soát kế toán (không phải phê duyệt)')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Lưu kết quả rà soát' })).toBeInTheDocument();
  expect(screen.queryByText('Ghi sự kiện tiền')).not.toBeInTheDocument();
});

test('khi chưa nhập ghi chú rà soát: nút disabled và hiển thị gợi ý thân thiện', () => {
  render(<ActionsPanel view={makeView({ job: 'B3' })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady onAction={noop} />);
  const btn = screen.getByRole('button', { name: 'Lưu kết quả rà soát' }) as HTMLButtonElement;
  expect(btn.disabled).toBe(true);
  expect(screen.getByTestId('review-note-hint')).toHaveTextContent(
    'Vui lòng nhập ghi chú rà soát để lưu kết quả.'
  );

  // Nhập ghi chú: nút enabled và gợi ý biến mất
  fireEvent.change(screen.getByLabelText('Ghi chú rà soát'), {
    target: { value: 'Đã đối soát xong bảng kê chi phí dự kiến.' },
  });
  expect(btn.disabled).toBe(false);
  expect(screen.queryByTestId('review-note-hint')).not.toBeInTheDocument();
});

test('sau khi lưu review: hiển thị thẻ tóm tắt nổi bật Kế toán đã rà soát nếu có trong history', () => {
  const historyEntry: AuditEntry = {
    id: 'H-01',
    case_id: 'C-t01',
    kind: 'REVIEW_RECORDED',
    operation: 'RECORD_REVIEW',
    actor_id: 'ACC-LEAD-01',
    command_key: 'ck-rev-1',
    occurred_at: '2026-10-11T09:30:00Z',
    detail: {
      note: 'Đã đối chiếu bảng kê và vé máy bay gốc.',
      report_id: 'R-run01',
    },
  };

  render(<ActionsPanel view={makeView({ job: 'B3' })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady history={[historyEntry]} onAction={noop} />);

  const summary = screen.getByTestId('accountant-review-summary');
  expect(summary).toBeInTheDocument();
  expect(summary).toHaveTextContent('Kế toán đã rà soát');
  expect(summary).toHaveTextContent('ACC-LEAD-01');
  expect(summary).toHaveTextContent('Ghi chú: "Đã đối chiếu bảng kê và vé máy bay gốc."');
  expect(summary).toHaveTextContent('Căn cứ report R-run01');
});

test('với hồ sơ B3: ẩn bảng tình trạng tiền, ẩn form quyết định Approver khỏi kế toán, hiển thị thông báo nghiệp vụ ngắn gọn', () => {
  render(<ActionsPanel view={makeView({ job: 'B3' })} role="ACCOUNTANT" actorId="ACC-01"
    decisionId={null} reportReady onAction={noop} />);

  // 1. Ẩn hoàn toàn bảng tình trạng tiền
  expect(screen.queryByTestId('money-summary')).not.toBeInTheDocument();
  expect(screen.queryByText('Tình trạng tiền')).not.toBeInTheDocument();

  // 2. Ẩn form/cảnh báo quyết định của Approver khỏi góc nhìn Kế toán
  expect(screen.queryByText('Quyết định (người duyệt)')).not.toBeInTheDocument();
  expect(screen.queryByText(/BEYOND_AUTHORITY/)).not.toBeInTheDocument();

  // 3. Hiển thị thông báo nghiệp vụ thay vì lỗi kỹ thuật B3_REPORT_ONLY
  expect(screen.getByText(/Chức năng hiện tại hỗ trợ rà soát đề nghị tạm ứng; chưa thực hiện duyệt và chi ứng/)).toBeInTheDocument();
  expect(screen.queryByText(/B3_REPORT_ONLY/)).not.toBeInTheDocument();
});

test('vai APPROVER trên hồ sơ B3 hiển thị thông báo nghiệp vụ và không hiện B3_REPORT_ONLY', () => {
  render(<ActionsPanel view={makeView({ job: 'B3' })} role="APPROVER" actorId="APR-01"
    decisionId={null} reportReady onAction={noop} />);

  expect(screen.getByText(/Chức năng hiện tại hỗ trợ rà soát đề nghị tạm ứng; chưa thực hiện duyệt và chi ứng/)).toBeInTheDocument();
  expect(screen.queryByText(/B3_REPORT_ONLY/)).not.toBeInTheDocument();
  expect(screen.queryByTestId('money-summary')).not.toBeInTheDocument();
});

