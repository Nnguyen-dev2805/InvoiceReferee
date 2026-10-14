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

  // Q32 employee paid-claim
  const [claimInvoice, setClaimInvoice] = useState("");
  const [claimAmount, setClaimAmount] = useState("");
  const [claimSourceName, setClaimSourceName] = useState("");
  const [claimQuote, setClaimQuote] = useState("");

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
      setStatus("Đã nộp hồ sơ và đối chiếu thành công.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="intake-title" className="bg-white border border-slate-200 rounded-xl p-5 text-xs shadow-xs space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h2 id="intake-title" className="text-sm font-bold text-slate-900 tracking-tight">
            Nộp hồ sơ quyết toán
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Quy trình 3 bước dành cho nhân viên đề nghị thanh toán
          </p>
        </div>

        {caseView !== null && (
          <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200 font-mono-nums font-semibold">
            {caseView.id}
          </span>
        )}
      </div>

      {/* Step 1: Chọn hoạt động */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-[11px]">1</span>
          <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wide">
            Hoạt động công tác / tiếp khách
          </h3>
        </div>

        <fieldset className="border border-slate-200 rounded-lg p-3.5 bg-slate-50/50 space-y-3">
          <div className="flex items-center gap-4 text-xs">
            <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-800">
              <input
                type="radio"
                name="activity-mode"
                value="existing"
                checked={mode === "existing"}
                onChange={() => setMode("existing")}
                className="text-slate-900 focus:ring-0 cursor-pointer"
              />
              <span>Hoạt động đã được duyệt ngân sách</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-800">
              <input
                type="radio"
                name="activity-mode"
                value="new"
                checked={mode === "new"}
                onChange={() => setMode("new")}
                className="text-slate-900 focus:ring-0 cursor-pointer"
              />
              <span>Khai báo hoạt động mới</span>
            </label>
          </div>

          {mode === "existing" ? (
            <div>
              <label htmlFor="activity-select" className="text-slate-700 block mb-1 font-medium text-xs">
                Danh mục hoạt động:
                <select
                  id="activity-select"
                  value={activityId}
                  onChange={(event) => setActivityId(event.target.value)}
                  className="w-full mt-1 bg-white border border-slate-200 rounded-lg text-xs px-3 py-2 text-slate-800 focus:outline-none focus:border-slate-400 font-medium cursor-pointer shadow-2xs"
                >
                  {session.activity_catalog.map((activity) => (
                    <option key={activity.id} value={activity.id}>
                      {activity.name}
                      {activity.occurred_at !== null
                        ? ` · ${formatDate(activity.occurred_at)}`
                        : ""}
                      {activity.budget_amount !== null
                        ? ` · Ngân sách: ${formatVnd(activity.budget_amount)}`
                        : " · Chưa có ngân sách"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : (
            <div className="space-y-2 bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
              <label htmlFor="activity-name" className="text-slate-700 block font-medium">
                Tên hoạt động
                <input
                  id="activity-name"
                  value={newName}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="Ví dụ: Công tác thị trường Đà Nẵng Q3"
                  className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
                />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label htmlFor="activity-date" className="text-slate-700 block font-medium">
                  Ngày diễn ra
                  <input
                    id="activity-date"
                    type="date"
                    value={newDate}
                    onChange={(event) => setNewDate(event.target.value)}
                    className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 font-mono-nums focus:outline-none focus:border-slate-400"
                  />
                </label>
                <label htmlFor="activity-purpose" className="text-slate-700 block font-medium">
                  Mục đích công tác
                  <input
                    id="activity-purpose"
                    value={newPurpose}
                    onChange={(event) => setNewPurpose(event.target.value)}
                    placeholder="Gặp gỡ khách hàng ký hợp đồng"
                    className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
                  />
                </label>
              </div>
            </div>
          )}

          <div>
            <button
              type="button"
              onClick={() => void createCase()}
              disabled={busy}
              className="border border-slate-300 bg-white hover:bg-slate-50 text-slate-900 text-xs font-semibold px-4 py-2 rounded-lg shadow-2xs transition-colors disabled:opacity-50 cursor-pointer"
            >
              Tạo hồ sơ
            </button>
          </div>
        </fieldset>
      </div>

      {/* Step 2: Đính kèm chứng từ */}
      <div className="space-y-3 pt-1">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-[11px]">2</span>
          <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wide">
            Đính kèm chứng từ chi phí
          </h3>
        </div>

        <div className="border border-slate-200 rounded-lg p-3.5 bg-slate-50/50 space-y-2.5">
          <label htmlFor="source-files" className="block text-slate-700">
            <span className="font-semibold text-xs block mb-1">Chứng từ (PDF/PNG/JPEG)</span>
            <input
              id="source-files"
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              onChange={(event) =>
                setFiles(Array.from(event.target.files ?? []))
              }
              className="w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-slate-900 file:text-white hover:file:bg-slate-800 cursor-pointer"
            />
          </label>

          {files.length > 0 && (
            <div className="text-xs text-slate-700 bg-white p-2.5 rounded-md border border-slate-200 space-y-1">
              <span className="font-semibold block text-slate-900">
                Tệp đã chọn sẵn sàng tải lên ({files.length}):
              </span>
              <ul className="list-disc list-inside text-slate-600 font-mono-nums">
                {files.map((f) => (
                  <li key={f.name}>{f.name} ({(f.size / 1024).toFixed(1)} KB)</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Step 3: Xác nhận tự chi Q32 (nếu có) */}
      <div className="space-y-3 pt-1">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-[11px]">3</span>
          <h3 className="font-bold text-slate-900 text-xs uppercase tracking-wide">
            Xác nhận nhân viên tự chi trả bằng tiền cá nhân
          </h3>
        </div>

        <fieldset className="border border-slate-200 rounded-lg p-3.5 bg-slate-50/50 space-y-3">
          <p className="text-[11px] text-slate-600 leading-relaxed">
            Nếu nhân viên trực tiếp dùng thẻ cá nhân / tiền mặt thanh toán, vui lòng khai báo để hệ thống tính vào khoản công ty hoàn tiền.
          </p>

          <div className="grid grid-cols-2 gap-2.5">
            <label htmlFor="claim-invoice" className="text-slate-700 block font-medium">
              Số hóa đơn đối chiếu
              <input
                id="claim-invoice"
                value={claimInvoice}
                onChange={(event) => setClaimInvoice(event.target.value)}
                placeholder="Ví dụ: 001284"
                className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 font-mono-nums focus:outline-none focus:border-slate-400"
              />
            </label>
            <label htmlFor="claim-amount" className="text-slate-700 block font-medium">
              Số tiền đã chi (VNĐ)
              <input
                id="claim-amount"
                type="number"
                min={0}
                value={claimAmount}
                onChange={(event) => setClaimAmount(event.target.value)}
                placeholder="Ví dụ: 3240000"
                className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 font-mono-nums focus:outline-none focus:border-slate-400"
              />
            </label>
          </div>

          <label htmlFor="claim-source" className="text-slate-700 block font-medium">
            Chứng từ cho khoản này:
            <select
              id="claim-source"
              value={claimSourceName}
              onChange={(event) => setClaimSourceName(event.target.value)}
              className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 cursor-pointer"
            >
              <option value="">— Chọn chứng từ —</option>
              {claimSourceOptions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label htmlFor="claim-quote" className="text-slate-700 block font-medium">
            Trích đoạn nguyên văn trên chứng từ:
            <input
              id="claim-quote"
              value={claimQuote}
              onChange={(event) => setClaimQuote(event.target.value)}
              placeholder="Ví dụ: 3.240.000 đ hoặc CÔNG TY CỔ PHẦN..."
              className="w-full mt-1 bg-white border border-slate-200 rounded-md text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400 font-mono-nums"
            />
          </label>
        </fieldset>
      </div>

      {/* Primary Submit Action */}
      <div className="pt-2">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || caseView === null}
          className="w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs py-2.5 px-4 rounded-lg shadow-sm transition-colors disabled:opacity-40 flex items-center justify-center gap-2 cursor-pointer"
        >
          Nộp hồ sơ
        </button>
      </div>

      {status !== null && (
        <p role="status" aria-live="polite" className="status p-3 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error p-3 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}

      {caseView !== null && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
          <p className="font-semibold text-slate-900 text-xs">{caseView.summary}</p>
          <p className="text-[11px] text-slate-500 font-mono-nums" data-testid="case-code">
            Mã hồ sơ: {caseView.id}
          </p>
        </div>
      )}
    </section>
  );
}
