// Case detail header: Sleek integrated workspace bar with Case ID, title, amount, and Debug button.
import { dossierReference, formatMoney } from '../displayText';
import type { AuditEntry, CaseView, DemoRole } from '../types';

interface CaseHeaderCardProps {
  view: CaseView;
  viewIsB3: boolean;
  role: DemoRole;
  actorId?: string;
  mainTitle?: string;
  sublineText?: string;
  b3WorkflowPending?: boolean;
  latestReview?: AuditEntry | undefined;
  copiedCaseId: boolean;
  onCopyCaseId: (caseId: string) => void;
  onOpenTech?: () => void;
  workbenchMode?: 'split' | 'doc' | 'form';
  onWorkbenchModeChange?: (mode: 'split' | 'doc' | 'form') => void;
  onBackToDesk?: () => void;
}

export function CaseHeaderCard({
  view, viewIsB3, role, mainTitle, sublineText,
  b3WorkflowPending, latestReview, copiedCaseId,
  onCopyCaseId, onOpenTech: _onOpenTech, workbenchMode, onWorkbenchModeChange,
  onBackToDesk,
}: CaseHeaderCardProps) {
  const isDraft = viewIsB3 && !view.submission.form.confirmed;
  const form = view.submission?.form as Record<string, unknown> | undefined;
  const requestAmount = viewIsB3
    ? (form?.request_amount_vnd ?? view.money_summary?.approved_vnd ?? null)
    : (form?.claim_total_amount_vnd ?? view.money_summary?.approved_vnd ?? null);

  return (
    <div className="case-header-container">
      {/* Sleek integrated header bar */}
      <div className="case-header-actions-bar sr-only">
        <div className="case-header-left">
          {onBackToDesk && (role === 'ACCOUNTANT' || role === 'APPROVER') && (
            <button
              type="button"
              className="btn-toggle-sidebar"
              onClick={onBackToDesk}
              title="Quay về Bàn làm việc"
              aria-label="Quay về Bàn làm việc"
            >
              ←
            </button>
          )}

          {/* Case ID badge with copy action */}
          <div className="case-id-badge" data-testid="case-id-badge">
            <code className="case-id-badge-code">{dossierReference(view) ?? view.id}</code>
            <button
              type="button"
              className="btn-copy-case-id"
              onClick={() => onCopyCaseId(dossierReference(view) ?? view.id)}
              aria-label="Sao chép mã hồ sơ"
              title="Sao chép mã hồ sơ"
            >
              {copiedCaseId ? 'Đã chép' : 'Sao chép'}
            </button>
          </div>

          {/* Context title & subline */}
          <div className="case-header-info">
            <span className="case-header-title">
              {mainTitle ?? (viewIsB3 ? 'Đề nghị tạm ứng' : 'Quyết toán')}
            </span>
            {sublineText && (
              <span className="case-header-subline" title={sublineText}>
                {sublineText}
              </span>
            )}
          </div>
        </div>

        <div className="case-header-right">
          {/* View mode toggles integrated right in the header bar */}
          {workbenchMode && onWorkbenchModeChange && (
            <div className="view-mode-btn-group" role="group" aria-label="Chế độ hiển thị">
              <button
                type="button"
                className={`view-mode-btn ${workbenchMode === 'split' ? 'active' : ''}`}
                onClick={() => onWorkbenchModeChange('split')}
                title="Chia đôi cân bằng (50:50)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="3" x2="12" y2="21"/></svg>
                Chia đôi
              </button>
              <button
                type="button"
                className={`view-mode-btn ${workbenchMode === 'doc' ? 'active' : ''}`}
                onClick={() => onWorkbenchModeChange('doc')}
                title="Phóng to chứng từ (70:30)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="16" y1="3" x2="16" y2="21"/></svg>
                Ưu tiên chứng từ
              </button>
              <button
                type="button"
                className={`view-mode-btn ${workbenchMode === 'form' ? 'active' : ''}`}
                onClick={() => onWorkbenchModeChange('form')}
                title="Phóng to biểu mẫu (30:70)"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="3" x2="8" y2="21"/></svg>
                Ưu tiên biểu mẫu
              </button>
            </div>
          )}

          {/* Prominent financial amount badge */}
          {requestAmount != null && Number(requestAmount) > 0 && (
            <div className="case-header-amount-pill">
              <span className="amount-label">{viewIsB3 ? 'Đề nghị:' : 'Quyết toán:'}</span>
              <span className="amount-value">{formatMoney(Number(requestAmount))}</span>
            </div>
          )}

          {/* Debug button moved to case tabs header row */}
        </div>
      </div>

      {/* Accountant review status (Only shown for Accountant) */}
      {role === 'ACCOUNTANT' && (
        <div
          className={`business-status-card ${isDraft ? 'business-status-pending-review' : b3WorkflowPending ? 'business-status-reviewed' : latestReview ? 'business-status-reviewed' : 'business-status-pending-review'}`}
          data-testid="accountant-status-card"
        >
          <div className="business-status-title-row">
            <span className={`status-pill ${isDraft ? 'status-pill-warning' : b3WorkflowPending || latestReview ? 'status-pill-success' : 'status-pill-warning'}`}>
              {isDraft
                ? 'Bản nháp của nhân viên (Chưa nộp)'
                : b3WorkflowPending
                  ? 'Chờ người duyệt tạm ứng'
                  : latestReview ? 'Đã lưu kết quả rà soát' : 'Chờ kế toán rà soát'}
            </span>
            {!isDraft && onBackToDesk && (
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={onBackToDesk}
                style={{ marginLeft: 'auto' }}
              >
                ← Về Bàn làm việc
              </button>
            )}
          </div>
          <div className="business-status-desc">
            {isDraft ? (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <span>Nhân viên chưa gửi đề nghị chính thức. Hồ sơ đang ở trạng thái bản nháp của nhân viên, kế toán chưa thực hiện rà soát.</span>
                {onBackToDesk && (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    onClick={onBackToDesk}
                  >
                    ← Về Bàn làm việc Kế toán
                  </button>
                )}
              </div>
            ) : b3WorkflowPending ? (
              <>
                Đã trình người có quyền <strong>{view.b3_workflow?.approver_ref}</strong> quyết định; chưa ghi nhận tiền thực nhận.
              </>
            ) : latestReview ? (
              <>
                Đã lưu kết quả rà soát bởi <strong>{latestReview.actor_id}</strong> lúc {new Date(latestReview.occurred_at).toLocaleString('vi-VN')}
                {latestReview.detail?.note ? ` — Ghi chú: “${String(latestReview.detail.note)}”` : ''}
              </>
            ) : (
              'Nhân viên đã xác nhận thông tin đề nghị. Hệ thống đã hoàn tất kiểm tra tự động. Chưa phê duyệt hoặc chi ứng.'
            )}
          </div>
        </div>
      )}
    </div>
  );
}
