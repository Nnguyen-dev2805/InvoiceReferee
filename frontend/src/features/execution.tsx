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
  selectedQuote?: string | null;
}) {
  const [amount, setAmount] = useState("");
  const [payee, setPayee] = useState(caseView?.employee ?? "employee:employee-a");
  const [completionClaim, setCompletionClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  if (caseView === null) return null;

  const summaryParts = caseView.summary.split(" · ");
  const employeeName = summaryParts.length >= 3 ? summaryParts[2].trim() : null;

  async function record() {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `bank:${crypto.randomUUID()}`,
        claimed_kind: "REIMBURSEMENT_RECEIVED",
        claimed_scope: caseView.activity ?? "",
        payer: "company:demo",
        payee,
        amount: Number(amount),
        event_at: new Date().toISOString(),
        completion_claim: completionClaim || null,
        reason: "Ghi nhận tiền thực tế",
      });
      onCase(result.case_view);
      setStatus("Đã ghi nhận tiền thực tế thành công.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  const numericAmount = Number(amount);
  const formattedPreview = !isNaN(numericAmount) && numericAmount > 0 ? formatVnd(numericAmount) : null;

  return (
    <section aria-labelledby="execution-title" className="space-y-4 select-none text-xs">
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="execution-title" className="text-xs font-semibold text-slate-900">
          Ghi nhận dòng tiền thực tế vào sổ cái
        </h2>
      </div>

      {/* Confirmed Actual Money Summary */}
      <div className="space-y-1.5">
        <h3 className="text-xs font-semibold text-slate-700">
          Dòng tiền thực tế đã ghi nhận trong sổ cái
        </h3>
        <div className="border-t border-b border-slate-200 divide-y sm:divide-y-0 sm:divide-x divide-slate-100 grid grid-cols-1 sm:grid-cols-3">
          {Object.entries(caseView.actual_money)
            .filter(([key]) => key in MONEY_LABELS)
            .map(([key, fact]) => (
              <div
                key={key}
                data-testid={`actual-${key}`}
                className="py-2.5 px-2 bg-white text-xs flex flex-col justify-between hover:bg-slate-50/50 transition-colors"
              >
                <span className="text-[11px] text-slate-500 font-medium">{MONEY_LABELS[key]}:</span>
                <strong
                  className={`font-mono-nums tabular-nums text-xs mt-1 ${
                    fact.state === "KNOWN" && fact.value !== null
                      ? "text-slate-900 font-semibold"
                      : "text-slate-400 font-normal select-none"
                  }`}
                  title={fact.state === "KNOWN" && fact.value !== null ? undefined : "Chưa xác minh"}
                >
                  {fact.state === "KNOWN" && fact.value !== null
                    ? formatVnd(fact.value)
                    : "—"}
                </strong>
              </div>
            ))}
        </div>
      </div>

      {/* Input Form */}
      <div className="space-y-3 pt-1">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="received-amount" className="text-slate-700 block text-xs font-medium">
              Số tiền giao dịch thực tế:
            </label>
            {formattedPreview && (
              <span className="text-[11px] font-mono-nums tabular-nums text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                {formattedPreview}
              </span>
            )}
          </div>
          <input
            id="received-amount"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 font-mono-nums tabular-nums font-semibold focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="received-payee" className="text-slate-700 block text-xs font-medium">
              Người nhận tiền:
            </label>
            {employeeName && (
              <span className="text-[11px] text-slate-500">
                Nhân viên đề nghị: <strong className="text-slate-800 font-semibold">{employeeName}</strong>
              </span>
            )}
          </div>
          <input
            id="received-payee"
            value={payee}
            onChange={(event) => setPayee(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 font-mono-nums focus:outline-none focus:border-slate-800"
          />
        </div>

        <div>
          <label htmlFor="completion-claim" className="text-slate-700 block text-xs font-medium mb-1">
            Xác nhận giao dịch ngân hàng / Bằng chứng chuyển khoản:
          </label>
          <input
            id="completion-claim"
            value={completionClaim}
            onChange={(event) => setCompletionClaim(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800"
          />
        </div>
      </div>

      <div className="pt-1">
        <button
          type="button"
          onClick={() => void record()}
          disabled={busy || amount === ""}
          className="bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs py-2.5 px-4 rounded transition-colors disabled:opacity-40 cursor-pointer"
        >
          {busy ? "Đang ghi nhận…" : "Ghi nhận vào sổ cái"}
        </button>
      </div>

      {status !== null && (
        <p role="status" aria-live="polite" className="status p-2.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}
    </section>
  );
}
