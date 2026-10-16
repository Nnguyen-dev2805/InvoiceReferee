import { useEffect, useState } from "react";

import {
  decideIssues,
  errorMessage,
  exceptionPreview,
  ocrPreviewUrl,
  refuseException,
  type ExceptionPreview,
} from "../api";
import { formatVnd } from "../format";
import type { CaseView, EvidenceRefView, IssueView } from "../types";

/** One boxed OCR region: image + file/page/quote + original link (S6 §7). */
export function OcrRegionView({
  caseView,
  reference,
  onSourceSelected,
}: {
  caseView: CaseView;
  reference: EvidenceRefView;
  onSourceSelected?: (sourceId: string) => void;
}) {
  const [failed, setFailed] = useState(false);
  const filename =
    caseView.sources.find((s) => s.id === reference.source_id)?.filename ??
    reference.source_id;
  const bbox = reference.bbox ?? null;
  if (bbox === null || failed) {
    return (
      <div className="rounded border border-slate-200 px-2.5 py-2 text-[11px] text-slate-600 space-y-1">
        <p className="font-medium text-slate-800">
          {filename}
          {reference.page ? ` · Trang ${reference.page}` : ""}
        </p>
        <p className="italic border-l-2 border-slate-300 pl-2">“{reference.exact_quote}”</p>
        {bbox === null && (
          <p className="text-slate-400">Không có vùng bbox nguồn — xem bản gốc để đối chiếu.</p>
        )}
        {onSourceSelected && (
          <button
            type="button"
            onClick={() => onSourceSelected(reference.source_id)}
            className="font-medium text-slate-900 underline underline-offset-2 cursor-pointer"
          >
            Mở bản gốc
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="rounded border border-slate-200 overflow-hidden">
      <img
        src={ocrPreviewUrl(caseView.id, reference.source_id, reference.page, bbox)}
        alt={`Vùng OCR cần kiểm tra trên ${filename}`}
        loading="lazy"
        onError={() => setFailed(true)}
        className="w-full block"
      />
      <div className="px-2.5 py-2 text-[11px] text-slate-600 space-y-1">
        <p className="font-medium text-slate-800">
          {filename}
          {reference.page ? ` · Trang ${reference.page}` : ""}
        </p>
        <p className="italic border-l-2 border-slate-300 pl-2">“{reference.exact_quote}”</p>
        {onSourceSelected && (
          <button
            type="button"
            onClick={() => onSourceSelected(reference.source_id)}
            className="font-medium text-slate-900 underline underline-offset-2 cursor-pointer"
          >
            Mở bản gốc
          </button>
        )}
      </div>
    </div>
  );
}

/** Accountant exception review for one missing-evidence POLICY (S6 §6). */
export function ExceptionReview({
  issue,
  caseView,
  onCase,
  onSourceSelected,
}: {
  issue: IssueView;
  caseView: CaseView;
  onCase: (view: CaseView) => void;
  onSourceSelected?: (sourceId: string) => void;
}) {
  const [preview, setPreview] = useState<ExceptionPreview | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await exceptionPreview(caseView.id, issue.id);
        if (!cancelled) setPreview(result);
      } catch (cause) {
        if (!cancelled) setError(errorMessage(cause));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [caseView.id, issue.id]);

  const openFacts = caseView.issues.filter(
    (i) =>
      i.kind === "FACT" &&
      i.status === "OPEN" &&
      preview?.expense_id !== null &&
      i.field_or_rule.startsWith(`${preview?.expense_id}:`),
  );

  async function accept() {
    if (!preview || preview.amount === null) return;
    if (!reason.trim()) {
      setError("Chấp nhận ngoại lệ cần có lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await decideIssues(
        caseView.id,
        {
          issue_ids: [issue.id],
          basis_id: `basis:${issue.id}`,
          actions: ["EXCEPT_POLICY"],
          effect_scope: caseView.activity ?? "",
          amount: preview.amount,
          reason: reason.trim(),
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

  async function refuse() {
    if (!reason.trim()) {
      setError("Từ chối ngoại lệ cần có lý do.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await refuseException(
        caseView.id,
        { issue_ids: [issue.id], reason: reason.trim() },
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
    <div className="space-y-3 text-xs max-w-2xl" data-testid="exception-review">
      <div>
        <h4 className="font-semibold text-slate-900 text-sm leading-relaxed">
          Xét ngoại lệ thiếu chứng từ gốc
        </h4>
        <p className="text-slate-600 text-xs leading-relaxed mt-1">{issue.basis}</p>
        <p className="text-slate-600 text-xs leading-relaxed mt-1">
          <strong>Cần xử lý:</strong> {issue.question}
        </p>
      </div>

      {preview?.amount !== null && preview?.amount !== undefined && (
        <p className="text-xs text-slate-800 tabular-nums">
          Số tiền hiệu lực: <strong>{formatVnd(preview.amount)}</strong>
        </p>
      )}

      {openFacts.length > 0 && (
        <div className="rounded border border-rose-200 bg-rose-50 px-3 py-2 space-y-1">
          <p className="font-semibold text-rose-900 text-xs">
            FACT còn mở ({openFacts.length}) — ngoại lệ không đóng các FACT này:
          </p>
          <ul className="list-disc pl-4 text-rose-900 text-[11px] space-y-0.5">
            {openFacts.map((f) => (
              <li key={f.id}>{f.basis}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="space-y-2">
        <p className="font-semibold text-slate-900 text-xs">Căn cứ hai phía</p>
        {(issue.refs ?? []).map((ref, idx) => (
          <OcrRegionView
            key={`${ref.source_id}:${ref.page}:${idx}`}
            caseView={caseView}
            reference={ref}
            onSourceSelected={onSourceSelected}
          />
        ))}
      </div>

      <div className="rounded border border-slate-200 px-3 py-2 space-y-1">
        <p className="font-semibold text-slate-900 text-xs">Quyền và hạn mức</p>
        {preview === null ? (
          <p className="text-slate-500 text-[11px]">Đang kiểm tra quyền…</p>
        ) : (
          <>
            <p className="text-[11px] text-slate-600">
              Rule: <span className="font-mono">{preview.rule_id ?? "—"}</span>
            </p>
            {preview.grants.length === 0 ? (
              <p className="text-amber-800 text-[11px] font-medium">
                ⚠ Bạn chưa có grant EXCEPT_POLICY hiệu lực cho khoản này — hành động
                chấp nhận sẽ bị chặn. Vượt hạn mức hoặc hết hiệu lực cũng bị chặn.
              </p>
            ) : (
              <ul className="text-[11px] text-slate-600 space-y-0.5">
                {preview.grants.map((g) => (
                  <li key={g.id} className="font-mono">
                    {g.id} · tối đa {formatVnd(g.max_amount)}
                    {g.effective_to ? ` · đến ${g.effective_to.slice(0, 10)}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {error && (
        <p role="alert" className="text-rose-700 text-xs">{error}</p>
      )}

      <div className="space-y-1.5">
        <label htmlFor={`exception-reason-${issue.id}`} className="text-xs font-medium text-slate-900">
          Lý do quyết định *
        </label>
        <textarea
          id={`exception-reason-${issue.id}`}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Nêu rõ lý do chấp nhận/từ chối ngoại lệ…"
          className="w-full text-xs border border-slate-300 rounded px-3 py-2 focus:outline-none focus:border-slate-900"
        />
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void accept()}
          disabled={busy || preview === null || !preview.covered}
          title={preview !== null && !preview.covered ? "Thiếu quyền hoặc vượt hạn mức" : undefined}
          className="bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white font-medium text-xs px-4 py-2 rounded cursor-pointer"
        >
          Chấp nhận ngoại lệ
        </button>
        <button
          type="button"
          onClick={() => void refuse()}
          disabled={busy}
          className="border border-slate-300 hover:border-slate-500 text-slate-800 font-medium text-xs px-4 py-2 rounded cursor-pointer"
        >
          Không chấp nhận
        </button>
      </div>
      <p className="text-[11px] text-slate-400">
        Xác minh dữ kiện, chấp nhận ngoại lệ, xác nhận tiền và đóng hồ sơ là các
        bước riêng — không có nút duyệt tất cả.
      </p>
    </div>
  );
}
