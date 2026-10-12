// B8 settlement-decision panel (b7-linked-intake-v1).
//
// Accountant presents the current settlement; approver APPROVES/RETURNS/REFUSES
// on the exact basis. The target (E/S/direction/amount) is server-derived and
// readonly here — the panel never calculates net or rights. Approval is not
// receipt.
import { useMemo, useState } from 'react';
import * as api from './api';
import { formatMoney } from './displayText';
import type {
  AuditEntry, B7DecisionOutcome, B7DecisionTarget, CaseView, DemoRole, Report,
} from './types';

function formatVnd(value: number | null | undefined): string {
  return formatMoney(value, { nullText: '—' });
}

function B7DecisionSummary({ target }: { target: B7DecisionTarget | null }) {
  if (!target) return <p className="muted">Chưa có quyết định phê duyệt.</p>;
  const label = {
    PAY_EMPLOYEE: 'Số tiền công ty cần trả thêm',
    COLLECT_FROM_EMPLOYEE: 'Số tiền nhân viên cần hoàn lại',
    BALANCED: 'Quyết toán cân bằng — không cần chi hoặc thu',
  }[target.direction];
  return (
    <p>
      <strong>{label}</strong>
      {target.direction === 'BALANCED' ? '' : `: ${formatVnd(target.amount_vnd)}`}
    </p>
  );
}

interface B7ApprovalProps {
  view: CaseView;
  report?: Report | null;
  history: AuditEntry[];
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
}

interface ReviewRecord {
  id: string;
  report_id: string;
  note: string;
  refs: string[];
  actor_id: string;
  created_at: string;
}

function currentReview(history: AuditEntry[], reportId: string | null,
                       actorId: string): ReviewRecord | null {
  if (!reportId) return null;
  for (const entry of [...history].reverse()) {
    if (entry.kind !== 'REVIEW_RECORDED') continue;
    const review = entry.detail?.review as ReviewRecord | undefined;
    if (review && review.report_id === reportId
        && review.actor_id === actorId) {
      return review;
    }
  }
  return null;
}

