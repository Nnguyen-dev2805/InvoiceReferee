import { CaseSummary, CaseStage } from './types';

interface ApprovalDeskProps {
  cases: CaseSummary[];
  getActorName: (ref: string) => string;
  stageLabels: Record<CaseStage, string>;
  onSelectCase: (caseId: string) => void;
}

export function ApprovalDesk({
  cases,
  getActorName,
  stageLabels,
  onSelectCase,
}: ApprovalDeskProps) {
  const pendingCases = cases.filter((c) => c.stage === 'AWAITING_DECISION' && c.confirmed !== false);
  const processedCases = cases.filter(
    (c) =>
      (c.stage === 'AWAITING_MONEY' ||
      c.stage === 'AWAITING_WORK_SETTLEMENT' ||
      c.stage === 'RESOLVING_OBLIGATIONS' ||
      c.stage === 'SETTLEMENT_CLOSED' ||
      c.stage === 'REJECTED_REQUEST_ENDED') && c.confirmed !== false
  );

  return (
    <div className="desk-container" data-testid="approval-desk">
      <div className="desk-metrics-grid">
        <div className="desk-metric-card">
          <div
            className="desk-metric-num"
            style={{ color: pendingCases.length > 0 ? '#09090b' : '#71717a' }}
          >
            {pendingCases.length}
          </div>
          <div className="desk-metric-label">Hồ sơ chờ phê duyệt</div>
        </div>
        <div className="desk-metric-card">
          <div className="desk-metric-num">{processedCases.length}</div>
          <div className="desk-metric-label">Hồ sơ đã xử lý / Hoàn tất</div>
        </div>
      </div>

      <div className="desk-section">
        <div className="desk-section-title">
          <span>Danh sách hồ sơ</span>
          {pendingCases.length > 0 && (
            <span className="badge">{pendingCases.length} hồ sơ</span>
          )}
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="desk-table">
            <thead>
              <tr>
                <th>Mã hồ sơ</th>
                <th>Người đề nghị</th>
                <th>Công việc</th>
                <th>Loại</th>
                <th>Ý kiến kế toán</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {pendingCases.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    style={{
                      textAlign: 'center',
                      padding: '36px 16px',
                      color: 'var(--color-muted-foreground)',
                      fontSize: '0.88rem',
                    }}
                  >
                    Không có hồ sơ nào chờ phê duyệt
                  </td>
                </tr>
              ) : (
                pendingCases.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <code style={{ fontWeight: 600 }} title={c.id}>#{c.id.replace(/^C-/, '')}</code>
                    </td>
                    <td>{getActorName(c.employee_ref)}</td>
                    <td>{c.work_ref}</td>
                    <td>
                      <span className={`case-item-job-badge badge-${c.job.toLowerCase()}`}>
                        {c.job === 'B3' ? 'B3 · Tạm ứng' : 'B7 · Quyết toán'}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontSize: '0.82rem', color: '#18181b', fontWeight: 500 }}>
                        {stageLabels[c.stage] ?? 'Đã đối soát xong — Chờ lãnh đạo duyệt'}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="swiss-btn swiss-btn-primary swiss-btn-sm"
                        onClick={() => onSelectCase(c.id)}
                      >
                        Xem & Phê duyệt →
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
