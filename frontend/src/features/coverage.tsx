import { useMemo, useState } from "react";

import { errorMessage, recordActual } from "../api";
import { formatVnd } from "../format";
import type { CaseView } from "../types";

const FLOW_KINDS = [
  ["ADVANCE_RECEIVED", "Ứng thực nhận"],
  ["REIMBURSEMENT_RECEIVED", "Công ty chi bổ sung"],
  ["EMPLOYEE_RETURN", "Nhân viên hoàn trả"],
  ["REVERSAL", "Giao dịch đảo"],
  ["OBSERVED_UNALLOCATED", "Khoản chưa phân bổ"],
] as const;

const KIND_LABELS: Record<string, string> = Object.fromEntries(FLOW_KINDS);

function reportedEmployeeReturns(caseView: CaseView): number[] {
  const documents = caseView.evidence_report?.documents ?? [];
  const amounts: number[] = [];
  for (const rawDocument of documents) {
    if (typeof rawDocument !== "object" || rawDocument === null) continue;
    const document = rawDocument as { document_type?: unknown; fields?: unknown };
    if (document.document_type !== "SETTLEMENT_FORM" || !Array.isArray(document.fields)) continue;
    for (const rawField of document.fields) {
      if (typeof rawField !== "object" || rawField === null) continue;
      const field = rawField as { field?: unknown; state?: unknown; value?: unknown };
      if (field.field !== "printed_return" || field.state !== "FOUND") continue;
      const digits = typeof field.value === "number"
        ? field.value
        : typeof field.value === "string"
          ? Number(field.value.replace(/[^0-9]/g, ""))
          : NaN;
      if (Number.isSafeInteger(digits) && digits > 0) amounts.push(digits);
    }
  }
  return amounts;
}

function eventStateLabel(event: { verification_state: string; allocation_state: string }) {
  if (event.verification_state !== "CONFIRMED") return "Chưa xác minh";
  if (event.allocation_state !== "ALLOCATED") return "Chưa gắn được giao dịch";
  return "Đã xác minh";
}

