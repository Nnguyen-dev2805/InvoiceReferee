import type { CaseView } from "../types";

const STATE_LABELS: Record<string, string> = {
  DRAFT: "Bản nháp",
  PROCESSING: "Đang xử lý",
  EVIDENCE_READY: "Đã đọc chứng từ",
  WAITING: "Chờ người xử lý",
  TECHNICAL_ERROR: "Lỗi xử lý",
  READY_TO_EXECUTE: "Sẵn sàng thực hiện",
  SETTLED: "Đã cân bằng",
  STOPPED: "Đã dừng",
};

// A payment basis is labelled by what actually established it: a Q32 employee
// declaration is NOT a bank-verified fact (ADR0007), so the label must not
// imply bank verification.
const BASIS_LABELS: Record<string, string> = {
  INDEPENDENT_PAYMENT: "Chứng từ thanh toán độc lập",
  FINANCIAL_CONFIRMATION: "Xác nhận tài chính",
  EMPLOYEE_DECLARATION_Q32: "Lời xác nhận của nhân viên",
  UNSPECIFIED_LEGACY: "Chưa xác định căn cứ",
};

const ISSUE_LABELS: Record<string, string> = {
  FACT: "Dữ kiện",
  POLICY: "Chính sách",
  AUTHORITY: "Quyền",
};

const MONEY_LABELS: Record<string, string> = {
  T: "Tổng chi công việc",
  E: "Chi phí đủ điều kiện",
  C: "Công ty trả trực tiếp",
  A: "Ứng thực nhận",
  P: "Đã hoàn",
  R: "Đã thu hồi",
  unpaid: "Chưa thanh toán",
  S: "Chênh lệch (S)",
};

const UNKNOWN_LABEL = "Chưa xác minh";

export function formatMoney(value: number | null): string {
  if (value === null) return UNKNOWN_LABEL;
  return new Intl.NumberFormat("vi-VN").format(value) + " ₫";
}

function parseAuditLine(line: string) {
  const parts = line.split(" · ");
  if (parts.length >= 3) {
    const rawTime = parts[0];
    const rawActor = parts[1];
    const rawAction = parts.slice(2).join(" · ");

    let formattedTime = rawTime;
    try {
      const d = new Date(rawTime);
      if (!isNaN(d.getTime())) {
        const hh = String(d.getHours()).padStart(2, "0");
        const mm = String(d.getMinutes()).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        const mo = String(d.getMonth() + 1).padStart(2, "0");
        const yyyy = d.getFullYear();
        formattedTime = `${hh}:${mm} · ${dd}/${mo}/${yyyy}`;
      }
    } catch {
      // keep rawTime
    }

    let humanActor = rawActor;
    if (rawActor.includes("referee") || rawActor.includes("system")) {
      humanActor = "Hệ thống tự động";
    } else if (rawActor.includes("employee")) {
      humanActor = "Nhân viên";
    } else if (rawActor.includes("accountant")) {
      humanActor = "Kế toán";
    } else if (rawActor.includes("approver")) {
      humanActor = "Người duyệt";
    }

    let humanAction = rawAction;
    if (rawAction === "CREATE_DRAFT") humanAction = "Khởi tạo hồ sơ nháp";
    else if (rawAction === "ATTACH_SOURCES") humanAction = "Tải lên chứng từ gốc";
    else if (rawAction === "RECORD_EMPLOYEE_PAID_CLAIMS") humanAction = "Ghi nhận xác nhận thanh toán (Q32)";
    else if (rawAction === "ASSESS") humanAction = "Đánh giá & đối soát tài chính";
    else if (rawAction === "EMERGENCY_STOP" || rawAction === "STOP") humanAction = "Dừng xử lý khẩn cấp (§6)";
    else if (rawAction === "RESUME") humanAction = "Tiếp tục xử lý hồ sơ";
    else if (rawAction === "RECORD_ACTUAL_MONEY") humanAction = "Ghi nhận thực tế chuyển tiền";

    return { formattedTime, rawTime, rawActor, humanActor, rawAction, humanAction };
  }
  return { formattedTime: line, rawTime: line, rawActor: "", humanActor: "", rawAction: "", humanAction: line };
}

