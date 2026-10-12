// Sticky bottom action bar of the case workbench: status pill + context actions
// (save draft / submit / run / review-scroll). Extracted from App.tsx.
import { STAGE_LABELS } from '../displayText';
import type { CaseStage, CaseView, DemoRole } from '../types';

type CaseTab = 'report' | 'draft' | 'sources' | 'questions' | 'history';

interface StickyActionBarProps {
  view: CaseView;
  viewIsB3: boolean;
  caseTab: CaseTab;
  role: DemoRole;
  canStartRun: boolean;
  b3ReviseReason: string;
  onReviseB3: (confirm: boolean) => void;
  onStartRun: () => void;
}

function scrollToReview(): void {
  const el = document.getElementById('accountant-review-section')
    || document.getElementById('review-note');
  if (el) {
    el.scrollIntoView?.({ behavior: 'smooth' });
    const input = document.getElementById('review-note');
    if (input instanceof HTMLElement) input.focus();
  }
}

export function StickyActionBar({
  view, viewIsB3, caseTab, role, canStartRun, b3ReviseReason,
  onReviseB3, onStartRun,
}: StickyActionBarProps) {
  return (
    <div className="workbench-sticky-bar" data-testid="workbench-sticky-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--color-muted-foreground)', fontWeight: 600 }}>TRẠNG THÁI:</span>
        <span className={`status-pill status-${view.stage.toLowerCase()}`} style={{ fontSize: '0.75rem' }}>
          {viewIsB3 && view.b3_workflow?.status === 'APPROVED'
            ? 'Đã duyệt tạm ứng'
            : viewIsB3 && view.b3_workflow?.status === 'PENDING'
              ? 'Chờ duyệt tạm ứng'
              : STAGE_LABELS[view.stage as CaseStage]}
        </span>
        {caseTab === 'draft' && !view.submission.form.confirmed && (
          <span className="pill-badge pill-badge-amber" style={{ fontSize: '0.75rem' }}>Bản nháp chưa gửi</span>
        )}
      </div>
      <div className="workbench-sticky-actions">
        {caseTab === 'draft' && viewIsB3 && !view.submission.form.confirmed && (
          <>
            <button
              type="button"
              className="swiss-btn swiss-btn-secondary swiss-btn-sm"
              onClick={() => onReviseB3(false)}
            >
              Lưu nháp
            </button>
            <button
              type="button"
              className="swiss-btn swiss-btn-primary swiss-btn-sm"
              onClick={() => onReviseB3(true)}
            >
              Gửi đề nghị
            </button>
          </>
        )}
        {caseTab === 'draft' && viewIsB3 && Boolean(view.submission.form.confirmed) && (
          <button
            type="button"
            className="swiss-btn swiss-btn-primary swiss-btn-sm"
            disabled={!b3ReviseReason.trim()}
            onClick={() => onReviseB3(true)}
          >
            Lưu cập nhật
          </button>
        )}
        {caseTab === 'report' && canStartRun && (
          <button
            type="button"
            className="swiss-btn swiss-btn-primary swiss-btn-sm"
            onClick={onStartRun}
          >
            {viewIsB3
              ? (view.submission.form.confirmed ? 'Chạy đối soát' : 'Trích xuất hồ sơ')
              : 'Thực hiện đối soát'}
          </button>
        )}
        {caseTab === 'report' && role === 'ACCOUNTANT' && (
          <button
            type="button"
            className="swiss-btn swiss-btn-secondary swiss-btn-sm"
            onClick={scrollToReview}
          >
            Rà soát ↓
          </button>
        )}
      </div>
    </div>
  );
}
