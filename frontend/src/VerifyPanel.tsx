import { useEffect, useRef, useState } from 'react';
import * as api from './api';
import type { VerifyJob } from './types';
import { runInFlight } from './format';

type Suite = 'core' | 'escalation' | 'all';

export function VerifyPanel() {
  const [job, setJob] = useState<VerifyJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  function poll(jobId: string) {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(async () => {
      try {
        const latest = await api.getVerifyRun(jobId);
        setJob(latest);
        if (runInFlight(latest.status)) poll(jobId);
        else setBusy(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không tải được verify job.');
        setBusy(false);
      }
    }, 1000);
  }

  async function run(suite: Suite) {
    setError(null);
    setBusy(true);
    setJob(null);
    try {
      const started = await api.startVerifyRun(suite, 'replay');
      setJob(started);
      poll(started.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không chạy được verify.');
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="verify-heading">
      <h2 id="verify-heading">Bộ kiểm thử tự động (Verify)</h2>
      <p className="muted">
        Chạy cùng đường xử lý production (replay, không gọi mạng). Kết quả nghiệp vụ
        <em> người cần xử lý</em> vẫn có thể là testcase ĐẠT khi đúng kỳ vọng.
      </p>
      <div className="detail-actions">
        {(['core', 'escalation', 'all'] as Suite[]).map((suite) => (
          <button
            key={suite}
            type="button"
            className="btn"
            onClick={() => run(suite)}
            disabled={busy}
          >
            Chạy {suite === 'all' ? 'tất cả' : suite}
          </button>
        ))}
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}

      {job && (
        <div className="verify-result" aria-live="polite">
          <p role="status">
            Trạng thái: {job.status} · {job.completed_count}/{job.total_count}
          </p>
          {job.report && (
            <table className="verify-table">
              <caption>Kết quả Verify ({job.report.mode})</caption>
              <thead>
                <tr>
                  <th scope="col">Case</th>
                  <th scope="col">Kỳ vọng</th>
                  <th scope="col">Thực tế</th>
                  <th scope="col">Kết luận</th>
                </tr>
              </thead>
              <tbody>
                {job.report.results.map((row) => (
                  <tr key={row.case_id}>
                    <td>{row.case_id}</td>
                    <td>{row.expected.action}</td>
                    <td>{String(row.actual.action ?? '—')}</td>
                    <td>{row.verdict}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
