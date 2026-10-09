// Verify panel (W06): run the settlement evaluation suite sequentially through
// the same Service path and show expected vs actual per case — including the
// checks that failed, technical (INCONCLUSIVE) outcomes and honest metrics.
import { useState } from 'react';
import * as api from './api';
import type { VerifyCaseResult, VerifySuiteReport } from './types';

const VERDICT_LABELS: Record<VerifyCaseResult['verdict'], string> = {
  PASS: 'PASS',
  FAIL: 'FAIL',
  INCONCLUSIVE: 'INCONCLUSIVE (trục kỹ thuật, không bỏ mẫu số)',
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function VerifyPanel() {
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<VerifySuiteReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      setReport(await api.runSettlementVerify(null));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không chạy được Verify.');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="panel" data-testid="verify-panel">
      <h2>Verify — bộ đánh giá settlement</h2>
      <p className="muted">
        Chạy tuần tự 20 packet development qua cùng Service với UI; expected nằm
        trong packet (không vào input), verdict chấm cả completion/links/state
        chứ không chỉ số tiền. Corpus DEVELOPMENT_ONLY một family — không phải
        holdout độc lập.
      </p>
      <button className="btn btn-primary" disabled={running}
              onClick={() => void handleRun()}>
        {running ? 'Đang chạy suite…' : 'Chạy Verify (20 packets)'}
      </button>
      {error && <div className="notice notice-error" role="alert">{error}</div>}

      {report && (
        <>
          <p>
            <strong>{report.suite}</strong> · chế độ <strong>{report.mode}</strong>{' '}
            · {new Date(report.timestamp).toLocaleString('vi-VN')}
          </p>
          <p className="muted">
            source_hash <code>{report.source_hash.slice(0, 16)}…</code> ·
            config_hash <code>{report.config_hash.slice(0, 16)}…</code>
          </p>
          <h3>Metrics</h3>
          <ul className="reasons" data-testid="verify-metrics">
            <li>
              Routine: {report.metrics.n_routine} · FP {report.metrics.fp}
              {report.metrics.fp_interval
                ? ` (khoảng bảo thủ ${report.metrics.fp_interval
                    .map((v) => (v * 100).toFixed(0)).join('%–')}%)`
                : ''}
              {' · U_routine '}{report.metrics.u_routine}
              {' · first-pass routine completion '}{report.metrics.routine_completion}
            </li>
            <li>
              Needs: {report.metrics.n_needs} · FN {report.metrics.fn}
              {report.metrics.fn_interval
                ? ` (khoảng bảo thủ ${report.metrics.fn_interval
                    .map((v) => (v * 100).toFixed(0)).join('%–')}%)`
                : ''}
              {' · U_needs '}{report.metrics.u_needs}
            </li>
          </ul>
          <h3>Kết quả từng case</h3>
          <table data-testid="verify-results">
            <thead>
              <tr>
                <th>Case</th>
                <th>Phase</th>
                <th>Verdict</th>
                <th>Run</th>
                <th>Sai/nhận xét</th>
              </tr>
            </thead>
            <tbody>
              {report.results.map((result, index) => {
                const failed = result.checks.filter((c) => !c.ok);
                return (
                  <tr key={`${result.case_id}-${result.phase}-${index}`}>
                    <td><code>{result.case_id}</code> ({result.job})</td>
                    <td>{result.phase}</td>
                    <td>{VERDICT_LABELS[result.verdict]}</td>
                    <td>{result.run_status ?? '—'}</td>
                    <td>
                      {failed.length > 0 && failed.map((check) => (
                        <p key={check.axis}>
                          <strong>{check.axis}</strong>: kỳ vọng{' '}
                          <code>{formatValue(check.expected)}</code> — thực tế{' '}
                          <code>{formatValue(check.actual)}</code>
                        </p>
                      ))}
                      {result.verdict === 'INCONCLUSIVE' && (
                        <p className="muted">
                          Không có output chấm được (trục kỹ thuật riêng).
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <h3>Lưu ý đo lường</h3>
          <ul className="reasons">
            {report.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </>
      )}
    </div>
  );
}
