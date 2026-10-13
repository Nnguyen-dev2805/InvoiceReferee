import { useState } from "react";

import { answerIssue, errorMessage } from "../api";
import type { CaseView, IssueView } from "../types";

const KIND_LABELS: Record<string, string> = {
  FACT: "Dữ kiện",
  POLICY: "Chính sách",
  AUTHORITY: "Quyền",
};

/** One answerable question card: known basis, the exact answer required, owner. */
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
          reason: reason || "Trả lời từ thẻ câu hỏi",
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
    <li className="question-card" data-testid={`question-${issue.kind}`}>
      <p>
        <strong>[{KIND_LABELS[issue.kind] ?? issue.kind}]</strong> {issue.question}
      </p>
      <p className="muted">
        Người xử lý: {issue.owner} · Căn cứ: {issue.basis}
      </p>
      <p>
        <label htmlFor={`answer-${issue.id}`}>
          Trả lời
          <input
            id={`answer-${issue.id}`}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
      </p>
      <p>
        <label htmlFor={`reason-${issue.id}`}>
          Lý do
          <input
            id={`reason-${issue.id}`}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
      </p>
      <p>
        <button type="button" onClick={() => void submit()} disabled={busy || value === ""}>
          Gửi câu trả lời
        </button>
      </p>
      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </li>
  );
}

export function Questions({
  caseView,
  onCase,
}: {
  caseView: CaseView | null;
  onCase: (view: CaseView) => void;
}) {
  if (caseView === null || caseView.issues.length === 0) return null;
  return (
    <section aria-labelledby="questions-title">
      <h2 id="questions-title">Câu hỏi cần trả lời ({caseView.issues.length})</h2>
      <ul className="questions">
        {caseView.issues.map((issue) => (
          <QuestionCard key={issue.id} issue={issue} caseView={caseView} onCase={onCase} />
        ))}
      </ul>
    </section>
  );
}
