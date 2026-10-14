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

  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);

  if (caseView === null) return null;

  async function read(file: File) {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setSelectedFileName(file.name);
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
      setSelectedFileName(null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  const numericAmount = Number(amount);
  const formattedPreview = !isNaN(numericAmount) && numericAmount > 0 ? formatVnd(numericAmount) : null;

  return (
    <section aria-labelledby="advance-title" className="space-y-4 select-none text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="advance-title" className="text-xs font-semibold text-slate-900">
          Ghi nhận tạm ứng từ chứng từ
        </h2>
      </div>

      <div className="bg-slate-50/60 border border-slate-200 rounded-lg p-3.5 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-slate-700 font-medium text-xs">Phương thức ứng:</label>
          <select
            aria-label="Phương thức ứng"
            value={method}
            onChange={(event) => setMethod(event.target.value as "TRANSFER" | "CASH")}
            className="bg-white border border-slate-300 rounded-md px-2.5 py-1 text-xs font-medium text-slate-800 focus:outline-none focus:border-slate-800 shadow-2xs cursor-pointer"
          >
            <option value="TRANSFER">Chuyển khoản ngân hàng</option>
            <option value="CASH">Tiền mặt</option>
          </select>
        </div>

        <div>
          <label className="block text-slate-700 font-medium text-xs mb-1.5">
            Chứng từ tạm ứng (Ủy nhiệm chi / Phiếu chi):
          </label>
          <div className="border border-dashed border-slate-300 hover:border-slate-400 bg-white rounded-lg p-3.5 text-center transition-colors">
            <label
              htmlFor="advance-file-input"
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold rounded-md border border-slate-200 cursor-pointer transition-colors"
            >
              <span>{selectedFileName ? "Đổi tệp chứng từ" : "Chọn tệp chứng từ ứng"}</span>
              <input
                id="advance-file-input"
                type="file"
                aria-label="Chứng từ ứng"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void read(file);
                }}
                className="sr-only"
              />
            </label>
            {selectedFileName ? (
              <span className="text-[11px] text-emerald-700 font-medium block mt-1.5">
                ✓ {selectedFileName}
              </span>
            ) : (
              <span className="text-[11px] text-slate-400 block mt-1">
                Hỗ trợ PDF, PNG, JPG (tự động nhận diện số tiền và mã tham chiếu)
              </span>
            )}
          </div>
        </div>
      </div>

      {draft !== null && (
        <div className="space-y-3 bg-white p-4 rounded-lg border border-slate-200 shadow-2xs" data-testid="advance-draft">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-xs font-semibold text-slate-900">Bản nháp trích xuất từ chứng từ</span>
              <span className="text-[11px] font-medium bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200">
                {draft.instrument_method === "TRANSFER" ? "Chuyển khoản" : draft.instrument_method === "CASH" ? "Tiền mặt" : draft.instrument_method ?? "—"}
              </span>
            </div>
            <span className="text-[11px] font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              {STATUS_LABELS[draft.instrument_status] ?? draft.instrument_status}
            </span>
          </div>

          {draft.missing_fields.length > 0 && (
            <p className="text-xs text-amber-800 bg-amber-50 p-2.5 rounded-md border border-amber-200">
              ⚠ Thiếu hoặc mờ trường: {draft.missing_fields.join(", ")} — vui lòng bổ sung thông tin bên dưới.
            </p>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-1">
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="advance-amount" className="block text-slate-700 font-medium text-xs">
                  Số tiền thực nhận:
                </label>
                {formattedPreview && (
                  <span className="text-[11px] font-mono-nums tabular-nums text-emerald-700 font-semibold bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                    {formattedPreview}
                  </span>
                )}
              </div>
              <input
                id="advance-amount"
                aria-label="Số tiền thực nhận"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-1.5 font-mono-nums tabular-nums font-semibold text-xs text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
              />
            </div>

            <div className="sm:col-span-1">
              <label htmlFor="advance-ref" className="block text-slate-700 font-medium text-xs mb-1">
                Mã giao dịch / Số phiếu:
              </label>
              <input
                id="advance-ref"
                aria-label="Mã giao dịch hoặc số phiếu"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-1.5 font-mono-nums text-xs text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
              />
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="advance-status" className="block text-slate-700 font-medium text-xs mb-1">
                Trạng thái theo nguồn:
              </label>
              <select
                id="advance-status"
                aria-label="Trạng thái theo nguồn"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs cursor-pointer"
              >
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            <div className="sm:col-span-2">
              <label htmlFor="advance-claim" className="block text-slate-700 font-medium text-xs mb-1">
                Xác nhận có trách nhiệm của kế toán:
              </label>
              <input
                id="advance-claim"
                aria-label="Xác nhận của kế toán"
                value={completionClaim}
                onChange={(event) => setCompletionClaim(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={busy || amount === ""}
              className="bg-slate-950 hover:bg-slate-800 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors disabled:opacity-40 cursor-pointer"
            >
              {busy ? "Đang xử lý…" : "Xác nhận ghi nhận"}
            </button>
          </div>
        </div>
      )}

      {notice !== null && (
        <p role="status" className="p-2.5 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">{notice}</p>
      )}
      {error !== null && (
        <p role="alert" className="error p-2.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">{error}</p>
      )}
    </section>
  );
}
