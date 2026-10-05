// Display helpers. These format values for humans; they never decide business
// meaning (that lives in the backend decision).
import type { Decision, DecisionAction, DemoMode, ExecutionStatus, Issue, IssueClass, WorkflowState } from './types';

const VND = new Intl.NumberFormat('vi-VN');

export function formatVnd(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '—';
  return `${VND.format(amount)}₫`;
}

/** Format raw numeric string with Vietnamese thousands separators while user types */
export function formatCurrencyInput(raw: string): string {
  const digits = raw.replace(/[^\d]/g, '');
  if (!digits) return '';
  const num = Number(digits);
  if (!Number.isSafeInteger(num) || num <= 0) return digits;
  return VND.format(num);
}

/** Parse formatted currency string into safe integer VND */
export function parseCurrencyInput(formatted: string): number {
  const digits = formatted.replace(/[^\d]/g, '');
  const num = Number(digits);
  return Number.isSafeInteger(num) && num > 0 ? num : 0;
}

export const ACTION_LABEL: Record<DecisionAction, string> = {
  CREATE_PAYMENT_REQUEST: 'Tạo đề nghị chi trả',
  REQUEST_INFO: 'Cần bổ sung thông tin',
  ESCALATE: 'Chuyển người có thẩm quyền',
  REJECT: 'Từ chối',
  NONE: 'Không hành động',
};

export const ISSUE_CLASS_LABEL: Record<IssueClass, string> = {
  FACTUAL_UNKNOWN: 'Thiếu/không chắc dữ kiện',
  OUTSIDE_POLICY: 'Ngoài quy định',
  BEYOND_AUTHORITY: 'Vượt thẩm quyền',
};

export const WORKFLOW_LABEL: Record<WorkflowState, string> = {
  DRAFT: 'Bản nháp',
  REVIEWING: 'Đang kiểm tra',
  WAITING_INPUT: 'Chờ bổ sung',
  WAITING_APPROVAL: 'Chờ phê duyệt',
  REQUEST_CREATED: 'Đã tạo đề nghị chi trả',
  REJECTED: 'Đã từ chối',
  STOPPED: 'Đã dừng',
  TECHNICAL_ERROR: 'Lỗi kỹ thuật',
};

export const RUN_STATUS_LABEL: Record<ExecutionStatus, string> = {
  QUEUED: 'Đang chờ',
  RUNNING: 'Đang xử lý',
  STOP_REQUESTED: 'Đang dừng',
  STOPPED: 'Đã dừng',
  SUCCEEDED: 'Hoàn tất',
  FAILED: 'Thất bại',
};

export function runInFlight(status: ExecutionStatus): boolean {
  return status === 'QUEUED' || status === 'RUNNING' || status === 'STOP_REQUESTED';
}

// --- Demo roles (single source of truth for the role selector + inbox) ---------

export const MODE_ORDER: DemoMode[] = ['EMPLOYEE', 'REVIEWER', 'APPROVER', 'POLICY_OWNER'];

export const MODE_LABEL: Record<DemoMode, string> = {
  EMPLOYEE: 'Nhân viên',
  REVIEWER: 'Kế toán / Reviewer',
  APPROVER: 'Người phê duyệt',
  POLICY_OWNER: 'Chủ sở hữu policy',
};

/** Open issues a role must act on. Presentation only — the backend enforces scope. */
export function openIssuesForRole(decision: Decision | null | undefined, mode: DemoMode): Issue[] {
  if (!decision) return [];
  return decision.issues.filter((issue) => issue.status === 'OPEN' && issue.owner_mode === mode);
}

// --- Stage labels (what the pipeline is doing right now) -----------------------

const STAGE_LABEL: Record<string, string> = {
  created: 'Đã tạo hồ sơ',
  intake: 'Tiếp nhận hồ sơ',
  finalized: 'Đã hoàn tất',
  policy: 'Áp policy',
  'before:evaluate': 'Đang tổng hợp quyết định',
  'before:return': 'Đang trả kết quả',
  'cross_source': 'Đang đối chiếu nguồn',
};

/** Turn a raw run stage like `analyze:ev-...:before` into a human label. */
export function stageLabel(stage: string | null | undefined): string | null {
  if (!stage) return null;
  if (STAGE_LABEL[stage]) return STAGE_LABEL[stage];
  const [head, , phase] = stage.split(':');
  const verb: Record<string, string> = { ocr: 'Đang đọc chứng từ', analyze: 'Đang trích xuất dữ kiện', apply: 'Đang áp dụng dữ kiện' };
  if (verb[head]) return phase === 'before' ? `${verb[head]}…` : `${verb[head]} — xong`;
  return stage;
}
