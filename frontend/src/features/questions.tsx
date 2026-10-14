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
      className="p-5 bg-white border border-slate-200 rounded-xl space-y-3.5 text-xs shadow-xs hover:border-slate-300 transition-colors"
      data-testid={`question-${issue.kind}`}
    >
      {/* Target & Status bar */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <span className="font-mono-nums font-semibold text-slate-800 bg-slate-100 px-2.5 py-0.5 rounded text-[11px] border border-slate-200">
            {formatIssueTarget(issue.field_or_rule)}
          </span>
          <span className="text-[11px] font-medium text-slate-600 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
            {KIND_LABELS[issue.kind] ?? issue.kind}
          </span>
        </div>
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-900 border border-amber-200 shadow-2xs">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          <span>Cần bạn giải trình</span>
        </span>
      </div>

      {/* Question & Known Basis */}
      <div className="space-y-1.5">
        <h4 className="font-bold text-slate-900 text-xs leading-relaxed">
          {issue.question}
        </h4>
        <div className="text-[11px] text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200/80">
          <span>Căn cứ hiện tại: <strong className="text-slate-800">{issue.basis}</strong></span>
        </div>
      </div>

      {/* Input Form */}
      <div className="space-y-2.5 pt-1">
        <div>
          <label htmlFor={`answer-${issue.id}`} className="text-slate-800 block font-semibold mb-1">
            Nội dung giải trình / xác nhận:
            <input
              id={`answer-${issue.id}`}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="Nhập nội dung giải trình hoặc xác nhận thực tế..."
              className="w-full mt-1 bg-white border border-slate-300 rounded-lg text-xs px-3.5 py-2 text-slate-900 focus:outline-none focus:border-slate-800 focus:ring-1 focus:ring-slate-800 shadow-2xs"
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
              className="w-full mt-1 bg-white border border-slate-300 rounded-lg text-xs px-3.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800 focus:ring-1 focus:ring-slate-800 shadow-2xs"
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
          className="bg-slate-950 hover:bg-slate-800 text-white font-semibold text-xs px-4 py-2 rounded-lg shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
        >
          {busy ? "Đang gửi…" : "Gửi giải trình"}
        </button>
      </div>

      {error !== null && (
        <p role="alert" className="error p-2.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs">
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
    <section aria-labelledby="questions-title" className="bg-white border border-slate-200 rounded-xl p-5 text-xs shadow-xs space-y-4 select-none">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h2 id="questions-title" className="text-sm font-bold text-slate-900 tracking-tight">
            Vấn đề &amp; Câu hỏi giải trình ({caseView.issues.length})
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Giải trình các điểm ngoại lệ để hệ thống đối soát và mở khóa phê duyệt thanh toán
          </p>
        </div>
      </div>

      {/* 1. Actionable Issues for Current Role */}
      {myIssues.length > 0 ? (
        <ul className="questions space-y-3">
          {myIssues.map((issue) => (
            <QuestionCard key={issue.id} issue={issue} caseView={caseView} onCase={onCase} />
          ))}
        </ul>
      ) : (
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-slate-600 text-xs space-y-1">
          <p className="font-semibold text-slate-800">
            Không có câu hỏi nào thuộc thẩm quyền của vai trò hiện tại.
          </p>
          <p className="text-[11px] text-slate-500">
            Các vấn đề còn lại đang thuộc thẩm quyền xử lý của Kế toán hoặc Quản trị hệ thống.
          </p>
        </div>
      )}

      {/* 2. Pending Issues Assigned to Other Roles (Compact informational view) */}
      {otherIssues.length > 0 && (
        <div className="bg-slate-50/70 border border-slate-200 rounded-lg p-3.5 space-y-2.5 mt-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Vấn đề đang chờ bộ phận khác xử lý ({otherIssues.length})
            </h3>
            <span className="text-[10px] text-slate-400 font-medium">
              Tự động cập nhật
            </span>
          </div>

          <ul className="divide-y divide-slate-200/80 text-xs">
            {otherIssues.map((issue) => (
              <li key={issue.id} className="py-2.5 flex items-start justify-between gap-3">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-800 truncate">
                      {issue.question}
                    </span>
                    <span className="text-[10px] font-mono-nums px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 shrink-0">
                      {formatIssueTarget(issue.field_or_rule)}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Căn cứ: {issue.basis}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <span className="text-[11px] font-semibold text-slate-700 bg-white px-2 py-0.5 rounded border border-slate-200 block">
                    {issue.owner === "org-data"
                      ? "Dữ liệu tổ chức"
                      : issue.owner === "accountant"
                      ? "Kế toán"
                      : issue.owner}
                  </span>
                  <span className="text-[10px] text-slate-400 mt-0.5 block">Chờ xử lý</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
