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
        // The dossier's own activity (server re-checks it), never a hard-coded id.
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
    <section aria-labelledby="execution-title" className="bg-white border border-slate-200 rounded-xl p-5 text-xs shadow-xs space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h2 id="execution-title" className="text-sm font-bold text-slate-900 tracking-tight">
            Ghi nhận dòng tiền thực tế
          </h2>
        </div>
      </div>

      {/* Confirmed Actual Money Summary */}
      <div className="bg-slate-50/70 p-3.5 rounded-lg border border-slate-200/80 space-y-2">
        <div className="text-xs font-bold text-slate-700 uppercase tracking-wide">
          Dòng tiền thực tế đã ghi nhận trong sổ cái
        </div>
        <ul className="money grid grid-cols-3 gap-2.5">
          {Object.entries(caseView.actual_money)
            .filter(([key]) => key in MONEY_LABELS)
            .map(([key, fact]) => (
              <li
                key={key}
                data-testid={`actual-${key}`}
                className="bg-white p-2.5 rounded-md border border-slate-200 text-xs flex flex-col shadow-2xs"
              >
                <span className="text-[11px] text-slate-500 font-medium">{MONEY_LABELS[key]}:</span>
                <strong className={`font-mono-nums text-xs font-semibold mt-1 ${fact.state === "KNOWN" && fact.value !== null ? "text-slate-900" : "text-amber-700 font-medium"}`}>
                  {fact.state === "KNOWN" && fact.value !== null
                    ? formatVnd(fact.value)
                    : "Chưa xác minh"}
                </strong>
              </li>
            ))}
        </ul>
      </div>

      {/* Input Form */}
      <div className="space-y-3 pt-1">
        <div>
          <label htmlFor="received-amount" className="text-slate-700 block text-xs font-semibold">
            Số tiền đã nhận / chuyển thực tế (VNĐ)
            <div className="relative mt-1">
              <input
                id="received-amount"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="Ví dụ: 3270000"
                className="w-full bg-white border border-slate-200 rounded-lg text-xs px-3 py-2 text-slate-900 font-mono-nums focus:outline-none focus:border-slate-400"
              />
              {formattedPreview && (
                <span className="absolute right-3 top-2 text-[11px] font-mono-nums text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                  {formattedPreview}
                </span>
              )}
            </div>
          </label>
        </div>

        <div>
          <label htmlFor="received-payee" className="text-slate-700 block text-xs font-semibold">
            Người nhận tiền
            <input
              id="received-payee"
              value={payee}
              onChange={(event) => setPayee(event.target.value)}
              className="w-full mt-1 bg-white border border-slate-200 rounded-lg text-xs px-3 py-2 text-slate-900 font-mono-nums focus:outline-none focus:border-slate-400"
            />
          </label>
        </div>

        <div>
          <label htmlFor="completion-claim" className="text-slate-700 block text-xs font-semibold">
            Xác nhận giao dịch chuyển khoản (Bắt buộc để tính là đã thực hiện hoàn tất)
            <input
              id="completion-claim"
              value={completionClaim}
              onChange={(event) => setCompletionClaim(event.target.value)}
              placeholder="Ví dụ: Đã chuyển khoản qua Techcombank NAPAS 247, mã giao dịch 992812"
              className="w-full mt-1 bg-white border border-slate-200 rounded-lg text-xs px-3 py-2 text-slate-900 focus:outline-none focus:border-slate-400"
            />
          </label>
        </div>
      </div>

      <div className="pt-2">
        <button
          type="button"
          onClick={() => void record()}
          disabled={busy || amount === ""}
          className="w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs py-2.5 px-4 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
        >
          Ghi nhận
        </button>
      </div>

      {status !== null && (
        <p role="status" aria-live="polite" className="status p-3 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error p-3 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}
    </section>
  );
}
