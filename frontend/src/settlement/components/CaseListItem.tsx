// One row in the case list sidebar: id, job/origin badges, stage pill, actor and
// work ref, plus a delete action. Extracted from App.tsx; props-only.
import { STAGE_LABELS } from '../displayText';
import type { CaseSummary } from '../types';

interface CaseListItemProps {
  item: CaseSummary;
  isActive: boolean;
  actorName?: string;
  onOpen: (caseId: string) => void;
  onDelete: (caseId: string) => void;
}

export function CaseListItem({
  item, isActive, actorName, onOpen, onDelete,
}: CaseListItemProps) {
  return (
    <div className={`case-item-card ${isActive ? 'case-item-card-active' : ''}`}>
      <button
        type="button"
        className="case-item-main"
        onClick={() => onOpen(item.id)}
      >
        <div className="case-item-top">
          <span className="case-item-id">{item.id}</span>
          <span className="case-item-badges">
            {item.origin === 'SYSTEM' && (
              <span className="case-item-system-badge">Hệ thống</span>
            )}
            <span className={`case-item-job-badge badge-${item.job.toLowerCase()}`}>{item.job}</span>
          </span>
        </div>
        <div className="case-item-stage">
          <span className="case-stage-pill">{STAGE_LABELS[item.stage]}</span>
          <span className="case-version-text">v{item.case_version}</span>
        </div>
        <div className="case-item-bottom">
          <span className="case-item-actor">
            {actorName ? `${actorName} (${item.employee_ref})` : item.employee_ref}
          </span>
          <span>/</span>
          <span className="case-item-work">{item.work_ref}</span>
        </div>
      </button>
      <button
        type="button"
        className="case-item-delete"
        data-testid={`delete-case-${item.id}`}
        aria-label={`Xoá hồ sơ ${item.id}`}
        title="Xoá hồ sơ"
        onClick={() => onDelete(item.id)}
      >
        🗑
      </button>
    </div>
  );
}
