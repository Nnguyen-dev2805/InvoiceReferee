import { describe, expect, test } from 'vitest';
import {
  STAGE_LABELS,
  checkLabel,
  dossierReference,
  errorText,
  factLabel,
  formatMoney,
  getInitials,
  historyKindLabel,
  roleLabel,
  stageLabel,
} from './displayText';
import type { CaseStage, CaseView } from './types';

const ALL_STAGES: CaseStage[] = [
  'CHECKING', 'ACCOUNTING_REVIEW', 'AWAITING_DECISION', 'AWAITING_MONEY',
  'AWAITING_WORK_SETTLEMENT', 'RESOLVING_OBLIGATIONS', 'ADVANCE_REQUEST_REFUSED',
  'SETTLEMENT_REQUEST_REFUSED', 'READY_TO_CLOSE', 'REJECTED_REQUEST_ENDED',
  'SETTLEMENT_CLOSED',
];

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-01', job: 'B7', case_version: 1, input_revision: 1, control_epoch: 1,
    stop_active: false, stage: 'CHECKING', current_run_id: null,
    submission: {
      employee_ref: 'NV-01', work_ref: 'C-01', job: 'B7',
      money_as_of: '2026-10-10T02:00:00Z',
      knowledge_cutoff: '2026-10-10T02:00:00Z', form: {},
    },
    sources: [], allowed_actions: [],
    money_summary: { approved_vnd: null, received_vnd: null, remaining_vnd: null,
                     pending_events: 0, incidents: [] },
    created_at: '2026-10-10T02:00:00Z', updated_at: '2026-10-10T02:00:00Z',
    ...overrides,
  };
}

describe('displayText', () => {
  test('formatMoney handles null, zero, and positive amounts', () => {
    expect(formatMoney(null)).toBe('Chưa xác định');
    expect(formatMoney(undefined)).toBe('Chưa xác định');
    expect(formatMoney(0)).toBe('0 đ');
    expect(formatMoney(2_000_000)).toBe('2.000.000 đ');
    expect(formatMoney(3_500_000)).toBe('3.500.000 đ');
  });

  test('formatMoney honours a caller nullText for unknown amounts', () => {
    expect(formatMoney(null, { nullText: '—' })).toBe('—');
    expect(formatMoney(undefined, { nullText: '—' })).toBe('—');
    expect(formatMoney(2_000_000, { nullText: '—' })).toBe('2.000.000 đ');
  });

  test('formatMoney never renders a signed zero', () => {
    expect(formatMoney(-0)).toBe('0 đ');
  });

  test('STAGE_LABELS covers every stage with the stageLabel text', () => {
    for (const stage of ALL_STAGES) {
      expect(STAGE_LABELS[stage]).toBeTruthy();
      expect(STAGE_LABELS[stage]).toBe(stageLabel(stage));
    }
    expect(Object.keys(STAGE_LABELS).sort()).toEqual([...ALL_STAGES].sort());
    // The previously divergent App-only wording must not reappear.
    expect(STAGE_LABELS.AWAITING_WORK_SETTLEMENT).toBe('Chờ quyết toán chi phí');
  });

  test('stageLabel provides clean business Vietnamese translations', () => {
    expect(stageLabel('CHECKING')).toBe('Đang kiểm tra nguồn');
    expect(stageLabel('ACCOUNTING_REVIEW')).toBe('Kế toán rà soát');
    expect(stageLabel('AWAITING_DECISION')).toBe('Chờ người có quyền quyết định');
    expect(stageLabel('AWAITING_MONEY')).toBe('Chờ thực nhận tiền');
    expect(stageLabel('AWAITING_WORK_SETTLEMENT')).toBe('Chờ quyết toán chi phí');
    expect(stageLabel('SETTLEMENT_CLOSED')).toBe('Hồ sơ đã đóng');
  });

  test('roleLabel translates demo roles to clear titles', () => {
    expect(roleLabel('EMPLOYEE')).toBe('Nhân viên');
    expect(roleLabel('ACCOUNTANT')).toBe('Kế toán');
    expect(roleLabel('APPROVER')).toBe('Người phê duyệt');
  });

  test('dossierReference uses server field, then typed link, else own id', () => {
    expect(dossierReference(makeView({ dossier_ref: 'C-root' }))).toBe('C-root');
    // Old view without the server field but with a typed linked origin.
    expect(dossierReference(makeView({
      linked_b7: {
        origin: { origin_case_id: 'C-parent', employee_ref: 'NV-01',
                  work_ref: 'WORK-1', created_at: '2026-10-11T10:00:00Z' },
        context_source_id: null, context_current: false, blocked_reasons: [],
        managed_advance_subtotal_vnd: null,
      },
    }))).toBe('C-parent');
    // Standalone / B3 with no link → own id.
    expect(dossierReference(makeView({ id: 'C-self' }))).toBe('C-self');
  });

  test('checkLabel maps B3 and B7 rule keys to Vietnamese descriptions', () => {
    expect(checkLabel('trip_context')).toBe('Thông tin chuyến công tác');
    expect(checkLabel('request_positive')).toBe('Số tiền đề nghị tạm ứng');
    expect(checkLabel('estimate_arithmetic')).toBe('Số học bảng dự toán');
    expect(checkLabel('eligibility')).toBe('Tính hợp lệ của chi phí');
    expect(checkLabel('budget')).toBe('Ngân sách được duyệt');
    expect(checkLabel('authority')).toBe('Thẩm quyền phê duyệt');
    expect(checkLabel('history_coverage')).toBe('Lịch sử tạm ứng & hoàn ứng');
    expect(checkLabel('unknown_rule_xyz')).toBe('Mục kiểm tra khác');
  });

  test('factLabel maps observation keys to Vietnamese labels', () => {
    expect(factLabel('history.advance.received')).toBe('Tạm ứng nhân viên đã nhận (A)');
    expect(factLabel('budget.approved')).toBe('Ngân sách được duyệt (B)');
    expect(factLabel('advance.request.amount')).toBe('Số tiền xin tạm ứng');
    expect(factLabel('forecast.employee')).toBe('Dự toán nhân viên tự chi');
  });

  test('errorText maps technical error codes to actionable advice', () => {
    expect(errorText('STALE_VERSION')).toContain('Hồ sơ đã được cập nhật');
    expect(errorText('UNSUPPORTED_FORMAT')).toContain('PDF, JPG, PNG');
    expect(errorText('FILE_TOO_LARGE')).toContain('20 MiB');
  });

  test('historyKindLabel maps history kinds to friendly Vietnamese names', () => {
    expect(historyKindLabel('CASE_CREATED')).toBe('Tạo hồ sơ');
    expect(historyKindLabel('SOURCE_ADDED')).toBe('Thêm tài liệu');
    expect(historyKindLabel('SUBMISSION_REVISED')).toBe('Cập nhật thông tin');
    expect(historyKindLabel('RUN_SUCCEEDED')).toBe('Hoàn thành kiểm tra');
    expect(historyKindLabel('UNKNOWN_EVENT_XYZ')).toBe('Thao tác khác');
  });

  test('getInitials extracts clean uppercase initials from person names', () => {
    expect(getInitials('Nguyễn An')).toBe('NA');
    expect(getInitials('Trần Bình')).toBe('TB');
    expect(getInitials('Lê Chi')).toBe('LC');
    expect(getInitials('Nguyễn Văn Hoà')).toBe('NH');
    expect(getInitials('Admin')).toBe('AD');
    expect(getInitials('')).toBe('U');
  });
});
