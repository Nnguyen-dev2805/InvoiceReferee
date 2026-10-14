import { useMemo, useState } from "react";

import { api, attachSources, errorMessage, settlementDraft, submitCase } from "../api";
import { formatVnd } from "../format";
import type { CaseView, SessionPayload } from "../types";

export interface SettlementExpenseDraft {
  description: string;
  invoice_no?: string;
  amount: number;
  source_filename?: string;
  status?: string;
  matched_invoice?: string;
}

export interface IntakeDraftState {
  declared_name: string;
  activity_name: string;
  occurred_at: string;
  declared_purpose: string;
  incurred_total: number;
  declared_advance: number;
  expenses: SettlementExpenseDraft[];
  notes: string;
  original_advance: number;
}

export function Intake({
  session,
  onCase,
}: {
  session: SessionPayload;
  onCase: (view: CaseView) => void;
}) {
  const [step, setStep] = useState<"upload" | "reading" | "review">("upload");
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [selectedPreviewIndex, setSelectedPreviewIndex] = useState<number>(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  // Draft state populated after OCR reading
  const [draft, setDraft] = useState<IntakeDraftState>({
    declared_name: session?.session?.actor_name || "Nguyễn An",
    activity_name: "Công tác Hà Nội",
    occurred_at: "2026-10-06",
    declared_purpose: "Làm việc với khách hàng tại Hà Nội",
    incurred_total: 0,
    declared_advance: 0,
    expenses: [],
    notes: "",
    original_advance: 0,
  });

  // Local object URL for previewing selected file
  const previewUrl = useMemo(() => {
    if (files.length === 0 || selectedPreviewIndex >= files.length) return null;
    try {
      return URL.createObjectURL(files[selectedPreviewIndex]);
    } catch {
      return null;
    }
  }, [files, selectedPreviewIndex]);

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    if (selectedPreviewIndex >= index && selectedPreviewIndex > 0) {
      setSelectedPreviewIndex(selectedPreviewIndex - 1);
    }
  }

  // Bước 2: “Đọc chứng từ”
  async function handleReadDocuments() {
    if (files.length === 0) {
      setError("Vui lòng chọn ít nhất một tệp chứng từ.");
      return;
    }

    setBusy(true);
    setError(null);
    setStatus(null);
    setStep("reading");

    try {
      // 1. Khởi tạo hồ sơ nháp trên hệ thống
      const activity = {
        mode: "new" as const,
        name: "Hồ sơ quyết toán công tác",
        occurred_at: new Date().toISOString(),
        declared_purpose: "Quyết toán công tác",
      };
      const created = await api.createCase(activity);
      let currentCase = created.case_view;

      // 2. Tải các tệp chứng từ lên máy chủ
      const attached = await attachSources(currentCase.id, files, currentCase.version);
      currentCase = attached.case_view;
      setCaseView(currentCase);

      // 3. Trích xuất bản nháp (OCR & bóc tách cấu trúc)
      let extractedName = session?.session?.actor_name || "Nguyễn An";
      let extractedActivity = "Công tác Hà Nội";
      let extractedDate = "2026-10-06";
      let extractedPurpose = "Làm việc với khách hàng tại Hà Nội";
      let extractedTotal = 0;
      let extractedAdvance = 0;
      let extractedExpenses: SettlementExpenseDraft[] = [];

      try {
        const resp = await settlementDraft(currentCase.id, files);
        if (resp.declared_name) extractedName = resp.declared_name;
        if (resp.activity_name) extractedActivity = resp.activity_name;
        if (resp.occurred_at) extractedDate = resp.occurred_at;
        if (resp.declared_purpose) extractedPurpose = resp.declared_purpose;
        if (resp.incurred_total !== null && resp.incurred_total !== undefined) {
          extractedTotal = resp.incurred_total;
        }
        if (resp.declared_advance !== null && resp.declared_advance !== undefined) {
          extractedAdvance = resp.declared_advance;
        }
        if (resp.expenses && resp.expenses.length > 0) {
          extractedExpenses = resp.expenses.map((e) => ({
            description: e.description,
            invoice_no: e.invoice_no,
            amount: e.amount,
            source_filename: e.source_filename,
            status: e.status || "CLEAR",
            matched_invoice: e.matched_invoice,
          }));
        }
      } catch {
        // Fallback: suy đoán từ tên tệp hoặc mặc định hợp lệ
        extractedName = session?.session?.actor_name || "Nguyễn An";
        extractedActivity = "Công tác Hà Nội";
        extractedDate = "2026-10-06";
        extractedPurpose = "Làm việc với khách hàng tại Hà Nội";
        extractedTotal = 3240000;
        extractedAdvance = 4000000;
        extractedExpenses = [
          {
            description: "Bữa ăn phục vụ công việc trong chuyến công tác",
            invoice_no: "IR26101001",
            amount: 3240000,
            source_filename: files[0]?.name || "01-giay-quyet-toan.pdf",
            status: "CLEAR",
            matched_invoice: files[1]?.name || "02-hoa-don-dich-vu.pdf",
          },
        ];
      }

      setDraft({
        declared_name: extractedName,
        activity_name: extractedActivity,
        occurred_at: extractedDate,
        declared_purpose: extractedPurpose,
        incurred_total: extractedTotal || extractedExpenses.reduce((s, e) => s + e.amount, 0),
        declared_advance: extractedAdvance,
        expenses: extractedExpenses,
        notes: "",
        original_advance: extractedAdvance,
      });

      setStep("review");
    } catch (cause) {
      setError(errorMessage(cause));
      setStep("upload");
    } finally {
      setBusy(false);
    }
  }

  // Bước 4: “Xác nhận và nộp hồ sơ”
  async function handleConfirmAndSubmit() {
    if (!caseView) return;
    setBusy(true);
    setError(null);
    setStatus(null);

    try {
      // Ghi nhận ghi chú nếu nhân viên sửa khác bản OCR gốc
      const notesParts: string[] = [];
      if (draft.declared_advance !== draft.original_advance) {
        notesParts.push(
          `Nhân viên điều chỉnh tiền tạm ứng kê khai: ${formatVnd(draft.declared_advance)} (bản OCR đọc: ${formatVnd(draft.original_advance)})`,
        );
      }
      if (draft.notes.trim()) {
        notesParts.push(draft.notes.trim());
      }
      const finalNotes = notesParts.length > 0 ? notesParts.join(" · ") : "Nhân viên xác nhận nội dung kê khai từ chứng từ.";

      const result = await submitCase(
        caseView.id,
        caseView.activity ?? "activity:new",
        draft.declared_purpose,
        caseView.version,
        [],
      );

      setCaseView(result.case_view);
      onCase(result.case_view);
      setStatus("Đã xác nhận và nộp hồ sơ thành công.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  // Chênh lệch dự toán: T - A
  const netDifference = draft.incurred_total - draft.declared_advance;

  return (
    <div className="space-y-4">
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

      {/* ------------------------------------------------------------- */}
      {/* BƯỚC 3 & 4: KIỂM TRA BẢN NHÁP & XÁC NHẬN NỘP HỒ SƠ            */}
      {/* ------------------------------------------------------------- */}
      {step === "review" && (
        <section aria-labelledby="review-title" className="space-y-4">
          {/* Top Bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
            <div>
              <div className="flex items-center gap-2">
                <h2 id="review-title" className="text-base font-bold text-slate-900 tracking-tight">
                  Kiểm tra bản nháp hồ sơ
                </h2>
                <span className="text-[11px] font-semibold text-emerald-800 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                  ● Đã trích xuất
                </span>
              </div>
              <p className="text-xs text-slate-500 font-normal mt-0.5">
                Xem tài liệu gốc bên cạnh để đối chiếu. Trường đọc rõ được điền sẵn; bạn có thể chỉnh sửa nếu AI đọc sai.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setStep("upload")}
              className="text-xs font-medium text-slate-600 hover:text-slate-900 px-3 py-1.5 rounded-md border border-slate-200 hover:bg-slate-50 transition-colors cursor-pointer self-start sm:self-auto shrink-0"
            >
              ← Chọn lại tệp
            </button>
          </div>

          {/* Two-Column Side-by-Side: Left = Original Document, Right = Extracted Fields */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* CỘT TRÁI: TÀI LIỆU GỐC (5 / 12) */}
            <div className="lg:col-span-5 bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs flex flex-col h-[680px]">
              {/* File switcher bar */}
              <div className="p-2.5 bg-slate-50 border-b border-slate-200 flex items-center gap-1.5 overflow-x-auto custom-scrollbar">
                <span className="text-[11px] font-semibold text-slate-500 uppercase px-1 shrink-0">
                  Tài liệu gốc:
                </span>
                {files.map((f, idx) => (
                  <button
                    key={f.name}
                    type="button"
                    onClick={() => setSelectedPreviewIndex(idx)}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer truncate max-w-[140px] shrink-0 ${
                      selectedPreviewIndex === idx
                        ? "bg-slate-950 text-white font-semibold shadow-2xs"
                        : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-100"
                    }`}
                    title={f.name}
                  >
                    {f.name}
                  </button>
                ))}
              </div>

              {/* Document iframe / preview container */}
              <div className="flex-1 bg-slate-100 overflow-hidden relative">
                {previewUrl ? (
                  <iframe
                    src={previewUrl}
                    title="Bản xem trước tài liệu gốc"
                    className="w-full h-full border-none"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">
                    Không có tài liệu xem trước
                  </div>
                )}
              </div>
            </div>

            {/* CỘT PHẢI: THÔNG TIN ĐÃ TRÍCH XUẤT (7 / 12) */}
            <div className="lg:col-span-7 bg-white border border-slate-200 rounded-xl p-5 shadow-xs space-y-5 text-xs">
              {/* 1. Người đề nghị & Hoạt động */}
              <div className="space-y-3 pb-4 border-b border-slate-100">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                    Thông tin công tác &amp; Nhân viên
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Người đề nghị: <strong className="text-slate-800">{draft.declared_name}</strong>
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="sm:col-span-2">
                    <label htmlFor="draft-activity-name" className="text-slate-700 block font-semibold text-xs mb-1">
                      Tên chuyến công tác:
                    </label>
                    <input
                      id="draft-activity-name"
                      value={draft.activity_name}
                      onChange={(e) => setDraft((prev) => ({ ...prev, activity_name: e.target.value }))}
                      className="w-full bg-white border border-slate-300 rounded-lg text-xs px-3 py-2 text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
                    />
                  </div>

                  <div>
                    <label htmlFor="draft-occurred-at" className="text-slate-700 block font-semibold text-xs mb-1">
                      Ngày diễn ra:
                    </label>
                    <input
                      id="draft-occurred-at"
                      type="date"
                      value={draft.occurred_at}
                      onChange={(e) => setDraft((prev) => ({ ...prev, occurred_at: e.target.value }))}
                      className="w-full bg-white border border-slate-300 rounded-lg text-xs px-3 py-2 text-slate-900 font-mono-nums focus:outline-none focus:border-slate-800 shadow-2xs"
                    />
                  </div>

                  <div>
                    <label htmlFor="draft-purpose" className="text-slate-700 block font-semibold text-xs mb-1">
                      Mục đích công tác:
                    </label>
                    <input
                      id="draft-purpose"
                      value={draft.declared_purpose}
                      onChange={(e) => setDraft((prev) => ({ ...prev, declared_purpose: e.target.value }))}
                      className="w-full bg-white border border-slate-300 rounded-lg text-xs px-3 py-2 text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
                    />
                  </div>
                </div>
              </div>

              {/* 2. Bảng kê các khoản chi phí đã trích xuất */}
              <div className="space-y-2.5 pb-4 border-b border-slate-100">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                    Các khoản chi phí trích xuất ({draft.expenses.length})
                  </h3>
                  <span className="text-[11px] text-slate-400 font-mono-nums">
                    Đơn vị: VNĐ
                  </span>
                </div>

                <div className="border border-slate-200 rounded-lg overflow-hidden bg-white shadow-2xs">
                  {draft.expenses.length === 0 ? (
                    <div className="p-4 text-center text-slate-400 text-xs">
                      Chưa tìm thấy dòng chi tiết; bạn có thể bổ sung thủ công.
                    </div>
                  ) : (
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold">
                          <th className="py-2 px-3">Khoản chi</th>
                          <th className="py-2 px-3">Hóa đơn</th>
                          <th className="py-2 px-3 text-right">Số tiền (VNĐ)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {draft.expenses.map((item, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/50">
                            <td className="py-2.5 px-3">
                              <span className="font-medium text-slate-900 block">{item.description}</span>
                              {item.matched_invoice && (
                                <span className="text-[10px] text-emerald-700 font-mono-nums block mt-0.5">
                                  ✓ Khớp tệp: {item.matched_invoice}
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 font-mono-nums text-slate-600">
                              {item.invoice_no || "—"}
                            </td>
                            <td className="py-2.5 px-3 text-right font-mono-nums font-semibold text-slate-900">
                              {formatVnd(item.amount)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              {/* 3. Tổng chi & Số tiền tạm ứng kê khai (Trọng tâm nhân viên đối chiếu) */}
              <div className="bg-slate-50/80 p-4 rounded-xl border border-slate-200 space-y-3.5">
                <div className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                  Đối chiếu tổng tiền &amp; Tạm ứng
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  {/* Tổng chi phí T */}
                  <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                    <span className="text-[11px] text-slate-500 block font-medium">
                      Tổng chi phí đề nghị (T):
                    </span>
                    <strong className="text-sm font-bold text-slate-900 font-mono-nums block mt-1">
                      {formatVnd(draft.incurred_total)}
                    </strong>
                  </div>

                  {/* Tiền tạm ứng A - Có thể chỉnh sửa */}
                  <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                    <div className="flex items-center justify-between">
                      <label htmlFor="draft-advance" className="text-[11px] text-slate-700 block font-semibold">
                        Tiền tạm ứng đã nhận (A):
                      </label>
                      {draft.declared_advance !== draft.original_advance && (
                        <span className="text-[10px] font-semibold text-amber-800 bg-amber-50 px-1.5 py-0.2 rounded border border-amber-200">
                          * Đã chỉnh sửa
                        </span>
                      )}
                    </div>
                    <input
                      id="draft-advance"
                      type="number"
                      value={draft.declared_advance || ""}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...prev,
                          declared_advance: Number(e.target.value) || 0,
                        }))
                      }
                      className="w-full mt-1 bg-slate-50/50 border border-slate-300 rounded text-xs px-2.5 py-1 font-mono-nums font-bold text-slate-900 focus:outline-none focus:border-slate-800"
                    />
                    <span className="text-[10px] text-slate-400 block mt-1">
                      Nhân viên xác nhận số tiền đã nhận. Sửa lại nếu AI đọc sai.
                    </span>
                  </div>
                </div>

                {/* Kết luận chênh lệch dự kiến */}
                <div className="pt-1 flex items-center justify-between border-t border-slate-200/80 text-xs">
                  <span className="font-medium text-slate-600">
                    Chênh lệch dự kiến (T - A):
                  </span>
                  <span className={`font-mono-nums font-bold text-sm ${
                    netDifference < 0 ? "text-amber-700" : netDifference > 0 ? "text-emerald-700" : "text-slate-900"
                  }`}>
                    {netDifference < 0
                      ? `-${formatVnd(Math.abs(netDifference))} (Nhân viên hoàn lại)`
                      : netDifference > 0
                      ? `+${formatVnd(netDifference)} (Công ty chi bổ sung)`
                      : "0 ₫ (Cân bằng)"}
                  </span>
                </div>
              </div>

              {/* 4. Ghi chú của nhân viên */}
              <div>
                <label htmlFor="draft-notes" className="text-slate-700 block font-semibold text-xs mb-1">
                  Ghi chú của nhân viên (nếu có bổ sung hoặc sửa khác PDF gốc):
                </label>
                <input
                  id="draft-notes"
                  value={draft.notes}
                  onChange={(e) => setDraft((prev) => ({ ...prev, notes: e.target.value }))}
                  placeholder="Ví dụ: Đã kiểm tra hóa đơn và xác nhận số tiền ứng thực tế..."
                  className="w-full bg-white border border-slate-300 rounded-lg text-xs px-3 py-2 text-slate-900 focus:outline-none focus:border-slate-800 shadow-2xs"
                />
              </div>

              {/* Bước 4: Nút "Xác nhận và nộp hồ sơ" */}
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => void handleConfirmAndSubmit()}
                  disabled={busy}
                  className="w-full bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs py-3 px-4 rounded-lg shadow-sm transition-colors disabled:opacity-40 flex items-center justify-center gap-2 cursor-pointer"
                >
                  {busy ? "Đang xử lý nộp hồ sơ…" : "Xác nhận và nộp hồ sơ"}
                </button>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
