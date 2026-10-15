import { useState } from "react";

import { attachSources, errorMessage, readEmployeeReturnDraft } from "../api";
import { formatVnd } from "../format";
import type { CaseView } from "../types";

export function EmployeeReturn({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [instructionId, setInstructionId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (caseView === null) return null;
  const activeCollects = caseView.instructions.filter(
    (item) => item.direction === "COLLECT" && ["ISSUED", "PARTIAL"].includes(item.status) && item.remaining > 0,
  );
  const drafts = caseView.employee_return_drafts ?? [];

  async function submit() {
    if (!caseView || !file || !instructionId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const attached = await attachSources(caseView.id, [file], caseView.version);
      onCase(attached.case_view);
      const source = attached.case_view.sources.filter((item) => item.filename === file.name).at(-1);
      if (!source) throw new Error("Không tìm thấy chứng từ vừa tải trong hồ sơ.");
      const result = await readEmployeeReturnDraft(
        caseView.id,
        source.id,
        instructionId,
        attached.case_view.version,
      );
      onCase(result.case_view);
      setNotice("Đã lưu bản đọc chứng từ. Sổ tiền chưa thay đổi; kế toán cần kiểm tra và xác nhận.");
      setFile(null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="employee-return-title" className="space-y-3 rounded-md border border-slate-200 bg-white p-4 text-xs">
      <div>
        <h2 id="employee-return-title" className="font-semibold text-slate-900">Nộp chứng từ tiền hoàn trả</h2>
        <p className="mt-1 text-slate-600">Tải chứng từ giao dịch thực nhận và chọn đúng lệnh thu. Tải lên hoặc OCR không ghi nhận tiền vào sổ.</p>
      </div>
      {activeCollects.length === 0 ? (
        <p className="rounded border border-slate-200 bg-slate-50 p-3 text-slate-600">Hồ sơ hiện không có lệnh thu đang hiệu lực; chưa thể nộp chứng từ hoàn trả.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <label className="block space-y-1">
            <span className="font-medium text-slate-700">Lệnh thu cần đối chiếu</span>
            <select aria-label="Lệnh thu cần đối chiếu" value={instructionId} onChange={(event) => setInstructionId(event.target.value)} className="w-full rounded border border-slate-300 px-2 py-2">
              <option value="">Chọn lệnh thu</option>
              {activeCollects.map((item) => <option key={item.id} value={item.id}>{item.id} · còn {formatVnd(item.remaining)}</option>)}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="font-medium text-slate-700">Chứng từ chuyển khoản</span>
            <input aria-label="Chứng từ chuyển khoản hoàn trả" type="file" accept="application/pdf,image/png,image/jpeg" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="block w-full rounded border border-slate-300 px-2 py-1.5" />
          </label>
          <button type="button" onClick={() => void submit()} disabled={busy || !file || !instructionId} className="rounded bg-slate-950 px-4 py-2 font-semibold text-white disabled:opacity-40">
            {busy ? "Đang đọc…" : "Tải lên và đọc"}
          </button>
        </div>
      )}
      {drafts.length > 0 && <div className="space-y-2">
        <h3 className="font-medium text-slate-800">Chứng từ đã nộp</h3>
        {drafts.map((draft) => <article key={draft.draft_id} className="rounded border border-slate-200 bg-slate-50 p-3" data-testid="employee-return-draft">
          <div className="flex flex-wrap justify-between gap-2"><strong>{draft.source_filename}</strong><span>{draft.status === "CONFIRMED" ? "Kế toán đã xác nhận" : "Chờ kế toán xác nhận"}</span></div>
          <p className="mt-1 text-slate-600">Đối chiếu {draft.instruction_id} · {draft.amount === null ? "Chưa đọc được số tiền" : formatVnd(draft.amount)} · {draft.match_status}</p>
          {draft.signals.map((signal, index) => <p key={`${signal.field}-${index}`} className="mt-1 text-amber-800">{signal.summary}</p>)}
        </article>)}
      </div>}
      {notice && <p role="status" className="rounded border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-800">{notice}</p>}
      {error && <p role="alert" className="rounded border border-rose-200 bg-rose-50 p-2.5 text-rose-800">{error}</p>}
    </section>
  );
}
