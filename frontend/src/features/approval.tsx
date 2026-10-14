import { formatVnd } from "../format";
import type { CaseView, InstructionView } from "../types";

const DIRECTION_LABELS: Record<string, string> = {
  PAY: "Công ty chi cho nhân viên",
  COLLECT: "Nhân viên hoàn lại công ty",
};

const EXECUTION_LABELS: Record<string, string> = {
  NOT_STARTED: "Chưa bắt đầu",
  OPEN: "Đang thực hiện ngoài app",
  CLOSED_CONFIRMED: "Đã xác nhận xong",
  UNKNOWN: "Chưa rõ",
};

function InstructionRow({ instruction }: { instruction: InstructionView }) {
  return (
    <li
      data-testid={`instruction-${instruction.direction}`}
      className="p-3 bg-slate-50 border border-slate-200 rounded space-y-1 text-xs"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-slate-900">
          <strong>{DIRECTION_LABELS[instruction.direction] ?? instruction.direction}</strong>:{" "}
          <span className="font-['JetBrains_Mono']">{formatVnd(instruction.amount)}</span>
        </span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 font-['JetBrains_Mono']">
          {instruction.status}
        </span>
      </div>
      <p className="muted text-[11px] text-slate-500">
        Còn lại: <span className="font-['JetBrains_Mono']">{formatVnd(instruction.remaining)}</span> · Trạng thái:{" "}
        {instruction.status} · Thực hiện:{" "}
        {EXECUTION_LABELS[instruction.execution_state] ?? instruction.execution_state}
      </p>
      <p className="muted text-[11px] text-slate-600 bg-white p-1.5 rounded border border-slate-100">
        Căn cứ: {instruction.basis}
      </p>
    </li>
  );
}

/** The list of actionable orders for the accountant/approver to execute. */
export function Approval({ caseView }: { caseView: CaseView | null }) {
  if (caseView === null) return null;
  const active = caseView.instructions.filter(
    (i) => i.status === "ISSUED" || i.status === "PARTIAL",
  );
  return (
    <section aria-labelledby="approval-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-3">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="approval-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-slate-700 text-sm" aria-hidden="true">assignment_turned_in</span>
          <span>Yêu cầu cần thực hiện ({active.length})</span>
        </h2>
      </div>
      {active.length === 0 ? (
        <p className="muted text-slate-400 italic text-[11px] py-2 text-center">
          Chưa có yêu cầu chi/thu nào cần thực hiện.
        </p>
      ) : (
        <ul className="instructions space-y-2">
          {active.map((instruction) => (
            <InstructionRow key={instruction.id} instruction={instruction} />
          ))}
        </ul>
      )}
    </section>
  );
}
