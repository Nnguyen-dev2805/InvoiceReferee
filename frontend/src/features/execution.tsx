import { useState } from "react";

import { errorMessage, recordActual } from "../api";
import { formatVnd } from "../format";
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
    <section aria-labelledby="execution-title" className="space-y-4 select-none text-xs">
      <div className="flex items-center justify-between border-b border-slate-200 pb-2">
        <h2 id="execution-title" className="font-semibold text-slate-900">Dòng tiền thực tế</h2>
      </div>
      <div className="space-y-1.5 border-b border-slate-200 pb-3">
        <h3 className="text-[11px] font-medium uppercase tracking-wider text-slate-500">Số đã xác minh</h3>
        <div className="grid grid-cols-1 gap-3 pt-1 sm:grid-cols-3">
          {Object.entries(caseView.actual_money).filter(([key]) => key in MONEY_LABELS).map(([key, fact]) => (
            <div key={key} data-testid={`actual-${key}`} className="flex items-baseline justify-between py-1 sm:flex-col sm:justify-start">
              <span className="text-[11px] font-medium text-slate-500">{MONEY_LABELS[key]}:</span>
              <strong className={`font-mono tabular-nums text-xs sm:mt-1 ${fact.state === "KNOWN" && fact.value !== null ? "font-semibold text-slate-900" : "text-slate-400"}`}>
                {fact.state === "KNOWN" && fact.value !== null ? formatVnd(fact.value) : "Chưa xác minh"}
              </strong>
            </div>
          ))}
        </div>
      </div>
      {activePays.length === 0 ? (
        <p className="rounded border border-slate-200 bg-slate-50 p-3 text-slate-600" data-testid="no-active-pay">
          Không có lệnh chi đang hiệu lực. Hồ sơ không cần ghi nhận khoản công ty chi bổ sung.
        </p>
      ) : (
        <div className="space-y-3 rounded-md border border-slate-200 bg-white p-3">
          <h3 className="font-medium text-slate-800">Ghi nhận chi bổ sung đã thực hiện</h3>
          <p className="text-slate-600">Chỉ ghi khi ngân hàng đã hoàn tất. Mã giao dịch phải lấy từ chứng từ; không tự tạo mã.</p>
          <label className="block space-y-1"><span>Lệnh chi</span><select aria-label="Lệnh chi" value={instructionId} onChange={(event) => setInstructionId(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2"><option value="">Chọn lệnh chi</option>{activePays.map((item) => <option key={item.id} value={item.id}>{item.id} · còn {formatVnd(item.remaining)}</option>)}</select></label>
          <label className="block space-y-1"><span>Chứng từ đã tải lên</span><select aria-label="Chứng từ chi bổ sung" value={sourceId} onChange={(event) => setSourceId(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2"><option value="">Chọn chứng từ</option>{caseView.sources.map((item) => <option key={item.id} value={item.id}>{item.filename ?? item.id}</option>)}</select></label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block space-y-1"><span>Số tiền thực chi (VND)</span><input aria-label="Số tiền thực chi" type="number" min="1" step="1" value={amount} onChange={(event) => setAmount(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2" /></label>
            <label className="block space-y-1"><span>Mã giao dịch trên chứng từ</span><input aria-label="Mã giao dịch chi" value={reference} onChange={(event) => setReference(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2" /></label>
            <label className="block space-y-1"><span>Ngày giao dịch</span><input aria-label="Ngày giao dịch chi" type="date" value={eventAt} onChange={(event) => setEventAt(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2" /></label>
            <label className="block space-y-1"><span>Trang chứng từ</span><input aria-label="Trang chứng từ chi" type="number" min="1" step="1" value={page} onChange={(event) => setPage(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2" /></label>
          </div>
          <label className="block space-y-1"><span>Đoạn căn cứ trên chứng từ</span><textarea aria-label="Căn cứ chứng từ chi" rows={2} value={quote} onChange={(event) => setQuote(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2" /></label>
          <div className="flex justify-end"><button type="button" onClick={() => void record()} disabled={busy} className="rounded bg-slate-950 px-4 py-2 font-semibold text-white disabled:opacity-40">{busy ? "Đang ghi nhận…" : "Xác nhận khoản chi đã nhận"}</button></div>
        </div>
      )}
      {status && <p role="status" className="rounded border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-800">{status}</p>}
      {error && <p role="alert" className="rounded border border-rose-200 bg-rose-50 p-2.5 text-rose-800">{error}</p>}
    </section>
  );
}
