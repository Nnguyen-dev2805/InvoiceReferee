import { useEffect, useRef, useState } from 'react';
import * as api from './api';
import type { VerifyJob } from './types';
import { runInFlight } from './format';
import { useToast } from './Toast';
import { SpinnerIcon } from './icons';

type Suite = 'core' | 'escalation' | 'all';
type VerdictFilter = 'ALL' | 'FAILED' | 'PASS';

export function VerifyPanel() {
  const [job, setJob] = useState<VerifyJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [activeSuite, setActiveSuite] = useState<Suite | null>(null);
  const [filter, setFilter] = useState<VerdictFilter>('ALL');
  const [search, setSearch] = useState('');
  const timerRef = useRef<number | null>(null);
  const toast = useToast();

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  function poll(jobId: string, suite: Suite) {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(async () => {
      try {
        const latest = await api.getVerifyRun(jobId);
        setJob(latest);
        if (runInFlight(latest.status)) {
          poll(jobId, suite);
        } else {
          setBusy(false);
          if (latest.report) {
            const pass = latest.report.results.filter((r) => r.verdict === 'PASS').length;
            const total = latest.report.results.length;
            const fail = latest.report.results.filter((r) => r.verdict === 'FAIL').length;
            if (fail > 0) {
              toast.error(`Kiểm thử ${suite} kết thúc: ${fail} ca Thất bại, ${pass}/${total} Đạt.`);
            } else {
              toast.success(`Kiểm thử ${suite} hoàn tất: ${pass}/${total} ca Đạt chuẩn!`);
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Không tải được verify job.');
        setBusy(false);
      }
    }, 1000);
  }

  async function run(suite: Suite) {
    setError(null);
    setBusy(true);
    setActiveSuite(suite);
    setJob(null);
    setFilter('ALL');
    setSearch('');
    try {
      const started = await api.startVerifyRun(suite, 'replay');
      setJob(started);
      toast.info(`Bắt đầu chạy kiểm thử ${suite === 'all' ? 'tất cả' : suite}…`);
      poll(started.id, suite);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không chạy được verify.');
      setBusy(false);
    }
  }

  // Filter results
  const allResults = job?.report?.results ?? [];
  const filteredResults = allResults.filter((row) => {
    if (filter === 'FAILED' && row.verdict !== 'FAIL') return false;
    if (filter === 'PASS' && row.verdict !== 'PASS') return false;
    if (search.trim() && !row.case_id.toLowerCase().includes(search.trim().toLowerCase())) {
      return false;
    }
    return true;
  });

  const passCount = allResults.filter((r) => r.verdict === 'PASS').length;
  const failCount = allResults.filter((r) => r.verdict === 'FAIL').length;

  return (
    <section className="panel" aria-labelledby="verify-heading">
      <div className="verify-header">
        <div>
          <h2 id="verify-heading">Bộ kiểm thử tự động (Verify)</h2>
          <p className="muted">
            Chạy cùng đường xử lý production (replay, không gọi mạng). Kết quả nghiệp vụ{' '}
            <em>người cần xử lý</em> vẫn có thể là testcase ĐẠT khi đúng kỳ vọng.
          </p>
        </div>
      </div>

      <div className="detail-actions">
        {(['core', 'escalation', 'all'] as Suite[]).map((suite) => (
          <button
            key={suite}
            type="button"
            className={`btn ${activeSuite === suite && busy ? 'btn-primary' : ''}`}
            onClick={() => run(suite)}
            disabled={busy}
          >
            {busy && activeSuite === suite ? (
              <>
                <SpinnerIcon size={14} />
                <span>Đang chạy…</span>
              </>
            ) : (
              `Chạy ${suite === 'all' ? 'tất cả' : suite}`
            )}
          </button>
        ))}
      </div>

      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}

      {job && (
        <div className="verify-result" aria-live="polite">
          <div className="verify-status-bar">
            <span role="status">
              Trạng thái: <strong>{job.status}</strong> · Tiến độ:{' '}
              <strong>
                {job.completed_count}/{job.total_count}
              </strong>
            </span>
          </div>

          {job.report && (
            <>
              <div className="verify-toolbar">
                <div className="verify-filters" role="group" aria-label="Bộ lọc kết quả">
                  <button
                    type="button"
                    className={`btn btn-sm ${filter === 'ALL' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setFilter('ALL')}
                  >
                    Tất cả ({allResults.length})
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${filter === 'FAILED' ? 'btn-danger' : 'btn-ghost'} ${
                      failCount > 0 ? 'has-fails' : ''
                    }`}
                    onClick={() => setFilter('FAILED')}
                  >
                    Chỉ ca Thất bại ({failCount})
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${filter === 'PASS' ? 'btn-success' : 'btn-ghost'}`}
                    onClick={() => setFilter('PASS')}
                  >
                    Chỉ ca Đạt ({passCount})
                  </button>
                </div>

                <div className="verify-search">
                  <input
                    type="search"
                    placeholder="Tìm theo mã case…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Tìm theo mã case"
                  />
                </div>
              </div>

              <div className="verify-table-wrapper">
                <table className="verify-table">
                  <caption>Kết quả Verify ({job.report.mode})</caption>
                  <thead>
                    <tr>
                      <th scope="col">Case</th>
                      <th scope="col">Kỳ vọng</th>
                      <th scope="col">Thực tế</th>
                      <th scope="col">Kết luận</th>
                      <th scope="col">Thời gian</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredResults.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="empty-cell">
                          Không tìm thấy kết quả phù hợp với bộ lọc.
                        </td>
                      </tr>
                    ) : (
                      filteredResults.map((row) => (
                        <tr
                          key={row.case_id}
                          className={row.verdict === 'FAIL' ? 'row-failed' : ''}
                        >
                          <td>
                            <strong>{row.case_id}</strong>
                          </td>
                          <td>{row.expected.action}</td>
                          <td>{String(row.actual.action ?? '—')}</td>
                          <td>
                            <span
                              className={`badge ${
                                row.verdict === 'PASS'
                                  ? 'badge-success'
                                  : row.verdict === 'FAIL'
                                  ? 'badge-error'
                                  : 'badge-warning'
                              }`}
                            >
                              {row.verdict === 'PASS' && '✓ '}
                              {row.verdict === 'FAIL' && '✕ '}
                              {row.verdict === 'INCONCLUSIVE' && '? '}
                              {row.verdict}
                            </span>
                          </td>
                          <td className="muted">{row.elapsed_ms}ms</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
