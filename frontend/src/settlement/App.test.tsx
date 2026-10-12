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
        case_version: 1, updated_at: '2026-10-10T09:00:00+07:00',
        origin: 'USER' as const}]
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
  await user.type(screen.getByLabelText(/Số tiền đề nghị tạm ứng|Số xin ứng/), '2000000');
  await user.click(screen.getByText('Nộp đề nghị B3 (web)'));
  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  const payload = createSpy.mock.calls[0][1];
  expect(payload.confirmed).toBe(true);
  expect(payload.intake_method).toBe('WEB');
  expect(payload.request_amount_vnd).toBe(2_000_000);
  await waitFor(() => expect(startSpy).toHaveBeenCalledTimes(1));
});

test('IMPORT creation không render form rỗng và tạo draft chưa confirm', async () => {
  const user = userEvent.setup();
  const createSpy = vi.spyOn(api, 'createB3Case')
    .mockResolvedValue(caseView(false));
  const startSpy = vi.spyOn(api, 'startRun').mockResolvedValue(RUN);
  setup(caseView(false));
  await screen.findByText('Nộp đề nghị B3 (web)');
  await user.selectOptions(screen.getByLabelText('Cách nộp'), 'IMPORT');
  expect(screen.queryByTestId('b3-intake-form')).toBeNull();
  await user.click(screen.getByText('Tạo hồ sơ nháp B3 (chưa xác nhận)'));
  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  const payload = createSpy.mock.calls[0][1];
  expect(payload.confirmed).toBe(false);
  expect(payload.intake_method).toBe('IMPORT');
  expect(startSpy).not.toHaveBeenCalled();
});

test('preview CTA focus editor và xác nhận gửi đề nghị dùng audit reason mặc định', async () => {
  const user = userEvent.setup();
  const reviseSpy = vi.spyOn(api, 'reviseSubmission')
    .mockResolvedValue(caseView(true));
  vi.spyOn(api, 'startRun').mockResolvedValue(RUN);

  setup(caseView(false), true);
  await user.click(await screen.findByText(/C-b3test01/));

  expect(await screen.findByText('Kiểm tra bản nháp trước khi gửi')).toBeInTheDocument();
  const checkBtn = screen.getByRole('button', { name: 'Kiểm tra bản nháp' });
  await user.click(checkBtn);
  expect(screen.getByLabelText('Nơi đến')).toHaveFocus();

  const confirmBtn = screen.getByText('Xác nhận và gửi đề nghị');
  await user.click(confirmBtn);

  await waitFor(() => expect(reviseSpy).toHaveBeenCalledTimes(1));
  const call = reviseSpy.mock.calls[0][1];
  expect(call.reason).toBe('Xác nhận bản nháp từ tài liệu đính kèm');
  expect((call.submission.form as unknown as B3Intake).confirmed).toBe(true);
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

test('màn mặc định không phơi raw run enum; details vẫn truy vết', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);
  await user.click(await screen.findByText(/C-b3test01/));
  await screen.findByTestId('report-panel');
  const strip = screen.getByTestId('run-panel');
  // Nhãn mô phỏng dễ thấy, không phải raw SUCCEEDED/publishing.
  expect(strip.textContent).toContain('Chế độ mô phỏng/replay');
  // Raw run id/status/stage nằm trong "Thông tin xử lý".
  const details = screen.getByTestId('processing-details');
  expect(details.textContent).toContain('R-b3run01');
  expect(details.textContent).toContain('SUCCEEDED');
});

