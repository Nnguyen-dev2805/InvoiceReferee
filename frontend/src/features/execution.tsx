import { useState } from "react";

import { errorMessage, recordActual, markExecution, attachSources } from "../api";
import { formatVnd, formatVndHint } from "../format";
import type { CaseView } from "../types";

const MONEY_LABELS: Record<string, string> = {
  P: "Chi bổ sung đã nhận",
  R: "Nhân viên đã hoàn trả",
  A: "Ứng thực nhận",
};

/** Accountant records a company payment only against an active PAY instruction and proof. */
export function Execution({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
  selectedQuote?: string | null;
}) {
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [instructionId, setInstructionId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [page, setPage] = useState("1");
  const [quote, setQuote] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [eventAt, setEventAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  if (caseView === null) return null;
  const activePays = caseView.instructions.filter(
    (item) => item.direction === "PAY" && ["ISSUED", "PARTIAL"].includes(item.status) && item.remaining > 0,
  );

  async function uploadProof() {
    if (!caseView || !proofFile) return;
    setBusy(true); setError(null);
    try {
      const result = await attachSources(caseView.id, [proofFile], caseView.version);
      const source = result.case_view.sources.filter(s => s.filename === proofFile.name).at(-1);
      onCase(result.case_view);
      if (source) setSourceId(source.id);
      setProofFile(null);
      setStatus("Đã lưu chứng từ chi bổ sung. Tiền chưa được ghi nhận.");
    } catch(cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }

  async function record() {
    if (caseView === null) return;
    const instruction = activePays.find((item) => item.id === instructionId);
    const source = caseView.sources.find((item) => item.id === sourceId);
    const number = Number(amount);
    const pageNumber = Number(page);
    if (!instruction || !source || !reference.trim() || !eventAt || !quote.trim() || !Number.isSafeInteger(number) || number <= 0) {
      setError("Chọn lệnh chi còn hiệu lực và chứng từ; nhập số tiền, mã giao dịch, ngày và căn cứ trên chứng từ.");
      return;
    }
    if (number > instruction.remaining) {
      setError(`Số tiền vượt phần còn lại của lệnh chi (${formatVnd(instruction.remaining)}).`);
      return;
    }
    if (!Number.isInteger(pageNumber) || pageNumber < 1) {
      setError("Trang căn cứ phải là số nguyên từ 1 trở lên.");
      return;
    }
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `transfer:${reference.trim()}`,
        claimed_kind: "REIMBURSEMENT_RECEIVED",
        claimed_scope: caseView.activity ?? "",
        payer: "company:demo",
        payee: caseView.employee ?? "",
        amount: number,
        event_at: new Date(`${eventAt}T12:00:00+07:00`).toISOString(),
        completion_claim: "Kế toán đã đối chiếu chứng từ và xác nhận tiền chi thực tế.",
        reason: "Ghi nhận khoản công ty chi bổ sung theo đúng lệnh chi và chứng từ đã đối chiếu.",
        instrument_method: "TRANSFER",
        instrument_status: "COMPLETED",
        instrument_reference: reference.trim(),
        instruction_id: instruction.id,
        refs: [{ source_id: source.id, source_sha256: source.digest, page: pageNumber, exact_quote: quote.trim() }],
      }, caseView.version);
      onCase(result.case_view);
      setStatus("Đã ghi nhận khoản chi bổ sung theo lệnh và chứng từ.");
      setAmount("");
      setReference("");
      setQuote("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="execution-title" className="space-y-4 text-xs">
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <h2 id="execution-title" className="font-semibold text-slate-900 text-xs">Dòng tiền thực tế</h2>
      </div>
      <div className="space-y-2 border-b border-slate-200 pb-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Số đã xác minh</h3>
        <div className="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-3">
          {Object.entries(caseView.actual_money).filter(([key]) => key in MONEY_LABELS).map(([key, fact]) => {
            const isKnown = fact.state === "KNOWN" && fact.value !== null;
            return (
              <div
                key={key}
                data-testid={`actual-${key}`}
                className="rounded-lg border border-slate-200 bg-white p-3 flex flex-col justify-between shadow-2xs"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-500">{MONEY_LABELS[key]}</span>
                  <span className={`w-2 h-2 rounded-full ${isKnown ? "bg-emerald-500" : "bg-slate-300"}`} />
                </div>
                <strong className={`font-mono tabular-nums text-sm mt-2 ${isKnown ? "font-semibold text-slate-900" : "font-normal text-slate-400"}`}>
                  {fact.state === "KNOWN" && fact.value !== null ? formatVnd(fact.value) : "Chưa xác minh"}
                </strong>
              </div>
            );
          })}
        </div>
      </div>
      {activePays.length === 0 ? (
        <p className="rounded border border-slate-200 bg-slate-50/70 p-3 text-xs text-slate-500" data-testid="no-active-pay">
          Không có lệnh chi đang hiệu lực. Hồ sơ không cần ghi nhận khoản công ty chi bổ sung.
        </p>
      ) : (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
          <div>
            <h3 className="font-semibold text-slate-800 text-xs">Ghi nhận chi bổ sung đã thực hiện</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">Chỉ ghi khi ngân hàng đã hoàn tất. Mã giao dịch phải lấy từ chứng từ; không tự tạo mã.</p>
          </div>
          <div className="space-y-2">
            <label className="block">Tải chứng từ chi bổ sung<input type="file" aria-label="Tải chứng từ chi bổ sung" accept="application/pdf,image/png,image/jpeg" onChange={e=>setProofFile(e.target.files?.[0] ?? null)}/></label>
            <button type="button" disabled={busy || !proofFile} onClick={()=>void uploadProof()} className="rounded border px-3 py-2 disabled:opacity-40">Lưu chứng từ chi bổ sung</button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Lệnh chi</span>
              <select
                aria-label="Lệnh chi"
                value={instructionId}
                onChange={(event) => setInstructionId(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs cursor-pointer"
              >
                <option value="">Chọn lệnh chi</option>
                {activePays.map((item) => (
                  <option key={item.id} value={item.id}>{item.id} · còn {formatVnd(item.remaining)}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Chứng từ đã tải lên</span>
              <select
                aria-label="Chứng từ chi bổ sung"
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs cursor-pointer"
              >
                <option value="">Chọn chứng từ</option>
                {caseView.sources.map((item) => (
                  <option key={item.id} value={item.id}>{item.filename ?? item.id}</option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Số tiền thực chi (VND)</span>
              <input
                aria-label="Số tiền thực chi"
                type="number"
                min="1"
                step="1"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 font-mono tabular-nums text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
              {formatVndHint(amount) && (
                <span className="text-[11px] text-slate-500 font-mono tabular-nums block">
                  ≈ {formatVndHint(amount)}
                </span>
              )}
            </label>
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Mã giao dịch trên chứng từ</span>
              <input
                aria-label="Mã giao dịch chi"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 font-mono text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Ngày giao dịch</span>
              <input
                aria-label="Ngày giao dịch chi"
                type="date"
                value={eventAt}
                onChange={(event) => setEventAt(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-slate-600 block text-[11px] font-medium">Trang chứng từ</span>
              <input
                aria-label="Trang chứng từ chi"
                type="number"
                min="1"
                step="1"
                value={page}
                onChange={(event) => setPage(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 font-mono text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
              />
            </label>
          </div>
          <label className="block space-y-1">
            <span className="text-slate-600 block text-[11px] font-medium">Đoạn căn cứ trên chứng từ</span>
            <textarea
              aria-label="Căn cứ chứng từ chi"
              rows={2}
              value={quote}
              onChange={(event) => setQuote(event.target.value)}
              className="w-full bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-950 transition-colors shadow-2xs"
            />
          </label>
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={() => void record()}
              disabled={busy}
              className="rounded bg-slate-950 hover:bg-slate-800 px-4 py-2 font-medium text-white text-xs disabled:opacity-40 transition-colors shadow-2xs cursor-pointer"
            >
              {busy ? "Đang ghi nhận…" : "Xác nhận khoản chi đã nhận"}
            </button>
          </div>
        </div>
      )}
      <ExecutionClosure caseView={caseView} onCase={onCase} />
      {status && <p role="status" className="rounded border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-800">{status}</p>}
      {error && <p role="alert" className="rounded border border-rose-200 bg-rose-50 p-2.5 text-rose-800">{error}</p>}
    </section>
  );
}


function ExecutionClosure({caseView, onCase}: {caseView: CaseView; onCase: (view: CaseView) => void}) {
  const [instructionId, setInstructionId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [quote, setQuote] = useState("");
  const [page, setPage] = useState("1");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = caseView.instructions.filter(i => i.status === "FULFILLED" && i.execution_state !== "CLOSED_CONFIRMED");
  if (!pending.length) return null;
  async function close() {
    const source = caseView.sources.find(s => s.id === sourceId);
    if (!source || !pending.some(i => i.id === instructionId) || !quote.trim() || !reason.trim() || !Number.isInteger(Number(page)) || Number(page) < 1) {
      setError("Chọn lệnh, chứng từ, trang và nêu căn cứ, lý do đã hoàn tất thực hiện."); return;
    }
    setBusy(true); setError(null);
    try {
      const result = await markExecution(caseView.id, {instruction_id: instructionId, execution_state: "CLOSED_CONFIRMED",
        refs: [{source_id: source.id, source_sha256: source.digest, page: Number(page), exact_quote: quote.trim()}], reason: reason.trim()}, caseView.version);
      onCase(result.case_view);
    } catch(cause) { setError(errorMessage(cause)); } finally { setBusy(false); }
  }
  return <div className="rounded border border-slate-200 p-4 space-y-3">
    <h3 className="font-semibold">Xác nhận hoàn tất thực hiện</h3>
    <p>Tiền theo lệnh đã ghi nhận đủ. Xác nhận đợt thực hiện đã kết thúc, không còn giao dịch đang chuyển. Thao tác này không ghi thêm tiền.</p>
    <label className="block">Lệnh xác nhận thực hiện<select aria-label="Lệnh xác nhận thực hiện" value={instructionId} onChange={e=>setInstructionId(e.target.value)}><option value="">Chọn lệnh</option>{pending.map(i=><option key={i.id} value={i.id}>{i.id}</option>)}</select></label>
    <label className="block">Chứng từ xác nhận thực hiện<select aria-label="Chứng từ xác nhận thực hiện" value={sourceId} onChange={e=>setSourceId(e.target.value)}><option value="">Chọn chứng từ</option>{caseView.sources.map(s=><option key={s.id} value={s.id}>{s.filename ?? s.id}</option>)}</select></label>
    <label className="block">Trang xác nhận thực hiện<input aria-label="Trang xác nhận thực hiện" type="number" min="1" value={page} onChange={e=>setPage(e.target.value)}/></label>
    <label className="block">Căn cứ xác nhận thực hiện<textarea aria-label="Căn cứ xác nhận thực hiện" value={quote} onChange={e=>setQuote(e.target.value)}/></label>
    <label className="block">Lý do xác nhận thực hiện<textarea aria-label="Lý do xác nhận thực hiện" value={reason} onChange={e=>setReason(e.target.value)}/></label>
    <button type="button" disabled={busy} onClick={()=>void close()} className="rounded bg-slate-950 text-white px-3 py-2 disabled:opacity-40">Xác nhận đã hoàn tất thực hiện</button>
    {error && <p role="alert">{error}</p>}
  </div>;
}
