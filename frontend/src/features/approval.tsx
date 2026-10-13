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
    <li data-testid={`instruction-${instruction.direction}`}>
      <p>
        <strong>{DIRECTION_LABELS[instruction.direction] ?? instruction.direction}</strong>:{" "}
        {formatVnd(instruction.amount)}
      </p>
      <p className="muted">
        Còn lại: {formatVnd(instruction.remaining)} · Trạng thái:{" "}
        {instruction.status} · Thực hiện:{" "}
        {EXECUTION_LABELS[instruction.execution_state] ?? instruction.execution_state}
      </p>
      <p className="muted">Căn cứ: {instruction.basis}</p>
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
    <section aria-labelledby="approval-title">
      <h2 id="approval-title">Yêu cầu cần thực hiện ({active.length})</h2>
      {active.length === 0 ? (
        <p className="muted">Chưa có yêu cầu chi/thu nào cần thực hiện.</p>
      ) : (
        <ul className="instructions">
          {active.map((instruction) => (
            <InstructionRow key={instruction.id} instruction={instruction} />
          ))}
        </ul>
      )}
    </section>
  );
}
