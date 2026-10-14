import { formatVnd } from "../format";
import type { CaseView } from "../types";

const STATE_LABELS: Record<string, string> = {
  DRAFT: "Bản nháp",
  PROCESSING: "Đang xử lý",
  EVIDENCE_READY: "Đã đọc chứng từ",
  WAITING: "Chờ xử lý ngoại lệ",
  TECHNICAL_ERROR: "Lỗi kỹ thuật",
  READY_TO_EXECUTE: "Sẵn sàng phê duyệt",
  SETTLED: "Đã quyết toán",
  STOPPED: "Đã tạm dừng",
};

const BASIS_LABELS: Record<string, string> = {
  INDEPENDENT_PAYMENT: "Chứng từ thanh toán độc lập",
  FINANCIAL_CONFIRMATION: "Đối soát tài chính xác nhận",
  EMPLOYEE_PAID_INVOICE: "Hóa đơn thanh toán cá nhân",
  EMPLOYEE_DECLARATION_Q32: "Lời xác nhận của nhân viên",
  UNSPECIFIED_LEGACY: "Chưa xác định căn cứ",
};

const ISSUE_LABELS: Record<string, string> = {
  FACT: "Dữ kiện thực tế",
  POLICY: "Chính sách chi tiêu",
  AUTHORITY: "Thẩm quyền phê duyệt",
};

export const MONEY_LABELS: Record<string, string> = {
  T: "Tổng chi công việc",
  E: "Chi phí đủ điều kiện",
  C: "Công ty trả trực tiếp",
  A: "Ứng thực nhận",
  P: "Đã hoàn",
  R: "Đã thu hồi",
  unpaid: "Chưa thanh toán",
  S: "Chênh lệch (S)",
};

const UNKNOWN_LABEL = "—";

export function formatMoney(value: number | null): string {
  if (value === null) return UNKNOWN_LABEL;
  return new Intl.NumberFormat("vi-VN").format(value) + " ₫";
}

function formatSummary(summary: string): string {
  if (!summary) return "Hồ sơ quyết toán công tác";
  const parts = summary.split(" · ");
  if (parts.length >= 2 && parts[0].trim().length <= 2) {
    return `Hoạt động công tác (${parts[0].trim()}) · ${parts.slice(1).join(" · ")}`;
  }
  return summary;
}

/** One money line with exact testid for test backward compatibility */
export function MoneyLine({
  label,
  fact,
  highlight = false,
}: {
  label: string;
  fact: { value: number | null; state: string };
  highlight?: boolean;
  subtext?: string;
}) {
  const known = fact.state === "KNOWN" && fact.value !== null;
  return (
    <li
      data-testid={`money-${label}`}
      className={`flex items-center justify-between px-1 py-2 text-xs transition-colors ${
        highlight
          ? "bg-slate-50/70 font-semibold text-slate-950"
          : "hover:bg-slate-50/40 text-slate-700"
      }`}
    >
      <span className={highlight ? "font-semibold text-slate-900 text-xs" : "text-slate-600 font-medium"}>
        {label}:
      </span>
      <div className="text-right shrink-0">
        <strong
          className={`text-xs ${
            known
              ? highlight
                ? "text-slate-950 font-bold font-mono-nums tabular-nums"
                : "text-slate-900 font-medium font-mono-nums tabular-nums"
              : "text-slate-400 font-normal select-none"
          }`}
          title={known ? undefined : "Chưa xác minh"}
        >
          {known ? formatMoney(fact.value) : UNKNOWN_LABEL}
        </strong>
      </div>
    </li>
  );
}

export function formatIssueTarget(fieldOrRule: string): string {
  const match = fieldOrRule.match(/expense(?::expense)?:(\d+)/);
  if (match) {
    const expenseNum = match[1];
    if (fieldOrRule.includes("paid_basis")) return `Khoản chi #${expenseNum} (Căn cứ thanh toán)`;
    if (fieldOrRule.includes("payer")) return `Khoản chi #${expenseNum} (Người trả)`;
    return `Khoản chi #${expenseNum}`;
  }
  if (fieldOrRule.includes("paid_basis")) return "Căn cứ thanh toán khoản chi";
  if (fieldOrRule.includes("payer")) return "Người chi trả thực tế";
  if (fieldOrRule === "budget:B") return "Ngân sách hoạt động (B)";
  if (fieldOrRule === "coverage") return "Lịch sử đối chiếu ứng/hoàn";
  return `#${fieldOrRule.split(":").pop()}`;
}

