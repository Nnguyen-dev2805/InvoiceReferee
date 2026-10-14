import { useEffect, useState } from "react";

import { api, attachSources, errorMessage, settlementDraft, submitCase } from "../api";
import { formatVnd } from "../format";
import type { CaseView, SessionPayload } from "../types";
import { DocumentViewer } from "./document_viewer";

export interface SettlementExpenseDraft {
  description: string;
  invoice_no?: string;
  amount: number;
  source_filename?: string;
  status?: string;
  matched_invoice?: string;
  suggested_invoice?: string;
}

export interface IntakeDraftState {
  declared_name: string | null;
  activity_name: string | null;
  occurred_at: string | null;
  declared_purpose: string | null;
  incurred_total: number | null;
  declared_advance: number | null;
  expenses: SettlementExpenseDraft[];
  notes: string;
  original_advance: number | null;
}

const EMPTY_DRAFT: IntakeDraftState = {
  declared_name: null,
  activity_name: null,
  occurred_at: null,
  declared_purpose: null,
  incurred_total: null,
  declared_advance: null,
  expenses: [],
  notes: "",
  original_advance: null,
};

export function Intake({
  session,
  onCase,
  onBack,
}: {
  session: SessionPayload;
  onCase: (view: CaseView) => void;
  onBack?: () => void;
}) {
  const [step, setStep] = useState<"upload" | "reading" | "review">("upload");
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  // The activity the draft is bound to. The employee chooses by name (never a
  // backend id). Empty until the draft is read and the employee picks one.
  const [activityId, setActivityId] = useState<string>("");

  // Draft state: null until a real read produces it. No demo defaults.
  const [draft, setDraft] = useState<IntakeDraftState>(EMPTY_DRAFT);

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  // Bước 2: “Đọc chứng từ”. Upload first, then read the SAME sources through the
  // OCR pipeline (no fabricated fallback). A failure keeps the files and offers
  // retry; it never shows a successful draft.
  async function handleReadDocuments() {
    if (files.length === 0) {
      setError("Vui lòng chọn ít nhất một tệp chứng từ.");
      return;
    }

    setBusy(true);
    setError(null);
    setStatus(null);
    setWarnings([]);
    setStep("reading");

    try {
      // 1. A draft root with an UNBOUND proposed activity; the real activity is
      //    chosen after reading (the activity fields are not invented here).
      const activity = {
        mode: "new" as const,
        name: "Hồ sơ quyết toán chi phí",
        occurred_at: new Date().toISOString(),
        declared_purpose: "Quyết toán chi phí công việc",
      };
      const created = await api.createCase(activity);
      let currentCase = created.case_view;

      // 2. Upload the sources.
      const attached = await attachSources(currentCase.id, files, currentCase.version);
      currentCase = attached.case_view;
      setCaseView(currentCase);

      // 3. Read the draft through the OCR pipeline. On failure, surface the
      //    error and keep the files; no demo facts are invented.
      const resp = await settlementDraft(currentCase.id, files);
      setWarnings(resp.warnings ?? []);
      setDraft({
        declared_name: resp.declared_name,
        activity_name: resp.activity_name,
        occurred_at: resp.occurred_at,
        declared_purpose: resp.declared_purpose,
        incurred_total: resp.incurred_total,
        declared_advance: resp.declared_advance,
        expenses: (resp.expenses ?? []).map((e) => ({
          description: e.description,
          invoice_no: e.invoice_no,
          amount: e.amount,
          source_filename: e.source_filename,
          status: e.status || "UNMATCHED",
          matched_invoice: e.matched_invoice,
          suggested_invoice: e.suggested_invoice,
        })),
        notes: "",
        original_advance: resp.declared_advance,
      });
      // Pre-select a matching catalog activity by purpose/name when one exists.
      // If none matches, pre-select the dossier's own NEW activity so the employee
      // is not stuck with an empty choice (it enters the authorization follow-up).
      const guess = session.activity_catalog.find(
        (a) =>
          resp.declared_purpose !== null &&
          (a.purpose === resp.declared_purpose || a.name === resp.activity_name),
      );
      setActivityId(guess?.id ?? currentCase.activity ?? "");
      setStep("review");
    } catch (cause) {
      setError(
        `Không đọc được chứng từ: ${errorMessage(cause)}. Kiểm tra kết nối và thử lại; tệp đã tải vẫn được giữ.`,
      );
      setStep("upload");
    } finally {
      setBusy(false);
    }
  }

  // Bước 4: “Xác nhận và nộp hồ sơ”. Sends the confirmed draft (edits + notes)
  // so the server persists it; the async worker result is polled below.
  async function handleConfirmAndSubmit() {
    if (!caseView) return;
    if (!activityId) {
      setError("Vui lòng chọn hoạt động cho hồ sơ trước khi nộp.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus(null);

    try {
      const result = await submitCase(
        caseView.id,
        activityId,
        draft.declared_purpose ?? "Quyết toán chi phí",
        caseView.version,
        [],
        {
          notes: draft.notes.trim() || null,
          declared_name: draft.declared_name,
          destination: draft.activity_name,
          declared_advance: draft.declared_advance,
          incurred_total: draft.incurred_total,
          original_declared_advance: draft.original_advance,
        },
      );
      setCaseView(result.case_view);
      onCase(result.case_view);
      setStatus("Đã nộp hồ sơ. Hệ thống đang đối soát…");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  // Chênh lệch kê khai dự kiến: T - A (chỉ khi cả hai số đã biết). Đây KHÔNG
  // phải kết luận tài chính S — S chính thức chỉ có sau đối soát.
  const netDifference =
    draft.incurred_total !== null && draft.declared_advance !== null
      ? draft.incurred_total - draft.declared_advance
      : null;

  // P1-5: after submit the backend processes asynchronously. Poll the visible
  // case (bounded) until it leaves PROCESSING, so the UI shows the server's
  // current version/state instead of a stale v3/"Đang xử lý". Stops on unmount
  // or a terminal state.
  useEffect(() => {
    if (caseView === null || caseView.state !== "PROCESSING") return;
    let cancelled = false;
    let attempts = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      try {
        const fresh = await api.getCase(caseView.id);
        if (cancelled) return;
        setCaseView(fresh);
        onCase(fresh);
        if (fresh.state !== "PROCESSING" || attempts >= 40) {
          window.clearInterval(timer);
        }
      } catch {
        if (attempts >= 40) window.clearInterval(timer);
      }
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [caseView, onCase]);

  if (step === "upload" || step === "reading") {
    return (
      <main className="h-[calc(100vh-48px)] overflow-y-auto custom-scrollbar p-6 bg-slate-50 flex justify-center flex-1">
        <div className="w-full max-w-3xl space-y-4">
          {onBack && (
            <div className="flex items-center justify-between pb-3 border-b border-slate-200">
              <button
                type="button"
                onClick={onBack}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
              >
                <span className="font-mono">←</span>
                <span>Quay lại</span>
              </button>
            </div>
          )}

          {/* Global Error Banner */}
          {error !== null && (
            <div role="alert" className="p-3 rounded-lg bg-rose-50 text-rose-900 border border-rose-200 text-xs">
              {error}
            </div>
          )}

          {/* Global Status Banner */}
          {status !== null && (
            <div role="status" className="p-3 rounded-lg bg-emerald-50 text-emerald-900 border border-emerald-200 text-xs">
              {status}
            </div>
          )}

          {/* ------------------------------------------------------------- */}
          {/* BƯỚC 1: TẢI TÀI LIỆU                                           */}
          {/* ------------------------------------------------------------- */}
          {step === "upload" && (
        <section aria-labelledby="intake-title" className="bg-white border border-slate-200 rounded-xl p-6 text-xs shadow-xs space-y-6">
          <div className="flex items-center justify-between pb-3.5 border-b border-slate-100">
            <div>
              <h2 id="intake-title" className="text-base font-bold text-slate-900 tracking-tight">
                Nộp hồ sơ quyết toán
              </h2>
              <p className="text-xs text-slate-500 font-normal mt-0.5">
                Chọn Giấy quyết toán / đề nghị thanh toán và các hóa đơn, chứng từ chi phí để hệ thống trích xuất bản nháp.
              </p>
            </div>
          </div>

          {/* Vùng chọn và danh sách tệp chứng từ */}
          <div className="space-y-4">
            <div className="border-2 border-dashed border-slate-200 hover:border-slate-400 rounded-xl p-8 text-center bg-slate-50/50 hover:bg-slate-50 transition-colors">
              <span className="font-semibold text-slate-800 block text-xs">
                Kéo thả hoặc tải lên toàn bộ tài liệu hồ sơ (PDF, PNG, JPG)
              </span>
              <span className="text-[11px] text-slate-400 block mt-1">
                Bao gồm: Giấy quyết toán / giấy thanh toán tạm ứng, hóa đơn điện tử, vé, biên nhận
              </span>
              <label
                htmlFor="source-files"
                className="inline-flex items-center bg-white border border-slate-300 hover:bg-slate-50 text-slate-800 font-semibold text-xs px-4 py-2 rounded-lg shadow-2xs cursor-pointer mt-4 transition-colors"
              >
                <span>Chọn tệp chứng từ</span>
                <input
                  id="source-files"
                  aria-label="Chứng từ (PDF/PNG/JPEG)"
                  type="file"
                  multiple
                  accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
                  onChange={(event) =>
                    setFiles((prev) => [
                      ...prev,
                      ...Array.from(event.target.files ?? []).filter(
                        (f) => !prev.some((p) => p.name === f.name),
                      ),
                    ])
                  }
                  className="sr-only"
                />
              </label>
            </div>

            {/* Danh sách tệp đã chọn */}
            {files.length > 0 && (
              <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-2xs">
                <div className="px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                  <span className="font-semibold text-slate-800 text-xs">
                    Tệp đã chọn sẵn sàng trích xuất ({files.length}):
                  </span>
                  <button
                    type="button"
                    onClick={() => setFiles([])}
                    className="text-[11px] text-slate-500 hover:text-slate-800 cursor-pointer font-medium"
                  >
                    Xóa tất cả
                  </button>
                </div>
                <ul className="divide-y divide-slate-100 text-xs">
                  {files.map((f, idx) => (
                    <li key={f.name} className="px-4 py-2.5 flex items-center justify-between hover:bg-slate-50/50 transition-colors">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 uppercase">
                          {f.name.split(".").pop()}
                        </span>
                        <span className="font-medium text-slate-900 truncate max-w-sm">{f.name}</span>
                        <span className="font-mono-nums text-[11px] text-slate-400 shrink-0">
                          ({(f.size / 1024).toFixed(1)} KB)
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                          Sẵn sàng
                        </span>
                        <button
                          type="button"
                          onClick={() => removeFile(idx)}
                          className="text-slate-400 hover:text-rose-600 px-1 py-0.5 text-xs cursor-pointer font-semibold"
                          title="Xóa tệp này"
                        >
                          ✕
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Nút hành động Bước 2: Đọc chứng từ */}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => void handleReadDocuments()}
              disabled={busy || files.length === 0}
              className="w-full bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs py-3 px-4 rounded-lg shadow-sm transition-colors disabled:opacity-40 flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Đọc chứng từ</span>
            </button>
          </div>
        </section>
      )}

      {/* ------------------------------------------------------------- */}
      {/* BƯỚC 2: TIẾN TRÌNH ĐỌC CHỨNG TỪ                                */}
      {/* ------------------------------------------------------------- */}
      {step === "reading" && (
        <section className="bg-white border border-slate-200 rounded-xl p-8 text-center text-xs shadow-xs space-y-4">
          <div className="inline-block w-8 h-8 border-2 border-slate-900 border-t-transparent rounded-full animate-spin mb-2" />
          <h3 className="text-sm font-bold text-slate-900">
            Hệ thống đang OCR &amp; trích xuất bản nháp
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Hệ thống đang nhận diện văn bản, phân loại Giấy quyết toán, đối chiếu số hóa đơn và tổng hợp các khoản chi...
          </p>
          <div className="max-w-sm mx-auto pt-2 text-left bg-slate-50 p-3.5 rounded-lg border border-slate-200 space-y-2">
            <div className="flex items-center gap-2 text-emerald-700 font-medium text-xs">
              <span>✓</span>
              <span>Đã tải lên {files.length} tệp chứng từ</span>
            </div>
            <div className="flex items-center gap-2 text-slate-800 font-medium text-xs">
              <span className="w-2 h-2 rounded-full bg-slate-800 animate-pulse" />
              <span>Đang đọc bảng kê &amp; hóa đơn chi phí</span>
            </div>
            <div className="flex items-center gap-2 text-slate-400 text-xs">
              <span className="w-2 h-2 rounded-full bg-slate-300" />
              <span>Chuẩn bị bản nháp đối chiếu</span>
            </div>
          </div>
        </section>
      )}
        </div>
      </main>
    );
  }

  return (
    <main className="h-[calc(100vh-48px)] flex flex-col md:flex-row overflow-hidden flex-1">
      {/* LEFT PANE: Document & Evidence Inspector (50%) */}
      <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-hidden flex flex-col">
        <DocumentViewer caseView={caseView} pendingFiles={files} />
      </div>

      {/* RIGHT PANE: Extracted Draft Workspace (50%) */}
      <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-hidden flex flex-col bg-white">
        {/* Sleek Subheader Bar (h-11) */}
        <div className="h-11 border-b border-slate-200 px-5 flex items-center justify-between shrink-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setStep("upload")}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
            >
              <span className="font-mono">←</span>
              <span>Chọn lại tệp</span>
            </button>
            <span className="text-slate-300">/</span>
            <span className="text-xs font-semibold text-slate-900">
              Kiểm tra bản nháp hồ sơ
            </span>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium border ${
                warnings.length === 0
                  ? "text-emerald-800 bg-emerald-50 border-emerald-200"
                  : "text-amber-800 bg-amber-50 border-amber-200"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  warnings.length === 0 ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
              <span>{warnings.length === 0 ? "Đã trích xuất" : "Cần kiểm tra"}</span>
            </span>
          </div>

          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
            >
              Đóng
            </button>
          )}
        </div>

        {/* Scrollable Canvas */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6 text-xs">
          {/* Global Error Banner */}
          {error !== null && (
            <div role="alert" className="p-3 rounded bg-rose-50 text-rose-900 border border-rose-200 text-xs">
              {error}
            </div>
          )}

          {/* Global Status Banner */}
          {status !== null && (
            <div role="status" className="p-3 rounded bg-emerald-50 text-emerald-900 border border-emerald-200 text-xs">
              {status}
            </div>
          )}

          {/* Header Info */}
          <div className="pb-4 border-b border-slate-100 space-y-1.5">
            <div className="flex items-center justify-between">
              <h2 id="review-title" className="text-base font-bold text-slate-900 tracking-tight">
                Bản nháp hồ sơ quyết toán
              </h2>
              <span className="text-[11px] text-slate-500">
                Người đề nghị: <strong className="text-slate-900 font-semibold">{draft.declared_name ?? "Chưa đọc được"}</strong>
              </span>
            </div>
            <p className="text-xs text-slate-500 font-normal">
              Xem tài liệu gốc ở khung bên cạnh để đối chiếu. Các trường đọc rõ đã được điền sẵn; bạn có thể chỉnh sửa nếu AI đọc sai.
            </p>
            {warnings.length > 0 && (
              <ul className="mt-2 space-y-1">
                {warnings.map((w, i) => (
                  <li key={i} className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5">
                    ⚠ {w}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 1. Người đề nghị & Hoạt động */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold text-slate-900">
              Thông tin hoạt động &amp; người đề nghị
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <label htmlFor="draft-activity" className="text-slate-700 block font-semibold text-xs mb-1">
                  Hoạt động của hồ sơ:
                </label>
                <select
                  id="draft-activity"
                  aria-label="Hoạt động của hồ sơ"
                  value={activityId}
                  onChange={(e) => setActivityId(e.target.value)}
                  className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800"
                >
                  <option value="">— Chọn hoạt động —</option>
                  {session.activity_catalog.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                      {a.occurred_at ? ` · ${a.occurred_at.slice(0, 10)}` : ""}
                    </option>
                  ))}
                  {caseView?.activity ? (
                    <option value={caseView.activity}>
                      ＋ Hoạt động mới: {draft.activity_name ?? draft.declared_purpose ?? "theo chứng từ"}
                    </option>
                  ) : null}
                </select>
                <span className="text-[10px] text-slate-400 block mt-1">
                  Danh mục do hệ thống cung cấp; không cần nhập mã nội bộ. Nếu hoạt động chưa có trong danh mục, chọn “Hoạt động mới” — hồ sơ sẽ vào luồng xin bổ sung ngân sách/quyền.
                </span>
              </div>

              <div className="sm:col-span-2">
                <label htmlFor="draft-activity-name" className="text-slate-700 block font-semibold text-xs mb-1">
                  Nội dung hoạt động (đọc từ giấy):
                </label>
                <input
                  id="draft-activity-name"
                  value={draft.activity_name ?? ""}
                  onChange={(e) => setDraft((prev) => ({ ...prev, activity_name: e.target.value }))}
                  className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800"
                />
              </div>

              <div className="sm:col-span-2">
                <label htmlFor="draft-purpose" className="text-slate-700 block font-semibold text-xs mb-1">
                  Mục đích:
                </label>
                <input
                  id="draft-purpose"
                  value={draft.declared_purpose ?? ""}
                  onChange={(e) => setDraft((prev) => ({ ...prev, declared_purpose: e.target.value }))}
                  className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800"
                />
              </div>
            </div>
          </div>

          {/* 2. Bảng kê các khoản chi phí đã trích xuất */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold text-slate-900">
              Các khoản chi phí trích xuất ({draft.expenses.length})
            </h3>

            <div className="border-t border-b border-slate-200">
              {draft.expenses.length === 0 ? (
                <div className="p-4 text-center text-slate-400 text-xs">
                  Chưa đọc được dòng chi tiết từ chứng từ. Kiểm tra lại tệp đã tải hoặc thử đọc lại.
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold">
                      <th className="py-2.5 px-3">Khoản chi</th>
                      <th className="py-2.5 px-3">Hóa đơn</th>
                      <th className="py-2.5 px-3 text-right">Số tiền</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {draft.expenses.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50">
                        <td className="py-2.5 px-3">
                          <span className="font-medium text-slate-900 block">{item.description}</span>
                          {item.matched_invoice ? (
                            <span className="text-[10px] text-emerald-700 font-mono-nums block mt-0.5">
                              ✓ Khớp tệp: {item.matched_invoice}
                            </span>
                          ) : item.suggested_invoice ? (
                            <span className="text-[10px] text-slate-500 block mt-0.5">
                              ? Có thể liên quan: {item.suggested_invoice} (chưa xác nhận)
                            </span>
                          ) : (
                            <span className="text-[10px] text-amber-700 block mt-0.5">
                              ⚠ Chưa liên kết được chứng từ cho khoản này
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono-nums tabular-nums text-slate-600">
                          {item.invoice_no || "—"}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono-nums tabular-nums font-semibold text-slate-900">
                          {formatVnd(item.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* 3. Tổng chi & Ứng NHÂN VIÊN KÊ KHAI */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-900">
                Tổng chi &amp; ứng nhân viên kê khai
              </h3>
              <span className="text-[11px] text-slate-400">
                Số liệu kê khai trên chứng từ
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              Đây là số nhân viên kê khai trên giấy, chưa phải số ứng công ty đã thực nhận.
              Ứng thực nhận và chênh lệch chính thức chỉ có sau khi hệ thống đối soát lịch sử.
            </p>

            <div className="border-t border-b border-slate-200 divide-y divide-slate-100">
              {/* Row 1: Tổng chi phí kê khai (T) */}
              <div className="flex items-center justify-between px-1 py-2 text-xs bg-slate-50/50">
                <span className="font-semibold text-slate-900">
                  Tổng chi phí kê khai:
                </span>
                <strong className="text-xs font-bold text-slate-950 font-mono-nums tabular-nums">
                  {draft.incurred_total !== null ? formatVnd(draft.incurred_total) : "Chưa đọc được"}
                </strong>
              </div>

              {/* Row 2: Ứng nhân viên kê khai - Có thể chỉnh sửa */}
              <div className="flex items-center justify-between px-1 py-2 text-xs">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <label htmlFor="draft-advance" className="font-medium text-slate-700">
                      Ứng nhân viên kê khai:
                    </label>
                    {draft.declared_advance !== draft.original_advance && (
                      <span className="text-[10px] font-semibold text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                        * Đã chỉnh sửa
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-400 block">
                    Sửa lại nếu AI đọc sai số trên giấy
                  </span>
                </div>
                <div className="w-40 shrink-0">
                  <input
                    id="draft-advance"
                    type="number"
                    value={draft.declared_advance ?? ""}
                    onChange={(e) =>
                      setDraft((prev) => ({
                        ...prev,
                        declared_advance: e.target.value === "" ? null : Number(e.target.value),
                      }))
                    }
                    className="w-full text-right bg-slate-50 hover:bg-white border border-slate-300 rounded px-2.5 py-1 text-xs font-mono-nums tabular-nums font-bold text-slate-900 focus:outline-none focus:border-slate-800 transition-colors"
                  />
                </div>
              </div>

              {/* Row 3: Chênh lệch kê khai dự kiến */}
              <div className="flex items-center justify-between px-1 py-2 text-xs bg-slate-50/30">
                <span className="font-medium text-slate-600">
                  Chênh lệch kê khai dự kiến (T - Ứng):
                </span>
                <div className="text-right">
                  {netDifference === null ? (
                    <span className="text-xs text-slate-400 font-normal">Chưa xác định</span>
                  ) : (
                    <div className="flex items-center gap-1.5 justify-end">
                      <span
                        className={`text-xs font-bold font-mono-nums tabular-nums ${
                          netDifference < 0
                            ? "text-amber-700"
                            : netDifference > 0
                            ? "text-emerald-700"
                            : "text-slate-900"
                        }`}
                      >
                        {netDifference < 0
                           ? `-${formatVnd(Math.abs(netDifference))}`
                          : netDifference > 0
                          ? `+${formatVnd(netDifference)}`
                          : "0 ₫"}
                      </span>
                      <span className="text-[11px] text-slate-500 font-normal font-sans">
                        {netDifference < 0
                          ? "(Nhân viên có thể hoàn lại)"
                          : netDifference > 0
                          ? "(Công ty có thể chi bổ sung)"
                          : "(Cân bằng kê khai)"}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 4. Ghi chú của nhân viên */}
          <div className="space-y-1.5">
            <label htmlFor="draft-notes" className="text-slate-700 block font-semibold text-xs">
              Ghi chú của nhân viên (nếu có bổ sung hoặc sửa khác PDF gốc):
            </label>
            <input
              id="draft-notes"
              value={draft.notes}
              onChange={(e) => setDraft((prev) => ({ ...prev, notes: e.target.value }))}
              className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800"
            />
          </div>

          {/* 5. Nút "Xác nhận và nộp hồ sơ" */}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => void handleConfirmAndSubmit()}
              disabled={busy}
              className="w-full bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs py-2.5 px-4 rounded transition-colors disabled:opacity-40 flex items-center justify-center gap-2 cursor-pointer"
            >
              {busy ? "Đang xử lý nộp hồ sơ…" : "Xác nhận và nộp hồ sơ"}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
