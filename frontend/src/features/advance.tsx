import { useState } from "react";

import { advanceDraft, errorMessage, recordActual } from "../api";
import { formatVnd } from "../format";
import type { CaseView } from "../types";

type Draft = {
  source_id: string;
  amount: number | null;
  payer_name: string | null;
  payee_name: string | null;
  transaction_reference: string | null;
  instrument_method: "TRANSFER" | "CASH" | null;
  instrument_status: "COMPLETED" | "PENDING" | "FAILED" | "UNKNOWN";
  event_at: string | null;
  missing_fields: string[];
  requires_confirmation: boolean;
};

const STATUS_LABELS: Record<string, string> = {
  COMPLETED: "Hoàn tất",
  PENDING: "Đang xử lý",
  FAILED: "Thất bại",
  UNKNOWN: "Chưa rõ",
};

/** Accountant records the advance the employee actually received (plan D). */
export function Advance({ caseView, onCase }: { caseView: CaseView | null; onCase: (view: CaseView) => void }) {
  const [method, setMethod] = useState<"TRANSFER" | "CASH">("TRANSFER");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [status, setStatus] = useState<string>("COMPLETED");
  const [completionClaim, setCompletionClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (caseView === null) return null;

  async function read(file: File) {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await advanceDraft(caseView.id, [file], method);
      setDraft(result);
      setAmount(result.amount !== null ? String(result.amount) : "");
      setReference(result.transaction_reference ?? "");
      setStatus(result.instrument_status);
      setNotice("Đã đọc chứng từ và điền bản nháp. Kiểm tra/sửa rồi xác nhận.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (caseView === null || draft === null) return;
    if (completionClaim.trim() === "") {
      setError("Kế toán cần xác nhận có trách nhiệm đã kiểm tra và giao/nhận tiền.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `${method.toLowerCase()}:${reference || crypto.randomUUID()}`,
        claimed_kind: "ADVANCE_RECEIVED",
        claimed_scope: caseView.activity ?? "",
        payer: "company:demo",
        payee: caseView.employee ?? "",
        amount: Number(amount),
        event_at: new Date().toISOString(),
        completion_claim: completionClaim,
        reason: "Ghi nhận tiền ứng thực nhận",
        instrument_method: method,
        instrument_status: status,
        instrument_reference: reference || null,
      });
      onCase(result.case_view);
      setNotice("Đã ghi nhận tiền ứng thực nhận.");
      setDraft(null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="advance-title" className="space-y-4 select-none text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="advance-title" className="text-xs font-bold text-slate-900 uppercase tracking-wider">
          Ghi nhận tiền ứng thực nhận
        </h2>
      </div>

      <div className="flex items-center gap-2.5">
        <label className="text-slate-700 font-semibold text-xs">Phương thức:</label>
        <select
          aria-label="Phương thức ứng"
          value={method}
          onChange={(event) => setMethod(event.target.value as "TRANSFER" | "CASH")}
          className="bg-white border border-slate-300 rounded px-2.5 py-1 text-xs font-medium text-slate-800 focus:outline-none focus:border-slate-900 shadow-2xs cursor-pointer"
        >
          <option value="TRANSFER">Chuyển khoản</option>
          <option value="CASH">Tiền mặt</option>
        </select>
      </div>

      <label className="block text-slate-700 font-semibold text-xs">
        Chứng từ ứng (PDF/PNG/JPEG)
        <input
          type="file"
          aria-label="Chứng từ ứng"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void read(file);
          }}
          className="mt-1.5 block w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border file:border-slate-300 file:text-xs file:font-semibold file:bg-white file:text-slate-700 hover:file:bg-slate-50 cursor-pointer"
        />
      </label>

      {draft !== null && (
        <div className="space-y-3 bg-slate-50/70 p-4 rounded-lg border border-slate-200" data-testid="advance-draft">
          <p className="text-xs text-slate-500 font-medium">
            Bản nháp từ chứng từ · {draft.instrument_method ?? "—"} · {STATUS_LABELS[draft.instrument_status]}
          </p>
          {draft.missing_fields.length > 0 && (
            <p className="text-xs text-amber-800 bg-amber-50 p-2.5 rounded border border-amber-200">
              Thiếu/mờ trường: {draft.missing_fields.join(", ")} — vui lòng bổ sung.
            </p>
          )}
          <label className="block text-slate-700 font-semibold text-xs">
            Số tiền thực nhận:
            <input
              aria-label="Số tiền thực nhận"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="mt-1 w-full bg-white border border-slate-300 rounded px-3 py-1.5 font-mono-nums text-xs text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs"
            />
          </label>
          <label className="block text-slate-700 font-semibold text-xs">
            Mã giao dịch / số phiếu:
            <input
              aria-label="Mã giao dịch hoặc số phiếu"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              className="mt-1 w-full bg-white border border-slate-300 rounded px-3 py-1.5 font-mono-nums text-xs text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs"
            />
          </label>
          <label className="block text-slate-700 font-semibold text-xs">
            Trạng thái theo nguồn:
            <select
              aria-label="Trạng thái theo nguồn"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
              className="mt-1 w-full bg-white border border-slate-300 rounded px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs cursor-pointer"
            >
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="block text-slate-700 font-semibold text-xs">
            Xác nhận có trách nhiệm của kế toán:
            <input
              aria-label="Xác nhận của kế toán"
              value={completionClaim}
              onChange={(event) => setCompletionClaim(event.target.value)}
              placeholder="Ví dụ: Đã kiểm tra chứng từ và giao đủ tiền cho nhân viên"
              className="mt-1 w-full bg-white border border-slate-300 rounded px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs"
            />
          </label>
          <div className="pt-1">
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={busy || amount === ""}
              className="bg-slate-950 hover:bg-slate-800 text-white text-xs font-semibold px-4 py-1.5 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
            >
              Xác nhận ghi nhận
            </button>
          </div>
        </div>
      )}

      {notice !== null && (
        <p role="status" className="p-2.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">{notice}</p>
      )}
      {error !== null && (
        <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">{error}</p>
      )}
    </section>
  );
}