export function Dossier({
  caseView,
  hideIssues = false,
}: {
  caseView: CaseView | null;
  hideIssues?: boolean;
}) {
  if (caseView === null) {
    return (
      <section
        aria-labelledby="dossier-title"
        className="py-12 text-xs text-center space-y-2 select-none"
      >
        <h2 id="dossier-title" className="text-sm font-semibold text-slate-700">
          Hồ sơ quyết toán
        </h2>
        <p className="text-xs text-slate-400">
          Chưa có hồ sơ nào được mở. Hãy chọn hoạt động và tạo hồ sơ để đối soát.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="dossier-title"
      className="space-y-6 select-none text-xs"
    >
      {/* Header Info */}
      <div className="pb-4 border-b border-slate-100 space-y-1.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h2 id="dossier-title" className="text-base font-bold text-slate-900 tracking-tight">
            Hồ sơ đối soát
          </h2>
          <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-600 font-mono-nums border border-slate-200">
            v{caseView.version}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border ${
              caseView.state === "READY_TO_EXECUTE"
                ? "bg-emerald-50 text-emerald-900 border-emerald-200/90"
                : caseView.state === "WAITING"
                ? "bg-amber-50 text-amber-900 border-amber-200/90"
                : caseView.state === "SETTLED"
                ? "bg-blue-50 text-blue-900 border-blue-200/90"
                : caseView.state === "STOPPED"
                ? "bg-rose-50 text-rose-900 border-rose-200/90"
                : "bg-slate-100 text-slate-700 border-slate-200"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                caseView.state === "READY_TO_EXECUTE"
                  ? "bg-emerald-500"
                  : caseView.state === "WAITING"
                  ? "bg-amber-500"
                  : caseView.state === "SETTLED"
                  ? "bg-blue-500"
                  : caseView.state === "STOPPED"
                  ? "bg-rose-500"
                  : "bg-slate-400"
              }`}
            />
            <span>{STATE_LABELS[caseView.state] ?? caseView.state}</span>
          </span>
        </div>
        <p className="text-xs text-slate-500 font-normal">
          {formatSummary(caseView.summary)}
        </p>
      </div>

      {/* Structured Reconciliation Ledger Table - Flat & Clean */}
      <div className="space-y-1.5">
        <h3 className="text-xs font-semibold text-slate-900">
          Chi tiết dòng tiền đối soát
        </h3>

        <div className="border-t border-b border-slate-200">
          <ul className="money divide-y divide-slate-100">
            {Object.entries(caseView.actual_money)
              .filter(([key]) => key in MONEY_LABELS)
              .map(([key, fact]) => (
                <MoneyLine
                  key={key}
                  label={MONEY_LABELS[key]}
                  fact={fact}
                  highlight={key === "T" || key === "S" || key === "unpaid"}
                />
              ))}
          </ul>
        </div>
      </div>

      {/* Payment Basis (Căn cứ pháp lý & nhân viên xác nhận) */}
      {caseView.payment_basis.length > 0 && (
        <div className="space-y-1.5">
          <h3 className="text-xs font-semibold text-slate-900">
            Căn cứ xác nhận chi trả
          </h3>
          <div
            className="border-t border-b border-slate-200 divide-y divide-slate-100"
            data-testid="payment-basis"
          >
            {caseView.payment_basis.map((basis) => (
              <div
                key={basis.expense_id}
                data-testid={`basis-${basis.expense_id}`}
                className="px-1 py-2.5 text-xs flex items-center justify-between hover:bg-slate-50/50 transition-colors"
              >
                <div className="space-y-0.5">
                  <span className="font-semibold text-slate-900 block">
                    {BASIS_LABELS[basis.kind] ?? basis.kind}
                  </span>
                  {basis.actor && (
                    <span className="text-[11px] text-slate-500 block">
                      Người chịu trách nhiệm: {basis.actor}
                    </span>
                  )}
                </div>
                {basis.rule_id && (
                  <span className="text-[11px] font-mono-nums font-medium text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                    Điều khoản: {basis.rule_id}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Issues / Exceptions to resolve (Hidden when interactive Questions workspace is present) */}
      {!hideIssues && caseView.issues.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-slate-900">
              Vấn đề cần xử lý ({caseView.issues.length})
            </h3>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-50 text-amber-900 border border-amber-200">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span>Chờ giải quyết</span>
            </span>
          </div>

          <div className="border-t border-b border-slate-200 divide-y divide-slate-100">
            {caseView.issues.map((issue) => {
              const kindLabel = ISSUE_LABELS[issue.kind] ?? issue.kind;
              return (
                <div
                  key={issue.id}
                  className="px-1 py-3 hover:bg-slate-50/50 transition-colors text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-800 border border-slate-200">
                        {kindLabel}
                      </span>
                      <span className="text-[11px] text-slate-600 font-medium">
                        Người xử lý: {issue.owner}
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-600 font-medium">
                      {formatIssueTarget(issue.field_or_rule)}
                    </span>
                  </div>
                  <p className="text-slate-900 font-medium text-xs leading-relaxed">
                    {issue.question}
                  </p>
                  <div className="text-[11px] text-slate-500 pt-0.5">
                    <span>Căn cứ: {issue.basis}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
