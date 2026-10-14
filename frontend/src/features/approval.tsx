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
      className={`p-3 rounded border space-y-2 text-xs transition-colors ${
        isPay
          ? "bg-emerald-50/40 border-emerald-200/80 text-emerald-950"
          : "bg-amber-50/40 border-amber-200/80 text-amber-950"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${isPay ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>
            {isPay ? "CHI" : "THU"}
          </span>
          <span className="font-semibold text-slate-900 text-xs">
            <strong>{DIRECTION_LABELS[instruction.direction] ?? instruction.direction}</strong>:{" "}
            <span className="font-mono-nums text-sm font-bold">{formatVnd(instruction.amount)}</span>
          </span>
        </div>
        <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-white border border-slate-200 font-mono-nums text-slate-700">
          {instruction.status}
        </span>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-slate-600 font-medium">
        <span>Còn lại: <strong className="font-mono-nums text-slate-900">{formatVnd(instruction.remaining)}</strong></span>
        <span className="text-slate-300">·</span>
        <span>Thực hiện: <strong>{EXECUTION_LABELS[instruction.execution_state] ?? instruction.execution_state}</strong></span>
      </div>

      <div className="text-[11px] text-slate-600 pl-2.5 border-l-2 border-slate-300 py-0.5">
        <span className="font-medium text-slate-700">Căn cứ chỉ thị:</span> {instruction.basis}
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
    <section aria-labelledby="approval-title" className="space-y-3 select-none text-xs">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="approval-title" className="text-xs font-semibold text-slate-900">
          Lệnh chi / thu ({active.length})
        </h2>
      </div>

      {active.length === 0 ? (
        <div className="bg-slate-50/60 border border-dashed border-slate-200 rounded p-5 text-center text-xs space-y-1.5">
          <p className="font-semibold text-slate-700">Chưa có lệnh chi hoặc thu cần thực hiện</p>
          <p className="text-slate-500 max-w-sm mx-auto text-[11px]">
            Sau khi hồ sơ được đối soát tài chính và cấp thẩm quyền phê duyệt, các lệnh thanh toán (chi bổ sung hoặc thu hồi) sẽ xuất hiện tại đây.
          </p>
        </div>
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
