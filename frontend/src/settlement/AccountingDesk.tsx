import { CaseSummary, CaseStage } from './types';

interface AccountingDeskProps {
  cases: CaseSummary[];
  getActorName: (ref: string) => string;
  stageLabels: Record<CaseStage, string>;
  onSelectCase: (caseId: string) => void;
  onSelfInitiate: () => void;
}

export function AccountingDesk({
  cases,
  getActorName,
  stageLabels,
  onSelectCase,
  onSelfInitiate,
}: AccountingDeskProps) {
  const pendingCases = cases.filter(
    (c) => c.stage === 'CHECKING' || c.stage === 'ACCOUNTING_REVIEW'
  );
  const nextStageCases = cases.filter(
    (c) =>
      c.stage === 'AWAITING_DECISION' ||
      c.stage === 'AWAITING_MONEY' ||
      c.stage === 'AWAITING_WORK_SETTLEMENT' ||
      c.stage === 'RESOLVING_OBLIGATIONS'
  );
  const closedCases = cases.filter(
    (c) => c.stage === 'SETTLEMENT_CLOSED' || c.stage === 'REJECTED_REQUEST_ENDED'
  );

  return (
    <div className="desk-container" data-testid="accounting-desk">
      <div className="desk-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span
              className="badge"
              style={{
                background: '#18181b',
                color: '#ffffff',
                fontSize: '0.72rem',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                padding: '2px 8px',
              }}
            >
              Kế toán thẩm tra
            </span>
            <h2 className="desk-header-title">Bàn làm việc Kế toán</h2>
          </div>
          <p className="desk-header-subtitle">
            Hàng đợi đối soát chứng từ, kiểm tra tính hợp lệ và lập tờ trình thanh quyết toán
          </p>
        </div>
        <button
          type="button"
          className="swiss-btn swiss-btn-secondary swiss-btn-sm"
          onClick={onSelfInitiate}
          title="Mở biểu mẫu nếu bạn cần lập đề nghị chi hoặc tạm ứng cá nhân"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Tự lập đề nghị của tôi
        </button>
      </div>

      <div className="desk-metrics-grid">
        <div className="desk-metric-card">
          <div
            className="desk-metric-num"
            style={{ color: pendingCases.length > 0 ? '#09090b' : '#71717a' }}
          >
            {pendingCases.length}
          </div>
          <div className="desk-metric-label">Hồ sơ chờ rà soát</div>
        </div>
        <div className="desk-metric-card">
          <div className="desk-metric-num">{nextStageCases.length}</div>
          <div className="desk-metric-label">Đã chuyển phê duyệt / Chi</div>
        </div>
        <div className="desk-metric-card">
          <div className="desk-metric-num">{closedCases.length}</div>
          <div className="desk-metric-label">Hồ sơ đã kết thúc</div>
        </div>
      </div>

      <div className="desk-section">
        <div className="desk-section-title">
          <span>Hàng đợi rà soát chứng từ</span>
          <span className="badge">{pendingCases.length} hồ sơ</span>
        </div>

        {pendingCases.length === 0 ? (
          <div className="desk-zero-inbox">
            <div className="desk-zero-icon">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
            <h3 className="desk-zero-title">Hàng đợi rà soát sạch sẽ</h3>
            <p className="desk-zero-desc">
              Hiện không có hồ sơ nào đang chờ kế toán đối soát chứng từ. Tất cả hồ sơ đề nghị tạm ứng
              và quyết toán trong hệ thống đã được xử lý hoặc chưa phát sinh mới.
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="desk-table">
              <thead>
                <tr>
                  <th>Mã hồ sơ</th>
                  <th>Người đề nghị</th>
                  <th>Công việc</th>
                  <th>Loại</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {pendingCases.map((c) => (
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
                      <span className="case-stage-pill">{stageLabels[c.stage] ?? c.stage}</span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="swiss-btn swiss-btn-primary swiss-btn-sm"
                        onClick={() => onSelectCase(c.id)}
                      >
                        Rà soát ngay →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
