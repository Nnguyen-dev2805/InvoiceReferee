// Case detail header: dossier badge + copy, job/status pills, main title and
// the unified business-status card. Extracted from App.tsx; props-only.
import { STAGE_LABELS, dossierReference, formatMoney } from '../displayText';
import type { AuditEntry, CaseView, DemoRole } from '../types';

interface CaseHeaderCardProps {
  view: CaseView;
  viewIsB3: boolean;
  role: DemoRole;
  actorId: string;
  mainTitle: string;
  sublineText: string;
  b3WorkflowPending: boolean;
  latestReview: AuditEntry | undefined;
  copiedCaseId: boolean;
  onCopyCaseId: (caseId: string) => void;
  onOpenTech: () => void;
}

export function CaseHeaderCard({
  view, viewIsB3, role, actorId, mainTitle, sublineText,
  b3WorkflowPending, latestReview, copiedCaseId, onCopyCaseId, onOpenTech,
}: CaseHeaderCardProps) {
  const requestAmount = (view.submission.form as Record<string, unknown>)?.request_amount_vnd;
  return (
    <div className="panel case-header-panel">
      <div className="case-header-top-bar">
        <div className="case-header-badge-row">
          {/* Mã hồ sơ chung (dossier root) dạng badge có nút sao chép */}
          <div className="case-id-badge" title="Mã hồ sơ" data-testid="case-id-badge">
            <span className="case-id-badge-label">Mã hồ sơ:</span>
            <code className="case-id-badge-code">{dossierReference(view) ?? 'Chưa xác định hồ sơ gốc'}</code>
            <button
              type="button"
              className="btn-copy-case-id"
              onClick={() => onCopyCaseId(dossierReference(view) ?? view.id)}
              title={copiedCaseId ? 'Đã sao chép vào bộ nhớ tạm' : 'Sao chép mã hồ sơ'}
              aria-label="Sao chép mã hồ sơ"
            >
              {copiedCaseId ? (
                <span className="copy-status-text">Đã chép</span>
              ) : (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              )}
            </button>
          </div>
          <span className="badge badge-job">{view.job} — {viewIsB3 ? 'Đề nghị tạm ứng' : 'Quyết toán'}</span>
          {viewIsB3 && (
            view.submission.form.confirmed ? (
              <span className="pill-badge pill-badge-green" title="Nhân viên đã xác nhận thông tin đề nghị">
                Nhân viên đã xác nhận thông tin đề nghị
              </span>
            ) : (
              <span className="pill-badge pill-badge-amber">Bản nháp chưa gửi</span>
            )
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {viewIsB3 && requestAmount != null && (
            <div className="case-header-amount-box">
              <span className="case-header-amount-label">Số tiền đề nghị:</span>
              <span className="case-header-amount-val">
                {formatMoney(Number(requestAmount))}
              </span>
            </div>
          )}
          <button
            type="button"
            className="swiss-btn swiss-btn-secondary swiss-btn-sm"
            style={{ fontSize: '0.78rem', padding: '3px 8px' }}
            onClick={onOpenTech}
            title="Xem chi tiết kỹ thuật & kiểm toán"
          >
            ℹ️ Kỹ thuật
          </button>
        </div>
      </div>

      {/* Tiêu đề chính to rõ: Đề nghị tạm ứng — [Tên nhân viên] */}
      <div className="case-header-title-section">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h2 className="case-main-title">{mainTitle}</h2>
          {actorId.trim() === view.submission.employee_ref ? (
            <span className="badge" style={{ fontSize: '0.72rem', background: '#e0f2fe', color: '#0369a1' }}>của bạn</span>
          ) : role === 'EMPLOYEE' ? (
            <span className="badge" style={{ fontSize: '0.72rem', background: '#fef3c7', color: '#b45309' }}>hồ sơ khác</span>
          ) : null}
        </div>
        {/* Dòng phụ ngay dưới: [Địa điểm] · [Thời gian chuyến đi] · Đề nghị [Số tiền VND] */}
        <div className="case-sub-meta">{sublineText}</div>
      </div>

      {/* MỘT trạng thái nghiệp vụ thống nhất trên cùng */}
      {role === 'ACCOUNTANT' ? (
        <div
          className={`business-status-card ${b3WorkflowPending ? 'business-status-reviewed' : latestReview ? 'business-status-reviewed' : 'business-status-pending-review'}`}
          data-testid="accountant-status-card"
        >
          <div className="business-status-title-row">
            <span className={`status-pill ${b3WorkflowPending || latestReview ? 'status-pill-success' : 'status-pill-warning'}`}>
              {b3WorkflowPending
                ? 'Chờ người duyệt tạm ứng'
                : latestReview ? 'Đã lưu kết quả rà soát' : 'Chờ kế toán rà soát'}
            </span>
          </div>
          <div className="business-status-desc">
            {b3WorkflowPending ? (
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
      ) : (
        <div className="business-status-card business-status-general" data-testid="business-status-card">
          <div className="business-status-title-row">
            <span className={`status-pill status-${view.stage.toLowerCase()}`}>
              {viewIsB3 && view.b3_workflow?.status === 'APPROVED'
                ? 'Đã duyệt tạm ứng — chờ chi ứng'
                : viewIsB3 && view.b3_workflow?.status === 'PENDING'
                  ? 'Chờ người duyệt tạm ứng'
                  : STAGE_LABELS[view.stage]}
            </span>
          </div>
        </div>
      )}

      {/* Thông tin hồ sơ gọn gàng */}
      <div className="case-header-tech-footer">
        <span>Mã NV: <code>{view.submission.employee_ref}</code></span>
        <span>·</span>
        <span>Mã công việc: <code>{view.submission.work_ref}</code></span>
        <span>·</span>
        <span>Phiên bản: <strong>v{view.case_version}</strong></span>
      </div>
    </div>
  );
}
