import { useState } from "react";

import { api, attachSources, errorMessage, submitCase } from "../api";
import { formatDate, formatVnd } from "../format";
import type { CaseView, SessionPayload } from "../types";

export function Intake({
  session,
  onCase,
}: {
  session: SessionPayload;
  onCase: (view: CaseView) => void;
}) {
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [activityId, setActivityId] = useState(
    session.activity_catalog[0]?.id ?? "",
  );
  const [newName, setNewName] = useState("");
  const [newDate, setNewDate] = useState("2026-10-06");
  const [newPurpose, setNewPurpose] = useState("");
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A Q32 employee paid-claim: the employee states which invoice they paid,
  // how much, and WHICH uploaded document supports it. The server derives the
  // actor/scope/time; the UI never asks for a backend actor id, never defaults
  // to the first document, and never fabricates a source quote (plan A8/E).
  const [claimInvoice, setClaimInvoice] = useState("");
  const [claimAmount, setClaimAmount] = useState("");
  const [claimSourceName, setClaimSourceName] = useState("");
  const [claimQuote, setClaimQuote] = useState("");
  // The documents the employee may pick for the claim: the files still in the
  // picker (uploaded on submit) plus any already attached, by display name.
  const claimSourceOptions = [
    ...files.map((f) => f.name),
    ...(caseView?.sources ?? []).map((s) => s.filename ?? s.id),
  ].filter((name, index, all) => all.indexOf(name) === index);

  async function createCase() {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const activity =
        mode === "existing"
          ? { mode: "existing", activity_id: activityId }
          : {
              mode: "new",
              name: newName,
              occurred_at: new Date(`${newDate}T09:00:00+07:00`).toISOString(),
              declared_purpose: newPurpose,
            };
      const result = await api.createCase(activity);
      setCaseView(result.case_view);
      onCase(result.case_view);
      setStatus("Đã mở hồ sơ cho hoạt động này (cùng hoạt động ⇒ cùng root).");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  // One primary action: upload any pending files, then submit. Uploading and
  // submitting separately let a user submit with files still only in the picker
  // (the case reached the server with zero evidence), so they are merged.
  async function submit() {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      let current = caseView;
      if (files.length > 0) {
        const attached = await attachSources(current.id, files, current.version);
        current = attached.case_view;
        setFiles([]);
      }
      // A typed claim references a specific uploaded document by its SERVER
      // source id (the id the backend checks), resolved from the employee's
      // chosen file, with a real quote the employee can see. The UI never
      // defaults to the first source and never fabricates a quote.
      const selectedSource = current.sources.find(
        (s) => (s.filename ?? s.id) === claimSourceName,
      );
      const claims =
        claimInvoice.trim() !== "" &&
        claimAmount.trim() !== "" &&
        selectedSource !== undefined &&
        claimQuote.trim() !== ""
          ? [
              {
                invoice_reference: claimInvoice.trim(),
                amount: Number(claimAmount),
                refs: [
                  {
                    source_id: selectedSource.id,
                    source_sha256: selectedSource.digest,
                    page: 1,
                    exact_quote: claimQuote.trim(),
                  },
                ],
                reason: "Nhân viên xác nhận đã trực tiếp thanh toán khoản chi này.",
              },
            ]
          : [];
      const result = await submitCase(
        current.id,
        activityId,
        "Công tác",
        current.version,
        claims,
      );
      setCaseView(result.case_view);
      onCase(result.case_view);
      setStatus("Đã nộp hồ sơ và đối chiếu.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="intake-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="intake-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-slate-700 text-sm" aria-hidden="true">upload_file</span>
          <span>Nộp hồ sơ</span>
        </h2>
        {caseView !== null && (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-medium bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-['JetBrains_Mono']">
            {caseView.id}
          </span>
        )}
      </div>

      <fieldset className="border border-slate-200 rounded p-3 bg-slate-50/60 space-y-2">
        <legend className="text-[11px] font-semibold text-slate-700 px-1">Chọn hoạt động</legend>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-700 font-normal">
            <input
              type="radio"
              name="activity-mode"
              value="existing"
              checked={mode === "existing"}
              onChange={() => setMode("existing")}
              className="text-slate-900 focus:ring-0"
            />
            <span>Hoạt động có sẵn</span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-700 font-normal">
            <input
              type="radio"
              name="activity-mode"
              value="new"
              checked={mode === "new"}
              onChange={() => setMode("new")}
              className="text-slate-900 focus:ring-0"
            />
            <span>Hoạt động mới</span>
          </label>
        </div>
      </fieldset>

      {mode === "existing" ? (
        <p>
          <label htmlFor="activity-select" className="text-slate-600 block mb-1 font-medium">
            Hoạt động
            <select
              id="activity-select"
              value={activityId}
              onChange={(event) => setActivityId(event.target.value)}
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            >
              {session.activity_catalog.map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.name}
                  {activity.occurred_at !== null
                    ? ` · ${formatDate(activity.occurred_at)}`
                    : ""}
                  {activity.budget_amount !== null
                    ? ` · ngân sách ${formatVnd(activity.budget_amount)}`
                    : " · chưa có ngân sách"}
                </option>
              ))}
            </select>
          </label>
        </p>
      ) : (
        <div className="space-y-2 bg-slate-50 p-2.5 rounded border border-slate-100">
          <p>
            <label htmlFor="activity-name" className="text-slate-600 block mb-1 font-medium">
              Tên hoạt động
              <input
                id="activity-name"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
              />
            </label>
          </p>
          <p>
            <label htmlFor="activity-date" className="text-slate-600 block mb-1 font-medium">
              Ngày
              <input
                id="activity-date"
                type="date"
                value={newDate}
                onChange={(event) => setNewDate(event.target.value)}
                className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-['JetBrains_Mono']"
              />
            </label>
          </p>
          <p>
            <label htmlFor="activity-purpose" className="text-slate-600 block mb-1 font-medium">
              Mục đích
              <input
                id="activity-purpose"
                value={newPurpose}
                onChange={(event) => setNewPurpose(event.target.value)}
                className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
              />
            </label>
          </p>
        </div>
      )}

      <p>
        <button
          type="button"
          onClick={() => void createCase()}
          disabled={busy}
          className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 text-xs font-medium px-3.5 py-1.5 rounded shadow-sm transition-colors disabled:opacity-50"
        >
          Tạo hồ sơ
        </button>
      </p>

      <div className="space-y-1.5 pt-2 border-t border-slate-100">
        <h3 className="text-[11px] font-semibold text-slate-700 uppercase tracking-wide">Chứng từ</h3>
        <p>
          <label htmlFor="source-files" className="block text-slate-600">
            <span className="font-medium text-xs block mb-1">Chứng từ (PDF/PNG/JPEG)</span>
            <input
              id="source-files"
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []))
              }
              className="w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
            />
          </label>
        </p>
        {files.length > 0 && (
          <div className="text-[11px] text-slate-600 bg-slate-50 p-2 rounded border border-slate-200 font-['JetBrains_Mono']">
            {files.length} tệp đã chọn: {files.map(f => f.name).join(", ")}
          </div>
        )}
      </div>

      <fieldset className="border border-slate-200 rounded p-3 bg-slate-50/60 space-y-2">
        <legend className="text-[11px] font-semibold text-slate-700 px-1">Khoản nhân viên đã trả (nếu có)</legend>
        <p className="muted text-[11px] text-slate-500 leading-relaxed">
          Nhân viên xác nhận trực tiếp đã thanh toán khoản chi này. Đây là lời
          xác nhận của nhân viên, không phải xác minh ngân hàng.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <p>
            <label htmlFor="claim-invoice" className="text-slate-600 block text-xs font-medium">
              Số hóa đơn
              <input
                id="claim-invoice"
                value={claimInvoice}
                onChange={(event) => setClaimInvoice(event.target.value)}
                placeholder="Ví dụ: 001284"
                className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-['JetBrains_Mono']"
              />
            </label>
          </p>
          <p>
            <label htmlFor="claim-amount" className="text-slate-600 block text-xs font-medium">
              Số tiền (VND)
              <input
                id="claim-amount"
                type="number"
                min={0}
                value={claimAmount}
                onChange={(event) => setClaimAmount(event.target.value)}
                placeholder="Ví dụ: 7920000"
                className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-['JetBrains_Mono']"
              />
            </label>
          </p>
        </div>
        <p>
          <label htmlFor="claim-source" className="text-slate-600 block text-xs font-medium">
            Chứng từ cho khoản này
            <select
              id="claim-source"
              value={claimSourceName}
              onChange={(event) => setClaimSourceName(event.target.value)}
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            >
              <option value="">— Chọn chứng từ —</option>
              {claimSourceOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </p>
        <p>
          <label htmlFor="claim-quote" className="text-slate-600 block text-xs font-medium">
            Trích đoạn trên chứng từ (nguyên văn)
            <input
              id="claim-quote"
              value={claimQuote}
              onChange={(event) => setClaimQuote(event.target.value)}
              placeholder="Ví dụ: 3.240.000 đ"
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            />
          </label>
        </p>
      </fieldset>

      <p className="pt-1">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || caseView === null}
          className="bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs px-4 py-2 rounded shadow-sm transition-colors disabled:opacity-40"
        >
          Nộp hồ sơ
        </button>
      </p>

      {status !== null && (
        <p role="status" aria-live="polite" className="status p-2 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error p-2 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      {caseView !== null && (
        <div className="case-line bg-slate-50 border border-slate-200 rounded p-2.5 space-y-1">
          <p className="summary font-medium text-slate-900 text-xs">{caseView.summary}</p>
          <p className="muted text-[11px] text-slate-500 font-['JetBrains_Mono']" data-testid="case-code">
            Mã hồ sơ: {caseView.id}
          </p>
        </div>
      )}
    </section>
  );
}
