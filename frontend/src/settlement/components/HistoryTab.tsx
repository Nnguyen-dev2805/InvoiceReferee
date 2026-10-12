// Case detail "history" tab: case info, run trace and the audit timeline.
// Extracted from App.tsx; props-only.
import { STAGE_LABELS, historyKindLabel } from '../displayText';
import type { AuditEntry, CaseView, RunView } from '../types';

interface HistoryTabProps {
  view: CaseView;
  viewIsB3: boolean;
  run: RunView | null;
  history: AuditEntry[];
}

export function HistoryTab({ view, viewIsB3, run, history }: HistoryTabProps) {
  return (
    <div>
      <div className="panel" style={{ marginBottom: 'var(--space-4)' }}>
        <h2>Thông tin hồ sơ {view.id}</h2>
        <p>
          <strong>Giai đoạn:</strong> {STAGE_LABELS[view.stage]} · v
          {view.case_version} (revision {view.input_revision}, epoch{' '}
          {view.control_epoch})
        </p>
        {viewIsB3 ? (
          <p>
            <strong>Đề nghị B3:</strong>{' '}
            {String(view.submission.form.purpose ?? '')}
            {view.submission.form.destination
              ? ` — ${String(view.submission.form.destination)}` : ''}
            {' · '}
            {view.submission.form.confirmed
              ? 'đã xác nhận' : 'draft chưa xác nhận'}
            {' · '}mã công việc <code>{view.submission.work_ref}</code>
          </p>
        ) : (
          <p>
            <strong>Khai báo:</strong> {String(view.submission.form.purpose ?? '')}
            {view.submission.form.scope
              ? ` — phạm vi: ${String(view.submission.form.scope)}`
              : ''}
          </p>
        )}
        {view.allowed_actions.length > 0 && (
          <>
            <h3>Hành động cho phép</h3>
            <ul className="reasons">
              {view.allowed_actions.map((a) => (
                <li key={a.action}>
                  <strong>{a.action}</strong> — {a.reason}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      {run && run.trace.length > 0 && (
        <div className="panel" style={{ marginBottom: 'var(--space-4)' }}>
          <h2>Dấu vết thực thi (Run Trace)</h2>
          <ul className="reasons">
            {run.trace.map((entry) => (
              <li key={entry.call_id}>
                {entry.stage}
                {entry.source_id ? ` · nguồn ${entry.source_id}` : ''}{' '}
                — {entry.ok ? 'ok' : `lỗi ${entry.error_code}`}
                {entry.usage
                  ? ` · tokens: ${entry.usage.total_tokens ?? '?'}`
                  : ' · usage: không có (None)'}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <h2>Lịch sử xử lý ({history.length})</h2>
        {history.length === 0 ? (
          <p className="muted">Chưa có lịch sử thao tác nào.</p>
        ) : (
          <ul className="history-timeline">
            {history.map((h) => (
              <li key={h.id} className="history-timeline-item">
                <span className="history-time">{new Date(h.occurred_at).toLocaleString('vi-VN')}</span>
                <span className="history-content">
                  <strong>{historyKindLabel(h.kind)}</strong> bởi <code>{h.actor_id}</code>
                  <details className="meta-details" style={{ display: 'inline-block', marginLeft: 'var(--space-1)' }}>
                    <summary style={{ cursor: 'pointer', color: 'var(--color-muted-foreground)' }}>({h.kind})</summary>
                    {h.detail && (
                      <pre style={{ margin: 'var(--space-1) 0', fontSize: '0.8rem' }}>
                        {JSON.stringify(h.detail, null, 2)}
                      </pre>
                    )}
                  </details>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
