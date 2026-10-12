// "What to do next" summary card with a primary CTA that switches tab and
// focuses the relevant panel. Extracted from App.tsx; props-only.
import type { UiSummary } from '../caseSummary';

type CaseTab = 'report' | 'draft' | 'sources' | 'questions' | 'history';

// Tab targets: switch tab, then focus the panel.
const TAB_TARGETS: Record<string, CaseTab> = {
  'draft-editor': 'draft',
  'issues': 'report',
  'accountant-review': 'report',
  'advance-decision': 'report',
  'advance-receipt': 'report',
  'prepare-settlement': 'report',
  'settlement-intake': 'report',
  'settlement-decision': 'report',
  'settlement-receipt': 'report',
  'case-history': 'history',
  'sources': 'sources',
};

// Element ids that live in specific panels.
const TARGET_IDS: Record<string, string> = {
  'draft-editor': 'b3-destination',
  'issues': 'report-issues-top',
  'accountant-review': 'accountant-review-section',
  'advance-decision': 'b3-approval-panel',
  'advance-receipt': 'b3-funding-panel',
  'prepare-settlement': 'b7-prepare-block',
  'settlement-intake': 'b7-company-context-panel',
  'settlement-decision': 'b7-approval-panel',
  'settlement-receipt': 'b7-funding-panel',
};

interface SummaryCardProps {
  summary: UiSummary;
  onSelectTab: (tab: CaseTab) => void;
}

export function SummaryCard({ summary, onSelectTab }: SummaryCardProps) {
  const handlePrimary = () => {
    const target = summary.primaryTarget;
    if (!target) return;
    const nextTab = TAB_TARGETS[target];
    if (nextTab) onSelectTab(nextTab);
    const elementId = TARGET_IDS[target];
    if (elementId) {
      setTimeout(() => {
        const el = document.getElementById(elementId)
          ?? document.querySelector('.report-issues-top, .issues, #report-panel');
        if (el instanceof HTMLElement) {
          el.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
          const focusable = el.matches('input,select,textarea,button')
            ? el : el.querySelector('input,select,textarea,button');
          if (focusable instanceof HTMLElement) focusable.focus();
        }
      }, 0);
    }
  };

  return (
    <div className={`panel summary-card summary-${summary.tone}`}>
      <div className="summary-header">
        <div className="summary-title-group">
          <svg className="summary-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <div className="summary-title">{summary.title}</div>
        </div>
        {summary.primaryTarget && (
          <button type="button" className="btn btn-primary" onClick={handlePrimary}>
            {summary.primaryLabel
              ?? (summary.primaryTarget === 'draft-editor'
                ? 'Kiểm tra bản nháp'
                : summary.primaryTarget === 'issues'
                  ? 'Xem việc cần làm rõ'
                  : 'Kiểm tra lại hồ sơ')}
          </button>
        )}
      </div>
      <div className="summary-description">{summary.description}</div>
      {summary.missingFields.length > 0 && (
        <div className="summary-missing">
          <strong>Trường còn thiếu:</strong> {summary.missingFields.join(', ')}
        </div>
      )}
    </div>
  );
}
