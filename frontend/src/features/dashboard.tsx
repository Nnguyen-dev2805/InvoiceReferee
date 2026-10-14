import { useMemo, useState } from "react";

import { formatVnd } from "../format";
import type { CaseView } from "../types";

export interface DashboardProps {
  cases: CaseView[];
  currentRole: string;
  onSelectCase: (caseView: CaseView) => void;
  onCreateNew: () => void;
}

function parseSummary(summary: string) {
  if (!summary) return { activity: "Hồ sơ quyết toán", date: "", person: "" };
  const parts = summary.split(" · ");
  return {
    activity: parts[0] || "Hồ sơ quyết toán",
    date: parts[1] || "",
    person: parts[2] || "",
  };
}

export function Dashboard({
  cases,
  currentRole,
  onSelectCase,
  onCreateNew,
}: DashboardProps) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<string>("ALL");

  const isEmployee = currentRole === "employee";
  const isApprover = currentRole === "approver";
  const isAccountant = currentRole === "accountant";

  // Compute status counts for tabs
  const counts = useMemo(() => {
    let employeeIssuesCount = 0;
    let readyToExecuteCount = 0;
    let policyIssuesCount = 0;
    let advancePendingCount = 0;
    let payPendingCount = 0;
    let collectPendingCount = 0;
    let settledCount = 0;

    for (const c of cases) {
      if (c.state === "SETTLED") settledCount++;
      if (c.state === "READY_TO_EXECUTE") readyToExecuteCount++;

      // Employee issues
      const empIssues = c.issues.filter(
        (i) => i.owner === "employee" || i.owner.startsWith("employee:"),
      );
      if (empIssues.length > 0) employeeIssuesCount++;

      // Policy issues for approver
      const polIssues = c.issues.filter(
        (i) => i.kind === "POLICY" || i.kind === "AUTHORITY",
      );
      if (polIssues.length > 0) policyIssuesCount++;

      // Net settlement S for accountant
      const sFact = c.actual_money?.S;
      if (sFact && sFact.state === "KNOWN" && sFact.value !== null && c.state !== "SETTLED") {
        if (sFact.value > 0) payPendingCount++;
        if (sFact.value < 0) collectPendingCount++;
      }

      // Advance pending check
      const aFact = c.actual_money?.A;
      if (!aFact || aFact.state !== "KNOWN") {
        advancePendingCount++;
      }
    }

    return {
      total: cases.length,
      employeeIssuesCount,
      readyToExecuteCount,
      policyIssuesCount,
      advancePendingCount,
      payPendingCount,
      collectPendingCount,
      settledCount,
    };
  }, [cases]);

  // Filter cases based on active tab and search
  const filteredCases = useMemo(() => {
    return cases.filter((c) => {
      const query = search.trim().toLowerCase();
      const matchesSearch =
        query === "" ||
        c.id.toLowerCase().includes(query) ||
        c.summary.toLowerCase().includes(query);

      if (!matchesSearch) return false;

      if (filter === "ALL") return true;
      if (filter === "EMPLOYEE_ISSUES") {
        return c.issues.some(
          (i) => i.owner === "employee" || i.owner.startsWith("employee:"),
        );
      }
      if (filter === "READY") return c.state === "READY_TO_EXECUTE";
      if (filter === "POLICY_ISSUES") {
        return c.issues.some(
          (i) => i.kind === "POLICY" || i.kind === "AUTHORITY",
        );
      }
      if (filter === "ADVANCE_PENDING") {
        return !c.actual_money?.A || c.actual_money?.A?.state !== "KNOWN";
      }
      if (filter === "PAY_PENDING") {
        const s = c.actual_money?.S?.value;
        return c.actual_money?.S?.state === "KNOWN" && s !== null && s > 0 && c.state !== "SETTLED";
      }
      if (filter === "COLLECT_PENDING") {
        const s = c.actual_money?.S?.value;
        return c.actual_money?.S?.state === "KNOWN" && s !== null && s < 0 && c.state !== "SETTLED";
      }
      if (filter === "SETTLED") return c.state === "SETTLED";

      return true;
    });
  }, [cases, search, filter]);

  return (
    <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-4 bg-white">
      {/* 1. Header (Clean, crisp, no essay subtitles) */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <h2 className="text-base font-semibold text-slate-900 tracking-tight">
          {isEmployee
            ? "Hồ sơ quyết toán của tôi"
            : isApprover
            ? "Bàn phê duyệt Chi tiêu"
            : "Bàn làm việc Kế toán"}
        </h2>

        {isEmployee && (
          <button
            type="button"
            onClick={onCreateNew}
            className="inline-flex items-center px-3 py-1.5 rounded text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 transition-colors shadow-2xs cursor-pointer"
          >
            <span className="text-white font-medium">+ Tạo hồ sơ mới</span>
          </button>
        )}
      </div>

      {/* 2. Linear/Stripe-style Underline Tabs (Zero AI pill clutter) */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-200">
        <nav className="flex items-center gap-6 overflow-x-auto custom-scrollbar -mb-px text-xs font-medium" aria-label="Bộ lọc trạng thái">
          <button
            type="button"
            onClick={() => setFilter("ALL")}
            className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
              filter === "ALL"
                ? "border-slate-900 text-slate-950 font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <span>Tất cả</span>
            <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
              {counts.total}
            </span>
          </button>

          {isEmployee && (
            <>
              <button
                type="button"
                onClick={() => setFilter("EMPLOYEE_ISSUES")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "EMPLOYEE_ISSUES"
                    ? "border-amber-600 text-amber-900 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Cần bạn giải trình</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums ${
                  counts.employeeIssuesCount > 0 ? "bg-amber-100 text-amber-900 font-semibold" : "bg-slate-100 text-slate-600"
                }`}>
                  {counts.employeeIssuesCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setFilter("READY")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "READY"
                    ? "border-slate-900 text-slate-950 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Chờ phê duyệt</span>
                <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
                  {counts.readyToExecuteCount}
                </span>
              </button>
            </>
          )}

          {isApprover && (
            <>
              <button
                type="button"
                onClick={() => setFilter("READY")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "READY"
                    ? "border-slate-900 text-slate-950 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Chờ phê duyệt</span>
                <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
                  {counts.readyToExecuteCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setFilter("POLICY_ISSUES")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "POLICY_ISSUES"
                    ? "border-amber-600 text-amber-900 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Vướng mắc chính sách</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums ${
                  counts.policyIssuesCount > 0 ? "bg-amber-100 text-amber-900 font-semibold" : "bg-slate-100 text-slate-600"
                }`}>
                  {counts.policyIssuesCount}
                </span>
              </button>
            </>
          )}

          {isAccountant && (
            <>
              <button
                type="button"
                onClick={() => setFilter("ADVANCE_PENDING")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "ADVANCE_PENDING"
                    ? "border-amber-600 text-amber-900 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Chờ tạm ứng</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums ${
                  counts.advancePendingCount > 0 ? "bg-amber-100 text-amber-900 font-semibold" : "bg-slate-100 text-slate-600"
                }`}>
                  {counts.advancePendingCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setFilter("PAY_PENDING")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "PAY_PENDING"
                    ? "border-slate-900 text-slate-950 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Cần chi trả</span>
                <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
                  {counts.payPendingCount}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setFilter("COLLECT_PENDING")}
                className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
                  filter === "COLLECT_PENDING"
                    ? "border-slate-900 text-slate-950 font-semibold"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Cần thu hồi</span>
                <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
                  {counts.collectPendingCount}
                </span>
              </button>
            </>
          )}

          <button
            type="button"
            onClick={() => setFilter("SETTLED")}
            className={`pb-2.5 flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 border-b-2 ${
              filter === "SETTLED"
                ? "border-slate-900 text-slate-950 font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <span>Đã quyết toán</span>
            <span className="px-1.5 py-0.2 rounded-full text-[11px] font-mono-nums bg-slate-100 text-slate-600">
              {counts.settledCount}
            </span>
          </button>
        </nav>

        {/* Quick Search */}
        <div className="pb-2">
          <input
            type="text"
            placeholder="Tìm theo mã hoặc tên hồ sơ…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full sm:w-56 bg-slate-50 hover:bg-white focus:bg-white border border-slate-300 focus:border-slate-400 rounded px-2.5 py-1 text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none transition-colors"
          />
        </div>
      </div>

      {/* 3. Bespoke Clean Enterprise Table */}
      <div className="border border-slate-200 rounded-lg overflow-hidden bg-white shadow-2xs">
        {filteredCases.length === 0 ? (
          <div className="py-12 px-4 text-center space-y-2">
            <h3 className="text-sm font-semibold text-slate-800">
              Chưa có hồ sơ nào được mở
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              {search.trim() !== "" || filter !== "ALL"
                ? "Không có hồ sơ nào khớp với bộ lọc hoặc từ khóa tìm kiếm."
                : isEmployee
                ? "Bạn chưa có hồ sơ nào. Bấm '+ Tạo hồ sơ mới' ở góc trên để gửi đề nghị thanh toán."
                : "Hàng đợi đang trống. Các hồ sơ nộp sẽ tự động hiển thị tại đây."}
            </p>
          </div>
        ) : (
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/75 text-xs font-medium text-slate-600">
                <th className="py-2.5 px-4 w-32 font-medium">Mã hồ sơ</th>
                <th className="py-2.5 px-4 font-medium">Nội dung hoạt động</th>
                <th className="py-2.5 px-4 text-right w-36 font-medium">Tổng chi (T)</th>
                <th className="py-2.5 px-4 text-right w-44 font-medium">Chênh lệch (S)</th>
                <th className="py-2.5 px-4 w-56 font-medium">Trạng thái</th>
                <th className="py-2.5 px-3 w-8 text-center"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredCases.map((c) => {
                const parsed = parseSummary(c.summary);
                const tVal = c.actual_money?.T?.state === "KNOWN" ? c.actual_money.T.value : null;
                const sFact = c.actual_money?.S;
                const sVal = sFact?.state === "KNOWN" ? sFact.value : null;

                // Fallback clean activity title if single letter or dummy
                const displayActivity =
                  !parsed.activity || parsed.activity.trim().length <= 2
                    ? "Hồ sơ quyết toán công tác"
                    : parsed.activity.trim();

                // Status tag with subtle status dot
                let statusBadge = (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium text-slate-600 bg-slate-100">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                    Đang đối soát
                  </span>
                );

                if (isEmployee) {
                  const myIssues = c.issues.filter(
                    (i) => i.owner === "employee" || i.owner.startsWith("employee:"),
                  );
                  if (myIssues.length > 0) {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-600 shrink-0"></span>
                        Cần bạn giải trình ({myIssues.length})
                      </span>
                    );
                  } else if (c.state === "READY_TO_EXECUTE") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 shrink-0"></span>
                        Chờ sếp phê duyệt
                      </span>
                    );
                  } else if (c.state === "SETTLED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0"></span>
                        Đã quyết toán xong
                      </span>
                    );
                  } else if (c.state === "STOPPED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-rose-50 text-rose-800 border border-rose-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-600 shrink-0"></span>
                        Tạm dừng xử lý
                      </span>
                    );
                  }
                } else if (isApprover) {
                  const policyIssues = c.issues.filter(
                    (i) => i.kind === "POLICY" || i.kind === "AUTHORITY",
                  );
                  if (policyIssues.length > 0) {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-600 shrink-0"></span>
                        Vướng mắc chính sách ({policyIssues.length})
                      </span>
                    );
                  } else if (c.state === "READY_TO_EXECUTE") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 shrink-0"></span>
                        Sẵn sàng duyệt
                      </span>
                    );
                  } else if (c.state === "SETTLED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0"></span>
                        Đã phê duyệt xong
                      </span>
                    );
                  }
                } else if (isAccountant) {
                  if (c.actual_money?.A?.state !== "KNOWN") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-600 shrink-0"></span>
                        Chờ ghi nhận tạm ứng (A)
                      </span>
                    );
                  } else if (sVal !== null && sVal > 0 && c.state !== "SETTLED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 shrink-0"></span>
                        Cần chi trả ({formatVnd(sVal)})
                      </span>
                    );
                  } else if (sVal !== null && sVal < 0 && c.state !== "SETTLED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-rose-50 text-rose-800 border border-rose-200/80">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-600 shrink-0"></span>
                        Cần thu hồi ({formatVnd(Math.abs(sVal))})
                      </span>
                    );
                  } else if (c.state === "SETTLED") {
                    statusBadge = (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0"></span>
                        Đã cân bằng xong
                      </span>
                    );
                  }
                }

                // Subtext line: Only date and person
                const metaLine = [parsed.date, parsed.person || c.employee]
                  .filter(Boolean)
                  .join(" · ");

                return (
                  <tr
                    key={c.id}
                    onClick={() => onSelectCase(c)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer group"
                  >
                    {/* 1. Case ID */}
                    <td className="py-3 px-4 font-mono-nums font-semibold text-slate-900 whitespace-nowrap">
                      <span>#{c.id.replace("case:", "").slice(0, 8)}</span>
                      <span className="text-[10px] text-slate-400 font-normal ml-1">
                        v{c.version}
                      </span>
                    </td>

                    {/* 2. Activity & Meta */}
                    <td className="py-3 px-4">
                      <span className="font-medium text-slate-900 block truncate">
                        {displayActivity}
                      </span>
                      {metaLine && (
                        <span className="text-[11px] text-slate-500 font-normal block mt-0.5">
                          {metaLine}
                        </span>
                      )}
                      <span className="sr-only">{c.summary}</span>
                    </td>

                    {/* 3. Total T */}
                    <td className="py-3 px-4 text-right font-mono-nums font-medium text-slate-900 whitespace-nowrap">
                      {tVal !== null ? formatVnd(tVal) : "—"}
                    </td>

                    {/* 4. Net Settlement S */}
                    <td className="py-3 px-4 text-right font-mono-nums font-medium whitespace-nowrap">
                      {sVal !== null ? (
                        sVal > 0 ? (
                          <span className="text-emerald-700">+{formatVnd(sVal)}</span>
                        ) : sVal < 0 ? (
                          <span className="text-rose-700">-{formatVnd(Math.abs(sVal))}</span>
                        ) : (
                          <span className="text-slate-600">0 ₫</span>
                        )
                      ) : (
                        <span className="text-slate-500 text-xs italic">Chưa xác định</span>
                      )}
                    </td>

                    {/* 5. Status Badge */}
                    <td className="py-3 px-4 whitespace-nowrap">
                      {statusBadge}
                    </td>

                    {/* 6. Subtle click-through chevron */}
                    <td className="py-3 px-3 text-center text-slate-300 group-hover:text-slate-700 transition-colors text-xs">
                      →
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
