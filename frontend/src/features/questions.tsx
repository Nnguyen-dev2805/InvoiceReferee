import { useState } from "react";

import type { CaseView, IssueView } from "../types";
import { DecisionCard } from "./decision_card";
import { ExceptionReview } from "./exception_review";

export function formatVndInText(text: string): string {
  // Only an explicitly labelled monetary token is formatted. Identifiers and
  // calendar dates are source text, including leading zeroes.
  return text.replace(/(?<![\w/-])(\d{4,})(?=\s*(?:VND|đồng|đ)(?:\b|$))/g, value => Number(value).toLocaleString("vi-VN"));
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
  if (fieldOrRule === "ledger:coverage" || fieldOrRule === "coverage") {
    return "Lịch sử đối chiếu tiền";
  }
  if (fieldOrRule === "activity:acceptance") return "Công việc theo chứng từ ứng";
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

  const rawLast = fieldOrRule.split(":").pop() ?? fieldOrRule;
  if (rawLast === "return") return "Khoản hoàn ứng";
  if (rawLast === "reimburse") return "Khoản chi thêm";
  if (rawLast === "advance") return "Khoản tạm ứng";
  return `#${rawLast}`;
}

export function roleMatchesOwner(role: string, owner: string, kind: string): boolean {
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

export interface SettlementLineTotalTable {
  items: { description: string; amount: string }[];
  calculatedTotal: string;
  printedTotal: string;
  diff: string;
}

export function parseSettlementLineTotal(basis: string | undefined): SettlementLineTotalTable | null {
  if (!basis) return null;
  const match = basis.match(
    /Tổng dòng chi phí \((.+?)\) là ([\d.,]+(?:\s*đ)?), nhưng tổng in trên giấy là ([\d.,]+(?:\s*đ)?) \(lệch ([\d.,]+(?:\s*đ)?)\)/i,
  );
  if (!match) return null;

  const rawItems = match[1].split(/\s*\+\s*/);
  const items: { description: string; amount: string }[] = [];

  for (const raw of rawItems) {
    const itemMatch = raw.trim().match(/^(.*?)\s*([\d.,]+\s*đ?)$/);
    if (itemMatch) {
      items.push({
        description: itemMatch[1].trim(),
        amount: itemMatch[2].trim(),
      });
    } else {
      items.push({
        description: raw.trim(),
        amount: "",
      });
    }
  }

  return {
    items,
    calculatedTotal: match[2].trim(),
    printedTotal: match[3].trim(),
    diff: match[4].trim(),
  };
}

export interface SettlementReturnTable {
  advance: string;
  total: string;
  expected: string;
  printed: string;
  diff: string;
  isReturn: boolean;
}

export function parseSettlementReturn(basis: string | undefined): SettlementReturnTable | null {
  if (!basis) return null;
  const matchReturn = basis.match(
    /Giấy ghi ứng ([\d.,]+(?:\s*đ)?) [−-] chi ([\d.,]+(?:\s*đ)?) = ([\d.,]+(?:\s*đ)?) nhưng số hoàn lại in trên giấy là ([\d.,]+(?:\s*đ)?) \(lệch ([\d.,]+(?:\s*đ)?)\)/i,
  );
  if (matchReturn) {
    return {
      advance: matchReturn[1].trim(),
      total: matchReturn[2].trim(),
      expected: matchReturn[3].trim(),
      printed: matchReturn[4].trim(),
      diff: matchReturn[5].trim(),
      isReturn: true,
    };
  }
  const matchReimburse = basis.match(
    /Giấy ghi chi ([\d.,]+(?:\s*đ)?) [−-] ứng ([\d.,]+(?:\s*đ)?) = ([\d.,]+(?:\s*đ)?) nhưng số đề nghị chi thêm là ([\d.,]+(?:\s*đ)?) \(lệch ([\d.,]+(?:\s*đ)?)\)/i,
  );
  if (matchReimburse) {
    return {
      total: matchReimburse[1].trim(),
      advance: matchReimburse[2].trim(),
      expected: matchReimburse[3].trim(),
      printed: matchReimburse[4].trim(),
      diff: matchReimburse[5].trim(),
      isReturn: false,
    };
  }
  return null;
}

/** Server metadata chooses the response path; role labels never grant actions. */
export function QuestionCard(props: {issue: IssueView;caseView:CaseView;onCase:(view:CaseView)=>void;onSourceSelected?:(id:string)=>void;currentRole?:string}) {
  return <DecisionCard {...props}/>;
}

export function Questions({
  caseView,
  onCase,
  currentRole = "employee",
  onSourceSelected,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
  currentRole?: string;
  onSourceSelected?: (sourceId: string) => void;
}) {
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);
  const [isOtherIssuesOpen, setIsOtherIssuesOpen] = useState(false);

  if (caseView === null || (caseView.issues.length === 0 && !(caseView.declaration_corrections?.length))) return null;

  const myIssues = caseView.issues.filter((issue) =>
    roleMatchesOwner(currentRole, issue.owner, issue.kind),
  );
  const otherIssues = caseView.issues.filter((issue) => !myIssues.includes(issue));

  const currentActiveId =
    myIssues.find((i) => i.id === activeIssueId)?.id ?? myIssues[0]?.id ?? null;

  return (
    <section aria-labelledby="questions-title" className="space-y-6 text-xs max-w-3xl">
      {(caseView.declaration_corrections?.length??0)>0 && <section aria-label="Kê khai điều chỉnh đã lưu" className="rounded border border-slate-200 bg-slate-50 p-3 text-xs space-y-2"><h3 className="font-semibold">Kê khai điều chỉnh đã lưu</h3>{caseView.declaration_corrections?.map(entry=><div key={entry.id}><p>{entry.reason}</p><p className="text-slate-500">Người kê khai: {entry.actor} · {entry.observed_at}</p><p>Chứng từ gốc được giữ nguyên; đây là kê khai bổ sung của nhân viên.</p></div>)}</section>}
      {/* 1. Actionable Issues for Current Role */}
      {myIssues.length > 0 ? (
        <div className="space-y-3">
          {/* Minimalist Underline Tabs if multiple issues */}
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

          {/* Panel Content */}
          <div className="pt-1">
            {myIssues.map((issue) => (
              <div
                key={issue.id}
                className={issue.id === currentActiveId ? "block" : "hidden"}
              >
                {issue.kind === "POLICY" &&
                issue.field_or_rule.endsWith(":missing_evidence") ? (
                  <ExceptionReview
                    issue={issue}
                    caseView={caseView}
                    onCase={onCase}
                    onSourceSelected={onSourceSelected}
                  />
                ) : (
                  <QuestionCard
                    issue={issue}
                    caseView={caseView}
                    onCase={onCase}
                    onSourceSelected={onSourceSelected}
                    currentRole={currentRole}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="py-8 text-center space-y-1 select-none text-xs text-slate-500">
          <p className="font-semibold text-slate-800">
            Bạn không có vấn đề nào cần giải trình trực tiếp
          </p>
          <p className="text-[11px] max-w-sm mx-auto">
            Hồ sơ hiện chỉ có vấn đề thuộc trách nhiệm xử lý của bộ phận khác.
          </p>
        </div>
      )}

      {/* 2. Pending Issues Assigned to Other Roles */}
      {otherIssues.length > 0 && (
        <div className="pt-6 border-t border-slate-200">
          <button
            type="button"
            onClick={() => setIsOtherIssuesOpen(!isOtherIssuesOpen)}
            className="text-xs text-slate-500 hover:text-slate-800 font-medium inline-flex items-center gap-1.5 cursor-pointer"
          >
            <span>{isOtherIssuesOpen ? "▾ Thu gọn" : "▸ Xem"}</span>
            <span>{otherIssues.length} vấn đề khác thuộc trách nhiệm của bộ phận liên quan</span>
          </button>

          {isOtherIssuesOpen && (
            <ul className="mt-3 divide-y divide-slate-100 border-t border-b border-slate-200 text-xs">
              {otherIssues.map((issue) => (
                <li
                  key={issue.id}
                  className="py-3 flex items-start justify-between gap-4"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="text-[11px] text-slate-500">
                      Phụ trách: <strong className="font-semibold text-slate-700">{formatOwner(issue.owner)}</strong>
                    </div>
                    <p className="text-xs text-slate-900 font-medium leading-relaxed">
                      {formatVndInText(issue.question)}
                    </p>
                    {issue.basis && (
                      <p className="text-[11px] text-slate-500 leading-normal">
                        Căn cứ: {formatVndInText(issue.basis)}
                      </p>
                    )}
                  </div>
                  <span className="text-[11px] text-slate-400 shrink-0">
                    Chờ xử lý
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
