import { useState } from "react";

import { answerIssue, errorMessage } from "../api";
import type { CaseView, IssueView } from "../types";

const KIND_LABELS: Record<string, string> = {
  FACT: "Dữ kiện thực tế",
  POLICY: "Chính sách chi tiêu",
  AUTHORITY: "Thẩm quyền phê duyệt",
};

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
      className="p-4 bg-white border border-slate-200 border-l-4 border-l-amber-500 rounded-lg space-y-3 text-xs shadow-2xs transition-colors"
      data-testid={`question-${issue.kind}`}
    >
      {/* Target & Status bar */}
      <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-800 bg-slate-100 px-2 py-0.5 rounded text-[11px] border border-slate-200">
            {formatIssueTarget(issue.field_or_rule)}
          </span>
          <span className="text-[11px] font-medium text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
            {KIND_LABELS[issue.kind] ?? issue.kind}
          </span>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-900 border border-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          <span>Cần bạn giải trình</span>
        </span>
      </div>

      {/* Question & Known Basis */}
      <div className="space-y-1.5">
        <h4 className="font-semibold text-slate-900 text-xs leading-relaxed">
          {issue.question}
        </h4>
        <div className="text-[11px] text-slate-600 bg-slate-50 p-2.5 rounded border border-slate-200/80">
          <span>Căn cứ hiện tại: <strong className="text-slate-800">{issue.basis}</strong></span>
        </div>
      </div>

      {/* Input Form */}
      <div className="space-y-2 pt-1">
        <div>
          <label htmlFor={`answer-${issue.id}`} className="text-slate-800 block font-semibold mb-1">
            Nội dung giải trình / xác nhận:
            <input
              id={`answer-${issue.id}`}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="Nhập nội dung giải trình hoặc xác nhận thực tế..."
              className="w-full mt-1 bg-white border border-slate-300 rounded text-xs px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs"
            />
          </label>
        </div>
        <div>
          <label htmlFor={`reason-${issue.id}`} className="text-slate-600 block text-[11px] font-medium mb-1">
            Căn cứ / Ghi chú đính kèm (tùy chọn):
            <input
              id={`reason-${issue.id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Ví dụ: Theo phiếu chuyển tiền ngân hàng, email phê duyệt..."
              className="w-full mt-1 bg-white border border-slate-300 rounded text-xs px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 shadow-2xs"
            />
          </label>
        </div>
      </div>

      {/* Submit Button */}
      <div className="pt-1">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || value.trim() === ""}
          className="bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs px-3.5 py-1.5 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
        >
          {busy ? "Đang gửi…" : "Gửi giải trình"}
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
                      {issue.question}
                    </p>
                    <p className="text-[11px] text-slate-500 leading-normal">
                      Căn cứ: {issue.basis}
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
