import { useState } from "react";

import { controlCase, errorMessage } from "../api";
import type { CaseView } from "../types";

/** Stop/Resume controls for the accountant, plus the audit trail. */
export function Controls({
  caseView,
  onCase,
  currentRole = "accountant",
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
  currentRole?: string;
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

  const isStopped = caseView.state === "STOPPED";

  return (
    <section aria-labelledby="controls-title" className="space-y-3 select-none text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="controls-title" className="text-xs font-semibold text-slate-900">
          Kiểm soát quy trình hồ sơ
        </h2>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void control("STOP")}
          disabled={busy || isStopped}
          className="border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-800 px-3.5 py-1.5 text-xs font-semibold rounded transition-colors disabled:opacity-40 cursor-pointer"
        >
          Dừng hồ sơ
        </button>
        <button
          type="button"
          onClick={() => void control("RESUME")}
          disabled={busy || !isStopped}
          className="border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 px-3.5 py-1.5 text-xs font-semibold rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
        >
          Tiếp tục
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      {currentRole === "accountant" && (
        <div className="pt-1 space-y-1.5">
          <h3 className="text-[11px] font-semibold text-slate-700">
            Nhật ký thao tác kiểm soát
          </h3>
          <ul
            className="audit space-y-1 max-h-40 overflow-y-auto custom-scrollbar bg-slate-50 p-3 rounded border border-slate-200 font-mono-nums text-[11px] text-slate-700"
            data-testid="controls-audit"
          >
            {caseView.audit.map((line, index) => (
              <li key={`${index}-${line}`} className="leading-relaxed">
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
