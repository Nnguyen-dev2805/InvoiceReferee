import { describe, expect, test } from 'vitest';
import {
  checkLabel,
  errorText,
  factLabel,
  formatMoney,
  historyKindLabel,
  roleLabel,
  stageLabel,
} from './uiCopy';

describe('uiCopy', () => {
  test('formatMoney handles null, zero, and positive amounts', () => {
    expect(formatMoney(null)).toBe('Chưa xác định');
    expect(formatMoney(undefined)).toBe('Chưa xác định');
    expect(formatMoney(0)).toBe('0 đ');
    expect(formatMoney(2_000_000)).toBe('2.000.000 đ');
    expect(formatMoney(3_500_000)).toBe('3.500.000 đ');
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
    expect(roleLabel('APPROVER')).toBe('Người duyệt');
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
});
