import type { CaseRecord, DemoMode, RunRecord } from './types';
import { ACTION_LABEL, MODE_LABEL, formatVnd, runInFlight } from './format';

interface InboxProps {
  cases: CaseRecord[];
  role: DemoMode;
  runsByCase: Record<string, RunRecord>;
  onOpen: (caseId: string) => void;
  selectedCaseId?: string | null;
}

// A case is "processing" until its current run produced a decision. While it has
// no decision yet it belongs to no role's queue, so every role sees it here.
function isProcessing(caseRecord: CaseRecord, run: RunRecord | undefined): boolean {
  if (!caseRecord.current_run_id) return false;
  if (!run) return true; // run referenced but not loaded yet
  return runInFlight(run.status) || run.result === null;
}

function caseTitle(caseRecord: CaseRecord): string {
  const claim = caseRecord.claim;
  return claim.purpose?.trim() || claim.profile;
}

export function Inbox({ cases, role, runsByCase, onOpen, selectedCaseId }: InboxProps) {
  const processing = cases.filter((c) => isProcessing(c, runsByCase[c.id]));
  const forRole = cases.filter(
    (c) => !isProcessing(c, runsByCase[c.id]) && c.open_owner_modes.includes(role),
  );

  return (
    <section className="panel" aria-labelledby="inbox-heading">
      <h2 id="inbox-heading">Hộp thư việc — {MODE_LABEL[role]}</h2>
      <p className="muted">
        Đăng nhập demo theo vai trò. Chỉ hiện hồ sơ đang chờ vai trò này xử lý; hệ
        thống vẫn kiểm tra quyền của từng hành động.
      </p>

      <div className="inbox-section">
        <h3>Việc của tôi</h3>
        {forRole.length === 0 ? (
          <p className="muted">Không có việc cần xử lý cho vai trò này.</p>
        ) : (
          <ul className="case-list">
            {forRole.map((c) => {
              const run = runsByCase[c.id];
              const action = run?.result?.decision.action;
              const isSelected = c.id === selectedCaseId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    className={`case-item ${isSelected ? 'case-item-active' : ''}`}
                    onClick={() => onOpen(c.id)}
                    aria-current={isSelected ? 'true' : undefined}
                  >
                    <span className="case-item-head">
                      <strong>{caseTitle(c)}</strong>
                      <span className="case-badge">{c.open_owner_modes.length} việc</span>
                    </span>
                    <span className="muted">
                      {c.claim.profile} · {formatVnd(c.claim.requested_amount_vnd)}
                      {action ? ` · ${ACTION_LABEL[action]}` : ''}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="inbox-section">
        <h3>Đang xử lý</h3>
        {processing.length === 0 ? (
          <p className="muted">Không có hồ sơ nào đang chạy.</p>
        ) : (
          <ul className="case-list">
            {processing.map((c) => {
              const isSelected = c.id === selectedCaseId;
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    className={`case-item ${isSelected ? 'case-item-active' : ''}`}
                    onClick={() => onOpen(c.id)}
                    aria-current={isSelected ? 'true' : undefined}
                  >
                    <span className="case-item-head">
                      <strong>{caseTitle(c)}</strong>
                      <span className="status status-running">Đang xử lý</span>
                    </span>
                    <span className="muted">
                      {c.claim.profile} · {formatVnd(c.claim.requested_amount_vnd)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
