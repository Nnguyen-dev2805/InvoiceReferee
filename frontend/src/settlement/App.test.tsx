// Task 4: App với company fixture B3 — persona readonly, WEB submit
// confirmed, IMPORT draft chưa confirm, không quảng cáo nút duyệt/chi.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, vi } from 'vitest';
import * as api from './api';
import { App } from './App';
import type { B3DemoContext, B3Intake, CaseView, Report, RunView } from './types';

const DEMO_CONTEXT: B3DemoContext = {
  version: 'synthetic-verbal-v2',
  synthetic: true,
  demo_clock: '2026-10-10T09:00:00+07:00',
  people: [
    {actor_ref: 'NV-DEMO-01', role: 'EMPLOYEE', name: 'Nguyễn An',
     department: 'Kinh doanh'},
    {actor_ref: 'ACC-DEMO-01', role: 'ACCOUNTANT', name: 'Trần Bình',
     department: 'Kế toán'},
    {actor_ref: 'APR-DEMO-01', role: 'APPROVER', name: 'Lê Chi',
     department: 'Quản lý'},
  ],
  routes: [{employee_ref: 'NV-DEMO-01', accountant_ref: 'ACC-DEMO-01',
            approver_ref: 'APR-DEMO-01'}],
};

const INTAKE_FORM: B3Intake = {
  schema_version: 'b3-intake-v1',
  intake_method: 'WEB',
  confirmed: true,
  destination: 'Hà Nội',
  trip_start: '2026-10-12',
  trip_end: '2026-10-13',
  purpose: 'Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án tại Hà Nội.',
  assignment_note: null,
  request_amount_vnd: 2_000_000,
  settlement_due: '2026-10-16',
  estimate_rows: [
    {row_id: 'flight', description: 'Vé máy bay khứ hồi', basis: '1 vé khứ hồi',
     company_vnd: 3_000_000, employee_vnd: 0},
    {row_id: 'hotel', description: 'Khách sạn', basis: '1 đêm',
     company_vnd: 0, employee_vnd: 3_000_000},
    {row_id: 'ground', description: 'Di chuyển tại Hà Nội', basis: 'ước tính',
     company_vnd: 0, employee_vnd: 1_000_000},
    {row_id: 'meal', description: 'Bữa ăn phục vụ công việc', basis: 'ước tính',
     company_vnd: 0, employee_vnd: 1_000_000},
  ],
};

function caseView(confirmed: boolean): CaseView {
  return {
    id: 'C-b3test01',
    job: 'B3',
    case_version: 1,
    input_revision: 1,
    control_epoch: 1,
    stop_active: false,
    stage: 'CHECKING',
    current_run_id: 'R-b3run01',
    submission: {
      employee_ref: 'NV-DEMO-01',
      work_ref: 'WORK-b3test01',
      job: 'B3',
      money_as_of: '2026-10-10T09:00:00+07:00',
      knowledge_cutoff: '2026-10-10T09:00:00+07:00',
      form: {...INTAKE_FORM, confirmed} as unknown as Record<string, unknown>,
    },
    sources: [],
    allowed_actions: [
      {action: 'REVISE_SUBMISSION', reason: 'sửa khai báo'},
      {action: 'ADD_SOURCE', reason: 'thêm nguồn'},
      {action: 'START_RUN', reason: 'chạy kiểm tra'},
    ],
    money_summary: {approved_vnd: null, received_vnd: null, remaining_vnd: null,
                    pending_events: 0, incidents: []},
    created_at: '2026-10-10T09:00:00+07:00',
    updated_at: '2026-10-10T09:00:00+07:00',
  };
}

const RUN: RunView = {
  id: 'R-b3run01', case_id: 'C-b3test01', status: 'QUEUED',
  mode: 'FAKE_OR_REPLAY', input_revision: 1, control_epoch: 1,
  stage: null, created_at: '2026-10-10T09:00:00Z',
  updated_at: '2026-10-10T09:00:00Z', detail: null, completion: null,
  trace: [], idempotent_replay: false,
};

function b3Report(readiness: Report['b3'] extends null ? never
  : NonNullable<Report['b3']>['readiness']): Report {
  const proposal = {
    readiness,
    intake: INTAKE_FORM,
    forecast_company_vnd: 3_000_000,
    forecast_employee_vnd: 5_000_000,
    forecast_total_vnd: 8_000_000,
    work_permission: 'PENDING_DECISION' as const,
    advance_approval: 'PENDING_DECISION' as const,
    accountant_ref: 'ACC-DEMO-01',
    approver_ref: 'APR-DEMO-01',
    field_refs: {request_amount_vnd: ['form:1:request_amount_vnd']},
  };
  const slot = (value: number | null,
                state: 'KNOWN' | 'UNKNOWN' | 'NOT_APPLICABLE') =>
    ({value, state, refs: []});
  return {
    run_id: 'R-b3run01', job: 'B3', completion: 'COMPLETE',
    mode: 'FAKE_OR_REPLAY', generated_at: '2026-10-10T09:00:00Z',
    components: {
      t: slot(null, 'NOT_APPLICABLE'), b: slot(null, 'UNKNOWN'),
      e: slot(null, 'NOT_APPLICABLE'), a: slot(0, 'KNOWN'),
      ra: slot(0, 'KNOWN'), p: slot(null, 'NOT_APPLICABLE'),
      rp: slot(null, 'NOT_APPLICABLE'),
    },
    calculated_net_vnd: null, proposed_net_vnd: null, direction: null,
    conditional_results: [], expense_rows: [],
    checks: [], issues: [], critical_facts: [], links: [],
    b3: proposal,
    next_step: 'đủ để rà soát',
    source_refs: [],
  };
}

