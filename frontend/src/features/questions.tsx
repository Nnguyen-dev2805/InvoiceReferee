import { useState } from "react";

import { answerIssue, errorMessage } from "../api";
import type { CaseView, IssueView } from "../types";

const KIND_LABELS: Record<string, string> = {
  FACT: "Dữ kiện thực tế",
  POLICY: "Chính sách chi tiêu",
  AUTHORITY: "Thẩm quyền phê duyệt",
};

export function formatVndInText(text: string): string {
  return text.replace(/\b\d+\b/g, (match) => {
    const num = parseInt(match, 10);
    if (num >= 1900 && num <= 2099 && match.length === 4) return match;
    if (num < 1000) return match;
    return num.toLocaleString("vi-VN") + " đ";
  });
}

export function formatIssueTarget(fieldOrRule: string): string {
  if (fieldOrRule.includes("arithmetic:return") || fieldOrRule === "return") {
    return "Khớp số tiền hoàn ứng";
  }
  if (fieldOrRule.includes("arithmetic:reimburse") || fieldOrRule === "reimburse") {
    return "Khớp số tiền chi thêm";
  }
  if (fieldOrRule.includes("arithmetic:tax") || fieldOrRule === "tax") {
    return "Khớp số tiền thuế";
  }
  if (fieldOrRule.includes("payer")) return "Người chi trả thực tế";
  if (fieldOrRule.includes("paid_basis")) return "Căn cứ thanh toán khoản chi";
  if (fieldOrRule.includes("claimant_binding")) return "Định danh người đề nghị";
  if (fieldOrRule.includes("buyer_binding")) return "Định danh người mua hàng";
  if (fieldOrRule.includes("missing_evidence")) return "Chứng từ bắt buộc";

  const match = fieldOrRule.match(/expense(?::expense)?:(\d+)/);
  if (match) {
    const expenseNum = match[1];
    if (fieldOrRule.includes("paid_basis")) return `Khoản chi #${expenseNum} (Căn cứ thanh toán)`;
    if (fieldOrRule.includes("payer")) return `Khoản chi #${expenseNum} (Người trả)`;
    return `Khoản chi #${expenseNum}`;
  }
  if (fieldOrRule === "budget:B") return "Ngân sách hoạt động (B)";
  if (fieldOrRule === "coverage") return "Lịch sử đối chiếu ứng/hoàn";

  const rawLast = fieldOrRule.split(":").pop() ?? fieldOrRule;
  if (rawLast === "return") return "Khoản hoàn ứng";
  if (rawLast === "reimburse") return "Khoản chi thêm";
  if (rawLast === "advance") return "Khoản tạm ứng";
  return `#${rawLast}`;
}

function roleMatchesOwner(role: string, owner: string, kind: string): boolean {
  if (role === "employee") {
    return owner === "employee" || owner.startsWith("employee:") || owner.startsWith("employee-");
  }
  if (role === "approver") {
    return owner === "approver" || kind === "POLICY" || kind === "AUTHORITY";
  }
  if (role === "accountant") {
    return owner === "accountant";
  }
  return owner === role;
}

function formatOwner(owner: string): string {
  if (owner === "org-data") return "Dữ liệu tổ chức";
  if (owner === "accountant") return "Kế toán";
  if (owner === "approver") return "Người phê duyệt";
  if (owner === "employee" || owner.startsWith("employee")) return "Nhân viên đề nghị";
  return owner;
}