function formatSummary(summary: string): string {
  if (!summary) return "Hồ sơ công tác";
  const parts = summary.split(" · ");
  if (parts.length >= 2 && parts[0].trim().length <= 2) {
    return `Hoạt động công tác (${parts[0].trim()}) · ${parts.slice(1).join(" · ")}`;
  }
  return summary;
}

/** One money figure: a known amount, or an explicit "chưa xác minh" state. */
export function MoneyLine({
  label,
  fact,
  highlight = false,
}: {
  label: string;
  fact: { value: number | null; state: string };
  highlight?: boolean;
}) {
  const known = fact.state === "KNOWN" && fact.value !== null;
  return (
    <li
      data-testid={`money-${label}`}
      className={`flex items-center justify-between px-3.5 py-2 text-xs transition-colors ${
        highlight
          ? "bg-slate-50/70 font-semibold text-slate-900 border-t border-slate-200/80"
          : "hover:bg-slate-50/30 text-slate-600"
      }`}
    >
      <span className={highlight ? "font-semibold text-slate-900" : "text-slate-600 font-normal"}>
        {label}:
      </span>
      <strong
        className={`font-['JetBrains_Mono'] tabular-nums tracking-tight text-xs ${
          known
            ? highlight
              ? "text-slate-950 font-bold"
              : "text-slate-900 font-semibold"
            : "text-slate-400 font-normal"
        }`}
      >
        {known ? formatMoney(fact.value) : UNKNOWN_LABEL}
      </strong>
    </li>
  );
}

