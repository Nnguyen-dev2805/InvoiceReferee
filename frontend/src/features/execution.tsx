import { useState } from "react";

import { errorMessage, recordActual } from "../api";
import { formatVnd } from "../format";
import type { CaseView } from "../types";

const MONEY_LABELS: Record<string, string> = {
  P: "Đã hoàn",
  R: "Đã thu hồi",
  A: "Ứng thực nhận",
};

/** The accountant records actual money moved (bank/cash) against a root. */
export function Execution({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [amount, setAmount] = useState("");
  const [payee, setPayee] = useState("employee:employee-a");
  const [completionClaim, setCompletionClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  if (caseView === null) return null;

  async function record() {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const result = await recordActual(caseView.id, {
        external_key: `bank:${crypto.randomUUID()}`,
        claimed_kind: "REIMBURSEMENT_RECEIVED",
        claimed_scope: "activity:travel-a",
        payer: "company:demo",
        payee,
        amount: Number(amount),
        event_at: new Date().toISOString(),
        // A bare amount is not proof: the accountant must confirm the transfer
        // responsibly, or the money stays observed and does not fulfill (§4).
        completion_claim: completionClaim || null,
        reason: "Ghi nhận tiền thực tế",
      });
      onCase(result.case_view);
      setStatus("Đã ghi nhận tiền thực tế.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="execution-title">
      <h2 id="execution-title">Ghi nhận tiền thực tế</h2>
      <ul className="money">
        {Object.entries(caseView.actual_money)
          .filter(([key]) => key in MONEY_LABELS)
          .map(([key, fact]) => (
            <li key={key} data-testid={`actual-${key}`}>
              {MONEY_LABELS[key]}:{" "}
              <strong>
                {fact.state === "KNOWN" && fact.value !== null
                  ? formatVnd(fact.value)
                  : "Chưa xác minh"}
              </strong>
            </li>
          ))}
      </ul>
      <p>
        <label htmlFor="received-amount">
          Số tiền đã nhận
          <input
            id="received-amount"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
      </p>
      <p>
        <label htmlFor="received-payee">
          Người nhận
          <input
            id="received-payee"
            value={payee}
            onChange={(event) => setPayee(event.target.value)}
          />
        </label>
      </p>
      <p>
        <label htmlFor="completion-claim">
          Xác nhận đã chuyển (bắt buộc để tính là đã thực hiện)
          <input
            id="completion-claim"
            value={completionClaim}
            onChange={(event) => setCompletionClaim(event.target.value)}
          />
        </label>
      </p>
      <p>
        <button type="button" onClick={() => void record()} disabled={busy || amount === ""}>
          Ghi nhận
        </button>
      </p>
      {status !== null && (
        <p role="status" aria-live="polite" className="status">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