test('IMPORT cho phép tải lên 2 tệp riêng biệt và thêm từng nguồn', async () => {
  const user = userEvent.setup();
  const createSpy = vi.spyOn(api, 'createB3Case').mockResolvedValue(caseView(false));
  const addSourceSpy = vi.spyOn(api, 'addSource').mockResolvedValue({
    id: 'src-1',
    filename: 'giay_de_nghi.pdf',
    media_type: 'application/pdf',
    sha256: 'abc123',
    size_bytes: 100,
    status: 'ACCEPTED',
    uploader_actor_id: 'NV-DEMO-01',
    received_at: '2026-10-10T09:00:00Z',
    supersedes_source_id: null,
    provenance: {},
  });
  const startSpy = vi.spyOn(api, 'startRun').mockResolvedValue(RUN);
  setup(caseView(false));
  await screen.findByText('Nộp đề nghị B3 (web)');
  await user.selectOptions(screen.getByLabelText('Cách nộp'), 'IMPORT');

  const file1 = new File(['de nghi content'], 'giay_de_nghi.pdf', { type: 'application/pdf' });
  const file2 = new File(['du toan content'], 'bang_du_toan.pdf', { type: 'application/pdf' });
  const file3 = new File(['thu moi content'], 'thu_moi.pdf', { type: 'application/pdf' });

  const fileInput = screen.getByTestId('b3-import-file-input') as HTMLInputElement;
  await user.upload(fileInput, [file1, file2, file3]);

  expect(screen.getByText(/giay_de_nghi\.pdf/)).toBeInTheDocument();
  expect(screen.getByText(/bang_du_toan\.pdf/)).toBeInTheDocument();
  expect(screen.getByText(/thu_moi\.pdf/)).toBeInTheDocument();
  expect(screen.getByText('Đã chọn 3 tệp đính kèm:')).toBeInTheDocument();

  const uploadBtn = screen.getByText('Tải lên & Tạo hồ sơ nháp B3');
  await user.click(uploadBtn);

  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(addSourceSpy).toHaveBeenCalledTimes(3));
  expect(startSpy).toHaveBeenCalledTimes(1);
});

test('Verify panel đóng mặc định và mở được mà không tự động chạy', async () => {
  const user = userEvent.setup();
  const verifySpy = vi.spyOn(api, 'runSettlementVerify');
  setup();

  expect(screen.queryByRole('button', { name: /Chạy Verify/ })).not.toBeInTheDocument();
  const toggleBtn = screen.getByText('Đánh giá hệ thống (Verify)');
  await user.click(toggleBtn);

  expect(screen.getByRole('button', { name: /Chạy Verify/ })).toBeVisible();
  expect(verifySpy).not.toHaveBeenCalled();
});

test('hồ sơ IMPORT tự động nạp AI draft data vào form xác nhận khi mở', async () => {
  const user = userEvent.setup();
  const emptyImportCase: CaseView = {
    ...caseView(false),
    submission: {
      ...caseView(false).submission,
      form: {
        schema_version: 'b3-intake-v1',
        intake_method: 'IMPORT',
        confirmed: false,
        destination: '',
        trip_start: null,
        trip_end: null,
        purpose: '',
        assignment_note: null,
        request_amount_vnd: null,
        settlement_due: null,
        estimate_rows: [],
      },
    },
  };
  setup(emptyImportCase, true);
  await user.click(await screen.findByText(/C-b3test01/));

  expect(await screen.findByTestId('b3-revise-panel')).toBeInTheDocument();
  expect(screen.getByText(/AI đã trích xuất dữ liệu từ chứng từ đính kèm/)).toBeInTheDocument();
  const destInput = screen.getByLabelText('Nơi đến') as HTMLInputElement;
  expect(destInput.value).toBe('Hà Nội');
});

test('hồ sơ hệ thống hiện tag và có nút xoá gọi API rồi tải lại danh sách', async () => {
  const user = userEvent.setup();
  vi.spyOn(api, 'getDemoContext').mockResolvedValue(DEMO_CONTEXT);
  vi.spyOn(api, 'getHistory').mockResolvedValue([]);
  vi.spyOn(api, 'getQuestions').mockResolvedValue([]);
  const systemCase = {
    id: 'C-sys01', job: 'B7' as const, employee_ref: 'NV-01',
    work_ref: 'CT-E2E-01', stage: 'CHECKING' as const, case_version: 1,
    updated_at: '2026-10-10T09:00:00+07:00', origin: 'SYSTEM' as const,
  };
  const listSpy = vi.spyOn(api, 'listCases')
    .mockResolvedValueOnce([systemCase]).mockResolvedValue([]);
  const deleteSpy = vi.spyOn(api, 'deleteCase').mockResolvedValue(undefined);
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

  render(<App />);

  expect(await screen.findByText('Hệ thống')).toBeInTheDocument();
  await user.click(screen.getByTestId('delete-case-C-sys01'));

  await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('C-sys01'));
  expect(confirmSpy).toHaveBeenCalled();
  await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(2));
});

