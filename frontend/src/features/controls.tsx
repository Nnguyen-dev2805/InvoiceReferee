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
    <div className="flex items-center gap-2 select-none text-xs">
      {error !== null && (
        <span role="alert" className="text-[11px] text-rose-600 font-medium">
          {error}
        </span>
      )}

      {isStopped && (
        <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium bg-rose-50 text-rose-700 border border-rose-200">
          <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
          <span>Hồ sơ đang tạm dừng</span>
        </span>
      )}

      <button
        type="button"
        onClick={() => void control("STOP")}
        disabled={busy || isStopped}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border ${
          isStopped
            ? "opacity-30 border-slate-200 text-slate-400 cursor-not-allowed bg-slate-50"
            : "border-rose-200 bg-rose-50/70 hover:bg-rose-100 text-rose-800"
        }`}
        title="Tạm dừng quy trình đối soát hồ sơ"
      >
        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
        <span>Dừng hồ sơ</span>
      </button>

      <button
        type="button"
        onClick={() => void control("RESUME")}
        disabled={busy || !isStopped}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border ${
          !isStopped
            ? "opacity-30 border-slate-200 text-slate-400 cursor-not-allowed bg-slate-50"
            : "border-emerald-300 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 font-semibold shadow-xs"
        }`}
        title="Tiếp tục xử lý hồ sơ"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${isStopped ? "bg-emerald-600 animate-pulse" : "bg-slate-400"}`} />
        <span>Tiếp tục</span>
      </button>
    </div>
  );
}