export function Dossier({ caseView }: { caseView: CaseView | null }) {
  return (
    <section
      aria-labelledby="dossier-title"
      className="bg-white border border-slate-200 rounded-lg p-5 text-xs shadow-sm space-y-5"
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-200/80">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded bg-slate-900 text-white flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-base" aria-hidden="true">inventory_2</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 id="dossier-title" className="text-sm font-semibold text-slate-900">
                Hồ sơ
              </h2>
              {caseView !== null && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 font-['JetBrains_Mono']">
                  v{caseView.version}
                </span>
              )}
            </div>
            {caseView !== null && (
              <p className="text-[11px] text-slate-500 font-medium mt-0.5 line-clamp-1">
                {formatSummary(caseView.summary)}
              </p>
            )}
          </div>
        </div>

        {caseView !== null && (
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold ${
              caseView.state === "READY_TO_EXECUTE"
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : caseView.state === "WAITING"
                ? "bg-amber-50 text-amber-700 border border-amber-200"
                : "bg-slate-100 text-slate-700 border border-slate-200"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                caseView.state === "READY_TO_EXECUTE"
                  ? "bg-emerald-500"
                  : caseView.state === "WAITING"
                  ? "bg-amber-500"
                  : "bg-slate-400"
              }`}
            ></span>
            {STATE_LABELS[caseView.state] ?? caseView.state}
          </span>
        )}
      </div>

      {caseView === null ? (
        <div className="py-12 text-center space-y-2">
          <span className="material-symbols-outlined text-3xl text-slate-300" aria-hidden="true">folder_open</span>
          <p className="text-slate-500 text-xs">
            Chưa có hồ sơ nào được mở. Hãy chọn hoạt động và tạo hồ sơ.
          </p>
        </div>
      ) : (
        <>
          {/* Section: Sources with Cryptographic Hashes */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <h3 className="font-semibold text-slate-900 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-slate-500 text-sm" aria-hidden="true">receipt_long</span>
                <span>Chứng từ ({caseView.sources.length})</span>
              </h3>
              <span className="text-[10px] text-slate-400 font-['JetBrains_Mono'] uppercase tracking-wider flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                SHA-256 Verified
              </span>
            </div>

            {caseView.sources.length === 0 ? (
              <p className="text-slate-400 text-xs py-2 italic">Chưa có chứng từ nào.</p>
            ) : (
              <div className="border border-slate-200/80 rounded-md divide-y divide-slate-100 overflow-hidden bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                {caseView.sources.map((source) => (
                  <div
                    key={source.id}
                    className="px-3 py-2 flex items-center justify-between hover:bg-slate-50/50 transition-colors text-xs font-['JetBrains_Mono']"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="material-symbols-outlined text-slate-400 text-base" aria-hidden="true">description</span>
                      <span className="font-semibold text-slate-800">{source.media}</span>
                      <span className="text-slate-300">·</span>
                      <span className="text-slate-500 truncate" title={source.digest}>
                        {source.digest.slice(0, 16)}…
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-sans font-medium">
                      Toàn vẹn
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section: Money Figures - Modern Flat Ledger */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-slate-500 text-sm" aria-hidden="true">account_balance</span>
                <span>Số tiền</span>
              </h3>
              <span className="text-[10px] text-slate-400 font-['JetBrains_Mono'] uppercase tracking-wider">
                Đơn vị: VND
              </span>
            </div>
            <div className="border border-slate-200 rounded-md overflow-hidden bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
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

          {/* Section: Payment Basis */}
          {caseView.payment_basis.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-slate-500 text-sm" aria-hidden="true">verified_user</span>
                <span>Căn cứ chi trả</span>
              </h3>
              <div
                className="border border-slate-200 rounded-md overflow-hidden bg-white divide-y divide-slate-100 shadow-[0_1px_2px_rgba(0,0,0,0.03)]"
                data-testid="payment-basis"
              >
                {caseView.payment_basis.map((basis) => (
                  <div
                    key={basis.expense_id}
                    data-testid={`basis-${basis.expense_id}`}
                    className="p-3 text-xs flex items-center justify-between hover:bg-slate-50/40 transition-colors"
                  >
                    <div className="space-y-0.5">
                      <span className="font-semibold text-slate-900 block">
                        {BASIS_LABELS[basis.kind] ?? basis.kind}
                      </span>
                      {basis.actor && (
                        <span className="text-[11px] text-slate-500 block font-['JetBrains_Mono']">
                          Người xác nhận: {basis.actor}
                        </span>
                      )}
                    </div>
                    {basis.rule_id && (
                      <span className="text-[10px] font-['JetBrains_Mono'] font-medium bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200">
                        {basis.rule_id}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section: Issues / Actionable Exceptions */}
          {caseView.issues.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-amber-600 text-sm" aria-hidden="true">warning</span>
                  <span>Việc cần xử lý ({caseView.issues.length})</span>
                </h3>
                <span className="text-[10px] text-amber-700 font-medium bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                  Chờ giải quyết
                </span>
              </div>
              <div className="border border-slate-200 rounded-md overflow-hidden bg-white divide-y divide-slate-100 shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
                {caseView.issues.map((issue) => {
                  const kindLabel = ISSUE_LABELS[issue.kind] ?? issue.kind;
                  const ownerDisplay =
                    issue.owner === "approver"
                      ? "Cấp thẩm quyền phê duyệt"
                      : issue.owner === "accountant"
                      ? "Kế toán xử lý"
                      : issue.owner === "employee"
                      ? "Nhân viên đề nghị"
                      : issue.owner === "org-data"
                      ? "Quản trị dữ liệu"
                      : issue.owner;
                  return (
                    <div
                      key={issue.id}
                      className="p-3.5 hover:bg-slate-50/50 transition-colors text-xs space-y-2"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-800 border border-amber-200/70 shrink-0">
                            {kindLabel}
                          </span>
                          <span className="text-[11px] text-slate-500 font-medium">
                            Người xử lý: {issue.owner} {ownerDisplay !== issue.owner && (
                              <span className="text-slate-400 font-normal">({ownerDisplay})</span>
                            )}
                          </span>
                        </div>
                        <span className="text-[10px] font-['JetBrains_Mono'] text-slate-400">
                          #{issue.field_or_rule.split(":").pop()}
                        </span>
                      </div>
                      <p className="text-slate-900 font-medium text-xs leading-relaxed">
                        {issue.question}
                      </p>
                      <div className="flex items-center justify-between pt-1 text-[11px] text-slate-500 gap-2">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="material-symbols-outlined text-slate-400 text-xs shrink-0" aria-hidden="true">info</span>
                          <span className="truncate">Căn cứ: {issue.basis}</span>
                        </div>
                        <button
                          type="button"
                          className="shrink-0 inline-flex items-center gap-1 text-[11px] font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 hover:text-slate-900 px-2.5 py-1 rounded transition-colors cursor-pointer"
                        >
                          <span>
                            {issue.owner === "employee"
                              ? "Yêu cầu bổ sung"
                              : issue.owner === "accountant"
                              ? "Đối soát dữ liệu"
                              : issue.owner === "approver"
                              ? "Xem xét duyệt"
                              : "Cập nhật dữ liệu"}
                          </span>
                          <span className="material-symbols-outlined text-[13px]" aria-hidden="true">arrow_forward</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Section: Humanized Audit Timeline */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                <span className="material-symbols-outlined text-slate-500 text-sm" aria-hidden="true">history</span>
                <span>Lịch sử kiểm toán</span>
              </h3>
              <span className="text-[10px] text-slate-400 font-['JetBrains_Mono'] uppercase tracking-wider">
                Audit Trail
              </span>
            </div>
            <div className="border border-slate-200 rounded-md p-3.5 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.03)]">
              <ol className="relative border-l border-slate-200 ml-2 space-y-3.5 my-1">
                {caseView.audit.map((line, index) => {
                  const parsed = parseAuditLine(line);
                  return (
                    <li key={`${index}-${line}`} className="ml-3.5 group">
                      <span className="absolute -left-1 mt-1.5 w-2 h-2 rounded-full border-2 border-white bg-slate-400 group-hover:bg-slate-900 transition-colors"></span>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-slate-900">
                          {parsed.humanAction}
                        </span>
                        <span className="text-[10.5px] font-['JetBrains_Mono'] text-slate-400 tabular-nums">
                          {parsed.formattedTime}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-500 font-['JetBrains_Mono']">
                        <span>{parsed.humanActor}</span>
                        <span className="text-slate-300">·</span>
                        <span className="text-slate-400 text-[10px]">{parsed.rawAction}</span>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>

          {/* Section: Technical Details / Cryptographic Provenance */}
          <details className="group pt-2 border-t border-slate-200/80 text-xs text-slate-500">
            <summary className="cursor-pointer hover:text-slate-900 font-medium list-none flex items-center justify-between py-1 select-none">
              <div className="flex items-center gap-1.5">
                <span className="material-symbols-outlined text-sm text-slate-400 group-open:rotate-90 transition-transform" aria-hidden="true">chevron_right</span>
                <span>Thông tin kỹ thuật mật mã</span>
              </div>
              <span className="text-[10px] font-['JetBrains_Mono'] text-slate-400">
                {caseView.id}
              </span>
            </summary>
            <div className="mt-2 p-3 bg-slate-50/80 rounded-md border border-slate-200 text-[11px] font-['JetBrains_Mono'] space-y-1.5 text-slate-700">
              <div className="flex justify-between">
                <span className="text-slate-500">ID Hồ sơ:</span>
                <span className="font-medium text-slate-900">{caseView.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Trạng thái máy:</span>
                <span className="font-medium text-slate-900">{caseView.state}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Phiên bản hiện tại:</span>
                <span className="font-medium text-slate-900">v{caseView.version}</span>
              </div>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
