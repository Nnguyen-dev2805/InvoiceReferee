import { useState } from "react";

import {
  attachSources,
  readDigitalDraft,
  saveDigitalDeclaration,
  type DigitalDeclarationInput,
  type SettlementDraftResponse,
} from "../api";
import { api } from "../api";
import { formatVnd } from "../format";

export type SettlementKind = "ADVANCE_SETTLEMENT" | "EMPLOYEE_REIMBURSEMENT";
export type EntryWay = "PAPER_SCAN" | "DIGITAL_FORM";

export interface DigitalLineDraft {
  clientId: string;
  description: string;
  category: string;
  expense_date: string;
  amount: string;
  evidence_status: "ORIGINAL" | "ALTERNATIVE" | "NO_EVIDENCE";
  alternative_type: string;
  exception_reason: string;
  note: string;
  files: File[];
  attachedIds: string[];
}

export function newDigitalLine(): DigitalLineDraft {
  return {
    clientId: `L${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`,
    description: "",
    category: "",
    expense_date: "",
    amount: "",
    evidence_status: "ORIGINAL",
    alternative_type: "PAYMENT_PROOF",
    exception_reason: "",
    note: "",
    files: [],
    attachedIds: [],
  };
}

const EVIDENCE_STATUS_LABEL: Record<DigitalLineDraft["evidence_status"], string> = {
  ORIGINAL: "Có chứng từ gốc",
  ALTERNATIVE: "Có bằng chứng thay thế",
  NO_EVIDENCE: "Không có chứng từ",
};

