import type { CaseView } from "../types";

export function parseAuditLine(line: string) {
  const parts = line.split(" · ");
  if (parts.length >= 3) {
    const rawTime = parts[0];
    const rawActor = parts[1];
    const rawAction = parts.slice(2).join(" · ");

    let formattedTime = rawTime;
    try {
      const d = new Date(rawTime);
      if (!isNaN(d.getTime())) {
        const hh = String(d.getHours()).padStart(2, "0");
        const mm = String(d.getMinutes()).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        const mo = String(d.getMonth() + 1).padStart(2, "0");
        const yyyy = d.getFullYear();
        formattedTime = `${hh}:${mm} · ${dd}/${mo}/${yyyy}`;
      }
    } catch {
      // keep rawTime
    }

    let humanActor = rawActor;
    if (rawActor.includes("referee") || rawActor.includes("system")) {
      humanActor = "Hệ thống tự động";
    } else if (rawActor.includes("employee")) {
      humanActor = "Nhân viên đề nghị";
    } else if (rawActor.includes("accountant")) {
      humanActor = "Kế toán viên";
    } else if (rawActor.includes("approver")) {
      humanActor = "Cấp phê duyệt";
    }

    let humanAction = rawAction;
    if (rawAction === "CREATE_DRAFT") humanAction = "Khởi tạo hồ sơ nháp";
    else if (rawAction === "ATTACH_SOURCES") humanAction = "Tải lên chứng từ gốc";
    else if (rawAction === "RECORD_EMPLOYEE_PAID_CLAIMS") humanAction = "Ghi nhận xác nhận thanh toán (Q32)";
    else if (rawAction === "ASSESS") humanAction = "Thẩm định & Đối soát tài chính";
    else if (rawAction === "EMERGENCY_STOP" || rawAction === "STOP") humanAction = "Dừng xử lý khẩn cấp (§6)";
    else if (rawAction === "RESUME") humanAction = "Tiếp tục xử lý hồ sơ";
    else if (rawAction === "RECORD_ACTUAL_MONEY") humanAction = "Ghi nhận dòng tiền thực tế";

    return { formattedTime, rawTime, rawActor, humanActor, rawAction, humanAction };
  }
  return { formattedTime: line, rawTime: line, rawActor: "", humanActor: "", rawAction: "", humanAction: line };
}

export function DebugModal({
  caseView,
  isOpen,
  onClose,
}: {
  caseView: CaseView | null;
  isOpen: boolean;
  onClose: () => void;
}) {
  if (!isOpen) return null;

  const audit = caseView?.audit ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4 select-none">
      <div className="bg-white rounded-xl shadow-2xl border border-slate-200 max-w-2xl w-full p-6 animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-3.5 border-b border-slate-200 shrink-0">
          <div>
            <h2 className="text-sm font-bold text-slate-900 tracking-tight">
              Nhật ký kiểm toán &amp; Debug hồ sơ
            </h2>
            <p className="text-[11px] text-slate-500 font-medium">
              Toàn bộ lịch sử can thiệp, mốc thời gian và trạng thái kỹ thuật (Audit Trail)
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-2.5 py-1 rounded hover:bg-slate-100 text-slate-600 hover:text-slate-900 text-xs font-semibold cursor-pointer transition-colors border border-slate-200"
            title="Đóng (Close)"
          >
            Đóng
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto custom-scrollbar py-4 space-y-4 flex-1">
          {/* Metadata quick bar */}
          {caseView !== null ? (
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 flex flex-wrap gap-4 text-xs font-mono-nums">
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-sans block">ID Hồ sơ</span>
                <span className="font-semibold text-slate-800">{caseView.id}</span>
              </div>
              <div className="border-l border-slate-200 pl-4">
                <span className="text-slate-400 text-[10px] uppercase font-sans block">Phiên bản</span>
                <span className="font-semibold text-slate-800">v{caseView.version}</span>
              </div>
              <div className="border-l border-slate-200 pl-4">
                <span className="text-slate-400 text-[10px] uppercase font-sans block">Trạng thái máy</span>
                <span className="font-semibold text-slate-800">{caseView.state}</span>
              </div>
              <div className="border-l border-slate-200 pl-4">
                <span className="text-slate-400 text-[10px] uppercase font-sans block">Số sự kiện</span>
                <span className="font-semibold text-slate-800">{audit.length} entries</span>
              </div>
            </div>
          ) : (
            <div className="text-center py-6 text-slate-400 text-xs">
              Chưa có hồ sơ nào được mở.
            </div>
          )}

          {/* Timeline */}
          {audit.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wide">
                Lịch sử tuần tự (Mới nhất ở dưới)
              </h3>
              <div className="border border-slate-200 rounded-lg p-4 bg-white shadow-2xs">
                <ol className="relative border-l border-slate-200 ml-2 space-y-3.5 my-1" data-testid="controls-audit">
                  {audit.map((line, index) => {
                    const parsed = parseAuditLine(line);
                    return (
                      <li key={`${index}-${line}`} className="ml-4">
                        <span className="absolute -left-1.5 mt-1.5 w-2.5 h-2.5 rounded-full border-2 border-white bg-slate-500"></span>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-bold text-slate-900">
                            {parsed.humanAction}
                          </span>
                          <span className="text-[11px] font-mono-nums text-slate-400">
                            {parsed.formattedTime}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-500">
                          <span className="font-medium text-slate-700">{parsed.humanActor}</span>
                          <span className="text-slate-300">·</span>
                          <span className="text-slate-400 font-mono-nums text-[10px]">{parsed.rawAction}</span>
                          <span className="text-slate-300">·</span>
                          <span className="text-slate-400 font-mono-nums text-[10px] truncate max-w-[200px]" title={parsed.rawActor}>
                            {parsed.rawActor}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>
          )}

          {/* Raw JSON inspection toggle */}
          {caseView !== null && (
            <details className="text-xs border border-slate-200 rounded-lg p-3 bg-slate-50/70">
              <summary className="font-semibold text-slate-700 cursor-pointer select-none flex items-center justify-between">
                <span>Dữ liệu thô máy chủ (Raw Case JSON)</span>
                <span className="text-[11px] text-slate-400 font-normal">Nhấp để xem</span>
              </summary>
              <pre className="mt-2 text-[10.5px] p-2 bg-slate-900 text-slate-100 rounded-md overflow-x-auto max-h-48 font-mono-nums">
                {JSON.stringify(caseView, null, 2)}
              </pre>
            </details>
          )}
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-slate-200 flex justify-end shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs rounded-lg transition-colors cursor-pointer"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