test('không xoá khi người dùng huỷ hộp thoại xác nhận', async () => {
  const user = userEvent.setup();
  vi.spyOn(api, 'getDemoContext').mockResolvedValue(DEMO_CONTEXT);
  vi.spyOn(api, 'getHistory').mockResolvedValue([]);
  vi.spyOn(api, 'getQuestions').mockResolvedValue([]);
  vi.spyOn(api, 'listCases').mockResolvedValue([{
    id: 'C-user01', job: 'B7' as const, employee_ref: 'NV-01',
    work_ref: 'CT-USER', stage: 'CHECKING' as const, case_version: 1,
    updated_at: '2026-10-10T09:00:00+07:00', origin: 'USER' as const,
  }]);
  const deleteSpy = vi.spyOn(api, 'deleteCase').mockResolvedValue(undefined);
  vi.spyOn(window, 'confirm').mockReturnValue(false);

  render(<App />);

  await user.click(await screen.findByTestId('delete-case-C-user01'));
  expect(deleteSpy).not.toHaveBeenCalled();
});

test('chuyển vai trò demo cập nhật đúng actorId theo roster demo context', async () => {
  const user = userEvent.setup();
  vi.spyOn(api, 'getDemoContext').mockResolvedValue(DEMO_CONTEXT);
  vi.spyOn(api, 'getHistory').mockResolvedValue([]);
  vi.spyOn(api, 'getQuestions').mockResolvedValue([]);
  vi.spyOn(api, 'listCases').mockResolvedValue([]);

  render(<App />);

  // Khởi đầu là EMPLOYEE -> actor NV-DEMO-01
  expect(await screen.findByDisplayValue('NV-DEMO-01')).toBeInTheDocument();

  // Đổi sang ACCOUNTANT -> actor tự động cập nhật ACC-DEMO-01
  await user.selectOptions(screen.getByLabelText('Vai trò demo'), 'ACCOUNTANT');
  expect(screen.getByDisplayValue('ACC-DEMO-01')).toBeInTheDocument();

  // Đổi sang APPROVER -> actor tự động cập nhật APR-DEMO-01
  await user.selectOptions(screen.getByLabelText('Vai trò demo'), 'APPROVER');
  expect(screen.getByDisplayValue('APR-DEMO-01')).toBeInTheDocument();
});

test('header nhận diện công việc: tiêu đề chính to rõ, dòng phụ hành trình, và nhãn xác nhận', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);

  await user.click(await screen.findByText(/C-b3test01/));

  // 1. Tiêu đề chính to rõ: Đề nghị tạm ứng — Nguyễn An (lấy tên từ demoContext)
  const mainHeading = await screen.findByRole('heading', { level: 2, name: /Đề nghị tạm ứng — Nguyễn An/ });
  expect(mainHeading).toHaveTextContent('Đề nghị tạm ứng — Nguyễn An');

  // 2. Dòng phụ: [Địa điểm] · [Thời gian chuyến đi] · Đề nghị [Số tiền VND]
  expect(screen.getByText(/Hà Nội · 12–13\/10\/2026 · Đề nghị 2\.000\.000 đ/)).toBeInTheDocument();

  // 3. Nhãn xác nhận
  expect(screen.getByText('Nhân viên đã xác nhận thông tin đề nghị')).toBeInTheDocument();
});

test('mã hồ sơ hiển thị dạng badge nhỏ gọn có nút sao chép clipboard', async () => {
  const user = userEvent.setup();
  const writeTextMock = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: writeTextMock },
    writable: true,
    configurable: true,
  });

  setup(caseView(true), true);
  await user.click(await screen.findByText(/C-b3test01/));

  // Kiểm tra badge mã hồ sơ
  const badge = await screen.findByTestId('case-id-badge');
  expect(badge).toBeInTheDocument();
  expect(badge).toHaveTextContent('C-b3test01');

  // Bấm nút sao chép
  const copyBtn = screen.getByLabelText('Sao chép mã hồ sơ');
  await user.click(copyBtn);

  expect(writeTextMock).toHaveBeenCalledWith('C-b3test01');
  expect(await screen.findByText('Đã chép')).toBeInTheDocument();
});

