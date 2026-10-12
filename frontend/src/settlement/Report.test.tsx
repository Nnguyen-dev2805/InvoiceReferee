import { render, screen } from '@testing-library/react';
import { ReportPanel } from './Report';
import type { Report } from './types';

function slot(value: number | null, state: Report['components']['t']['state'],
              refs: string[] = []) {
  return { value, state, refs };
}

function makeReport(overrides: Partial<Report> = {}): Report {
  return {
    run_id: 'R-test01',
    job: 'B7',
    completion: 'INCOMPLETE',
    mode: 'FAKE_OR_REPLAY',
    generated_at: '2026-10-09T12:00:00+00:00',
    components: {
      t: slot(5_000_000, 'KNOWN', ['EXP-1']),
      b: slot(8_000_000, 'KNOWN', ['S-budget']),
      e: slot(5_000_000, 'KNOWN', ['EXP-1']),
      a: slot(null, 'UNKNOWN', []),
      ra: slot(0, 'KNOWN', ['S-history']),
      p: slot(0, 'KNOWN', ['S-history']),
      rp: slot(0, 'KNOWN', ['S-history']),
    },
    calculated_net_vnd: null,
    proposed_net_vnd: null,
    direction: null,
    conditional_results: [],
    expense_rows: [{
      expense_id: 'EXP-1',
      claimed_amount_vnd: 5_000_000,
      eligible_employee_vnd: 5_000_000,
      company_direct_vnd: 0,
      state: 'ELIGIBLE',
      refs: ['F1', 'S-bill'],
      reason: 'đủ căn cứ',
    }],
    checks: [{ rule: 'history_coverage', status: 'UNRESOLVED', refs: [], reason: 'thiếu A' }],
    issues: [{
      issue_id: 'I-HISTORY',
      type: 'FACT',
      owner: 'ACCOUNTANT',
      message: 'Thiếu lịch sử advance trong scope.',
      refs: ['S-history'],
      blocked: 'net',
      unresolved: true,
    }],
    next_step: 'Xử lý issue rồi chạy lại.',
    source_refs: ['S-bill', 'S-history', 'S-budget'],
    critical_facts: [],
    links: [],
    b3: null,
    ...overrides,
  };
}

test('chiều thu hiển thị khi S âm và mâu thuẫn fact không bị giấu', () => {
  render(<ReportPanel report={makeReport({
    completion: 'INCOMPLETE',
    calculated_net_vnd: -700_000,
    direction: 'EMPLOYEE_TO_COMPANY',
    critical_facts: [{
      key: 'history.advance.received', value: null, state: 'CONTRADICTED',
      refs: ['S-history'],
    }],
    links: [{
      relation_id: 'R1', kind: 'EXPENSE_PAYMENT', from_id: 'EXP-1',
      to_id: 'PAY-1', portion_vnd: null, status: 'PROPOSED',
    }],
  })} />);
  const panel = screen.getByTestId('report-panel');
  expect(panel.textContent).toContain('nhân viên hoàn lại công ty');
  const facts = screen.getByTestId('critical-facts').textContent ?? '';
  expect(facts).toContain('MÂU THUẪN');
  const links = screen.getByTestId('report-links').textContent ?? '';
  expect(links).toContain('PROPOSED');
  expect(links).toContain('chưa dùng làm căn cứ tiền');
});

test('hiển thị components, unknown giữ "—" không phải 0', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/A — ứng đã thực nhận/)).toBeTruthy();
  const reportPanel = screen.getByTestId('report-panel');
  expect(reportPanel.textContent).toContain('5.000.000 đ');
  expect(reportPanel.textContent).not.toContain('A — ứng đã thực nhận 0');
});

test('nhãn FAKE_OR_REPLAY hiển thị rõ là reader giả lập', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/FAKE_OR_REPLAY — reader giả lập\/offline/)).toBeTruthy();
});

