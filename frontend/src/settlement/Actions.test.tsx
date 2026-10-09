import { render, screen } from '@testing-library/react';
import { ActionsPanel } from './Actions';
import type { CaseView, MoneySummary } from './types';

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
