import { useState } from "react";

import { controlCase, errorMessage } from "../api";
import type { CaseView } from "../types";

/** Stop/Resume controls for the accountant, plus the audit trail. */
export function Controls({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (caseView === null) return null;

  async function control(action: "STOP" | "RESUME") {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await controlCase(caseView.id, action, `${action} bởi người dùng`);
      onCase(result.case_view);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="controls-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-3.5">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="controls-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-slate-700 text-sm" aria-hidden="true">tune</span>
          <span>Kiểm soát</span>
        </h2>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-700 font-['JetBrains_Mono']">
          Hợp đồng §6
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => void control("STOP")}
          disabled={busy}
          className="border border-rose-200 bg-rose-50/50 hover:bg-rose-100/70 text-rose-700 px-3 py-1.5 text-xs font-medium rounded transition-colors disabled:opacity-40"
        >
          Dừng hồ sơ
        </button>
        <button
          type="button"
          onClick={() => void control("RESUME")}
          disabled={busy}
          className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 px-3 py-1.5 text-xs font-medium rounded shadow-sm transition-colors disabled:opacity-40"
        >
          Tiếp tục
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      <div>
        <h3 className="text-[11px] font-semibold text-slate-700 uppercase tracking-wide mb-1.5">
          Lịch sử kiểm toán
        </h3>
        <ul
          className="audit space-y-1 max-h-48 overflow-y-auto custom-scrollbar bg-slate-50 p-2 rounded border border-slate-200/80 font-['JetBrains_Mono'] text-[10.5px] text-slate-700"
          data-testid="controls-audit"
        >
          {caseView.audit.map((line, index) => (
            <li key={`${index}-${line}`} className="leading-relaxed">
              {line}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
