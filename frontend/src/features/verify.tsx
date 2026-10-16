import { useEffect, useState } from "react";

import {
  errorMessage,
  getLastVerify,
  runVerify,
  type VerifyReportView,
  type VerifyRowView,
} from "../api";

export function Verify({
  isOpen = false,
  onClose,
}: {
  isOpen?: boolean;
  onClose?: () => void;
}) {
  const [report, setReport] = useState<VerifyReportView | null>(null);
  const [busy, setBusy] = useState(false);
  const [busySuite, setBusySuite] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"RECORDED_REPLAY" | "LIVE">("RECORDED_REPLAY");
  const [showLiveWarning, setShowLiveWarning] = useState(false);
  const [pendingSuite, setPendingSuite] = useState<"core" | "escalation" | null>(null);

  useEffect(() => {
    let active = true;
    void getLastVerify()
      .then((existing) => {
        if (active && existing) {
          setReport(existing);
        }
      })
      .catch(() => {
        // Ignore background load error
      });
    return () => {
      active = false;
    };
  }, []);

  async function executeRun(suite: "core" | "escalation", runMode: string) {
    setBusy(true);
    setBusySuite(suite);
    setError(null);
    try {
      const res = await runVerify(suite, runMode);
      setReport(res);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
      setBusySuite(null);
    }
  }

  function handleStartRun(suite: "core" | "escalation") {
    if (mode === "LIVE") {
      setPendingSuite(suite);
      setShowLiveWarning(true);
    } else {
      void executeRun(suite, "RECORDED_REPLAY");
    }
  }

  function confirmLiveRun() {
    setShowLiveWarning(false);
    if (pendingSuite) {
      void executeRun(pendingSuite, "LIVE");
      setPendingSuite(null);
    }
  }

  if (onClose && !isOpen) return null;

  // Status derivation according to Prompt §6
  let statusText = "Chưa chạy";
  let statusBadgeClass = "bg-slate-100 text-slate-700 border-slate-200";

  if (busy) {
    statusText = `Đang chạy ${busySuite ? (busySuite === "core" ? "Core4" : "Escalation5") : ""}...`;
    statusBadgeClass = "bg-amber-50 text-amber-800 border-amber-200 animate-pulse";
  } else if (error) {
    statusText = "Lỗi thực thi";
    statusBadgeClass = "bg-rose-50 text-rose-800 border-rose-200";
  } else if (report) {
    if (report.status === "NEEDS_RECORDING") {
      statusText = "Chưa có recording thật phù hợp";
      statusBadgeClass = "bg-amber-50 text-amber-800 border-amber-200";
    } else if (report.status === "ERROR") {
      statusText = "Lỗi thực thi";
      statusBadgeClass = "bg-rose-50 text-rose-800 border-rose-200";
    } else if (report.release) {
      statusText = "Đạt bộ kiểm thử này";
      statusBadgeClass = "bg-emerald-50 text-emerald-800 border-emerald-200 font-semibold";
    } else {
      statusText = "Không đạt";
      statusBadgeClass = "bg-rose-50 text-rose-800 border-rose-200 font-semibold";
    }
  }

  const formatAmounts = (amounts: Record<string, number> | undefined) => {
    if (!amounts || Object.keys(amounts).length === 0) return "—";
    return Object.entries(amounts)
      .map(([dir, amt]) => `${dir} ${amt.toLocaleString("vi-VN")}`)
      .join(", ");
  };

  const content = (
    <section aria-labelledby="verify-title" className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2">
            <h2 id="verify-title" className="text-sm font-bold text-slate-900">
              Kiểm chuẩn Benchmark
            </h2>
            <span
              data-testid="verify-status-badge"
              className={`px-2 py-0.5 rounded text-[11px] border ${statusBadgeClass}`}
            >
              {statusText}
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Bộ kiểm thử phát triển: Core4 gồm 4 ca; Escalation5 gồm 3 thường quy và 2 cần người xử lý.
          </p>
        </div>

        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="px-2.5 py-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 text-xs font-semibold cursor-pointer border border-slate-200"
          >
            Đóng
          </button>
        )}
      </div>

      <p className="text-xs text-slate-500">Replay cần bản ghi OCR/LLM thật tương thích. Fixture viết tay không được tính là recording. Đây không phải kết quả holdout hay chứng nhận production.</p>
      {/* Mode selection & Action buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
        {/* Mode radio */}
        <div className="flex items-center gap-4 text-xs">
          <span className="font-semibold text-slate-700">Chế độ:</span>
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-800">
            <input
              type="radio"
              name="verify-mode"
              value="RECORDED_REPLAY"
              checked={mode === "RECORDED_REPLAY"}
              onChange={() => setMode("RECORDED_REPLAY")}
              disabled={busy}
              className="text-slate-900 focus:ring-slate-900"
            />
            <span>Replay đã ghi sẵn (Offline, 0 provider call)</span>
          </label>

          <label className="flex items-center gap-1.5 cursor-pointer text-slate-800">
            <input
              type="radio"
              name="verify-mode"
              value="LIVE"
              checked={mode === "LIVE"}
              onChange={() => setMode("LIVE")}
              disabled={busy}
              className="text-slate-900 focus:ring-slate-900"
            />
            <span className="text-amber-800 font-medium">LIVE (Kimi-K3 provider thật)</span>
          </label>
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="run-core-btn"
            onClick={() => handleStartRun("core")}
            disabled={busy}
            className="bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs px-3.5 py-1.5 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
          >
            Chạy Core4 (4 ca)
          </button>

          <button
            type="button"
            data-testid="run-escalation-btn"
            onClick={() => handleStartRun("escalation")}
            disabled={busy}
            className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-3.5 py-1.5 rounded shadow-2xs transition-colors disabled:opacity-40 cursor-pointer"
          >
            Chạy Escalation5 (5 ca)
          </button>
        </div>
      </div>

      {/* Live Warning Confirmation Modal */}
      {showLiveWarning && (
        <div
          role="alertdialog"
          className="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-2 animate-in fade-in"
        >
          <div className="font-semibold flex items-center gap-1.5 text-amber-950">
            <span>Cảnh báo sử dụng Quota LIVE</span>
          </div>
          <p>
            Chế độ LIVE sẽ gửi toàn bộ tài liệu lên nhà cung cấp Kimi-K3 và tiêu tốn quota thực tế.
            Bạn có chắc chắn muốn tiến hành chạy bộ kiểm thử {pendingSuite === "core" ? "Core4" : "Escalation5"} ở chế độ LIVE không?
          </p>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={confirmLiveRun}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white font-semibold rounded text-xs cursor-pointer"
            >
              Xác nhận chạy LIVE
            </button>
            <button
              type="button"
              onClick={() => {
                setShowLiveWarning(false);
                setPendingSuite(null);
              }}
              className="px-3 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 font-semibold rounded text-xs cursor-pointer"
            >
              Hủy
            </button>
          </div>
        </div>
      )}

      {/* Error display */}
      {error !== null && (
        <p
          role="alert"
          className="error p-2.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 text-xs"
        >
          {error}
        </p>
      )}

      {/* Report view */}
      {report !== null && (
        <div data-testid="verify-report" className="space-y-3 pt-1">
          {/* Header metadata */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] bg-slate-50 p-2.5 rounded-lg border border-slate-200 font-mono-nums">
            <div>
              <span className="text-slate-500 block">Lượt chạy (Run ID):</span>
              <strong className="text-slate-800 truncate block" title={report.run_id}>
                {report.run_id}
              </strong>
            </div>
            <div>
              <span className="text-slate-500 block">Bộ kiểm / Chế độ:</span>
              <strong className="text-slate-800">
                {report.suite.toUpperCase()} ({report.mode})
              </strong>
            </div>
            <div>
              <span className="text-slate-500 block">Tiến độ thực thi:</span>
              <span>
                Đã chạy: <strong>{report.completed}</strong>/{report.planned} · Đạt:{" "}
                <strong className={report.passed === report.planned ? "text-emerald-700" : "text-rose-700"}>
                  {report.passed}
                </strong>
              </span>
            </div>
            <div>
              <span className="text-slate-500 block">Lỗi nguy hiểm / Thời gian:</span>
              <span>
                Lỗi bỏ sót: <strong className={report.union_dangerous_miss === 0 ? "text-emerald-700" : "text-rose-700"}>{report.union_dangerous_miss}</strong> ·{" "}
                {Math.round(report.elapsed_ms)} ms
              </span>
            </div>
          </div>

          {/* Versions bar */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-500 px-1 font-mono-nums">
            <span>Mã nguồn: {report.versions?.code?.slice(0, 8)} · Cấu hình: {report.versions?.config}</span>
            <span>Dataset: {report.versions?.dataset ?? "Chưa xác thực"} · Bản ghi: {report.versions?.recording}</span>
            <span>Bắt đầu: {report.started_at} · Kết thúc: {report.finished_at}</span>
            <span>Chất lượng câu hỏi: chưa được người đánh giá (NOT_REVIEWED)</span>
          </div>

          {/* Table of cases */}
          <div className="overflow-x-auto border border-slate-200 rounded-lg max-h-80 custom-scrollbar">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-[11px] font-semibold sticky top-0">
                <tr>
                  <th className="p-2.5">Hồ sơ</th>
                  <th className="p-2.5 text-center">Kết quả</th>
                  <th className="p-2.5">Tuyến đường</th>
                  <th className="p-2.5">Số tiền quyết toán</th>
                  <th className="p-2.5">Câu hỏi / Chủ thể</th>
                  <th className="p-2.5">Lý do không đạt</th>
                  <th className="p-2.5 text-right">Thời gian</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono-nums text-[11px]">
                {report.rows.map((row: VerifyRowView) => (
                  <tr key={row.root_id} className="hover:bg-slate-50/70">
                    <td className="p-2.5 text-slate-900 font-medium whitespace-nowrap">
                      {row.root_id}
                    </td>
                    <td className="p-2.5 text-center whitespace-nowrap">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          row.passed
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-rose-100 text-rose-800"
                        }`}
                      >
                        {row.passed ? "ĐẠT" : "KHÔNG ĐẠT"}
                      </span>
                    </td>
                    <td className="p-2.5 text-slate-700 whitespace-nowrap">
                      <span>{row.actual_route}</span>
                      {row.actual_route !== row.expected_route && (
                        <span className="text-slate-400 block text-[10px]">
                          (Kỳ vọng: {row.expected_route})
                        </span>
                      )}
                    </td>
                    <td className="p-2.5 text-slate-800 whitespace-nowrap">
                      <span>{formatAmounts(row.actual_amounts)}</span>
                      {JSON.stringify(row.actual_amounts) !== JSON.stringify(row.expected_amounts) && (
                        <span className="text-slate-400 block text-[10px]">
                          (Kỳ vọng: {formatAmounts(row.expected_amounts)})
                        </span>
                      )}
                    </td>
                    <td className="p-2.5 text-slate-600 text-[10px]">
                      {row.actual_issues?.map((issue,index)=><div key={index} className="mb-1"><strong>{issue.kind} · {issue.owner}</strong><p>{issue.question}</p>{issue.refs?.map((ref,i)=><p key={i}>{ref.source_id} · trang {ref.page}: {ref.exact_quote}</p>)}</div>)}
                      {row.question_required ? (
                        row.question_present ? (
                          <span className="text-emerald-700">Đã nêu câu hỏi ({row.actual_owner || "người duyệt"})</span>
                        ) : (
                          <span className="text-rose-700">Thiếu câu hỏi</span>
                        )
                      ) : (
                        <span className="text-slate-400">Không yêu cầu</span>
                      )}
                    </td>
                    <td className="p-2.5 text-rose-700 text-[10px]">
                      {row.failure_reasons && row.failure_reasons.length > 0
                        ? row.failure_reasons.join(", ")
                        : "—"}
                    </td>
                    <td className="p-2.5 text-right font-medium text-slate-500 whitespace-nowrap">
                      {Math.round(row.elapsed_ms)} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );

  if (onClose) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
        <div className="bg-white rounded border border-slate-200 shadow-xl max-w-4xl w-full p-6 animate-in fade-in zoom-in-95 duration-150">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded p-5 text-xs">
      {content}
    </div>
  );
}
