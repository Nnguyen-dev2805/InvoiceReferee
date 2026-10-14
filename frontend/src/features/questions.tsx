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

export function formatQuestionTitle(question: string, hasBasis: boolean): string {
  if (hasBasis) {
    const colonIndex = question.indexOf(":");
    if (colonIndex > 0) {
      const prefix = question.slice(0, colonIndex).trim();
      if (prefix.length >= 8) {
        return prefix.replace("Xác nhận/sửa", "Xác nhận / sửa");
      }
    }
  }
  return formatVndInText(question);
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

/** One answerable question panel: known basis, the exact answer required, owner. */
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
    <div
      className="space-y-3.5 text-xs"
      data-testid={`question-${issue.kind}`}
    >
      {/* Question */}
      <h4 className="font-semibold text-slate-900 text-sm leading-snug">
        {formatQuestionTitle(issue.question, Boolean(issue.basis))}
      </h4>

      {/* Basis (clean subtle quote line, no nested box) */}
      {issue.basis && (
        <div className="pl-3 border-l-2 border-slate-300 py-0.5 text-xs">
          <span className="text-[11px] text-slate-400 font-medium block">Căn cứ ghi nhận:</span>
          <p className="text-slate-600 leading-relaxed font-medium">{formatVndInText(issue.basis)}</p>
        </div>
      )}

      {/* Input Form */}
      <div className="space-y-3 pt-1">
        <div>
          <label htmlFor={`answer-${issue.id}`} className="text-slate-700 block text-xs font-medium mb-1.5">
            Nội dung giải trình / xác nhận:
          </label>
          <textarea
            id={`answer-${issue.id}`}
            rows={3}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className="w-full bg-white border border-slate-300 rounded text-xs p-2.5 text-slate-900 focus:outline-none focus:border-slate-800 resize-y transition-colors"
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
            className="w-full bg-white border border-slate-300 rounded text-xs px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800 transition-colors"
          />
        </div>
      </div>

      {/* Submit Action */}
      <div className="pt-2 flex items-center justify-end">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || value.trim() === ""}
          className="font-medium text-xs px-4 py-1.5 rounded transition-colors disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed bg-slate-900 hover:bg-slate-800 text-white cursor-pointer"
        >
          {busy ? "Đang gửi…" : "Gửi giải trình"}
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
          {error}
        </p>
      )}
    </div>
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
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);

  if (caseView === null || caseView.issues.length === 0) return null;

  const myIssues = caseView.issues.filter((issue) =>
    roleMatchesOwner(currentRole, issue.owner, issue.kind),
  );
  const otherIssues = caseView.issues.filter((issue) => !myIssues.includes(issue));

  const currentActiveId =
    myIssues.find((i) => i.id === activeIssueId)?.id ?? myIssues[0]?.id ?? null;

  return (
    <section aria-labelledby="questions-title" className="space-y-5 select-none text-xs">
      {/* 1. Actionable Issues for Current Role - Flat Open Section */}
      {myIssues.length > 0 && (
        <div className="space-y-3">
          {/* Section Header */}
          <div className="flex items-center justify-between">
            <h2 id="questions-title" className="text-xs font-semibold text-slate-900">
              Vấn đề cần bạn giải trình ({myIssues.length})
            </h2>
          </div>

          {/* Minimalist Underline Tabs */}
          {myIssues.length > 1 && (
            <div className="flex border-b border-slate-200 gap-6 overflow-x-auto" role="tablist">
              {myIssues.map((issue) => {
                const isActive = issue.id === currentActiveId;
                const targetName = formatIssueTarget(issue.field_or_rule);
                return (
                  <button
                    key={issue.id}
                    role="tab"
                    aria-selected={isActive}
                    type="button"
                    onClick={() => setActiveIssueId(issue.id)}
                    className={`py-2 text-xs transition-colors cursor-pointer border-b-2 -mb-px flex items-center gap-2 ${
                      isActive
                        ? "border-slate-900 text-slate-900 font-semibold"
                        : "border-transparent text-slate-500 hover:text-slate-800 font-medium"
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        isActive ? "bg-amber-500" : "bg-slate-300"
                      }`}
                    />
                    <span>{targetName}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Panel Content - Flat, without nested card frame */}
          <div className="pt-1">
            {myIssues.map((issue) => (
              <div
                key={issue.id}
                className={issue.id === currentActiveId ? "block" : "hidden"}
              >
                <QuestionCard
                  issue={issue}
                  caseView={caseView}
                  onCase={onCase}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. Pending Issues Assigned to Other Roles (Flat Reference List) */}
      {otherIssues.length > 0 && (
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-200">
            <h3 className="text-xs font-semibold text-slate-700">
              Vấn đề đang chờ bộ phận khác ({otherIssues.length})
            </h3>
            <span className="text-[11px] text-slate-400 font-normal">
              Tự động cập nhật
            </span>
          </div>

          <ul className="divide-y divide-slate-100 text-xs border-b border-slate-200">
            {otherIssues.map((issue) => (
              <li
                key={issue.id}
                className="py-3 px-1 flex items-start justify-between gap-4 hover:bg-slate-50/50 transition-colors"
              >
                <div className="space-y-1.5 min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-semibold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
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
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                    Chờ xử lý
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