test('issue nêu đúng owner kế toán và refs mở được nguồn', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.getByText(/Kế toán: Thiếu lịch sử advance trong scope/)).toBeTruthy();
  const links = screen.getAllByRole('link', { name: 'S-history' });
  expect(links.length).toBeGreaterThan(0);
  expect(links[0].getAttribute('href')).toBe('/api/sources/S-history/content');
});

test('proposed khác calculated: proposed null giữ "—"', () => {
  render(<ReportPanel report={makeReport({
    calculated_net_vnd: 3_000_000,
    proposed_net_vnd: null,
  })} />);
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Calculated:');
  expect(text).toContain('3.000.000 đ');
  expect(text).toContain('Proposed (chưa duyệt, chưa chi): —');
});

// --- B3 v1 proposal (Task 4) ---------------------------------------------------

function makeB3Report(): Report {
  return makeReport({
    job: 'B3',
    b3: {
      readiness: 'READY_FOR_ACCOUNTANT_REVIEW',
      intake: {
        schema_version: 'b3-intake-v1',
        intake_method: 'WEB',
        confirmed: true,
        destination: 'Hà Nội',
        trip_start: '2026-10-12',
        trip_end: '2026-10-13',
        purpose: 'Khảo sát yêu cầu và thống nhất phạm vi triển khai dự án.',
        assignment_note: null,
        request_amount_vnd: 2_000_000,
        settlement_due: '2026-10-16',
        estimate_rows: [
          {row_id: 'flight', description: 'Vé máy bay khứ hồi', basis: '1 vé',
           company_vnd: 3_000_000, employee_vnd: 0},
          {row_id: 'hotel', description: 'Khách sạn', basis: '1 đêm',
           company_vnd: 0, employee_vnd: 3_000_000},
        ],
      },
      forecast_company_vnd: 3_000_000,
      forecast_employee_vnd: 5_000_000,
      forecast_total_vnd: 8_000_000,
      work_permission: 'PENDING_DECISION',
      advance_approval: 'PENDING_DECISION',
      accountant_ref: 'ACC-DEMO-01',
      approver_ref: 'APR-DEMO-01',
      field_refs: {request_amount_vnd: ['form:1:request_amount_vnd']},
    },
  });
}

test('report B3 dùng section proposal, không dùng bảng S; pending không là issue', () => {
  render(<ReportPanel report={makeB3Report()} />);
  expect(screen.queryByText(/S = E/)).not.toBeInTheDocument();
  expect(screen.getAllByText(/Đang chờ quyết định/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/2[.,]000[.,]000/).length).toBeGreaterThan(0);
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Tổng dự toán');
  expect(text).toContain('8.000.000 đ');
  expect(text).toContain('kế toán ACC-DEMO-01');
  expect(text).toContain('người duyệt APR-DEMO-01');
  expect(text).toContain('dự toán không phải ngân sách đã duyệt');
  expect(text).toContain('Complete nghĩa là đủ căn cứ rà soát, không nghĩa đã duyệt');
});

test('màn mặc định không phơi raw readiness enum; tiêu đề theo job', () => {
  render(<ReportPanel report={makeB3Report()} />);
  const text = screen.getByTestId('report-panel').textContent ?? '';
  // Nhãn người dùng thay cho enum kỹ thuật.
  expect(text).not.toContain('READY_FOR_ACCOUNTANT_REVIEW');
  expect(text).toContain('Đủ để kế toán rà soát');
  // Tiêu đề đúng job, không dùng chung "Thẩm định tài chính".
  expect(text).toContain('Kiểm tra đề nghị tạm ứng');
  expect(text).not.toContain('Thẩm định tài chính');
});

test('report B7 dùng tiêu đề đối chiếu quyết toán', () => {
  render(<ReportPanel report={makeReport({ job: 'B7' })} />);
  const text = screen.getByTestId('report-panel').textContent ?? '';
  expect(text).toContain('Đối chiếu quyết toán');
  expect(text).not.toContain('Thẩm định tài chính');
});

