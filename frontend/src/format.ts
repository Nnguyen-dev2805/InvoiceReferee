// Display helpers. These format values for humans; they never decide business
// meaning (that lives in the backend decision).
import type { DecisionAction, ExecutionStatus, IssueClass, WorkflowState } from './types';

const VND = new Intl.NumberFormat('vi-VN');

export function formatVnd(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '—';
  return `${VND.format(amount)}₫`;
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