/** One answerable question card: known basis, the exact answer required, owner. */
export function QuestionCard({
  issue,
  caseView,
  onCase,
}: {
  issue: IssueView;
  caseView: CaseView;
  onCase: (view: CaseView) => void;
}) {
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const result = await answerIssue(
        caseView.id,
        {
          issue_id: issue.id,
          basis_id: `basis:${issue.id}`,
          answer_kind: issue.kind,
          value,
          reason: reason || "Giải trình bổ sung cho hồ sơ",
        },
        caseView.version,
      );
      onCase(result.case_view);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      className="p-5 bg-white border border-slate-200 border-l-4 border-l-amber-500 rounded-xl space-y-4 text-xs shadow-xs hover:border-slate-300 transition-all"
      data-testid={`question-${issue.kind}`}
    >
      {/* Target & Status bar */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-slate-800 bg-slate-100 px-2.5 py-1 rounded text-xs border border-slate-200">
            {formatIssueTarget(issue.field_or_rule)}
          </span>
          <span className="text-[11px] font-medium text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
            {KIND_LABELS[issue.kind] ?? issue.kind}
          </span>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-900 border border-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          <span>Chờ giải trình</span>
        </span>
      </div>

      {/* Question & Known Basis */}
      <div className="space-y-2">
        <h4 className="font-semibold text-slate-900 text-sm leading-relaxed">
          {formatVndInText(issue.question)}
        </h4>
        {issue.basis && (
          <div className="flex items-start gap-2.5 bg-slate-50 p-3 rounded-lg border border-slate-200/80 text-xs text-slate-700">
            <svg className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="space-y-0.5 min-w-0">
              <span className="text-[11px] font-medium text-slate-500 block">Căn cứ ghi nhận:</span>
              <p className="font-medium text-slate-800 leading-relaxed">{formatVndInText(issue.basis)}</p>
            </div>
          </div>
        )}
      </div>

      {/* Input Form */}
      <div className="space-y-3 pt-1">
        <div>
          <label htmlFor={`answer-${issue.id}`} className="text-slate-800 block text-xs font-semibold mb-1.5">
            Nội dung giải trình / xác nhận:
          </label>
          <textarea
            id={`answer-${issue.id}`}
            rows={2}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded-lg text-xs p-2.5 text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 shadow-2xs resize-y transition-colors"
          />
        </div>
        <div>
          <label htmlFor={`reason-${issue.id}`} className="text-slate-600 block text-[11px] font-medium mb-1.5">
            Căn cứ / Ghi chú đính kèm (tùy chọn):
          </label>
          <input
            id={`reason-${issue.id}`}
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded-lg text-xs px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900/10 focus:border-slate-800 shadow-2xs transition-colors"
          />
        </div>
      </div>

      {/* Submit Row */}
      <div className="pt-2 flex items-center justify-between border-t border-slate-100">
        <div className="text-[11px] text-slate-500">
          {value.trim() === "" ? (
            <span className="text-slate-400">Vui lòng nhập nội dung để gửi giải trình</span>
          ) : (
            <span className="text-emerald-700 font-medium flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Sẵn sàng gửi
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || value.trim() === ""}
          className="inline-flex items-center gap-1.5 font-medium text-xs px-4 py-2 rounded-lg transition-all duration-150 disabled:opacity-50 disabled:bg-slate-100 disabled:text-slate-400 disabled:border disabled:border-slate-200 disabled:cursor-not-allowed bg-slate-900 hover:bg-slate-800 text-white shadow-2xs cursor-pointer active:scale-[0.98]"
        >
          {busy ? (
            <>
              <span className="inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>Đang gửi…</span>
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
              <span>Gửi giải trình</span>
            </>
          )}
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}
    </li>
  );
}

export function Questions({
  caseView,
  onCase,
  currentRole = "employee",
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
  currentRole?: string;
}) {
  if (caseView === null || caseView.issues.length === 0) return null;

  const myIssues = caseView.issues.filter((issue) =>
    roleMatchesOwner(currentRole, issue.owner, issue.kind),
  );
  const otherIssues = caseView.issues.filter((issue) => !myIssues.includes(issue));

  return (
    <section aria-labelledby="questions-title" className="space-y-4 select-none text-xs">
      {/* 1. Actionable Issues for Current Role */}
      {myIssues.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <h2 id="questions-title" className="text-xs font-semibold text-slate-900">
              Vấn đề cần bạn giải trình ({myIssues.length})
            </h2>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-900 border border-amber-200">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              <span>Cần xử lý</span>
            </span>
          </div>

          <ul className="questions space-y-3">
            {myIssues.map((issue) => (
              <QuestionCard key={issue.id} issue={issue} caseView={caseView} onCase={onCase} />
            ))}
          </ul>
        </div>
      )}

      {/* 2. Pending Issues Assigned to Other Roles (Quiet, non-intrusive) */}
      {otherIssues.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-100">
            <h3 className="text-xs font-semibold text-slate-700">
              Vấn đề đang chờ bộ phận khác ({otherIssues.length})
            </h3>
            <span className="text-[11px] text-slate-400 font-normal">
              Tự động cập nhật
            </span>
          </div>

          <div className="border border-slate-200 rounded-lg overflow-hidden bg-white divide-y divide-slate-100 shadow-2xs">
            <ul className="divide-y divide-slate-100 text-xs">
              {otherIssues.map((issue) => (
                <li
                  key={issue.id}
                  className="p-3.5 flex items-start justify-between gap-4 hover:bg-slate-50/50 transition-colors"
                >
                  <div className="space-y-1.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[11px] font-semibold text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                        {formatIssueTarget(issue.field_or_rule)}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        Phụ trách: <strong className="font-semibold text-slate-700">{formatOwner(issue.owner)}</strong>
                      </span>
                    </div>
                    <p className="text-xs text-slate-900 font-medium leading-relaxed">
                      {formatVndInText(issue.question)}
                    </p>
                    <p className="text-[11px] text-slate-500 leading-normal">
                      Căn cứ: {formatVndInText(issue.basis)}
                    </p>
                  </div>
                  <div className="text-right shrink-0 pt-0.5">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                      Chờ xử lý
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
