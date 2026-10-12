// B3 present-and-approve panel (b3-intake-v1).
//
// Accountant: save a review note/refs (or reuse a saved one) and present the
// basis to the configured approver. Approver: APPROVE / RETURN / REFUSE with a
// reason. Employee: read the outcome and approved figures. The backend owns
// authority, basis currency and stage — this panel only chooses how to render
// and never derives permission from the demo role picker.
import { useEffect, useMemo, useState } from 'react';
import * as api from './api';
import { formatMoney } from './displayText';
import type {
  AuditEntry, B3DecisionOutcome, CaseView, DemoRole, Report,
} from './types';

function formatVnd(value: number | null | undefined): string {
  return formatMoney(value, { nullText: '—' });
}

interface B3ApprovalProps {
  view: CaseView;
  report: Report | null;
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

/** The accountant's own review bound to the current report, if any. */
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

export function B3ApprovalPanel({
  view, report, history, role, actorId, onAction,
}: B3ApprovalProps) {
  const workflow = view.b3_workflow ?? null;
  const reportId = view.current_run_id;
  const b3 = report?.b3 ?? null;
  const requested = b3?.intake.request_amount_vnd ?? null;
  const forecastTotal = b3?.forecast_total_vnd ?? null;

  const savedReview = useMemo(
    () => currentReview(history, reportId, actorId.trim()),
    [history, reportId, actorId]);

  const [note, setNote] = useState('');
  const [refs, setRefs] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [allowWork, setAllowWork] = useState(false);
  const [budget, setBudget] = useState('');
  const [advance, setAdvance] = useState('');

  // Suggest budget/advance from the proposal, but never auto-approve.
  useEffect(() => {
    if (budget === '' && forecastTotal !== null) setBudget(String(forecastTotal));
  }, [forecastTotal]);
  useEffect(() => {
    if (advance === '' && requested !== null) setAdvance(String(requested));
  }, [requested]);

  if (!workflow) return null;

  const presentation = workflow.presentation;
  const decision = workflow.decision;
  const canPresent = workflow.status !== 'REFUSED'
    && decision === null
    && (workflow.status === 'NOT_PRESENTED'
        || workflow.status === 'RETURNED'
        || workflow.status === 'NEEDS_RECHECK');
  const canDecide = workflow.status === 'PENDING' && presentation !== null
    && workflow.basis_current && !view.stop_active;

  const presentBody = () => {
    if (savedReview) {
      return {
        actor_id: actorId.trim(), demo_role: role,
        expected_case_version: view.case_version,
        basis_report_id: reportId ?? '',
        review_id: savedReview.id,
      };
    }
    return {
      actor_id: actorId.trim(), demo_role: role,
      expected_case_version: view.case_version,
      basis_report_id: reportId ?? '',
      review: { report_id: reportId ?? '', note: note.trim(), refs },
    };
  };

  const budgetNum = budget.trim() === '' ? null : Number(budget);
  const advanceNum = advance.trim() === '' ? null : Number(advance);
  const approveValid = allowWork
    && budgetNum !== null && Number.isFinite(budgetNum) && budgetNum > 0
    && advanceNum !== null && Number.isFinite(advanceNum) && advanceNum > 0
    && reason.trim() !== '';

  const submitDecision = (outcome: B3DecisionOutcome) => {
    const payload: Record<string, unknown> = {
      actor_id: actorId.trim(), demo_role: role,
      expected_case_version: view.case_version,
      presentation_id: presentation?.id ?? '',
      outcome, reason: reason.trim(),
    };
    if (outcome === 'APPROVE') {
      payload.work_allowed = true;
      payload.budget_vnd = budgetNum;
      payload.advance_vnd = advanceNum;
    }
    return api.decideB3(view.id, payload as never);
  };

  // --- Approved (terminal for this slice) ---
  if (decision && decision.outcome === 'APPROVE') {
    return (
      <div className="panel" id="b3-approval-panel" data-testid="b3-approval-panel">
        <h2>Đã duyệt tạm ứng — chờ chi ứng</h2>
        <ul className="reasons">
          <li><strong>Công việc được phép:</strong> {decision.work_allowed ? 'Có' : 'Không'}</li>
          <li><strong>Ngân sách đã duyệt (B):</strong> {formatVnd(decision.budget_vnd)}</li>
          <li><strong>Số xin tạm ứng:</strong> {formatVnd(requested)}</li>
          <li><strong>Số ứng đã duyệt:</strong> {formatVnd(decision.advance_vnd)}</li>
          <li><strong>Thực nhận:</strong> Chưa ghi nhận</li>
        </ul>
        <p className="muted">{decision.reason}</p>
        {!workflow.basis_current && (
          <p className="notice notice-warn" role="alert">
            Căn cứ đã thay đổi kể từ khi duyệt — cần kiểm lại trước khi chi.
          </p>
        )}
        <p className="muted">
          Chưa ghi nhận tiền thực nhận và chưa có đường chi ngân hàng trong lát cắt này.
        </p>
      </div>
    );
  }

  // --- Returned / Refused: read-only outcome + reason ---
  if (decision && (decision.outcome === 'RETURN' || decision.outcome === 'REFUSE')) {
    return (
      <div className="panel" id="b3-approval-panel" data-testid="b3-approval-panel">
        <h2>{decision.outcome === 'RETURN'
          ? 'Yêu cầu bổ sung' : 'Đề nghị tạm ứng bị từ chối'}</h2>
        <p className="notice notice-warn" role="alert">{decision.reason}</p>
        {decision.outcome === 'RETURN' ? (
          <p className="muted">
            Nhân viên sửa/xác nhận lại, chạy kiểm tra, kế toán trình lại. Không
            tạo hồ sơ hay mã công việc mới.
          </p>
        ) : (
          <p className="muted">
            Từ chối có hiệu lực cho đề nghị này; chưa có đường mở lại. Không hủy
            tiền hay nguồn đã có.
          </p>
        )}
      </div>
    );
  }

  // --- Pending: approver decides; accountant/employee read status ---
  if (workflow.status === 'PENDING' && presentation) {
    return (
      <div className="panel" id="b3-approval-panel" data-testid="b3-approval-panel">
        <h2>Chờ người duyệt tạm ứng</h2>
        <div className="review-summary-card">
          <div className="review-summary-line">
            Kế toán <strong>{presentation.accountant_ref}</strong> đã trình · người
            duyệt <strong>{presentation.approver_ref}</strong> · căn cứ report{' '}
            <code>{presentation.basis_report_id}</code>
          </div>
        </div>
        {!workflow.basis_current && (
          <p className="notice notice-warn" role="alert">
            {workflow.blocked_reason ?? 'Căn cứ đã đổi; cần chạy và trình lại.'}
          </p>
        )}

        {role === 'APPROVER' && canDecide ? (
          <div className="field">
            <h3>Quyết định (người duyệt)</h3>
            <label htmlFor="b3-allow-work">
              <input id="b3-allow-work" type="checkbox" checked={allowWork}
                     onChange={(e) => setAllowWork(e.target.checked)} />{' '}
              Cho phép thực hiện công việc
            </label>
            <label htmlFor="b3-budget">Ngân sách duyệt (VND)</label>
            <input id="b3-budget" type="number" min="0" value={budget}
                   onChange={(e) => setBudget(e.target.value)} />
            <label htmlFor="b3-advance">Số ứng duyệt (VND)</label>
            <input id="b3-advance" type="number" min="0" value={advance}
                   onChange={(e) => setAdvance(e.target.value)} />
            <label htmlFor="b3-reason">Lý do</label>
            <input id="b3-reason" value={reason}
                   onChange={(e) => setReason(e.target.value)}
                   placeholder="Duyệt theo đề nghị và dự toán." />
            <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <button className="btn btn-primary"
                      disabled={!approveValid}
                      onClick={() => void onAction('B3_APPROVE',
                        () => submitDecision('APPROVE'))}>
                Phê duyệt tạm ứng
              </button>
              <button className="btn"
                      disabled={!reason.trim()}
                      onClick={() => void onAction('B3_RETURN',
                        () => submitDecision('RETURN'))}>
                Yêu cầu bổ sung
              </button>
              <button className="btn"
                      disabled={!reason.trim()}
                      onClick={() => void onAction('B3_REFUSE',
                        () => submitDecision('REFUSE'))}>
                Từ chối đề nghị
              </button>
            </div>
            {!approveValid && (
              <p className="review-hint">
                Phê duyệt cần: cho phép công việc, ngân sách &gt; 0, số ứng &gt; 0
                và lý do.
              </p>
            )}
          </div>
        ) : (
          <p className="muted">
            Đang chờ người có quyền quyết định. Chưa ghi nhận tiền.
          </p>
        )}
      </div>
    );
  }

  // --- NOT_PRESENTED / RETURNED (awaiting re-present) / NEEDS_RECHECK ---
  if (role === 'ACCOUNTANT') {
    return (
      <div className="panel" id="b3-approval-panel" data-testid="b3-approval-panel">
        <h2>Trình người duyệt tạm ứng</h2>
        {savedReview ? (
          <div className="review-summary-card" data-testid="b3-saved-review">
            <div className="review-summary-line">
              Đã có rà soát của <strong>{savedReview.actor_id}</strong> cho report{' '}
              <code>{savedReview.report_id}</code> — ghi chú: <em>"{savedReview.note}"</em>
            </div>
          </div>
        ) : (
          <>
            <label htmlFor="b3-present-note">Ghi chú rà soát</label>
            <input id="b3-present-note" value={note}
                   onChange={(e) => setNote(e.target.value)}
                   placeholder="Đã đối chiếu bảng và mở nguồn gốc." />
            {view.sources.length > 0 && (
              <div style={{ marginTop: 'var(--space-2)' }}>
                <label>Tài liệu căn cứ</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {view.sources.map((src) => (
                    <label key={src.id} className="helper">
                      <input type="checkbox" checked={refs.includes(src.id)}
                             onChange={(e) => setRefs(e.target.checked
                               ? [...refs, src.id]
                               : refs.filter((id) => id !== src.id))} />{' '}
                      {src.filename} (<code>{src.id}</code>)
                    </label>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
        <button className="btn btn-primary"
                style={{ marginTop: 'var(--space-2)' }}
                disabled={!reportId || !canPresent
                  || (!savedReview && !note.trim())}
                onClick={() => void onAction('B3_PRESENT',
                  () => api.presentB3(view.id, presentBody() as never))}>
          {savedReview ? 'Trình người duyệt' : 'Lưu rà soát và trình duyệt'}
        </button>
      </div>
    );
  }

  // Employee / approver with nothing to act on: read-only status.
  return (
    <div className="panel" data-testid="b3-approval-panel">
      <h2>Đề nghị tạm ứng</h2>
      <p className="muted">
        {workflow.status === 'NEEDS_RECHECK'
          ? 'Căn cứ đã thay đổi; cần kế toán chạy và trình lại.'
          : 'Chưa được trình duyệt; kế toán sẽ rà soát và trình người có quyền.'}
      </p>
    </div>
  );
}
