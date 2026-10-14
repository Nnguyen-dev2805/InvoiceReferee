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
    <section aria-labelledby="verify-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-3.5">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="verify-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-slate-700 text-sm" aria-hidden="true">fact_check</span>
          <span>Kiểm chứng (Verify)</span>
        </h2>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 font-['JetBrains_Mono']">
          Contracts §7 &amp; §11
        </span>
      </div>

      <p>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs px-3.5 py-1.5 rounded shadow-sm transition-colors disabled:opacity-40"
        >
          Chạy kiểm chứng
        </button>
      </p>

      {error !== null && (
        <p role="alert" className="error p-2 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      {report !== null && (
        <div data-testid="verify-report" className="space-y-3 pt-2">
          <div className="flex items-center gap-4 text-xs bg-slate-50 p-2.5 rounded border border-slate-200">
            <span>
              Suite: <strong>{report.suite}</strong> · Chế độ: {report.mode} · Số hồ sơ:{" "}
              <span className="font-['JetBrains_Mono']">{report.total}</span>
            </span>
            <span className="border-l border-slate-200 pl-4">
              Dangerous miss: <strong className="font-['JetBrains_Mono']">{report.union_dangerous_miss}</strong> ·{" "}
              <span className={report.release ? "text-emerald-700 font-medium" : "text-rose-700 font-medium"}>
                {report.release ? "Đạt" : "Không đạt"}
              </span>
            </span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-[11px] font-medium">
                <tr>
                  <th className="p-2">Hồ sơ</th>
                  <th className="p-2">Kỳ vọng</th>
                  <th className="p-2">Thực tế</th>
                  <th className="p-2 text-right">Nguy hiểm</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-['JetBrains_Mono'] text-[11px]">
                {report.rows.map((row) => (
                  <tr key={row.root_id} className="hover:bg-slate-50/50">
                    <td className="p-2 text-slate-900 font-medium">{row.root_id}</td>
                    <td className="p-2 text-slate-600">{row.expected_route}</td>
                    <td className="p-2 text-slate-800">{row.actual_route}</td>
                    <td className="p-2 text-right font-medium">{row.union_dangerous_miss}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