test('report B3 với company context hiển thị grants/coverage và nhãn mô phỏng', () => {
  render(<ReportPanel report={makeB3Report()} b3Context={{
    version: 'synthetic-verbal-v2',
    synthetic: true,
    demo_clock: '2026-10-10T09:00:00+07:00',
    grants: [{
      actor_ref: 'APR-DEMO-01', employee_ref: 'NV-DEMO-01', work_ref: null,
      allow_work: true, max_budget_vnd: 10_000_000,
      max_advance_vnd: 5_000_000,
      effective_from: '2026-10-01T00:00:00+07:00',
      effective_to: '2026-10-31T23:59:59+07:00',
      ref: 'company:grant-01',
    }],
    coverage: [{
      employee_ref: 'NV-DEMO-01', work_ref: null,
      from: '2026-10-01T00:00:00+07:00', to: '2026-10-10T09:00:00+07:00',
      complete_prior_history: true, groups: ['ADVANCE'], methods: ['CASH'],
      missing_ranges: [], owner_ref: 'ACC-DEMO-01',
      origin: 'synthetic register', ref: 'company:coverage-01',
    }],
    history: [],
  }} />);
  const context = screen.getByTestId('b3-run-context').textContent ?? '';
  expect(context).toContain('company:grant-01');
  expect(context).toContain('mô phỏng');
  expect(context).toContain('gồm mở sổ/tồn trước kỳ');
  expect(context).toContain('Lịch sử company-side: trống');
});

test('report B7 không có section B3 proposal', () => {
  render(<ReportPanel report={makeReport()} />);
  expect(screen.queryByTestId('b3-proposal')).not.toBeInTheDocument();
  expect(screen.getByText(/S = E/)).toBeInTheDocument();
});

test('điều kiện NOT_APPLICABLE hiển thị Không áp dụng, không phải CHỜ XỬ LÝ', () => {
  render(<ReportPanel report={makeReport({
    checks: [
      { rule: 'advance_limit', status: 'NOT_APPLICABLE', refs: [], reason: 'Không có hạn mức' },
    ],
  })} />);
  const panel = screen.getByTestId('report-panel');
  expect(panel.textContent).toContain('KHÔNG ÁP DỤNG');
  expect(panel.textContent).not.toContain('CHỜ XỬ LÝ (NOT_APPLICABLE)');
});

test('Task 3: bảng dự toán tinh gọn với các tiêu đề chuẩn và nút căn cứ "Xem dự toán"', () => {
  render(<ReportPanel report={makeB3Report()} />);
  const table = screen.getByTestId('b3-estimate-report');
  expect(table).toBeInTheDocument();
  expect(table.textContent).toContain('Nội dung chi phí');
  expect(table.textContent).toContain('Cơ sở tính toán');
  expect(table.textContent).toContain('Công ty dự kiến trả');
  expect(table.textContent).toContain('Nhân viên dự kiến trả');
  expect(table.textContent).toContain('Căn cứ');
  expect(table.textContent).toContain('Xem dự toán');
});

