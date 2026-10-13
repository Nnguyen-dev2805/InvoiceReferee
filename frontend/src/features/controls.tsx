import { useState } from "react";

import { controlCase, errorMessage } from "../api";
import type { CaseView } from "../types";

/** Stop/Resume controls for the accountant, plus the audit trail. */
export function Controls({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (caseView === null) return null;

  async function control(action: "STOP" | "RESUME") {
    if (caseView === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await controlCase(caseView.id, action, `${action} bởi người dùng`);
      onCase(result.case_view);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="controls-title">
      <h2 id="controls-title">Kiểm soát</h2>
      <p>
        <button type="button" onClick={() => void control("STOP")} disabled={busy}>
          Dừng hồ sơ
        </button>
        <button type="button" onClick={() => void control("RESUME")} disabled={busy}>
          Tiếp tục
        </button>
      </p>
      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <h3>Lịch sử kiểm toán</h3>
      <ul className="audit" data-testid="controls-audit">
        {caseView.audit.map((line, index) => (
          <li key={`${index}-${line}`}>{line}</li>
        ))}
      </ul>
    </section>
  );
}
