import { formatVnd } from "../format";
import type { CaseView, InstructionView } from "../types";

const DIRECTION_LABELS: Record<string, string> = {
  PAY: "Công ty chi trả cho nhân viên",
  COLLECT: "Nhân viên hoàn nộp lại công ty",
};

const EXECUTION_LABELS: Record<string, string> = {
  NOT_STARTED: "Chưa bắt đầu",
  OPEN: "Đang thực hiện ngoài app",
  CLOSED_CONFIRMED: "Đã xác nhận xong",
  UNKNOWN: "Chưa rõ",
};

function InstructionRow({ instruction }: { instruction: InstructionView }) {
  const isPay = instruction.direction === "PAY";
  return (
    <li
      data-testid={`instruction-${instruction.direction}`}
      className={`p-4 rounded-xl border space-y-2.5 text-xs transition-all shadow-xs ${
        isPay
          ? "bg-emerald-50/60 border-emerald-200/90 text-emerald-950"
          : "bg-amber-50/60 border-amber-200/90 text-amber-950"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${isPay ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
            {isPay ? "CHI" : "THU"}
          </span>
          <span className="font-semibold text-slate-900 text-xs">
            <strong>{DIRECTION_LABELS[instruction.direction] ?? instruction.direction}</strong>:{" "}
            <span className="font-mono-nums text-sm font-bold">{formatVnd(instruction.amount)}</span>
          </span>
        </div>
        <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-white border border-slate-200 font-mono-nums shadow-2xs text-slate-700">
          {instruction.status}
        </span>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-slate-600 font-medium">
        <span>Còn lại: <strong className="font-mono-nums text-slate-900">{formatVnd(instruction.remaining)}</strong></span>
        <span className="text-slate-300">·</span>
        <span>Thực hiện: <strong>{EXECUTION_LABELS[instruction.execution_state] ?? instruction.execution_state}</strong></span>
      </div>

      <div className="text-[11px] text-slate-600 bg-white/90 p-2.5 rounded-lg border border-slate-200/80">
        <span className="font-semibold text-slate-700">Căn cứ chỉ thị:</span> {instruction.basis}
      </div>
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
    <section aria-labelledby="approval-title" className="bg-white border border-slate-200 rounded-xl p-5 text-xs shadow-xs space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <div>
          <h2 id="approval-title" className="text-sm font-bold text-slate-900 tracking-tight">
            Lệnh chi / thu cần thực hiện ({active.length})
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Chỉ thị thanh toán hoặc thu hồi tiền sau khi đối soát xong
          </p>
        </div>
      </div>

      {active.length === 0 ? (
        <p className="text-slate-400 italic text-xs py-4 text-center">
          Chưa có yêu cầu chi/thu nào cần thực hiện trong hồ sơ này.
        </p>
      ) : (
        <ul className="instructions space-y-2.5">
          {active.map((instruction) => (
            <InstructionRow key={instruction.id} instruction={instruction} />
          ))}
        </ul>
      )}
    </section>
  );
}
