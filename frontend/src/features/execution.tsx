import { useState } from "react";

import { errorMessage, recordActual } from "../api";
import { formatVnd } from "../format";
import type { CaseView } from "../types";

const MONEY_LABELS: Record<string, string> = {
  P: "Đã hoàn",
  R: "Đã thu hồi",
  A: "Ứng thực nhận",
};

/** The accountant records actual money moved (bank/cash) against a root. */
export function Execution({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [amount, setAmount] = useState("");
  const [payee, setPayee] = useState("employee:employee-a");
  const [completionClaim, setCompletionClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  if (caseView === null) return null;

  async function record() {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `bank:${crypto.randomUUID()}`,
        claimed_kind: "REIMBURSEMENT_RECEIVED",
        claimed_scope: "activity:travel-a",
        payer: "company:demo",
        payee,
        amount: Number(amount),
        event_at: new Date().toISOString(),
        // A bare amount is not proof: the accountant must confirm the transfer
        // responsibly, or the money stays observed and does not fulfill (§4).
        completion_claim: completionClaim || null,
        reason: "Ghi nhận tiền thực tế",
      });
      onCase(result.case_view);
      setStatus("Đã ghi nhận tiền thực tế.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="execution-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="execution-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-slate-700 text-sm" aria-hidden="true">payments</span>
          <span>Ghi nhận tiền thực tế</span>
        </h2>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-200 font-['JetBrains_Mono']">
          NAPAS 247 Ready
        </span>
      </div>

      <div className="bg-slate-50/70 p-3 rounded border border-slate-100 space-y-2">
        <div className="text-[11px] font-semibold text-slate-700 uppercase tracking-wide">
          Tiền thực tế đã xác nhận
        </div>
        <ul className="money grid grid-cols-3 gap-2">
          {Object.entries(caseView.actual_money)
            .filter(([key]) => key in MONEY_LABELS)
            .map(([key, fact]) => (
              <li
                key={key}
                data-testid={`actual-${key}`}
                className="bg-white p-2 rounded border border-slate-200 text-xs flex flex-col"
              >
                <span className="text-[11px] text-slate-500">{MONEY_LABELS[key]}:</span>
                <strong className={`font-['JetBrains_Mono'] text-xs font-medium mt-0.5 ${fact.state === "KNOWN" && fact.value !== null ? "text-slate-900" : "text-amber-700 font-normal"}`}>
                  {fact.state === "KNOWN" && fact.value !== null
                    ? formatVnd(fact.value)
                    : "Chưa xác minh"}
                </strong>
              </li>
            ))}
        </ul>
      </div>

      <div className="space-y-3">
        <p>
          <label htmlFor="received-amount" className="text-slate-600 block text-xs font-medium">
            Số tiền đã nhận
            <input
              id="received-amount"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="Ví dụ: 3270000"
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-['JetBrains_Mono']"
            />
          </label>
        </p>
        <p>
          <label htmlFor="received-payee" className="text-slate-600 block text-xs font-medium">
            Người nhận
            <input
              id="received-payee"
              value={payee}
              onChange={(event) => setPayee(event.target.value)}
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-['JetBrains_Mono']"
            />
          </label>
        </p>
        <p>
          <label htmlFor="completion-claim" className="text-slate-600 block text-xs font-medium">
            Xác nhận đã chuyển (bắt buộc để tính là đã thực hiện)
            <input
              id="completion-claim"
              value={completionClaim}
              onChange={(event) => setCompletionClaim(event.target.value)}
              placeholder="Ví dụ: Đã chuyển khoản qua Techcombank NAPAS 247"
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            />
          </label>
        </p>
      </div>

      <p className="pt-1">
        <button
          type="button"
          onClick={() => void record()}
          disabled={busy || amount === ""}
          className="bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs px-4 py-2 rounded shadow-sm transition-colors disabled:opacity-40"
        >
          Ghi nhận
        </button>
      </p>

      {status !== null && (
        <p role="status" aria-live="polite" className="status p-2 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error p-2 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}
    </section>
  );
}
