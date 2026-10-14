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
    <li
      className="question-card p-3 bg-amber-50/40 border border-amber-200 rounded space-y-2 text-xs"
      data-testid={`question-${issue.kind}`}
    >
      <div className="flex items-center justify-between pb-1 border-b border-amber-200/60">
        <span className="font-semibold text-amber-950">
          <strong>[{KIND_LABELS[issue.kind] ?? issue.kind}]</strong> {issue.question}
        </span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-100 text-amber-800 font-['JetBrains_Mono']">
          {issue.kind}
        </span>
      </div>
      <p className="muted text-[11px] text-slate-600">
        Người xử lý: <strong className="text-slate-800">{issue.owner}</strong> · Căn cứ: {issue.basis}
      </p>
      <div className="space-y-2 pt-1">
        <p>
          <label htmlFor={`answer-${issue.id}`} className="text-slate-700 block font-medium">
            Trả lời
            <input
              id={`answer-${issue.id}`}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              placeholder="Nhập nội dung trả lời..."
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            />
          </label>
        </p>
        <p>
          <label htmlFor={`reason-${issue.id}`} className="text-slate-700 block font-medium">
            Lý do
            <input
              id={`reason-${issue.id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Nhập lý do hoặc căn cứ..."
              className="w-full mt-1 bg-white border border-slate-200 rounded text-xs px-2.5 py-1.5 text-slate-800 focus:outline-none focus:border-slate-400"
            />
          </label>
        </p>
      </div>
      <p className="pt-1">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={busy || value === ""}
          className="bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs px-3.5 py-1.5 rounded shadow-sm transition-colors disabled:opacity-40"
        >
          Gửi câu trả lời
        </button>
      </p>
      {error !== null && (
        <p role="alert" className="error p-2 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
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
    <section aria-labelledby="questions-title" className="bg-white border border-slate-200 rounded p-4 text-xs shadow-sm space-y-3">
      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
        <h2 id="questions-title" className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-amber-600 text-sm" aria-hidden="true">help</span>
          <span>Câu hỏi cần trả lời ({caseView.issues.length})</span>
        </h2>
      </div>
      <ul className="questions space-y-2.5">
        {caseView.issues.map((issue) => (
          <QuestionCard key={issue.id} issue={issue} caseView={caseView} onCase={onCase} />
        ))}
      </ul>
    </section>
  );
}