test('kế toán thấy trạng thái "Chờ kế toán rà soát" và nút Tạo hồ sơ mới dạng thứ cấp', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);

  // Đổi vai sang ACCOUNTANT
  await user.selectOptions(screen.getByLabelText('Vai trò demo'), 'ACCOUNTANT');

  // Nút Tạo hồ sơ mới chuyển sang dạng thứ cấp (gọn hơn, không chiếm spotlight)
  const newCaseBtn = screen.getByRole('button', { name: /Tạo hồ sơ mới/ });
  expect(newCaseBtn).toHaveClass('btn-new-case-accountant');

  // Mở hồ sơ
  await user.click(await screen.findByText(/C-b3test01/));

  // Trạng thái nghiệp vụ thống nhất trên cùng khi chưa có review
  const statusCard = await screen.findByTestId('accountant-status-card');
  expect(statusCard).toHaveTextContent('Chờ kế toán rà soát');
  expect(statusCard).toHaveTextContent(
    'Nhân viên đã xác nhận thông tin đề nghị. Hệ thống đã hoàn tất kiểm tra tự động. Chưa phê duyệt hoặc chi ứng.'
  );
});

test('kế toán thấy trạng thái "Đã lưu kết quả rà soát" khi có bản ghi review trong history', async () => {
  const user = userEvent.setup();
  setup(caseView(true), true);

  vi.spyOn(api, 'getHistory').mockResolvedValue([
    {
      id: 'H-01',
      case_id: 'C-b3test01',
      kind: 'REVIEW_RECORDED',
      operation: 'RECORD_REVIEW',
      actor_id: 'ACC-DEMO-01',
      command_key: 'ck-1',
      occurred_at: '2026-10-10T10:00:00+07:00',
      detail: { note: 'Đã đối chiếu bảng kê và vé máy bay.' },
    },
  ]);

  await user.selectOptions(screen.getByLabelText('Vai trò demo'), 'ACCOUNTANT');
  await user.click(await screen.findByText(/C-b3test01/));

  const statusCard = await screen.findByTestId('accountant-status-card');
  expect(statusCard).toHaveTextContent('Đã lưu kết quả rà soát');
  expect(statusCard).toHaveTextContent('ACC-DEMO-01');
  expect(statusCard).toHaveTextContent('Đã đối chiếu bảng kê và vé máy bay.');
});

test('tab Nguồn chứng từ cho phép chọn và tải lên nhiều tệp cùng lúc', async () => {
  const user = userEvent.setup();
  const initialCase = caseView(true);
  const updatedCase1: CaseView = {
    ...initialCase,
    case_version: 2,
    sources: [
      {
        id: 'src-1',
        filename: 'A01.pdf',
        media_type: 'application/pdf',
        sha256: 'sha1',
        size_bytes: 1024,
        status: 'ACCEPTED',
        uploader_actor_id: 'NV-DEMO-01',
        received_at: '2026-10-10T09:00:00Z',
        supersedes_source_id: null,
        provenance: {},
      },
    ],
  };
  setup(initialCase, true);

  let currentVer = 1;
  vi.spyOn(api, 'getCase').mockImplementation(async () => ({
    ...initialCase,
    case_version: currentVer,
  }));
  const addSourceSpy = vi.spyOn(api, 'addSource').mockImplementation(async () => {
    currentVer += 1;
    return updatedCase1.sources[0];
  });

  await user.click(await screen.findByText(/C-b3test01/));

  // Chuyển sang tab Nguồn chứng từ
  await user.click(screen.getByRole('tab', { name: /Nguồn chứng từ/ }));

  const file1 = new File(['content 1'], 'A01.pdf', { type: 'application/pdf' });
  const file2 = new File(['content 2'], 'A02.pdf', { type: 'application/pdf' });

  const fileInput = screen.getByTestId('sources-file-input') as HTMLInputElement;
  expect(fileInput).toHaveAttribute('multiple');

  await user.upload(fileInput, [file1, file2]);

  expect(screen.getByText('Đã chọn 2 tệp:')).toBeInTheDocument();
  expect(screen.getByText(/A01\.pdf/)).toBeInTheDocument();
  expect(screen.getByText(/A02\.pdf/)).toBeInTheDocument();

  const uploadBtn = screen.getByRole('button', { name: 'Tải lên 2 nguồn' });
  await user.click(uploadBtn);

  await waitFor(() => expect(addSourceSpy).toHaveBeenCalledTimes(2));
  expect(addSourceSpy).toHaveBeenNthCalledWith(
    1,
    'C-b3test01',
    file1,
    1,
    expect.any(String),
    expect.any(String),
    expect.any(String),
  );
  expect(addSourceSpy).toHaveBeenNthCalledWith(
    2,
    'C-b3test01',
    file2,
    2,
    expect.any(String),
    expect.any(String),
    expect.any(String),
  );
});





