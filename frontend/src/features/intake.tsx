import { useEffect, useState } from "react";

import { api, attachSources, errorMessage, getSettlementDraft, settlementDraftByRole, submitCase } from "../api";
import type { SettlementArithmeticFinding, SettlementLink } from "../api";
import { formatVnd, formatVndHint } from "../format";
import type { CaseView, SessionPayload } from "../types";
import { DocumentViewer } from "./document_viewer";

export interface SettlementExpenseDraft {
  description: string | null;
  invoice_no?: string;
  amount: number | null;
  amount_state?: string;
  description_state?: string;
  source_filename?: string;
  status?: string;
  matched_invoice?: string;
  suggested_invoice?: string;
}

export interface IntakeDraftState {
  declared_name: string | null;
  activity_name: string | null;
  destination: string | null;
  trip_start: string | null;
  trip_end: string | null;
  occurred_at: string | null;
  declared_purpose: string | null;
  incurred_total: number | null;
  incurred_total_basis: "PRINTED_TOTAL" | "ROW_SUM" | null;
  declared_advance: number | null;
  expenses: SettlementExpenseDraft[];
  notes: string;
  original_advance: number | null;
}

const EMPTY_DRAFT: IntakeDraftState = {
  declared_name: null,
  activity_name: null,
  destination: null,
  trip_start: null,
  trip_end: null,
  occurred_at: null,
  declared_purpose: null,
  incurred_total: null,
  incurred_total_basis: null,
  declared_advance: null,
  expenses: [],
  notes: "",
  original_advance: null,
};

