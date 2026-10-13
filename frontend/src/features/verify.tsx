import { useState } from "react";

import { errorMessage, runVerify } from "../api";

interface ScoreRowView {
  root_id: string;
  expected_route: string;
  actual_route: string;
  union_dangerous_miss: number;
  correct_auto_completion: number;
  technical_failure: number;
}

interface VerifyReport {
  suite: string;
  mode: string;
  total: number;
  union_dangerous_miss: number;
  release: boolean;
  rows: ScoreRowView[];
}

/** Verify: run a suite through the workflow and score with independent gold. */
export function Verify() {
  const [report, setReport] = useState<VerifyReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setReport(await runVerify("development", "STUB"));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="verify-title">
      <h2 id="verify-title">Kiểm chứng (Verify)</h2>
      <p>
        <button type="button" onClick={() => void run()} disabled={busy}>
          Chạy kiểm chứng
        </button>
      </p>
      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {report !== null && (
        <div data-testid="verify-report">
          <p>
            Suite: <strong>{report.suite}</strong> · Chế độ: {report.mode} · Số hồ sơ:{" "}
            {report.total}
          </p>
          <p>
            Dangerous miss: <strong>{report.union_dangerous_miss}</strong> ·{" "}
            {report.release ? "Đạt" : "Không đạt"}
          </p>
          <table>
            <thead>
              <tr>
                <th>Hồ sơ</th>
                <th>Kỳ vọng</th>
                <th>Thực tế</th>
                <th>Nguy hiểm</th>
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row) => (
                <tr key={row.root_id}>
                  <td>{row.root_id}</td>
                  <td>{row.expected_route}</td>
                  <td>{row.actual_route}</td>
                  <td>{row.union_dangerous_miss}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