export function DigitalForm({
  settlementKind,
  purpose,
  setPurpose,
  noAdvanceReason,
  setNoAdvanceReason,
  lines,
  setLines,
  onRead,
  busy,
}: {
  settlementKind: SettlementKind;
  purpose: string;
  setPurpose: (v: string) => void;
  noAdvanceReason: string;
  setNoAdvanceReason: (v: string) => void;
  lines: DigitalLineDraft[];
  setLines: (v: DigitalLineDraft[]) => void;
  onRead: () => void;
  busy: boolean;
}) {
  function updateLine(clientId: string, patch: Partial<DigitalLineDraft>) {
    setLines(lines.map((l) => (l.clientId === clientId ? { ...l, ...patch } : l)));
  }

  const total = lines.reduce((sum, l) => sum + (parseInt(l.amount, 10) || 0), 0);

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <label htmlFor="digital-purpose" className="text-xs font-semibold text-slate-900">
          Mục đích công việc
        </label>
        <textarea
          id="digital-purpose"
          rows={2}
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
          placeholder="Sửa chữa máy in văn phòng…"
          className="w-full text-xs border border-slate-300 rounded px-3 py-2 focus:outline-none focus:border-slate-900"
        />
      </div>

      {settlementKind === "EMPLOYEE_REIMBURSEMENT" && (
        <div className="space-y-1.5 rounded border border-slate-200 bg-slate-50 px-3 py-2.5">
          <p className="text-xs font-semibold text-slate-900">
            Khai không nhận tạm ứng
          </p>
          <p className="text-[11px] text-slate-500">
            Khai báo này không tự biến sổ thành 0; hệ thống vẫn đối chiếu với
            khoản ứng đã ghi nhận trong phạm vi.
          </p>
          <input
            aria-label="Lý do không nhận tạm ứng"
            value={noAdvanceReason}
            onChange={(e) => setNoAdvanceReason(e.target.value)}
            placeholder="Tự chi, không nhận tạm ứng…"
            className="w-full text-xs border border-slate-300 rounded px-3 py-2 focus:outline-none focus:border-slate-900 bg-white"
          />
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-900">
            Các khoản chi ({lines.length})
          </span>
          <button
            type="button"
            onClick={() => setLines([...lines, newDigitalLine()])}
            className="text-xs font-medium text-slate-900 underline underline-offset-2 cursor-pointer"
          >
            + Thêm khoản
          </button>
        </div>
        {lines.map((line, idx) => (
          <div key={line.clientId} className="rounded border border-slate-200 px-3 py-2.5 space-y-2 bg-white">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400">Khoản {idx + 1}</span>
              {lines.length > 1 && (
                <button
                  type="button"
                  onClick={() => setLines(lines.filter((l) => l.clientId !== line.clientId))}
                  className="text-[11px] text-slate-400 hover:text-rose-600 cursor-pointer"
                >
                  Xóa
                </button>
              )}
            </div>
            <input
              aria-label={`Nội dung khoản ${idx + 1}`}
              value={line.description}
              onChange={(e) => updateLine(line.clientId, { description: e.target.value })}
              placeholder="Nội dung khoản chi"
              className="w-full text-xs border border-slate-300 rounded px-3 py-2 focus:outline-none focus:border-slate-900"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                aria-label={`Số tiền khoản ${idx + 1}`}
                value={line.amount}
                inputMode="numeric"
                onChange={(e) => updateLine(line.clientId, { amount: e.target.value.replace(/[^\d]/g, "") })}
                placeholder="Số tiền VND"
                className="text-xs border border-slate-300 rounded px-3 py-2 focus:outline-none focus:border-slate-900 tabular-nums"
              />
              <input
                aria-label={`Ngày chi khoản ${idx + 1}`}
                type="date"
                value={line.expense_date}
                onChange={(e) => updateLine(line.clientId, { expense_date: e.target.value })}
                className="text-xs border border-slate-300 rounded px-2 py-2 focus:outline-none focus:border-slate-900"
              />
              <select
                aria-label={`Tình trạng chứng từ khoản ${idx + 1}`}
                value={line.evidence_status}
                onChange={(e) =>
                  updateLine(line.clientId, {
                    evidence_status: e.target.value as DigitalLineDraft["evidence_status"],
                  })
                }
                className="text-xs border border-slate-300 rounded px-2 py-2 focus:outline-none focus:border-slate-900 bg-white"
              >
                {(Object.keys(EVIDENCE_STATUS_LABEL) as Array<DigitalLineDraft["evidence_status"]>).map((s) => (
                  <option key={s} value={s}>{EVIDENCE_STATUS_LABEL[s]}</option>
                ))}
              </select>
            </div>
            {line.evidence_status === "ALTERNATIVE" && (
              <div className="grid grid-cols-2 gap-2">
                <select
                  aria-label={`Loại bằng chứng thay thế khoản ${idx + 1}`}
                  value={line.alternative_type}
                  onChange={(e) => updateLine(line.clientId, { alternative_type: e.target.value })}
                  className="text-xs border border-slate-300 rounded px-2 py-2 bg-white"
                >
                  <option value="PAYMENT_PROOF">Chứng từ thanh toán</option>
                  <option value="RECEIPT_OR_COLLECTION_NOTE">Biên nhận/phiếu thu</option>
                  <option value="CONTRACT_OR_ACCEPTANCE">Hợp đồng/nghiệm thu</option>
                  <option value="SUPPLIER_CONFIRMATION">Xác nhận nhà cung cấp</option>
                  <option value="OTHER">Khác</option>
                </select>
                <input
                  aria-label={`Lý do thiếu chứng từ gốc khoản ${idx + 1}`}
                  value={line.exception_reason}
                  onChange={(e) => updateLine(line.clientId, { exception_reason: e.target.value })}
                  placeholder="Lý do thiếu hóa đơn gốc *"
                  className="text-xs border border-amber-300 rounded px-3 py-2 focus:outline-none focus:border-amber-600"
                />
              </div>
            )}
            {line.evidence_status === "NO_EVIDENCE" && (
              <input
                aria-label={`Lý do không có chứng từ khoản ${idx + 1}`}
                value={line.exception_reason}
                onChange={(e) => updateLine(line.clientId, { exception_reason: e.target.value })}
                placeholder="Lý do không có chứng từ *"
                className="w-full text-xs border border-amber-300 rounded px-3 py-2 focus:outline-none focus:border-amber-600"
              />
            )}
            <input
              aria-label={`Ghi chú khoản ${idx + 1}`}
              value={line.note}
              onChange={(e) => updateLine(line.clientId, { note: e.target.value })}
              placeholder="Ghi chú mô tả (tùy chọn, không thay lý do)"
              className="w-full text-xs border border-slate-200 rounded px-3 py-2 focus:outline-none focus:border-slate-900"
            />
            <label className="block">
              <span className="text-[11px] text-slate-500">
                Chứng từ của khoản này ({line.files.length} tệp)
              </span>
              <input
                aria-label={`Chứng từ khoản ${idx + 1}`}
                type="file"
                multiple
                accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                onChange={(e) =>
                  updateLine(line.clientId, {
                    files: [
                      ...line.files,
                      ...Array.from(e.target.files ?? []).filter(
                        (f) => !line.files.some((p) => p.name === f.name),
                      ),
                    ],
                  })
                }
                className="mt-1 block w-full text-[11px] text-slate-500 file:mr-2 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1 file:text-[11px] cursor-pointer"
              />
            </label>
            {line.files.length > 0 && (
              <ul className="text-[11px] text-slate-600 space-y-0.5">
                {line.files.map((f) => (
                  <li key={f.name} className="truncate">· {f.name}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-slate-200">
        <span className="text-xs text-slate-500">
          Tổng khai báo: <strong className="text-slate-900 tabular-nums">{formatVnd(total)}</strong>
        </span>
        <button
          type="button"
          onClick={() => void onRead()}
          disabled={busy}
          className="inline-flex items-center gap-1.5 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white font-medium text-xs px-4 py-2 rounded cursor-pointer"
        >
          <span>Đọc &amp; lập bản nháp</span>
          <span aria-hidden="true" className="font-mono">→</span>
        </button>
      </div>
    </div>
  );
}

export function toDigitalDeclarationInput(
  purpose: string,
  settlementKind: SettlementKind,
  noAdvanceReason: string,
  lines: DigitalLineDraft[],
): DigitalDeclarationInput {
  return {
    declared_purpose: purpose,
    settlement_type: settlementKind,
    digital_lines: lines.map((l, i) => ({
      item_id: `L${String(i + 1).padStart(2, "0")}`,
      description: l.description,
      category: l.category || null,
      expense_date: l.expense_date,
      amount: parseInt(l.amount, 10) || 0,
      evidence_status: l.evidence_status,
      alternative_type: l.evidence_status === "ALTERNATIVE" ? l.alternative_type : null,
      exception_reason: l.exception_reason || null,
      note: l.note || null,
      source_ids: [...l.attachedIds],
    })),
    no_advance_asserted: settlementKind === "EMPLOYEE_REIMBURSEMENT",
    no_advance_reason: settlementKind === "EMPLOYEE_REIMBURSEMENT" ? noAdvanceReason || null : null,
  };
}

export async function runDigitalRead(
  settlementKind: SettlementKind,
  purpose: string,
  noAdvanceReason: string,
  lines: DigitalLineDraft[],
  setLines: (v: DigitalLineDraft[]) => void,
): Promise<{ caseId: string; version: number; draft: SettlementDraftResponse }> {
  const activity = {
    mode: "new" as const,
    name: "Hồ sơ quyết toán chi phí",
    occurred_at: new Date().toISOString(),
    declared_purpose: purpose || "Quyết toán chi phí công việc",
  };
  const created = await api.createCase(activity);
  let currentCase = created.case_view;
  const withIds = [...lines];
  for (const line of withIds) {
    if (line.files.length === 0) continue;
    const attached = await attachSources(currentCase.id, line.files, currentCase.version, "evidence");
    currentCase = attached.case_view;
    // Map in the line's own file order (never the server's source order).
    const byName = new Map(currentCase.sources.map((s) => [s.filename, s.id]));
    line.attachedIds = line.files.map((f) => byName.get(f.name)).filter((id): id is string => Boolean(id));
  }
  setLines(withIds);
  const declaration = toDigitalDeclarationInput(purpose, settlementKind, noAdvanceReason, withIds);
  await saveDigitalDeclaration(currentCase.id, declaration);
  const draft = await readDigitalDraft(currentCase.id);
  return { caseId: currentCase.id, version: currentCase.version, draft };
}

export function draftValidationError(
  settlementKind: SettlementKind,
  purpose: string,
  noAdvanceReason: string,
  lines: DigitalLineDraft[],
): string | null {
  if (!purpose.trim()) return "Vui lòng nhập mục đích công việc.";
  if (lines.length === 0) return "Vui lòng thêm ít nhất một khoản chi.";
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!l.description.trim()) return `Khoản ${i + 1}: thiếu nội dung.`;
    if (!l.amount || parseInt(l.amount, 10) <= 0) return `Khoản ${i + 1}: số tiền VND phải > 0.`;
    if (!l.expense_date) return `Khoản ${i + 1}: thiếu ngày chi.`;
    if ((l.evidence_status === "ALTERNATIVE" || l.evidence_status === "NO_EVIDENCE") && !l.exception_reason.trim())
      return `Khoản ${i + 1}: cần lý do thiếu chứng từ gốc.`;
  }
  if (settlementKind === "EMPLOYEE_REIMBURSEMENT" && !noAdvanceReason.trim())
    return "Tự chi cần lý do không nhận tạm ứng.";
  return null;
}
