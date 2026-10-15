import { useState } from "react";

import { answerIssue, errorMessage } from "../api";
import type { CaseView, IssueView } from "../types";

const KIND_LABELS: Record<string, string> = {
  FACT: "Dữ kiện thực tế",
  POLICY: "Chính sách chi tiêu",
  AUTHORITY: "Thẩm quyền phê duyệt",
};

function employeePaidInvoiceReference(fieldOrRule: string): string | null {
  const prefix = "expense:";
  const suffix = ":employee_paid";
  if (!fieldOrRule.startsWith(prefix) || !fieldOrRule.endsWith(suffix)) return null;
  const reference = fieldOrRule.slice(prefix.length, -suffix.length).trim();
  return reference || null;
}

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
  const invoiceReference = employeePaidInvoiceReference(issue.field_or_rule);
  const historyCoverageIssue = issue.field_or_rule === "ledger:coverage";
  const lineTable = parseSettlementLineTotal(issue.basis);
  const returnTable = parseSettlementReturn(issue.basis);

  // Group refs by source and page
  const groupedRefs = (issue.refs ?? []).reduce<
    Record<string, { filename: string; page: number | null; quotes: string[] }>
  >((acc, ref) => {
    const filename =
      caseView.sources.find((source) => source.id === ref.source_id)?.filename ??
      ref.source_id;
    const key = `${ref.source_id}::${ref.page ?? 1}`;
    if (!acc[key]) {
      acc[key] = {
        filename,
        page: ref.page ?? null,
        quotes: [],
      };
    }
    if (!acc[key].quotes.includes(ref.exact_quote)) {
      acc[key].quotes.push(ref.exact_quote);
    }
    return acc;
  }, {});

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
      className="space-y-4 text-xs max-w-2xl"
      data-testid={`question-${issue.kind}`}
    >
      {/* 1. Câu hỏi & Diễn giải */}
      <div className="space-y-1.5">
        <h4 className="font-semibold text-slate-900 text-sm leading-relaxed">
          {formatQuestionTitle(issue.question, Boolean(issue.basis))}
        </h4>
        {!lineTable && !returnTable && issue.basis && issue.basis !== issue.question && (
          <p className="text-slate-600 text-xs leading-relaxed">
            {formatVndInText(issue.basis)}
          </p>
        )}
      </div>

      {/* 2. Chứng từ liên quan */}
      {Object.keys(groupedRefs).length > 0 && (
        <div
          aria-label="Trích dẫn nguồn cho căn cứ"
          className="text-xs text-slate-600 flex items-baseline gap-2 flex-wrap pt-0.5"
        >
          <span className="text-slate-400 font-medium shrink-0">Chứng từ đối chiếu:</span>
          {Object.entries(groupedRefs).map(([key, group]) => (
            <span key={key} className="inline-flex items-baseline gap-1.5 flex-wrap">
              <span className="font-semibold text-slate-800">{group.filename}</span>
              <span className="text-slate-500">· trang {group.page ?? "?"}</span>
              {!lineTable && !returnTable && (
                <>
                  <span className="text-slate-300">|</span>
                  <span className="text-slate-400">Trích dẫn:</span>
                  {group.quotes.map((quote, idx) => (
                    <span
                      key={idx}
                      className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-[11px] font-mono-nums"
                    >
                      {quote}
                    </span>
                  ))}
                </>
              )}
            </span>
          ))}
        </div>
      )}

      {/* 3. Bảng kê đối chiếu mini (Phương án A) */}
      {lineTable && (
        <div className="border border-slate-200 rounded overflow-hidden max-w-xl text-xs bg-white">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <th className="py-2 px-3 font-semibold text-xs">Khoản mục trích xuất</th>
                <th className="py-2 px-3 font-semibold text-xs text-right">Số tiền</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lineTable.items.map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-50/50">
                  <td className="py-2 px-3 text-slate-800">• {item.description}</td>
                  <td className="py-2 px-3 text-right font-mono-nums text-slate-900 font-medium">
                    {item.amount}
                  </td>
                </tr>
              ))}
              <tr className="bg-slate-50/60 font-semibold border-t border-slate-200">
                <td className="py-2 px-3 text-slate-700">Tổng cộng các dòng chi</td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900">
                  {lineTable.calculatedTotal}
                </td>
              </tr>
              <tr className="bg-slate-50/60 font-semibold">
                <td className="py-2 px-3 text-slate-700">Tổng in trên giấy quyết toán</td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900">
                  {lineTable.printedTotal}
                </td>
              </tr>
              <tr className="bg-rose-50/80 font-semibold border-t border-rose-200 text-rose-900">
                <td className="py-2 px-3 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
                  <span>Chênh lệch chưa khớp</span>
                </td>
                <td className="py-2 px-3 text-right font-mono-nums text-rose-700 font-bold">
                  {lineTable.diff.startsWith("+") || lineTable.diff.startsWith("-")
                    ? lineTable.diff
                    : `± ${lineTable.diff}`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {returnTable && (
        <div className="border border-slate-200 rounded overflow-hidden max-w-xl text-xs bg-white">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                <th className="py-2 px-3 font-semibold text-xs">Mục đối chiếu</th>
                <th className="py-2 px-3 font-semibold text-xs text-right">Số tiền</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="hover:bg-slate-50/50">
                <td className="py-2 px-3 text-slate-800">• Tiền tạm ứng</td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900 font-medium">
                  {returnTable.advance}
                </td>
              </tr>
              <tr className="hover:bg-slate-50/50">
                <td className="py-2 px-3 text-slate-800">• Tiền thực chi</td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900 font-medium">
                  {returnTable.total}
                </td>
              </tr>
              <tr className="bg-slate-50/60 font-semibold border-t border-slate-200">
                <td className="py-2 px-3 text-slate-700">
                  Số tiền {returnTable.isReturn ? "hoàn ứng" : "chi thêm"} theo phép tính
                </td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900">
                  {returnTable.expected}
                </td>
              </tr>
              <tr className="bg-slate-50/60 font-semibold">
                <td className="py-2 px-3 text-slate-700">
                  Số tiền ghi trên giấy quyết toán
                </td>
                <td className="py-2 px-3 text-right font-mono-nums text-slate-900">
                  {returnTable.printed}
                </td>
              </tr>
              <tr className="bg-rose-50/80 font-semibold border-t border-rose-200 text-rose-900">
                <td className="py-2 px-3 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
                  <span>Chênh lệch chưa khớp</span>
                </td>
                <td className="py-2 px-3 text-right font-mono-nums text-rose-700 font-bold">
                  {returnTable.diff.startsWith("+") || returnTable.diff.startsWith("-")
                    ? returnTable.diff
                    : `± ${returnTable.diff}`}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* 3. Form giải trình */}
      {historyCoverageIssue ? (
        <div className="pt-2 text-xs text-slate-600 space-y-1">
          <p className="font-medium text-slate-800">
            Không áp dụng giải trình bằng văn bản tự do cho mục này.
          </p>
          <p className="text-slate-500">
            Vui lòng chuyển sang tab <strong className="text-slate-700 font-semibold">Sổ cái & Dòng tiền</strong> ở trên để thực hiện đối chiếu và xác nhận.
          </p>
        </div>
      ) : (
        <div className="space-y-3 pt-3 border-t border-slate-200">
          <div>
            <label
              htmlFor={`answer-${issue.id}`}
              className="text-slate-900 block text-xs font-medium mb-1.5"
            >
              {invoiceReference
                ? `Số tiền VND nhân viên trực tiếp thanh toán cho hóa đơn ${invoiceReference}`
                : "Nội dung giải trình / xác nhận:"}
            </label>
            {invoiceReference ? (
              <input
                id={`answer-${issue.id}`}
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={value}
                onChange={(event) => setValue(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded text-xs px-3 py-2 text-slate-900 focus:outline-none focus:border-slate-800 transition-colors"
              />
            ) : (
              <textarea
                id={`answer-${issue.id}`}
                rows={3}
                value={value}
                onChange={(event) => setValue(event.target.value)}
                className="w-full bg-white border border-slate-300 rounded text-xs p-2.5 text-slate-900 focus:outline-none focus:border-slate-800 resize-y transition-colors leading-relaxed"
              />
            )}
          </div>

          <div>
            <label
              htmlFor={`reason-${issue.id}`}
              className="text-slate-600 block text-[11px] font-medium mb-1"
            >
              {invoiceReference
                ? "Lý do / xác nhận cụ thể"
                : "Căn cứ / Ghi chú đính kèm (tùy chọn):"}
            </label>
            <input
              id={`reason-${issue.id}`}
              type="text"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required={invoiceReference !== null}
              className="w-full bg-white border border-slate-300 rounded text-xs px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-800 transition-colors"
            />
          </div>

          <div className="pt-1 flex items-center justify-end">
            <button
              type="button"
              onClick={() => void submit()}
              disabled={busy || value.trim() === "" || (invoiceReference !== null && reason.trim() === "")}
              className="px-4 py-2 text-xs font-medium rounded transition-colors disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed bg-slate-900 hover:bg-slate-800 text-white cursor-pointer"
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
  const [isOtherIssuesOpen, setIsOtherIssuesOpen] = useState(false);

  if (caseView === null || caseView.issues.length === 0) return null;

  const myIssues = caseView.issues.filter((issue) =>
    roleMatchesOwner(currentRole, issue.owner, issue.kind),
  );
  const otherIssues = caseView.issues.filter((issue) => !myIssues.includes(issue));

  const currentActiveId =
    myIssues.find((i) => i.id === activeIssueId)?.id ?? myIssues[0]?.id ?? null;

  return (
    <section aria-labelledby="questions-title" className="space-y-6 select-none text-xs max-w-3xl">
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
                <QuestionCard
                  issue={issue}
                  caseView={caseView}
                  onCase={onCase}
                />
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