export function Coverage({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingDraft, setConfirmingDraft] = useState<string | null>(null);

  const history = caseView?.money_history ?? [];
  const returnClaims = caseView === null ? [] : reportedEmployeeReturns(caseView);
  const confirmedReturns = history
    .filter((event) => event.kind === "EMPLOYEE_RETURN" && event.verification_state === "CONFIRMED" && event.allocation_state === "ALLOCATED")
    .reduce((total, event) => total + event.amount, 0);
  const unaccountedReturnClaims = returnClaims.filter((amount) => amount > confirmedReturns);
  const unallocatedEventIds = useMemo(
    () => history
      .filter((event) => event.verification_state !== "CONFIRMED" || event.allocation_state !== "ALLOCATED")
      .map((event) => event.id),
    [history],
  );

  if (caseView === null) return null;

  async function confirmReturn(draft: NonNullable<CaseView["employee_return_drafts"]>[number]) {
    if (caseView === null || draft.amount === null || !draft.event_at || !draft.external_key || !draft.transaction_reference) return;
    setConfirmingDraft(draft.draft_id);
    setError(null);
    setNotice(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: draft.external_key,
        claimed_kind: "EMPLOYEE_RETURN",
        claimed_scope: draft.activity,
        payer: draft.employee,
        payee: "company:demo",
        amount: draft.amount,
        event_at: draft.event_at,
        completion_claim: "Kế toán xác nhận đã nhận tiền theo chứng từ hoàn trả.",
        reason: "Đối chiếu chứng từ hoàn trả với đúng lệnh thu và xác nhận giao dịch đã hoàn tất.",
        instrument_method: draft.instrument_method,
        instrument_status: draft.instrument_status,
        instrument_reference: draft.transaction_reference,
        instruction_id: draft.instruction_id,
        money_movement_draft_id: draft.draft_id,
        refs: draft.refs,
      }, caseView.version);
      onCase(result.case_view);
      setNotice("Đã xác nhận khoản hoàn vào sổ đúng một lần.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setConfirmingDraft(null);
    }
  }

  return (
    <section id="history-coverage" aria-labelledby="coverage-title" className="space-y-3 border-t border-slate-200 pt-4 text-xs">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="coverage-title" className="font-semibold text-slate-900">
            Lịch sử tiền của hồ sơ
          </h2>
          <p className="mt-1 text-slate-500">
            Kiểm tra các khoản đã ghi nhận. Tải chứng từ không tự xác nhận công ty đã nhận hoặc chi tiền.
          </p>
        </div>
        {caseView.coverage_record && (
          <div className="text-right">
            <span className={`rounded border px-2 py-1 text-[11px] font-medium ${
              caseView.coverage_current
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-amber-200 bg-amber-50 text-amber-800"
            }`}>
              {caseView.coverage_current ? "Đã đối chiếu" : "Cần đối chiếu lại"}
            </span>
            <p className="mt-1 text-[10px] text-slate-500">
              {["MANAGED_HISTORY", "DOSSIER_RECORDS"].includes(caseView.coverage_record.source) ? "Hệ thống theo dõi đến" : "Mốc kiểm tra"}: {new Date(caseView.coverage_record.as_of).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}
            </p>
          </div>
        )}
      </div>

      <div className="rounded-md border border-slate-200 bg-white p-3">
        <h3 className="font-medium text-slate-800">Giao dịch đã ghi nhận trong hồ sơ</h3>
        {history.length === 0 ? (
          <p className="mt-1 text-slate-500">Chưa có giao dịch nào được ghi nhận.</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100">
            {history.map((event) => (
              <li key={`${event.id}:${event.external_key}`} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="font-medium text-slate-800">{KIND_LABELS[event.kind] ?? "Dòng tiền khác"}</p>
                  <p className="truncate text-[11px] text-slate-500">
                    {event.payer} → {event.payee} · {new Date(event.event_at).toLocaleDateString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "2-digit", year: "numeric" })}
                  </p>
                  {event.verification_state !== "CONFIRMED" || event.allocation_state !== "ALLOCATED" ? (
                    <p className="mt-0.5 text-[11px] text-amber-800">
                      {eventStateLabel(event)} — cần kiểm tra chứng từ này.
                    </p>
                  ) : null}
                </div>
                <strong className="shrink-0 font-mono-nums tabular-nums text-slate-900">
                  {formatVnd(event.amount)}
                </strong>
              </li>
            ))}
          </ul>
        )}
        {unallocatedEventIds.length > 0 && (
          <p className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-amber-900">
            Chứng từ đang chờ xử lý hoặc chưa gắn được giao dịch. Hệ thống vẫn hiện khoản tiền này và không coi nó là 0.
          </p>
        )}
      </div>

      {(caseView.employee_return_drafts ?? []).filter((draft) => draft.status !== "CONFIRMED").map((draft) => {
        const canConfirm = ["MATCHED", "OVERPAY"].includes(draft.match_status)
          && draft.amount !== null && draft.event_at !== null && draft.external_key !== null
          && draft.transaction_reference !== null && draft.instrument_status === "COMPLETED";
        return <article key={draft.draft_id} className="rounded-md border border-amber-200 bg-amber-50 p-3" data-testid="accountant-return-review">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold text-amber-950">Chờ xác nhận tiền hoàn</h3>
            <strong className="font-mono tabular-nums">{draft.amount === null ? "Chưa đọc được số tiền" : formatVnd(draft.amount)}</strong>
          </div>
          <p className="mt-1 text-amber-900">{draft.source_filename} · lệnh thu {draft.instruction_id} · {draft.match_status}</p>
          <p className="mt-1 text-[11px] text-slate-600">{draft.payer_name ?? "Chưa rõ bên chuyển"} → {draft.payee_name ?? "Chưa rõ bên nhận"} · {draft.transaction_reference ?? "Chưa có mã giao dịch"}</p>
          {draft.signals.map((signal, index) => <p key={`${signal.field}-${index}`} className="mt-1 text-[11px] text-amber-900">{signal.summary}</p>)}
          <div className="mt-2 flex justify-end"><button type="button" onClick={() => void confirmReturn(draft)} disabled={!canConfirm || confirmingDraft !== null} className="rounded bg-slate-950 px-3 py-2 font-semibold text-white disabled:opacity-40">{confirmingDraft === draft.draft_id ? "Đang xác nhận…" : "Kế toán xác nhận đã nhận"}</button></div>
        </article>;
      })}

      {unaccountedReturnClaims.map((amount, index) => (
        <p key={`${amount}:${index}`} className="rounded-md border border-amber-300 bg-amber-50 p-3 text-amber-950">
          Giấy quyết toán khai nhân viên hoàn lại {formatVnd(amount)}. Đây là số khai trên giấy, chưa phải giao dịch công ty đã nhận; hiện chưa có giao dịch hoàn đã xác minh trong hồ sơ. Chỉ ghi khoản hoàn khi có chứng từ tiền thực nhận và kế toán xác nhận. Chưa có căn cứ tiền vào thì chưa ghi khoản hoàn là đã thu.
        </p>
      ))}

      {notice && <p role="status" className="rounded border border-emerald-200 bg-emerald-50 p-2.5 text-emerald-800">{notice}</p>}
      {error && <p role="alert" className="rounded border border-rose-200 bg-rose-50 p-2.5 text-rose-800">{error}</p>}
    </section>
  );
}
