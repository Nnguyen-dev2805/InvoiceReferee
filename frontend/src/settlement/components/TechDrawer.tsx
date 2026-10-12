// Technical details slide-over drawer: raw ids + run/report trace. Extracted
// from App.tsx; props-only, no state.
import { ProcessingDetails } from '../ProcessingDetails';
import { dossierReference } from '../displayText';
import type { CaseView, Report, RunView } from '../types';

interface TechDrawerProps {
  view: CaseView;
  run: RunView | null;
  report: Report | null;
  onClose: () => void;
}

export function TechDrawer({ view, run, report, onClose }: TechDrawerProps) {
  return (
    <div className="swiss-tech-drawer-overlay" onClick={onClose}>
      <div
        className="swiss-tech-drawer"
        data-testid="swiss-tech-drawer"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="swiss-drawer-header">
          <h3 className="swiss-drawer-title">Thông tin kỹ thuật &amp; Kiểm toán</h3>
          <button
            type="button"
            className="btn-icon-subtle"
            onClick={onClose}
            aria-label="Đóng bảng kỹ thuật"
          >
            ✕
          </button>
        </div>
        <div className="swiss-drawer-body">
          <div style={{ marginBottom: 'var(--space-4)', lineHeight: '1.6' }}>
            <div><strong>Mã hồ sơ gốc:</strong> <code>{dossierReference(view) ?? '—'}</code></div>
            <div><strong>Mã bản ghi:</strong> <code>{view.id}</code></div>
            <div><strong>Mã nhân viên:</strong> <code>{view.submission.employee_ref}</code></div>
            <div><strong>Mã công việc:</strong> <code>{view.submission.work_ref}</code></div>
            <div><strong>Phiên bản:</strong> v{view.case_version} (rev {view.input_revision}, epoch {view.control_epoch})</div>
            {run && (
              <div><strong>Run ID:</strong> <code>{run.id}</code> ({run.mode})</div>
            )}
          </div>
          {run && report && (
            <ProcessingDetails run={run} report={report} />
          )}
        </div>
      </div>
    </div>
  );
}