export function Intake({
  onCase,
  onBack,
  existingCase,
}: {
  session: SessionPayload;
  onCase: (view: CaseView) => void;
  onBack?: () => void;
  existingCase?: CaseView | null;
}) {
  const [step, setStep] = useState<"upload" | "reading" | "review">(
    existingCase && existingCase.state === "DRAFT" ? "reading" : "upload",
  );
  const [caseView, setCaseView] = useState<CaseView | null>(existingCase ?? null);
  // Role-aware upload (16/10/2026): the paper box holds exactly one settlement
  // form; the evidence box holds many invoices/receipts. Roles are submitter
  // intent and stay distinct from the content-determined document_type.
  const [paperFiles, setPaperFiles] = useState<File[]>([]);
  const [evidenceFiles, setEvidenceFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [processingStatus, setProcessingStatus] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [arithmeticFindings, setArithmeticFindings] = useState<SettlementArithmeticFinding[]>([]);
  // Backend dossier link (14/10/2026): the server decides which advance/work
  // dossier this settlement belongs to. The employee only confirms when the
  // basis is weak (NEEDS_CONFIRMATION) — never by picking a standing code.
  const [link, setLink] = useState<SettlementLink | null>(null);
  const [confirmedActivityId, setConfirmedActivityId] = useState<string>("");
  const [draft, setDraft] = useState<IntakeDraftState>(EMPTY_DRAFT);
  const [isViewerExpanded, setIsViewerExpanded] = useState(false);

  // Resume draft from server when an existing draft case is opened
  useEffect(() => {
    if (!existingCase || existingCase.state !== "DRAFT") return;
    let cancelled = false;
    setBusy(true);
    setStep("reading");
    setCaseView(existingCase);

    void (async () => {
      try {
        const resp = await getSettlementDraft(existingCase.id);
        if (cancelled) return;
        setWarnings(resp.warnings ?? []);
        setProcessingStatus(resp.processing_status ?? null);
        setArithmeticFindings(resp.arithmetic_findings ?? []);
        setDraft({
          declared_name: resp.declared_name,
          activity_name: resp.activity_name,
          destination: resp.destination,
          trip_start: resp.trip_start,
          trip_end: resp.trip_end,
          occurred_at: resp.occurred_at,
          // One merged proposal-content field (see handleReadDocuments).
          declared_purpose: resp.declared_purpose ?? resp.activity_name,
          incurred_total: resp.incurred_total,
          incurred_total_basis: resp.incurred_total_basis ?? null,
          declared_advance: resp.declared_advance,
          expenses: (resp.expenses ?? []).map((e) => ({
            description: e.description,
            invoice_no: e.invoice_no,
            amount: e.amount,
            amount_state: e.amount_state,
            description_state: e.description_state,
            source_filename: e.source_filename,
            status: e.status || "UNMATCHED",
            matched_invoice: e.matched_invoice,
            suggested_invoice: e.suggested_invoice,
          })),
          notes: "",
          original_advance: resp.declared_advance,
        });
        // The backend link decides the dossier; the employee confirms only a
        // weak link. No activity guessing on the client.
        setLink(resp.link ?? null);
        setConfirmedActivityId("");
        setStep("review");
      } catch (cause) {
        if (cancelled) return;
        setError(
          `Không tải lại được bản nháp: ${errorMessage(cause)}. Bạn có thể chọn tệp để đọc lại.`,
        );
        setStep("upload");
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [existingCase?.id]);

  function removeFile(index: number) {
    setEvidenceFiles((prev) => prev.filter((_, i) => i !== index));
  }

  // Bước 2: “Đọc chứng từ”. Upload per role, then read the SAME sources
  // through the OCR pipeline (no fabricated fallback). A failure keeps the
  // files and offers retry; it never shows a successful draft.
  async function handleReadDocuments() {
    if (paperFiles.length !== 1) {
      setError("Vui lòng chọn đúng 1 tệp đơn quyết toán ở ô trên.");
      return;
    }
    if (evidenceFiles.length === 0) {
      setError("Vui lòng chọn ít nhất một hóa đơn/chứng từ kèm theo ở ô dưới.");
      return;
    }

    setBusy(true);
    setError(null);
    setStatus(null);
    setWarnings([]);
    setArithmeticFindings([]);
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

      // 2. Upload the sources per role (one call per box so the server
      //    records upload_role=paper / evidence with each file).
      const attachedPaper = await attachSources(currentCase.id, paperFiles, currentCase.version, "paper");
      currentCase = attachedPaper.case_view;
      const attached = await attachSources(currentCase.id, evidenceFiles, currentCase.version, "evidence");
      currentCase = attached.case_view;
      setCaseView(currentCase);

      // 3. Read the draft through the OCR pipeline. On failure, surface the
      //    error and keep the files; no demo facts are invented.
      const resp = await settlementDraftByRole(currentCase.id, paperFiles, evidenceFiles);
      setWarnings(resp.warnings ?? []);
      setProcessingStatus(resp.processing_status ?? null);
      setArithmeticFindings(resp.arithmetic_findings ?? []);
      setDraft({
        declared_name: resp.declared_name,
        activity_name: resp.activity_name,
        destination: resp.destination,
        trip_start: resp.trip_start,
        trip_end: resp.trip_end,
        occurred_at: resp.occurred_at,
        // One merged proposal-content field: prefer the read purpose, fall
        // back to the read activity name. The trip destination is kept as its
        // own travel field and is never fed the proposal content.
        declared_purpose: resp.declared_purpose ?? resp.activity_name,
        incurred_total: resp.incurred_total,
        incurred_total_basis: resp.incurred_total_basis ?? null,
        declared_advance: resp.declared_advance,
        expenses: (resp.expenses ?? []).map((e) => ({
          description: e.description,
          invoice_no: e.invoice_no,
          amount: e.amount,
          amount_state: e.amount_state,
          description_state: e.description_state,
          source_filename: e.source_filename,
          status: e.status || "UNMATCHED",
          matched_invoice: e.matched_invoice,
          suggested_invoice: e.suggested_invoice,
        })),
        notes: "",
        original_advance: resp.declared_advance,
      });
      // The backend link decides the dossier; the employee confirms only a
      // weak link. No activity guessing on the client.
      setLink(resp.link ?? null);
      setConfirmedActivityId("");
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
  // so the server persists it; the async worker result is polled below. The
  // backend owns the dossier link: the client only forwards the employee's
  // confirmation of a weak link, never a standing activity choice.
  async function handleConfirmAndSubmit() {
    if (!caseView) return;
    if (link?.status === "CONFLICT") {
      setError(
        "Chứng từ mang căn cứ trái nhau về hồ sơ tạm ứng; kế toán xác minh trước khi nộp tiếp.",
      );
      return;
    }
    if (link?.status === "NEEDS_CONFIRMATION" && !confirmedActivityId) {
      setError("Vui lòng chọn khoản tạm ứng mà hồ sơ này quyết toán.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus(null);

    try {
      const result = await submitCase(
        caseView.id,
        null,
        draft.declared_purpose ?? "Quyết toán chi phí",
        caseView.version,
        [],
        {
          notes: draft.notes.trim() || null,
          declared_name: draft.declared_name,
          destination: draft.destination ?? undefined,
          declared_advance: draft.declared_advance,
          incurred_total: draft.incurred_total,
          original_declared_advance: draft.original_advance,
          confirmed_activity_id: confirmedActivityId || null,
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
    arithmeticFindings.length === 0 && draft.incurred_total !== null && draft.declared_advance !== null
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
      <main className="h-[calc(100vh-48px)] overflow-y-auto custom-scrollbar p-6 bg-white flex justify-center flex-1">
        <div className="w-full max-w-3xl space-y-5">
          <div className="flex items-center justify-between pb-3.5 border-b border-slate-200">
            <div className="flex items-center gap-3">
              {onBack && (
                <button
                  type="button"
                  onClick={onBack}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 transition-colors cursor-pointer py-1 px-2 -ml-2 rounded hover:bg-slate-100"
                >
                  <span className="font-mono">←</span>
                  <span>Quay lại</span>
                </button>
              )}
              {onBack && <div className="h-4 w-px bg-slate-200" />}
              <h1 id="intake-title" className="text-sm font-semibold text-slate-900 tracking-tight">
                Nộp hồ sơ quyết toán
              </h1>
            </div>
          </div>

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

          {/* ------------------------------------------------------------- */}
          {/* BƯỚC 1: TẢI TÀI LIỆU                                           */}
          {/* ------------------------------------------------------------- */}
          {step === "upload" && (
            <section aria-labelledby="intake-title" className="space-y-4 text-xs">
              {/* Ô 1: đơn quyết toán — đúng 1 tệp */}
              <div className="border border-slate-200 rounded overflow-hidden bg-white">
                <div className="px-3.5 py-2.5 bg-slate-50 border-b border-slate-200 text-xs">
                  <span className="font-semibold text-slate-900">Đơn quyết toán (đúng 1 tệp)</span>
                  <span className="text-[11px] text-slate-500 block mt-0.5">Giấy đề nghị/quyết toán hoàn ứng có bảng chi.</span>
                </div>
                <div className="p-3.5 space-y-2">
                  {paperFiles.map((f) => (
                    <div key={f.name} className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-800 truncate">{f.name}</span>
                      <button
                        type="button"
                        onClick={() => setPaperFiles([])}
                        className="text-[11px] text-slate-400 hover:text-rose-600 cursor-pointer font-medium"
                      >
                        Xóa
                      </button>
                    </div>
                  ))}
                  {paperFiles.length === 0 && (
                    <label
                      htmlFor="paper-file"
                      className="border border-dashed border-slate-300 hover:border-slate-500 bg-slate-50/40 hover:bg-slate-50 rounded py-2.5 px-4 text-center flex items-center justify-center gap-2 cursor-pointer transition-colors block group text-xs text-slate-600 hover:text-slate-900"
                    >
                      <span className="font-medium">Chọn đơn quyết toán (PDF/DOC/DOCX/PNG/JPG)</span>
                      <input
                        id="paper-file"
                        aria-label="Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"
                        type="file"
                        accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg"
                        onChange={(event) => {
                          const picked = Array.from(event.target.files ?? []);
                          if (picked.length > 0) setPaperFiles([picked[0]]);
                        }}
                        className="sr-only"
                      />
                    </label>
                  )}
                </div>
              </div>

              {/* Ô 2: hóa đơn/chứng từ kèm theo — nhiều tệp */}
              <div className="border border-slate-200 rounded overflow-hidden bg-white">
                <div className="px-3.5 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs">
                  <span>
                    <span className="font-semibold text-slate-900">Hóa đơn / chứng từ kèm theo ({evidenceFiles.length})</span>
                    <span className="text-[11px] text-slate-500 block mt-0.5">Hóa đơn điện tử, vé, phiếu thu… — loại chứng từ do hệ thống đọc từ nội dung.</span>
                  </span>
                  {evidenceFiles.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setEvidenceFiles([])}
                      className="text-[11px] text-slate-400 hover:text-rose-600 cursor-pointer font-medium transition-colors"
                    >
                      Xóa tất cả
                    </button>
                  )}
                </div>
                {evidenceFiles.length > 0 && (
                  <ul className="divide-y divide-slate-100 text-xs">
                    {evidenceFiles.map((f, idx) => (
                      <li key={f.name} className="px-3.5 py-2.5 flex items-center justify-between hover:bg-slate-50/70 transition-colors">
                        <span className="font-medium text-slate-800 truncate">{f.name}</span>
                        <button
                          type="button"
                          onClick={() => removeFile(idx)}
                          className="text-slate-400 hover:text-rose-600 cursor-pointer text-xs"
                          title="Xóa tệp này"
                        >
                          ✕
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="p-3.5">
                  <label
                    htmlFor="evidence-files"
                    className="border border-dashed border-slate-300 hover:border-slate-500 bg-slate-50/40 hover:bg-slate-50 rounded py-2.5 px-4 text-center flex items-center justify-center gap-2 cursor-pointer transition-colors block group text-xs text-slate-600 hover:text-slate-900"
                  >
                    <span className="font-medium">Thêm hóa đơn / chứng từ (kéo thả hoặc nhấn để chọn)</span>
                    <input
                      id="evidence-files"
                      aria-label="Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"
                      type="file"
                      multiple
                      accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg"
                      onChange={(event) =>
                        setEvidenceFiles((prev) => [
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
              </div>

              {/* Nút hành động Bước 2: Đọc chứng từ */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                <div className="text-xs text-slate-500">
                  {(paperFiles.length > 0 || evidenceFiles.length > 0) && (
                    <span>Đã chọn <strong className="font-semibold text-slate-900">1</strong> đơn + <strong className="font-semibold text-slate-900">{evidenceFiles.length}</strong> chứng từ kèm theo</span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void handleReadDocuments()}
                  disabled={busy || paperFiles.length !== 1 || evidenceFiles.length === 0}
                  className="inline-flex items-center gap-1.5 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white font-medium text-xs px-4 py-2 rounded transition-colors cursor-pointer"
                >
                  <span>Đọc chứng từ</span>
                  <span aria-hidden="true" className="font-mono">→</span>
                </button>
              </div>
            </section>
          )}

          {/* ------------------------------------------------------------- */}
          {/* BƯỚC 2: TIẾN TRÌNH ĐỌC CHỨNG TỪ                                */}
          {/* ------------------------------------------------------------- */}
          {step === "reading" && (
            <section className="py-12 px-4 flex flex-col items-center justify-center text-xs space-y-7">
              <div className="flex flex-col items-center text-center space-y-3">
                <div className="relative flex items-center justify-center">
                  <div className="w-11 h-11 rounded-full bg-slate-100 flex items-center justify-center text-slate-800">
                    <svg className="w-5 h-5 animate-pulse text-slate-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.75" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="absolute -inset-1.5 rounded-full border border-slate-200 border-t-slate-800 animate-spin" />
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-slate-900 tracking-tight">
                    Hệ thống đang OCR &amp; trích xuất bản nháp
                  </h3>
                  <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 leading-relaxed">
                    Hệ thống đang nhận diện văn bản, phân loại Giấy quyết toán, đối chiếu số hóa đơn và tổng hợp các khoản chi...
                  </p>
                </div>
              </div>

              {/* Connected Timeline Stepper */}
              <div className="w-full max-w-sm pt-2">
                <div className="relative pl-6 space-y-5 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-px before:bg-slate-200">
                  {/* Bước 1: Đã xong */}
                  <div className="relative flex items-start gap-3">
                    <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-emerald-600 text-white flex items-center justify-center text-[9px] font-bold">
                      ✓
                    </span>
                    <div>
                      <p className="text-xs font-medium text-slate-900">
                        Đã tải lên 1 đơn + {evidenceFiles.length} chứng từ kèm theo
                      </p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Tệp nguồn đã sẵn sàng đưa vào luồng trích xuất
                      </p>
                    </div>
                  </div>

                  {/* Bước 2: Đang xử lý */}
                  <div className="relative flex items-start gap-3">
                    <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-slate-900 text-white flex items-center justify-center">
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                    </span>
                    <div>
                      <p className="text-xs font-semibold text-slate-900">
                        Đang đọc bảng kê &amp; hóa đơn chi phí
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        OCR nhận diện số tiền, ngày tháng và mã tra cứu
                      </p>
                    </div>
                  </div>

                  {/* Bước 3: Chờ đối chiếu */}
                  <div className="relative flex items-start gap-3 opacity-60">
                    <span className="absolute -left-6 top-0.5 w-4 h-4 rounded-full bg-slate-100 border border-slate-300" />
                    <div>
                      <p className="text-xs font-medium text-slate-700">
                        Chuẩn bị bản nháp đối chiếu
                      </p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Tổng hợp bảng rà soát để người dùng kiểm tra
                      </p>
                    </div>
                  </div>
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
      {/* LEFT PANE: Document & Evidence Inspector */}
      <div className={`w-full ${isViewerExpanded ? "md:w-3/4" : "md:w-1/2"} h-1/2 md:h-full overflow-hidden flex flex-col transition-all duration-200 ease-in-out`}>
        <DocumentViewer
          caseView={caseView}
          pendingFiles={[...paperFiles, ...evidenceFiles]}
          isExpanded={isViewerExpanded}
          onToggleExpand={() => setIsViewerExpanded((v) => !v)}
        />
      </div>

      {/* RIGHT PANE: Extracted Draft Workspace */}
      <div className={`w-full ${isViewerExpanded ? "md:w-1/4" : "md:w-1/2"} h-1/2 md:h-full overflow-hidden flex flex-col bg-white transition-all duration-200 ease-in-out`}>
        {/* Sleek Subheader Bar (h-11) */}
        <div className="h-11 border-b border-slate-200 px-5 flex items-center justify-between shrink-0 bg-white z-10">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack ?? (() => setStep("upload"))}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
            >
              <span className="font-mono">←</span>
              <span>Quay lại</span>
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

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setStep("upload")}
              className="text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors cursor-pointer px-2.5 py-1 rounded hover:bg-slate-100 border border-slate-200"
              title="Quay lại bước chọn tệp để tải lên tài liệu khác"
            >
              Chọn lại tệp
            </button>
          </div>
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
          <div className="pb-4 border-b border-slate-200">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2.5 flex-wrap">
                  <h2 id="review-title" className="text-sm font-semibold text-slate-900 tracking-tight">
                    Bản nháp hồ sơ quyết toán
                  </h2>
                  {link?.status === "LINKED" && (
                    <span role="status" className="inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span>Khoản ứng: {link.candidates.find((c) => c.activity_id === link.activity_id)?.name ?? link.activity_id}</span>
                    </span>
                  )}
                  {link?.status === "NOT_FOUND" && (
                    <span role="status" className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                      <span>Thanh toán trực tiếp</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Đối chiếu chứng từ gốc ở khung bên trái và xác nhận thông tin trước khi nộp.
                </p>
              </div>
              <div className="text-right shrink-0">
                <span className="text-[11px] text-slate-400 block">Người đề nghị</span>
                <strong className="text-xs font-semibold text-slate-900">{draft.declared_name ?? "Chưa đọc được"}</strong>
              </div>
            </div>

            {link?.status === "CONFLICT" && (
              <div role="alert" className="mt-3 text-xs text-rose-800 bg-rose-50 px-3 py-2 rounded border border-rose-200 flex items-center gap-1.5">
                <span>⚠</span>
                <span>Chứng từ mang căn cứ trái nhau về hồ sơ tạm ứng; kế toán sẽ xác minh trước khi duyệt.</span>
              </div>
            )}
          </div>

          {processingStatus === "technical_incomplete" && (
            <div role="alert" className="text-xs text-rose-800 bg-rose-50 px-3 py-2 rounded border border-rose-200">
              Đọc chứng từ chưa xong do lỗi kỹ thuật (hết thời gian/budget hoặc lỗi đọc).
              Hãy bấm “Đọc chứng từ” lại để tiếp tục phần còn thiếu — không cần tải lại từ đầu.
              Đây không phải yêu cầu bổ sung chứng từ mới.
            </div>
          )}

          {processingStatus === "needs_supplement" && (
            <div role="alert" className="text-xs text-amber-800 bg-amber-50 px-3 py-2 rounded border border-amber-200">
              Một số tệp chưa đọc được hoặc sai ô (đơn/evidence). Kiểm tra cảnh báo dưới đây,
              chuyển tệp đúng ô rồi đọc lại.
            </div>
          )}

          {arithmeticFindings.length > 0 && (
            <section role="alert" aria-label="Mâu thuẫn số học trên giấy quyết toán" className="space-y-3 rounded border border-rose-300 bg-rose-50 p-3 text-rose-950">
              <div>
                <h3 className="font-semibold">Có mâu thuẫn số liệu — chưa xác định tổng chi phí cuối cùng</h3>
                <p className="mt-1 text-[11px] text-rose-900">Các số dưới đây được giữ nguyên theo chứng từ. Hệ thống chưa xác minh chi phí hoặc số tiền quyết toán.</p>
              </div>
              {arithmeticFindings.map((finding, index) => (
                <article key={`${finding.code}:${index}`} className="space-y-1 border-t border-rose-200 pt-2">
                  <p className="font-medium">{finding.basis}</p>
                  <p>{finding.question}</p>
                  {finding.refs.length > 0 && (
                    <ul className="space-y-1 text-[11px] text-rose-900">
                      {finding.refs.map((ref, refIndex) => {
                        const sourceName = caseView?.sources.find((source) => source.id === ref.source_id)?.filename ?? ref.source_id;
                        return <li key={`${ref.source_id}:${ref.page}:${refIndex}`}>
                          {sourceName} · trang {ref.page ?? "?"}: <q>{ref.exact_quote}</q>
                        </li>;
                      })}
                    </ul>
                  )}
                </article>
              ))}
            </section>
          )}

          {warnings.filter((warning) => !arithmeticFindings.some((finding) => finding.basis === warning)).length > 0 && (
            <div className="space-y-1">
              {warnings.filter((warning) => !arithmeticFindings.some((finding) => finding.basis === warning)).map((w, i) => (
                <div key={i} className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-1.5 flex items-center gap-1.5">
                  <span>⚠</span>
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* 1. Lựa chọn liên kết (nếu cần xác nhận) */}
          {link?.status === "NEEDS_CONFIRMATION" && (
            <div className="py-2 border-b border-amber-200 bg-amber-50/50 px-3 py-2.5 rounded text-xs space-y-2">
              <p className="font-semibold text-amber-900">
                Hồ sơ này quyết toán cho khoản tạm ứng nào?
              </p>
              <p className="text-[11px] text-amber-800">
                Chứng từ chỉ tương đồng một số trường dữ liệu. Vui lòng chọn khoản tạm ứng phù hợp trong danh sách:
              </p>
              <div role="radiogroup" aria-label="Khoản tạm ứng cần quyết toán" className="space-y-1">
                {link.candidates.map((c) => (
                  <label key={c.activity_id} className="flex items-start gap-2 text-xs py-1 cursor-pointer">
                    <input
                      type="radio"
                      name="link-confirm"
                      value={c.activity_id}
                      checked={confirmedActivityId === c.activity_id}
                      onChange={(e) => setConfirmedActivityId(e.target.value)}
                      className="mt-0.5"
                    />
                    <span>
                      <strong className="font-medium text-slate-900">{c.name}</strong>
                      <span className="text-slate-500 font-mono tabular-nums text-[11px] ml-2">
                        {c.activity_id}
                        {c.occurred_at ? ` · ${c.occurred_at.slice(0, 10)}` : ""}
                        {c.amount !== null && c.amount !== undefined ? ` · ${formatVnd(c.amount)}` : ""}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* 2. Nội dung đề nghị quyết toán (Borderless Underline Input) */}
          <div className="space-y-1">
            <label htmlFor="draft-purpose" className="text-slate-500 block text-[11px] font-medium uppercase tracking-wider">
              Nội dung đề nghị quyết toán:
            </label>
            <input
              id="draft-purpose"
              value={draft.declared_purpose ?? ""}
              onChange={(e) => setDraft((prev) => ({ ...prev, declared_purpose: e.target.value }))}
              className="w-full bg-transparent border-0 border-b border-slate-200 hover:border-slate-400 focus:border-slate-900 focus:outline-none rounded-none py-1.5 px-0 text-xs font-semibold text-slate-900 transition-colors"
            />
            {(draft.destination || draft.trip_start || draft.trip_end) && (
              <span className="text-[11px] text-slate-400 block pt-0.5">
                Địa điểm &amp; thời gian: {[draft.destination, draft.trip_start, draft.trip_end].filter(Boolean).join(" · ")}
              </span>
            )}
          </div>

          {/* 3. Bảng kê chứng từ & Quyết toán tài chính liền mạch (Borderless Sheet) */}
          <div className="space-y-2 pt-2">
            <div className="flex items-center justify-between pb-1">
              <span className="text-slate-500 text-[11px] font-medium uppercase tracking-wider">
                Chi tiết chứng từ ({draft.expenses.length})
              </span>
            </div>

            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-400 font-medium text-[11px]">
                  <th className="py-2 px-0 font-normal">Khoản chi</th>
                  <th className="py-2 px-3 w-32 font-normal">Hóa đơn</th>
                  <th className="py-2 px-0 text-right w-32 font-normal">Số tiền</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {draft.expenses.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-4 text-center text-slate-400">
                      Chưa đọc được dòng chi tiết từ chứng từ.
                    </td>
                  </tr>
                ) : (
                  draft.expenses.map((item, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/50 transition-colors">
                      <td className="py-2.5 px-0">
                        <span className="font-medium text-slate-900 block">{item.description || `Dòng ${idx + 1} — chưa đọc được nội dung`}</span>
                        {item.amount === null ? (
                          <span className="text-[11px] text-amber-700 block mt-0.5">⚠ Chưa đọc rõ số tiền; dòng này chưa được tính vào tổng</span>
                        ) : item.matched_invoice ? (
                          <span className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                            <span className="text-emerald-600 font-bold">✓</span>
                            <span>Tệp: {item.matched_invoice}</span>
                          </span>
                        ) : item.suggested_invoice ? (
                          <span className="text-[11px] text-slate-500 block mt-0.5">
                            ? Có thể liên quan: {item.suggested_invoice}
                          </span>
                        ) : (
                          <span className="text-[11px] text-amber-700 block mt-0.5">
                            ⚠ Chưa liên kết được chứng từ
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 font-mono tabular-nums text-slate-600">
                        {item.invoice_no || "—"}
                      </td>
                      <td className="py-2.5 px-0 text-right font-mono tabular-nums font-medium text-slate-900">
                        {item.amount === null ? "Chưa đọc được" : formatVnd(item.amount)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              <tfoot className="border-t border-slate-200 divide-y divide-slate-100 text-xs">
                <tr>
                  <td colSpan={2} className="py-2.5 px-0 font-medium text-slate-700">
                    {draft.incurred_total_basis === "ROW_SUM"
                      ? "Tạm tính từ dòng chi phí (chưa đối soát):"
                      : "Tổng trên giấy (chưa xác minh):"}
                  </td>
                  <td className="py-2.5 px-0 text-right font-semibold text-slate-950 font-mono tabular-nums">
                    {draft.incurred_total !== null ? formatVnd(draft.incurred_total) : "Chưa đọc được"}
                  </td>
                </tr>

                {/* Row 2: Ứng nhân viên kê khai */}
                <tr>
                  <td colSpan={2} className="py-2.5 px-0">
                    <div className="flex items-center gap-2">
                      <label htmlFor="draft-advance" className="font-medium text-slate-700 cursor-pointer">
                        Ứng nhân viên kê khai:
                      </label>
                      {draft.declared_advance !== draft.original_advance && (
                        <span className="text-[10px] font-medium text-amber-700 bg-amber-50 px-1.5 py-0.2 rounded border border-amber-200">
                          Đã sửa
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 px-0 text-right">
                    <div className="flex flex-col items-end">
                      <div className="inline-flex items-center gap-1 justify-end">
                        <input
                          id="draft-advance"
                          aria-label="Ứng nhân viên kê khai:"
                          type="number"
                          value={draft.declared_advance ?? ""}
                          onChange={(e) =>
                            setDraft((prev) => ({
                              ...prev,
                              declared_advance: e.target.value === "" ? null : Number(e.target.value),
                            }))
                          }
                          className="w-32 text-right bg-transparent border-0 border-b border-slate-300 hover:border-slate-500 focus:border-slate-900 rounded-none py-0.5 px-0 font-mono tabular-nums font-semibold text-slate-900 focus:outline-none transition-colors"
                        />
                        <span className="text-slate-500 font-medium">đ</span>
                      </div>
                      {formatVndHint(draft.declared_advance) && (
                        <span className="text-[10px] text-slate-500 font-mono tabular-nums pt-0.5">
                          ≈ {formatVndHint(draft.declared_advance)}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>

                {/* Row 3: Chênh lệch kê khai dự kiến */}
                <tr className="border-t-2 border-slate-900/10">
                  <td colSpan={2} className="py-3 px-0 font-semibold text-slate-900">
                    Chênh lệch kê khai dự kiến:
                  </td>
                  <td className="py-3 px-0 text-right">
                    {netDifference === null ? (
                      <span className="text-slate-400 font-normal">Chưa xác định</span>
                    ) : (
                      <div className="flex items-baseline gap-1.5 justify-end">
                        <span className="text-sm font-bold font-mono tabular-nums text-slate-950">
                          {formatVnd(Math.abs(netDifference))}
                        </span>
                        <span className="text-[11px] text-slate-500 font-normal">
                          {netDifference < 0
                            ? "(Hoàn ứng)"
                            : netDifference > 0
                            ? "(Chi thêm)"
                            : "(Cân bằng)"}
                        </span>
                      </div>
                    )}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* 4. Ghi chú của nhân viên (Borderless Underline Input) */}
          <div className="pt-2 space-y-1">
            <label htmlFor="draft-notes" className="text-slate-500 block text-[11px] font-medium uppercase tracking-wider">
              Ghi chú của nhân viên (tùy chọn):
            </label>
            <input
              id="draft-notes"
              aria-label="Ghi chú của nhân viên (tùy chọn):"
              value={draft.notes}
              onChange={(e) => setDraft((prev) => ({ ...prev, notes: e.target.value }))}
              className="w-full bg-transparent border-0 border-b border-slate-200 hover:border-slate-400 focus:border-slate-900 focus:outline-none rounded-none py-1.5 px-0 text-xs text-slate-900 transition-colors"
            />
          </div>

          {/* 5. Nút "Xác nhận và nộp hồ sơ" */}
          <div className="pt-4 flex items-center justify-between border-t border-slate-200">
            <span className="text-[11px] text-slate-400">
              Kiểm tra kỹ trước khi gửi đối soát
            </span>
            <button
              type="button"
              onClick={() => void handleConfirmAndSubmit()}
              disabled={busy}
              className="bg-slate-950 hover:bg-slate-800 text-white font-medium text-xs py-2 px-5 rounded transition-colors disabled:opacity-40 flex items-center gap-2 cursor-pointer shadow-xs"
            >
              {busy ? "Đang xử lý nộp hồ sơ…" : "Xác nhận và nộp hồ sơ"}
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