function setup(caseAfterCreate?: CaseView, withCaseList = false) {
  vi.spyOn(api, 'getDemoContext').mockResolvedValue(DEMO_CONTEXT);
  vi.spyOn(api, 'listCases').mockResolvedValue(withCaseList
    ? [{id: 'C-b3test01', job: 'B3' as const, employee_ref: 'NV-DEMO-01',
        work_ref: 'WORK-b3test01', stage: 'CHECKING' as const,
        case_version: 1, updated_at: '2026-10-10T09:00:00+07:00'}]
    : []);
  vi.spyOn(api, 'getHistory').mockResolvedValue([]);
  vi.spyOn(api, 'getQuestions').mockResolvedValue([]);
  if (caseAfterCreate) {
    vi.spyOn(api, 'getCase').mockResolvedValue(caseAfterCreate);
    vi.spyOn(api, 'getRun').mockResolvedValue(
      {...RUN, status: 'SUCCEEDED', completion: 'COMPLETE'});
    vi.spyOn(api, 'getReport').mockResolvedValue(b3Report('READY_FOR_ACCOUNTANT_REVIEW'));
    vi.spyOn(api, 'getB3RunContext').mockResolvedValue({
      version: 'synthetic-verbal-v2', synthetic: true,
      demo_clock: '2026-10-10T09:00:00+07:00',
      grants: [], coverage: [], history: [],
    });
  }
  return render(<App />);
}

afterEach(() => {
  vi.restoreAllMocks();
});

test('persona demo hiển thị profile; không nhập người duyệt/mã work/mốc trong B3', async () => {
  setup();
  expect(await screen.findByTestId('b3-intake-panel')).toBeTruthy();
  expect(await screen.findByText(/Nguyễn An — Kinh doanh/)).toBeTruthy();
  const panel = screen.getByTestId('b3-intake-panel');
  // không có approver dropdown / work-id / clock input trong panel B3
  expect(screen.queryByLabelText(/người duyệt/i)).not.toBeInTheDocument();
  expect(panel.querySelector('#work-ref')).toBeNull();
  expect(panel.querySelector('input[type="datetime-local"]')).toBeNull();
});

test('WEB submit tạo case confirmed và tự chạy kiểm tra', async () => {
  const user = userEvent.setup();
  const createSpy = vi.spyOn(api, 'createB3Case')
    .mockResolvedValue(caseView(true));
  const startSpy = vi.spyOn(api, 'startRun').mockResolvedValue(RUN);
  setup(caseView(true));
  await screen.findByText('Nộp đề nghị B3 (web)');
  await user.type(screen.getByLabelText('Nơi đến'), 'Hà Nội');
  await user.type(
    screen.getByLabelText('Mục đích công tác', {selector: '#b3-purpose'}),
    'Khảo sát dự án');
  await user.type(screen.getByLabelText(/Số xin ứng/), '2000000');
  await user.click(screen.getByText('Nộp đề nghị B3 (web)'));
  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  const payload = createSpy.mock.calls[0][1];
  expect(payload.confirmed).toBe(true);
  expect(payload.intake_method).toBe('WEB');
  expect(payload.request_amount_vnd).toBe(2_000_000);
  await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
});

test('IMPORT tạo draft chưa confirm và không tự submit/confirm', async () => {
  const user = userEvent.setup();
  const createSpy = vi.spyOn(api, 'createB3Case')
    .mockResolvedValue(caseView(false));
  const startSpy = vi.spyOn(api, 'startRun').mockResolvedValue(RUN);
  setup(caseView(false));
  await screen.findByText('Nộp đề nghị B3 (web)');
  await user.selectOptions(screen.getByLabelText('Cách nộp'), 'IMPORT');
  await user.type(screen.getByLabelText('Nơi đến'), 'Hà Nội');
  await user.click(screen.getByText('Tạo hồ sơ nháp B3 (chưa xác nhận)'));
  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  const payload = createSpy.mock.calls[0][1];
  expect(payload.confirmed).toBe(false);  // chưa đánh dấu submitted sau preview
  expect(payload.intake_method).toBe('IMPORT');
  expect(startSpy).not.toHaveBeenCalled(); // không tự nộp vì vừa upload
});

test('report B3 hiển thị "đang chờ quyết định", không nút đã duyệt ứng', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);
  await user.click(await screen.findByText(/C-b3test01/));
  await screen.findByTestId('report-panel');
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Đang chờ quyết định');
  expect(text).toContain('2.000.000 VND');
  expect(text).not.toContain('S = E −');
  expect(screen.queryByText(/Đã duyệt ứng/)).not.toBeInTheDocument();
});
