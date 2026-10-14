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

/** Verify Drawer / Dialog: Isolated benchmark tool for engineering audit. */
export function Verify({
  isOpen = false,
  onClose,
}: {
  isOpen?: boolean;
  onClose?: () => void;
}) {
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

  // If not open (when used as modal), return null unless rendered unconditionally
  if (onClose && !isOpen) return null;

  const content = (
    <section aria-labelledby="verify-title" className="space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div>
          <h2 id="verify-title" className="text-sm font-bold text-slate-900">
            Kiểm chứng độc lập (Benchmark Runner)
          </h2>
          <p className="text-[11px] text-slate-500">
            Chạy bộ test suite đối soát với gold oracle độc lập (Contracts §7 &amp; §11)
          </p>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="px-2.5 py-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 text-xs font-semibold cursor-pointer border border-slate-200"
          >
            Đóng
          </button>
        )}
      </div>

      <div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs px-4 py-2 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
        >
          Chạy kiểm chứng
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      {report !== null && (
        <div data-testid="verify-report" className="space-y-3 pt-2">
          <div className="flex items-center gap-4 text-xs bg-slate-50 p-3 rounded-lg border border-slate-200 font-mono-nums">
            <span>
              Suite: <strong>{report.suite}</strong> · Chế độ: {report.mode} · Tổng số hồ sơ:{" "}
              <strong>{report.total}</strong>
            </span>
            <span className="border-l border-slate-200 pl-4">
              Dangerous miss: <strong>{report.union_dangerous_miss}</strong> ·{" "}
              <span className={report.release ? "text-emerald-700 font-bold" : "text-rose-700 font-bold"}>
                {report.release ? "ĐẠT CHUẨN PHÁT HÀNH" : "CHƯA ĐẠT"}
              </span>
            </span>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg max-h-72 custom-scrollbar">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-[11px] font-semibold sticky top-0">
                <tr>
                  <th className="p-2.5">Hồ sơ</th>
                  <th className="p-2.5">Kỳ vọng</th>
                  <th className="p-2.5">Thực tế</th>
                  <th className="p-2.5 text-right">Nguy hiểm</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono-nums text-[11px]">
                {report.rows.map((row) => (
                  <tr key={row.root_id} className="hover:bg-slate-50/70">
                    <td className="p-2.5 text-slate-900 font-medium">{row.root_id}</td>
                    <td className="p-2.5 text-slate-600">{row.expected_route}</td>
                    <td className="p-2.5 text-slate-800">{row.actual_route}</td>
                    <td className="p-2.5 text-right font-semibold">{row.union_dangerous_miss}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );

  if (onClose) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
        <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-2xl w-full p-6 animate-in fade-in zoom-in-95 duration-150">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 text-xs shadow-xs">
      {content}
    </div>
  );
}