export function B7ApprovalPanel({
  view, history, role, actorId, onAction,
}: B7ApprovalProps) {
  const workflow = view.b7_workflow ?? null;
  const reportId = view.current_run_id;
  const savedReview = useMemo(
    () => currentReview(history, reportId, actorId.trim()),
    [history, reportId, actorId]);

  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  if (!workflow) return null;

  const presentation = workflow.presentation;
  const decision = workflow.decision;
  const isAccountant = role === 'ACCOUNTANT';
  const isApprover = role === 'APPROVER';
  const canPresent = isAccountant
    && (workflow.status === 'NOT_PRESENTED'
        || workflow.status === 'RETURNED'
        || workflow.status === 'NEEDS_RECHECK');
  const canDecide = isApprover && workflow.status === 'PENDING'
    && presentation !== null && workflow.basis_current;

  const present = () => {
    setBusy(true);
    const payload = savedReview
      ? { actor_id: actorId.trim(), demo_role: role,
          expected_case_version: view.case_version,
          basis_report_id: reportId ?? '', review_id: savedReview.id }
      : { actor_id: actorId.trim(), demo_role: role,
          expected_case_version: view.case_version,
          basis_report_id: reportId ?? '',
          review: { report_id: reportId ?? '', note: note.trim(), refs: [] } };
    void onAction('PRESENT_B7', () => api.presentB7(view.id, payload as never))
      .finally(() => setBusy(false));
  };

  const decide = (outcome: B7DecisionOutcome) => {
    setBusy(true);
    void onAction(`B7_${outcome}`, () => api.decideB7(view.id, {
      actor_id: actorId.trim(), demo_role: role,
      expected_case_version: view.case_version,
      presentation_id: presentation?.id ?? '',
      outcome, reason: reason.trim(),
    })).finally(() => setBusy(false));
  };

  // --- Approved: reflect the actual fulfillment/closure state, not a fixed
  // "not yet received" message. Unknown is not received 0; BALANCED is not a
  // fake 0 payment.
  if (decision && decision.outcome === 'APPROVE') {
    const fulfillment = workflow.fulfillment;
    const closureView = workflow.closure;
    const isBalanced = decision.target?.direction === 'BALANCED';
    const received = fulfillment?.recorded_received_vnd;
    return (
      <div className="panel" id="b7-approval-panel" data-testid="b7-approval-panel">
        <h2>{closureView ? 'Quyết toán đã đóng'
          : isBalanced ? 'Đã duyệt quyết toán — cân bằng'
            : 'Đã duyệt quyết toán — theo dõi chi/thu'}</h2>
        <B7DecisionSummary target={decision.target} />
        <ul className="reasons" data-testid="b7-approved-summary">
          <li><strong>Chi phí nhân viên được duyệt (E):</strong> {formatVnd(decision.target?.employee_cost_vnd)}</li>
          <li><strong>Đã đối chiếu thực nhận:</strong> {
            isBalanced
              ? 'Cân bằng — không cần chi/thu'
              : (received === null || received === undefined
                  ? 'Chưa ghi nhận' : formatVnd(received))}</li>
          {fulfillment && !isBalanced && (
            <li><strong>Còn lại:</strong> {
              fulfillment.remaining_vnd === null
                ? 'Chưa xác định (còn pending/unknown)'
                : formatVnd(fulfillment.remaining_vnd)}</li>
          )}
        </ul>
        <p className="muted">{decision.reason}</p>
        <p className="muted">
          {closureView
            ? 'Hồ sơ quyết toán đã đóng; nguồn mới có ảnh hưởng mở hồ sơ điều chỉnh liên kết.'
            : isBalanced
              ? 'Quyết toán cân bằng: đủ gate để đóng mà không tạo sự kiện tiền 0.'
              : 'Kế toán ghi nhận chi/thu thực tế theo nguồn; receipt đúng giảm phần còn lại nhưng không hủy quyết định.'}
        </p>
      </div>
    );
  }

  // --- Returned / Refused ---
  if (decision && (decision.outcome === 'RETURN' || decision.outcome === 'REFUSE')) {
    return (
      <div className="panel" id="b7-approval-panel" data-testid="b7-approval-panel">
        <h2>{decision.outcome === 'RETURN'
          ? 'Yêu cầu làm rõ' : 'Từ chối đề nghị quyết toán'}</h2>
        <p className="notice notice-warn" role="alert">{decision.reason}</p>
        <p className="muted">
          {decision.outcome === 'RETURN'
            ? 'Bổ sung/chỉnh sửa rồi kiểm lại và trình lại; nghĩa vụ tiền vẫn giữ.'
            : 'Đề nghị bị từ chối; nghĩa vụ tiền đã có vẫn giữ, không tự thu hồi.'}
        </p>
      </div>
    );
  }

  // --- Pending: approver decides; accountant/employee read ---
  if (workflow.status === 'PENDING' && presentation) {
    return (
      <div className="panel" id="b7-approval-panel" data-testid="b7-approval-panel">
        <h2>Chờ duyệt quyết toán</h2>
        <div className="review-summary-card">
          <div className="review-summary-line">
            Kế toán <strong>{presentation.accountant_ref}</strong> đã trình · người
            duyệt <strong>{presentation.approver_ref}</strong> · căn cứ report{' '}
            <code>{presentation.basis_report_id}</code>
          </div>
        </div>
        <B7DecisionSummary target={presentation.target} />
        {!workflow.basis_current && (
          <p className="notice notice-warn" role="alert">
            {workflow.blocked_reasons.join('; ') || 'Căn cứ đã đổi; cần chạy và trình lại.'}
          </p>
        )}
        {isApprover && canDecide ? (
          <div className="field">
            <h3>Quyết định (người duyệt)</h3>
            <label htmlFor="b7-reason">Lý do</label>
            <input id="b7-reason" value={reason}
                   onChange={(e) => setReason(e.target.value)}
                   placeholder="Duyệt theo kết quả đã rà soát." />
            <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <button className="btn btn-primary" disabled={busy || !reason.trim()}
                      onClick={() => decide('APPROVE')}>
                Phê duyệt quyết toán
              </button>
              <button className="btn" disabled={busy || !reason.trim()}
                      onClick={() => decide('RETURN')}>
                Yêu cầu làm rõ
              </button>
              <button className="btn" disabled={busy || !reason.trim()}
                      onClick={() => decide('REFUSE')}>
                Từ chối đề nghị
              </button>
            </div>
          </div>
        ) : (
          <p className="muted">Đang chờ người có quyền duyệt quyết toán.</p>
        )}
      </div>
    );
  }

  // --- NOT_PRESENTED / RETURNED / NEEDS_RECHECK: accountant presents ---
  if (isAccountant) {
    return (
      <div className="panel" id="b7-approval-panel" data-testid="b7-approval-panel">
        <h2>Trình duyệt quyết toán</h2>
        {savedReview ? (
          <div className="review-summary-card" data-testid="b7-saved-review">
            <div className="review-summary-line">
              Đã có rà soát của <strong>{savedReview.actor_id}</strong> cho report{' '}
              <code>{savedReview.report_id}</code> — ghi chú: <em>"{savedReview.note}"</em>
            </div>
          </div>
        ) : (
          <>
            <label htmlFor="b7-present-note">Ghi chú rà soát</label>
            <input id="b7-present-note" value={note}
                   onChange={(e) => setNote(e.target.value)}
                   placeholder="Đã đối chiếu bảng và mở nguồn gốc." />
          </>
        )}
        <button className="btn btn-primary"
                style={{ marginTop: 'var(--space-2)' }}
                disabled={!reportId || !canPresent || busy
                  || (!savedReview && !note.trim())}
                onClick={present}>
          {savedReview ? 'Trình duyệt quyết toán' : 'Lưu rà soát và trình duyệt'}
        </button>
      </div>
    );
  }

  // Employee / approver with nothing to act on.
  return (
    <div className="panel" id="b7-approval-panel" data-testid="b7-approval-panel">
      <h2>Quyết toán</h2>
      <p className="muted">
        {workflow.status === 'NEEDS_RECHECK'
          ? 'Căn cứ đã thay đổi; cần kế toán chạy và trình lại.'
          : 'Chưa được trình duyệt; kế toán sẽ rà soát và trình người có quyền.'}
      </p>
    </div>
  );
}
