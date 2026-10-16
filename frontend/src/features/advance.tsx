import { useState } from "react";

import { advanceDraft, api, errorMessage, getAdvanceDraft, recordActual } from "../api";
import { formatVnd } from "../format";
import { Coverage } from "./coverage";
import type { ActivityLinkSignalView, CaseView } from "../types";

type DraftRef = {
  source_id: string;
  source_sha256: string;
  page: number | null;
  exact_quote: string;
};

type Draft = {
  source_id: string;
  draft_id: string;
  amount: number | null;
  payer_name: string | null;
  payee_name: string | null;
  transaction_reference: string | null;
  activity_reference: string | null;
  activity_link_status: "LINKED" | "NEEDS_CONFIRMATION" | "NOT_FOUND" | "CONFLICT";
  matched_activity_id: string | null;
  activity_link_basis: string | null;
  activity_link_signals: ActivityLinkSignalView[];
  activity_link_candidate_count: number;
  instrument_method: "TRANSFER" | "CASH" | null;
  instrument_status: "COMPLETED" | "PENDING" | "FAILED" | "UNKNOWN";
  event_at: string | null;
  missing_fields: string[];
  requires_confirmation: boolean;
  already_recorded: boolean;
  refs: DraftRef[];
};

const STATUS_LABELS: Record<string, string> = {
  COMPLETED: "Hoàn tất",
  PENDING: "Đang xử lý",
  FAILED: "Thất bại",
  UNKNOWN: "Chưa rõ",
};

const FIELD_LABELS: Record<string, string> = {
  amount: "số tiền",
  payer_name: "bên chi",
  payee_name: "người nhận",
  transaction_reference: "mã giao dịch/số phiếu",
  instrument_status: "trạng thái giao dịch",
  event_at: "ngày giao dịch",
};