test('Task 4: bảng đối chiếu nghiệp vụ B3 hiển thị 4 dòng nghiệp vụ và critical facts dạng accordion', () => {
  const b3Report = makeB3Report();
  b3Report.checks = [
    { rule: 'amount_words_consistency', status: 'PASS', refs: ['S-B3-REQ'], reason: 'Khớp số và chữ' },
    { rule: 'estimate_arithmetic', status: 'PASS', refs: ['S-B3-FC'], reason: 'Khớp tổng dòng' },
    { rule: 'proposal_relation', status: 'PASS', refs: ['S-B3-REQ', 'S-B3-FC'], reason: 'Cùng chuyến đi' },
  ];
  b3Report.critical_facts = [
    { key: 'document.role', value: 'ADVANCE_REQUEST, FORECAST', state: 'KNOWN', refs: ['S-B3-REQ', 'S-B3-FC'] },
    { key: 'advance.request.amount', value: 2_000_000, state: 'KNOWN', refs: ['S-B3-REQ'] },
  ];

  render(<ReportPanel report={b3Report} sources={[
    { id: 'S-B3-REQ', filename: '01_giay_de_nghi_tam_ung.pdf', media_type: 'application/pdf', sha256: 'h1', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
    { id: 'S-B3-FC', filename: '02_bang_du_toan.pdf', media_type: 'application/pdf', sha256: 'h2', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
  ]} />);

  const crossCheckTable = screen.getByTestId('business-cross-check-table');
  expect(crossCheckTable).toBeInTheDocument();

  // Dòng 1: Số xin ứng và số bằng chữ
  const row1 = screen.getByTestId('cross-check-words');
  expect(row1.textContent).toContain('Số xin ứng và số bằng chữ');
  expect(row1.textContent).toContain('Khớp: 2.000.000 đ');
  expect(row1.textContent).toContain('Xem giấy đề nghị');

  // Dòng 2: Tổng dự toán và chi tiết các dòng
  const row2 = screen.getByTestId('cross-check-arithmetic');
  expect(row2.textContent).toContain('Tổng dự toán và chi tiết các dòng');
  expect(row2.textContent).toContain('Khớp: 8.000.000 đ');
  expect(row2.textContent).toContain('Xem bảng dự toán');

  // Dòng 3: Thông tin chuyến đi giữa hai giấy
  const row3 = screen.getByTestId('cross-check-trip');
  expect(row3.textContent).toContain('Thông tin chuyến đi giữa hai giấy');
  expect(row3.textContent).toContain('Khớp thông tin chuyến đi');
  expect(row3.textContent).toContain('Xem căn cứ');

  // Dòng 4: Loại chứng từ & Phân vai hồ sơ
  const row4 = screen.getByTestId('cross-check-role');
  expect(row4.textContent).toContain('Loại chứng từ & Phân vai hồ sơ');
  expect(row4.textContent).toContain('Đầy đủ 2 chứng từ theo quy định');
  expect(row4.textContent).toContain('Xem căn cứ');

  // Critical facts nằm trong accordion collapsible
  const accordion = screen.getByTestId('critical-facts-accordion');
  expect(accordion).toBeInTheDocument();
  expect(accordion.textContent).toContain('Chi tiết kỹ thuật: Dữ liệu đã trích xuất từ hồ sơ (Critical facts)');
});

test('Task 4: đối chiếu nghiệp vụ phản ánh đúng trạng thái khi mâu thuẫn hoặc lệch số', () => {
  const b3Report = makeB3Report();
  b3Report.checks = [
    { rule: 'amount_words_consistency', status: 'FAIL', refs: ['S-B3-REQ'], reason: 'Chữ ghi Ba triệu' },
    { rule: 'estimate_arithmetic', status: 'FAIL', refs: ['S-B3-FC'], reason: 'Lệch 1 triệu' },
    { rule: 'proposal_relation', status: 'UNRESOLVED', refs: [], reason: 'Khác địa điểm' },
  ];

  render(<ReportPanel report={b3Report} />);
  const row1 = screen.getByTestId('cross-check-words');
  expect(row1.textContent).toContain('Mâu thuẫn');

  const row2 = screen.getByTestId('cross-check-arithmetic');
  expect(row2.textContent).toContain('Lệch phép tính');

  const row3 = screen.getByTestId('cross-check-trip');
  expect(row3.textContent).toContain('Cần làm rõ');
});

test('R2.2: thiếu check/refs thì nói chưa có kết quả, không tự PASS', () => {
  const b3Report = makeB3Report();
  // No checks and no critical facts: the table must not invent PASS or refs.
  b3Report.checks = [];
  b3Report.critical_facts = [];
  b3Report.source_refs = [];
  render(<ReportPanel report={b3Report} sources={[
    { id: 'S-1', filename: 'de_nghi.pdf', media_type: 'application/pdf', sha256: 'h1', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
    { id: 'S-2', filename: 'du_toan.pdf', media_type: 'application/pdf', sha256: 'h2', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
  ]} />);
  const table = screen.getByTestId('business-cross-check-table');
  const text = table.textContent ?? '';
  // Two same-looking files do NOT make the rows pass or fabricate a basis.
  expect(text).toContain('Chưa có kết quả kiểm tra/căn cứ cho mục này');
  expect(text).not.toContain('Khớp: 2.000.000 đ');
  expect(text).not.toContain('Đầy đủ 2 chứng từ theo quy định');
  // The row basis cells show "—" (no invented refs) but documents are still
  // reachable via the general document links area.
  expect(screen.getByTestId('cross-check-documents')).toBeTruthy();
});

test('R2.2: filename gây nhầm không tạo PASS cho vai chứng từ', () => {
  const b3Report = makeB3Report();
  b3Report.checks = [];
  // Two sources with role-suggesting names but NO document.role fact.
  b3Report.critical_facts = [];
  render(<ReportPanel report={b3Report} sources={[
    { id: 'S-1', filename: '01_giay_de_nghi_tam_ung.pdf', media_type: 'application/pdf', sha256: 'h1', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
    { id: 'S-2', filename: '02_bang_du_toan.pdf', media_type: 'application/pdf', sha256: 'h2', size_bytes: 100, status: 'ACCEPTED', uploader_actor_id: 'NV-1', received_at: '', supersedes_source_id: null, provenance: {} },
  ]} />);
  const row4 = screen.getByTestId('cross-check-role');
  expect(row4.textContent).toContain('Chưa có kết quả kiểm tra/căn cứ cho mục này');
  expect(row4.textContent).not.toContain('Đầy đủ 2 chứng từ theo quy định');
});

test('Task 5: checklist chính sách hiển thị tiêu đề gọn gàng, mã tag nhỏ và không lặp lại reason', () => {
  const report = makeReport({
    checks: [
      { rule: 'destination_scope', status: 'PASS', refs: [], reason: 'Địa điểm công tác nằm trong phạm vi phê duyệt.' },
      { rule: 'advance_limit', status: 'PASS', refs: [], reason: 'Số tiền tạm ứng không vượt hạn mức công ty.' },
    ],
  });

  render(<ReportPanel report={report} />);
  const panel = screen.getByTestId('report-panel');

  // Header tiêu đề mới: "[passCount] mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát."
  expect(panel.textContent).toContain('2 mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát.');
  expect(panel.textContent).not.toContain('2/2 điều kiện tuân thủ quy chế tài chính');

  // Tag mã rule nhỏ
  expect(panel.textContent).toContain('(mã: destination_scope)');
  expect(panel.textContent).toContain('(mã: advance_limit)');

  // Kiểm tra không lặp lại câu {rule}: {status} — {reason}
  expect(panel.textContent).not.toContain('destination_scope: PASS — Địa điểm công tác nằm trong phạm vi phê duyệt.');
});


test('hiển thị bảng đối chiếu claim↔expense khi có claim_comparisons', () => {
  const report = makeReport({
    claim_comparisons: [{
      claim_id: 'CL-hotel', expense_id: 'EXP-hotel',
      declared_amount_vnd: 3_000_000, verified_amount_vnd: 2_500_000,
      payer_declaration: 'PERSONAL', verified_payer: 'COMPANY',
      status: 'CONFLICT', refs: ['company:INV-H'],
      reason: 'Số khai khác chi phí thực tế.',
    }],
  });
  render(<ReportPanel report={report} />);
  const table = screen.getByTestId('claim-comparisons');
  expect(table).toHaveTextContent('CL-hotel');
  expect(table).toHaveTextContent('CONFLICT');
  expect(table).toHaveTextContent('2.500.000');
});
