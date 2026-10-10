import type { CaseStage, DemoRole } from './types';

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Chưa xác định';
  }
  if (value === 0) {
    return '0 đ';
  }
  return `${value.toLocaleString('vi-VN')} đ`;
}

export function stageLabel(stage: CaseStage): string {
  switch (stage) {
    case 'CHECKING':
      return 'Đang kiểm tra nguồn';
    case 'ACCOUNTING_REVIEW':
      return 'Kế toán rà soát';
    case 'AWAITING_DECISION':
      return 'Chờ người có quyền quyết định';
    case 'AWAITING_MONEY':
      return 'Chờ thực nhận tiền';
    case 'AWAITING_WORK_SETTLEMENT':
      return 'Chờ quyết toán chi phí';
    case 'RESOLVING_OBLIGATIONS':
      return 'Đang xử lý nghĩa vụ';
    case 'REJECTED_REQUEST_ENDED':
      return 'Yêu cầu bị từ chối đã kết thúc';
    case 'SETTLEMENT_CLOSED':
      return 'Hồ sơ đã đóng';
    default:
      return stage;
  }
}

export function roleLabel(role: DemoRole): string {
  switch (role) {
    case 'EMPLOYEE':
      return 'Nhân viên';
    case 'ACCOUNTANT':
      return 'Kế toán';
    case 'APPROVER':
      return 'Người duyệt';
    default:
      return role;
  }
}

const CHECK_LABELS: Record<string, string> = {
  // B3 rules
  trip_context: 'Thông tin chuyến công tác',
  request_positive: 'Số tiền đề nghị tạm ứng',
  amount_words_consistency: 'Khớp số tiền và chữ viết',
  estimate_arithmetic: 'Số học bảng dự toán',
  request_forecast_consistency: 'Khớp số xin ứng và dự toán',
  proposal_relation: 'Liên kết chứng từ & đề nghị',
  source_form_consistency: 'Khớp dữ liệu giấy và form',
  history_coverage: 'Lịch sử tạm ứng & hoàn ứng',
  prior_advance_state: 'Trạng thái tạm ứng trước',
  decision_route: 'Tuyến phê duyệt đề xuất',

  // B7 & general rules
  eligibility: 'Tính hợp lệ của chi phí',
  payer_parts: 'Phân định người chi trả',
  budget: 'Ngân sách được duyệt',
  authority: 'Thẩm quyền phê duyệt',
  forecast: 'Dự toán kinh phí',
  fact_quality: 'Chất lượng dữ liệu đọc được',
  contradictions: 'Tính nhất quán của chứng từ',
  relation_status: 'Trạng thái đối soát chứng từ',
  duplicate_events: 'Kiểm tra trùng lặp sự kiện',
};

export function checkLabel(rule: string): string {
  return CHECK_LABELS[rule] ?? 'Mục kiểm tra khác';
}

const FACT_LABELS: Record<string, string> = {
  'history.advance.received': 'Tạm ứng nhân viên đã nhận (A)',
  'history.advance.returned': 'Hoàn tạm ứng công ty đã nhận (RA)',
  'history.reimbursement.received': 'Hoàn trả nhân viên đã nhận (P)',
  'history.reimbursement.returned': 'Nhận lại từ khoản hoàn trả (RP)',
  'budget.approved': 'Ngân sách được duyệt (B)',
  'advance.request.amount': 'Số tiền xin tạm ứng',
  'forecast.employee': 'Dự toán nhân viên tự chi',
  'forecast.company': 'Dự toán công ty chi trả',
  'trip.destination': 'Nơi đến',
  'trip.start': 'Ngày bắt đầu công tác',
  'trip.end': 'Ngày kết thúc công tác',
  'trip.purpose': 'Mục đích công tác',
};

export function factLabel(key: string): string {
  if (FACT_LABELS[key]) return FACT_LABELS[key];
  if (key.startsWith('expense.') && key.endsWith('.amount')) return 'Số tiền chi phí';
  if (key.startsWith('expense.') && key.endsWith('.purpose')) return 'Mục đích chi tiêu';
  if (key.startsWith('payment.') && key.endsWith('.amount')) return 'Số tiền thanh toán';
  if (key.startsWith('payment.') && key.endsWith('.payer')) return 'Bên chi trả';
  if (key.startsWith('payment.') && key.endsWith('.status')) return 'Trạng thái thanh toán';
  return key;
}

const ERROR_TEXTS: Record<string, string> = {
  STALE_VERSION: 'Hồ sơ đã được cập nhật ở nơi khác. Vui lòng tải lại trước khi tiếp tục.',
  UNSUPPORTED_FORMAT: 'Định dạng chưa được hỗ trợ. Hãy dùng PDF, JPG, PNG, CSV hoặc văn bản.',
  UNSUPPORTED_MEDIA_TYPE: 'Định dạng chưa được hỗ trợ. Hãy dùng PDF, JPG, PNG, CSV hoặc văn bản.',
  FILE_TOO_LARGE: 'Tệp vượt quá giới hạn 20 MiB của hệ thống.',
  PAYLOAD_TOO_LARGE: 'Tệp vượt quá giới hạn 20 MiB của hệ thống.',
  PERMISSION_DENIED: 'Vai trò hiện tại không được thực hiện thao tác này.',
  ROLE_NOT_AUTHORIZED: 'Vai trò hiện tại không được thực hiện thao tác này.',
  PROVIDER_FAILURE: 'Chưa đọc được tài liệu này do lỗi dịch vụ.',
  OCR_FAILED: 'Chưa đọc được tài liệu này do lỗi dịch vụ OCR.',
  LLM_FAILED: 'Chưa đọc được tài liệu này do lỗi dịch vụ AI.',
  STOP_ACTIVE: 'Hồ sơ đang tạm dừng xử lý; không thể thực hiện thao tác.',
  CASE_STOPPED: 'Hồ sơ đang tạm dừng xử lý; không thể thực hiện thao tác.',
  CLOSURE_BLOCKED: 'Chưa thể đóng hồ sơ do còn nghĩa vụ hoặc việc cần làm rõ.',
  SUPERSEDED: 'Kết quả thuộc về bản kiểm tra cũ.',
  CONTEXT_MISSING: 'Chưa có dữ liệu nhân viên và tuyến duyệt để thử luồng này.',
};

export function errorText(code: string | null): string {
  if (!code) return 'Đã xảy ra lỗi không xác định.';
  return ERROR_TEXTS[code] ?? code;
}

const HISTORY_KIND_LABELS: Record<string, string> = {
  CASE_CREATED: 'Tạo hồ sơ',
  SOURCE_ADDED: 'Thêm tài liệu',
  SUBMISSION_REVISED: 'Cập nhật thông tin',
  RUN_CREATED: 'Bắt đầu kiểm tra',
  RUN_SUCCEEDED: 'Hoàn thành kiểm tra',
  RUN_FAILED: 'Kiểm tra thất bại',
  REVIEW_RECORDED: 'Kế toán lưu rà soát',
  DECISION_RECORDED: 'Ghi nhận quyết định',
  MONEY_RECORDED: 'Ghi sự kiện tiền',
  HANDOFF_CREATED: 'Bàn giao chi tiền',
  QUESTION_ANSWERED: 'Trả lời câu hỏi',
  CASE_CONTROLLED: 'Điều khiển hồ sơ (Stop/Resume)',
  CASE_CLOSED: 'Đóng hồ sơ',
};

export function historyKindLabel(kind: string): string {
  return HISTORY_KIND_LABELS[kind] ?? 'Thao tác khác';
}