/** Accountant records the advance the employee actually received (plan D). */
export function Advance({
  caseView,
  onCase,
  onSourceSelected,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
  onSourceSelected?: (sourceId: string) => void;
}) {
  const [method, setMethod] = useState<"TRANSFER" | "CASH">("TRANSFER");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [payer, setPayer] = useState("");
  const [payee, setPayee] = useState("");
  const [eventAt, setEventAt] = useState("");
  const [status, setStatus] = useState<string>("COMPLETED");
  const [completionClaim, setCompletionClaim] = useState("");
  const [activityLinkConfirmed, setActivityLinkConfirmed] = useState(false);
  const [activityLinkReason, setActivityLinkReason] = useState("");
  const [rechecking, setRechecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);

  if (caseView === null) return null;

  function showDraft(result: Awaited<ReturnType<typeof advanceDraft>>) {
    onCase(result.case_view);
    onSourceSelected?.(result.draft.source_id);
    setDraft({
      ...result.draft,
      refs: result.draft.refs ?? [],
      activity_link_signals: result.draft.activity_link_signals ?? [],
      activity_link_candidate_count: result.draft.activity_link_candidate_count ?? 0,
      already_recorded: result.draft.already_recorded ?? false,
    });
    setAmount(result.draft.amount !== null ? String(result.draft.amount) : "");
    setReference(result.draft.transaction_reference ?? "");
    setPayer(result.draft.payer_name ?? "");
    setPayee(result.draft.payee_name ?? "");
    setEventAt(result.draft.event_at ?? "");
    setStatus(result.draft.instrument_status);
    setMethod(result.draft.instrument_method ?? method);
    setSelectedFileName(result.case_view.sources.find((source) => source.id === result.draft.source_id)?.filename ?? "Chứng từ đã lưu");
    setActivityLinkConfirmed(false);
    setActivityLinkReason("");
    setCompletionClaim("");
  }

  async function recheck() {
    if (caseView === null) return;
    setRechecking(true);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      showDraft(await getAdvanceDraft(caseView.id, draft?.draft_id));
      setNotice("Đã kiểm tra lại liên kết từ bản đọc đã lưu.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
      setRechecking(false);
    }
  }

  async function read(file: File) {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setSelectedFileName(file.name);
    try {
      const result = await advanceDraft(caseView.id, [file], caseView.version, method);
      showDraft(result);
      setNotice("Đã đọc chứng từ và điền bản nháp. Kiểm tra/sửa rồi xác nhận.");
    } catch (cause) {
      // Source attachment commits before provider I/O. Refresh the case version
      // even when OCR fails so a retry does not use a stale expected version.
      try {
        onCase(await api.getCase(caseView.id));
      } catch {
        // Preserve the original read error; the source remains attached.
      }
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (caseView === null || draft === null) return;
    // No fabricated identity: a missing transaction code stays an unresolved
    // draft — the server rejects a UUID minted in place of the real reference.
    if (reference.trim() === "") {
      setError("Thiếu mã giao dịch / số phiếu: bổ sung đúng thông tin thiếu, không tự bịa định danh.");
      return;
    }
    if (payer.trim() === "" || payee.trim() === "") {
      setError("Thiếu bên chi hoặc người nhận trên chứng từ: kế toán xử lý đúng thông tin thiếu.");
      return;
    }
    // The transaction time comes from the source document, never the confirm
    // moment (recorded_at is the server's own clock).
    if (eventAt.trim() === "") {
      setError("Thiếu ngày giao dịch trên chứng từ: bổ sung ngày thực tế, không dùng thời điểm xác nhận.");
      return;
    }
    const referenceLinkedToThisCase =
      draft.activity_link_status === "LINKED" &&
      draft.matched_activity_id === caseView.activity;
    const referenceConflicts =
      draft.activity_link_status === "CONFLICT" ||
      (draft.activity_link_status === "LINKED" && !referenceLinkedToThisCase);
    if (referenceConflicts) {
      setError("Mã công việc trên chứng từ trỏ tới hồ sơ khác; giữ giao dịch để kế toán xác minh.");
      return;
    }
    if (
      !referenceLinkedToThisCase &&
      (!activityLinkConfirmed || activityLinkReason.trim().length < 12)
    ) {
      setError("Kế toán cần xác nhận chứng từ thuộc đúng công việc và nêu căn cứ đối chiếu.");
      return;
    }
    const explanation = completionClaim.trim() || activityLinkReason.trim();
    if (draft.missing_fields.length > 0 && explanation.length < 12) {
      setError("Ghi rõ căn cứ bổ sung thông tin OCR còn thiếu trước khi ghi nhận.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `${method.toLowerCase()}:${reference.trim()}`,
        claimed_kind: "ADVANCE_RECEIVED",
        claimed_scope: caseView.activity ?? "",
        payer: payer.trim(),
        payee: payee.trim(),
        amount: Number(amount),
        event_at: eventAt.trim(),
        completion_claim: null,
        refs: draft.refs ?? [],
        reason: explanation,
        instrument_method: method,
        instrument_status: status,
        instrument_reference: reference.trim() || null,
        advance_draft_id: draft.draft_id,
        activity_link_confirmed: referenceLinkedToThisCase || activityLinkConfirmed,
        activity_link_reason: activityLinkReason.trim() || null,
      }, caseView.version);
      onCase(result.case_view);
      setNotice(
        status === "COMPLETED"
          ? "Đã ghi nhận tiền ứng thực nhận."
          : "Đã lưu chứng từ để đối chiếu (trạng thái nguồn chưa hoàn tất nên chưa thành ứng thực nhận đã xác minh).",
      );
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
    <section aria-labelledby="advance-title" className="space-y-4 text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200">
        <h2 id="advance-title" className="text-xs font-semibold text-slate-900">
          Ghi nhận tạm ứng từ chứng từ
        </h2>
      </div>

      <div className="space-y-3 pt-1">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <label htmlFor="advance-method-select" className="text-slate-700 font-medium text-xs">Phương thức ứng:</label>
            <select
              id="advance-method-select"
              aria-label="Phương thức ứng"
              value={method}
              onChange={(event) => setMethod(event.target.value as "TRANSFER" | "CASH")}
              className="bg-white border border-slate-300 rounded px-2.5 py-1 text-xs font-medium text-slate-800 focus:outline-none focus:border-slate-800 cursor-pointer shadow-2xs"
            >
              <option value="TRANSFER">Chuyển khoản ngân hàng</option>
              <option value="CASH">Tiền mặt</option>
            </select>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void recheck()}
            className="rounded border border-slate-300 hover:border-slate-400 bg-white hover:bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 disabled:opacity-40 transition-colors shadow-2xs cursor-pointer"
          >
            Kiểm tra lại bản nháp đã lưu
          </button>
        </div>

        <div>
          <label
            htmlFor="advance-file-input"
            className={`border border-dashed rounded-lg p-5 text-center flex flex-col items-center justify-center transition-colors block group ${
              busy
                ? "border-slate-400 bg-slate-50/80 cursor-wait pointer-events-none"
                : "border-slate-300 hover:border-slate-500 bg-slate-50/40 hover:bg-slate-50/80 cursor-pointer"
            }`}
          >
            <div className={`w-9 h-9 rounded-full flex items-center justify-center mb-2.5 transition-colors ${
              busy ? "bg-slate-200 text-slate-800" : "bg-slate-100 text-slate-500 group-hover:text-slate-900 group-hover:bg-slate-200"
            }`}>
              {busy ? (
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              )}
            </div>

            {busy ? (
              <>
                <span className="font-semibold text-slate-900 block text-xs">
                  {rechecking ? "Đang kiểm tra bản nháp đã lưu…" : "Đang nhận diện chứng từ tạm ứng…"}
                </span>
                <span className="text-[11px] text-slate-500 block mt-1 animate-pulse">
                  {rechecking ? "Đối chiếu lại thông tin từ bản đọc đã lưu." : `Tệp ${selectedFileName ?? "chứng từ"} · OCR đang bóc tách số tiền, mã UNC và người nhận`}
                </span>
              </>
            ) : selectedFileName ? (
              <>
                <span className="font-semibold text-slate-800 block text-xs">
                  {selectedFileName}
                </span>
                <span className="text-[11px] text-emerald-700 font-medium block mt-1">
                  ✓ Đã tải lên — Nhấn để chọn tệp chứng từ khác
                </span>
              </>
            ) : (
              <>
                <span className="font-semibold text-slate-800 block text-xs">
                  Nhấn để chọn tệp hoặc kéo thả tài liệu vào đây
                </span>
                <span className="text-[11px] text-slate-500 block mt-1 max-w-md">
                  Hỗ trợ PDF, PNG, JPG (Ủy nhiệm chi ngân hàng, giấy báo nợ, phiếu chi tiền mặt)
                </span>
              </>
            )}
            <input
              id="advance-file-input"
              type="file"
              aria-label="Chứng từ ứng"
              accept=".pdf,.png,.jpg,.jpeg"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void read(file);
              }}
              className="sr-only"
            />
          </label>
        </div>
      </div>

      {/* Connected Micro-Stepper & Skeleton Preview during Active Processing */}
      {busy && !rechecking && draft === null && (
        <div className="space-y-4 pt-3 border-t border-slate-200">
          {/* Connected Micro-Stepper */}
          <div className="pl-6 space-y-3.5 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-slate-200">
            {/* Step 1: Upload Complete */}
            <div className="relative flex items-start gap-3">
              <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-emerald-600 text-white flex items-center justify-center text-[9px] font-bold">
                ✓
              </span>
              <div>
                <p className="text-xs font-medium text-slate-900">
                  Đã tiếp nhận tệp: <span className="font-mono text-slate-700">{selectedFileName}</span>
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Tệp nguồn đã sẵn sàng đưa vào luồng trích xuất
                </p>
              </div>
            </div>

            {/* Step 2: OCR Running */}
            <div className="relative flex items-start gap-3">
              <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-slate-900 text-white flex items-center justify-center">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
              </span>
              <div>
                <p className="text-xs font-semibold text-slate-900">
                  Đang nhận diện &amp; bóc tách thông tin giao dịch
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5 animate-pulse">
                  OCR đọc số tiền thực nhận, mã UNC/số phiếu, người thụ hưởng và ngày giao dịch…
                </p>
              </div>
            </div>

            {/* Step 3: Pending Draft Fill */}
            <div className="relative flex items-start gap-3 opacity-50">
              <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-slate-100 border border-slate-300" />
              <div>
                <p className="text-xs font-medium text-slate-700">
                  Điền tự động vào bản nháp tạm ứng
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Kế toán kiểm tra, đối chiếu chứng từ và xác nhận ghi nhận
                </p>
              </div>
            </div>
          </div>

          {/* Skeleton Shimmer Draft Preview */}
          <div className="pt-2 space-y-3 opacity-60 pointer-events-none">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-300 animate-pulse" />
                <span className="text-xs font-medium text-slate-400">Đang chuẩn bị bản nháp…</span>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-1 space-y-2">
                <div className="h-3 w-24 bg-slate-200 rounded animate-pulse" />
                <div className="h-6 w-full border-b border-slate-200 animate-pulse bg-slate-50" />
              </div>
              <div className="sm:col-span-1 space-y-2">
                <div className="h-3 w-28 bg-slate-200 rounded animate-pulse" />
                <div className="h-6 w-full border-b border-slate-200 animate-pulse bg-slate-50" />
              </div>
              <div className="sm:col-span-1 space-y-2">
                <div className="h-3 w-32 bg-slate-200 rounded animate-pulse" />
                <div className="h-6 w-full border-b border-slate-200 animate-pulse bg-slate-50" />
              </div>
              <div className="sm:col-span-1 space-y-2">
                <div className="h-3 w-32 bg-slate-200 rounded animate-pulse" />
                <div className="h-6 w-full border-b border-slate-200 animate-pulse bg-slate-50" />
              </div>
            </div>
          </div>
        </div>
      )}

      {draft !== null && (
        <div className="space-y-3 pt-3 border-t border-slate-200" data-testid="advance-draft">
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
              ⚠ Chưa đọc rõ: {draft.missing_fields.map((field) => FIELD_LABELS[field] ?? "thông tin giao dịch").join(", ")} — kiểm tra trên chứng từ và bổ sung bên dưới.
            </p>
          )}

          {draft.already_recorded && (
            <p className="text-xs text-slate-700 bg-slate-100 p-2.5 rounded-md border border-slate-300">
              ⓘ Mã giao dịch này đã có trong lịch sử công ty — ghi nhận lại không làm tăng ứng thực nhận (idempotent).
            </p>
          )}

          {draft.activity_reference && (
            <p className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded-md border border-slate-200">
              Tham chiếu khoản ứng trên chứng từ: <strong>{draft.activity_reference}</strong>
            </p>
          )}
          {draft.activity_link_status === "CONFLICT" ||
          (draft.activity_link_status === "LINKED" && draft.matched_activity_id !== caseView.activity) ? (
            <div role="alert" className="space-y-1 rounded-md border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-900">
              <p className="font-medium">Có mâu thuẫn; chưa thể liên kết chứng từ với hồ sơ này.</p>
              {draft.activity_link_signals.filter((signal) => signal.state === "CONFLICT").map((signal, index) => (
                <p key={`${signal.field}:${index}`}>{signal.summary}</p>
              ))}
            </div>
          ) : draft.activity_link_status === "LINKED" ? (
            <div role="status" className="space-y-1 rounded-md border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-900">
              <p className="font-medium">
                {draft.activity_link_basis === "MULTI_FIELD_MATCH"
                  ? "Đã tự liên kết với hồ sơ này"
                  : "Mã hồ sơ trên chứng từ khớp duy nhất với công việc trong hồ sơ này."}
              </p>
              {draft.activity_link_basis === "MULTI_FIELD_MATCH" && (
                <ul className="list-disc space-y-0.5 pl-4 text-emerald-800">
                  {draft.activity_link_signals
                    .filter((signal) => signal.state === "MATCHED")
                    .map((signal, index) => <li key={`${signal.field}:${index}`}>{signal.summary}</li>)}
                </ul>
              )}
              {draft.activity_link_signals.some((signal) => signal.state === "UNMAPPED") && (
                <details className="text-slate-600">
                  <summary className="cursor-pointer">Chi tiết tham chiếu khoản ứng</summary>
                  {draft.activity_link_signals.filter((signal) => signal.state === "UNMAPPED")
                    .map((signal, index) => <p key={index}>{signal.summary}</p>)}
                </details>
              )}
            </div>
          ) : (
            <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-2.5">
              <p className="text-xs font-medium text-amber-900">
                {draft.activity_link_candidate_count > 1
                  ? `Có ${draft.activity_link_candidate_count} hồ sơ cùng phù hợp; kế toán cần xác nhận đúng công việc.`
                  : "Chưa đủ căn cứ tự liên kết. Hãy kiểm tra các thông tin còn thiếu với công việc đang mở."}
              </p>
              {draft.activity_link_signals.some((signal) => ["MISSING", "MISMATCH", "AMBIGUOUS", "UNMAPPED"].includes(signal.state)) && (
                <ul className="list-disc space-y-0.5 pl-4 text-xs text-amber-800">
                  {draft.activity_link_signals
                    .filter((signal) => ["MISSING", "MISMATCH", "AMBIGUOUS", "UNMAPPED"].includes(signal.state))
                    .map((signal, index) => <li key={`${signal.field}:${index}`}>{signal.summary}</li>)}
                </ul>
              )}
              <label className="flex items-start gap-2 text-xs text-slate-800">
                <input
                  type="checkbox"
                  aria-label="Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này"
                  checked={activityLinkConfirmed}
                  onChange={(event) => setActivityLinkConfirmed(event.target.checked)}
                  className="mt-0.5"
                />
                <span>Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này: {caseView.summary}</span>
              </label>
              <label htmlFor="advance-activity-link-reason" className="block text-slate-700 font-medium text-xs">
                Căn cứ đối chiếu với công việc
              </label>
              {draft.missing_fields.length > 0 && (
                <p className="text-xs text-amber-800">Nêu cả căn cứ bổ sung các thông tin OCR chưa đọc rõ.</p>
              )}
              <textarea
                id="advance-activity-link-reason"
                aria-label="Căn cứ đối chiếu với công việc"
                value={activityLinkReason}
                onChange={(event) => setActivityLinkReason(event.target.value)}
                rows={2}
                className="w-full bg-white border border-slate-300 rounded-md px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-slate-800"
              />
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div className="sm:col-span-1 space-y-1">
              <div className="flex items-center justify-between">
                <label htmlFor="advance-amount" className="text-slate-600 block text-[11px] font-medium">
                  Số tiền thực nhận:
                </label>
                {formattedPreview && (
                  <span className="text-[11px] font-mono tabular-nums text-emerald-700 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                    {formattedPreview}
                  </span>
                )}
              </div>
              <input
                id="advance-amount"
                aria-label="Số tiền thực nhận"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 font-mono tabular-nums font-semibold text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </div>

            <div className="sm:col-span-1 space-y-1">
              <label htmlFor="advance-ref" className="text-slate-600 block text-[11px] font-medium">
                Mã giao dịch / Số phiếu:
              </label>
              <input
                id="advance-ref"
                aria-label="Mã giao dịch hoặc số phiếu"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 font-mono text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </div>

            <div className="sm:col-span-1 space-y-1">
              <label htmlFor="advance-payer" className="text-slate-600 block text-[11px] font-medium">
                Bên chi (theo chứng từ):
              </label>
              <input
                id="advance-payer"
                aria-label="Bên chi theo chứng từ"
                value={payer}
                onChange={(event) => setPayer(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-sm font-medium text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </div>

            <div className="sm:col-span-1 space-y-1">
              <label htmlFor="advance-payee" className="text-slate-600 block text-[11px] font-medium">
                Người nhận (theo chứng từ):
              </label>
              <input
                id="advance-payee"
                aria-label="Người nhận theo chứng từ"
                value={payee}
                onChange={(event) => setPayee(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-sm font-medium text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </div>

            <div className="sm:col-span-2 space-y-1">
              <label htmlFor="advance-event-at" className="text-slate-600 block text-[11px] font-medium">
                Ngày giao dịch (theo chứng từ, giữ nguyên):
              </label>
              <input
                id="advance-event-at"
                aria-label="Ngày giao dịch theo chứng từ"
                value={eventAt}
                onChange={(event) => setEventAt(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
              <span className="text-[11px] text-slate-400 block pt-0.5">
                Giữ ngày trên chứng từ; thời điểm kế toán xác nhận do máy chủ ghi riêng.
              </span>
            </div>

            <div className="sm:col-span-2 space-y-1">
              <label htmlFor="advance-status" className="text-slate-600 block text-[11px] font-medium">
                Trạng thái theo nguồn:
              </label>
              <select
                id="advance-status"
                aria-label="Trạng thái theo nguồn"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors cursor-pointer shadow-2xs"
              >
                {Object.entries(STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              {status !== "COMPLETED" && (
                <span className="text-[11px] text-amber-800 block pt-0.5">
                  Trạng thái chưa hoàn tất: chứng từ được lưu để đối chiếu, chưa thành ứng thực nhận đã xác minh.
                </span>
              )}
            </div>

            {draft.missing_fields.length > 0 && draft.activity_link_status === "LINKED" && (
            <div className="sm:col-span-2 space-y-1">
              <label htmlFor="advance-claim" className="text-slate-600 block text-[11px] font-medium">
                Căn cứ bổ sung thông tin:
              </label>
              <input
                id="advance-claim"
                aria-label="Căn cứ bổ sung thông tin"
                value={completionClaim}
                onChange={(event) => setCompletionClaim(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </div>
            )}
          </div>

          <p className="text-xs text-slate-600">
            {status === "COMPLETED"
              ? "Khi xác nhận, bạn ghi nhận nhân viên đã thực nhận khoản ứng theo chứng từ này."
              : "Chứng từ chưa hoàn tất chỉ được lưu để đối chiếu, chưa ghi nhận tiền thực nhận."}
          </p>
          <div className="pt-2 flex items-center justify-end">
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={
                busy || amount === "" ||
                draft.activity_link_status === "CONFLICT" ||
                (draft.activity_link_status === "LINKED" && draft.matched_activity_id !== caseView.activity)
              }
              className="bg-slate-950 hover:bg-slate-800 text-white text-xs font-medium px-5 py-2 rounded transition-colors disabled:opacity-40 cursor-pointer shadow-xs"
            >
              {busy ? "Đang xử lý…" : "Xác nhận ghi nhận"}
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
      <Coverage
        caseView={caseView}
        onCase={onCase}

      />
    </section>
  );
}
