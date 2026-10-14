import { useEffect, useMemo, useState } from "react";

import type { CaseView, SourceView } from "../types";

export interface DocumentViewerProps {
  caseView: CaseView | null;
  pendingFiles?: File[];
  onFilesSelected?: (files: File[]) => void;
}

export function DocumentViewer({
  caseView,
  pendingFiles = [],
  onFilesSelected,
}: DocumentViewerProps) {
  const sources = caseView?.sources ?? [];
  const [selectedTabId, setSelectedTabId] = useState<string | null>(null);

  // Active tab selection (deduplicated)
  const allTabs = useMemo(() => {
    const seenKeys = new Set<string>();
    const remote = [];
    for (const s of sources) {
      const key = s.digest ? s.digest : s.id;
      if (!seenKeys.has(key)) {
        seenKeys.add(key);
        remote.push({
          id: s.id,
          name: s.filename ?? s.id,
          isPending: false,
          source: s,
          file: null as File | null,
        });
      }
    }
    const local = [];
    for (let i = 0; i < pendingFiles.length; i++) {
      const f = pendingFiles[i];
      // Do not duplicate if remote source has the same filename
      if (!remote.some((r) => r.name === f.name)) {
        local.push({
          id: `pending-${i}-${f.name}`,
          name: f.name,
          isPending: true,
          source: null as SourceView | null,
          file: f,
        });
      }
    }
    return [...remote, ...local];
  }, [sources, pendingFiles]);

  const activeTab = allTabs.find((t) => t.id === selectedTabId) ?? allTabs[0] ?? null;

  // Generate URL for active document
  const documentUrl = useMemo(() => {
    if (!activeTab) return null;
    if (activeTab.isPending && activeTab.file) {
      return URL.createObjectURL(activeTab.file);
    }
    if (activeTab.source && caseView) {
      return `/api/cases/${caseView.id}/sources/${activeTab.source.id}`;
    }
    return null;
  }, [activeTab, caseView]);

  // Cleanup object URLs for pending files
  useEffect(() => {
    return () => {
      if (documentUrl && documentUrl.startsWith("blob:")) {
        URL.revokeObjectURL(documentUrl);
      }
    };
  }, [documentUrl]);

  const isPdf = activeTab?.name.toLowerCase().endsWith(".pdf") ||
    activeTab?.source?.media === "PDF" ||
    activeTab?.file?.type === "application/pdf";

  return (
    <section aria-label="Trình xem chứng từ gốc" className="h-full flex flex-col bg-slate-100 border-r border-slate-200 select-none overflow-hidden">
      {/* 1. Document Tab Bar */}
      <div className="h-11 bg-white border-b border-slate-200 flex items-center px-3 gap-1.5 shrink-0 overflow-x-auto custom-scrollbar">
        {allTabs.length === 0 ? (
          <span className="text-xs text-slate-400 font-medium px-2 py-1">
            Chưa có chứng từ được tải lên
          </span>
        ) : (
          allTabs.map((tab) => {
            const isSelected = activeTab?.id === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setSelectedTabId(tab.id)}
                className={`h-7 px-3 rounded-lg text-xs flex items-center gap-2 transition-all shrink-0 cursor-pointer ${
                  isSelected
                    ? "bg-slate-950 text-white font-semibold shadow-2xs"
                    : "bg-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium"
                }`}
              >
                <span className="truncate max-w-[180px]">{tab.name}</span>
                {tab.isPending ? (
                  <span className={`text-[10px] ${isSelected ? "text-amber-300" : "text-amber-700"} font-normal italic`}>(chờ nộp)</span>
                ) : (
                  <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono-nums ${
                    isSelected ? "bg-slate-800 text-slate-200" : "bg-slate-100 text-slate-600 border border-slate-200"
                  }`}>
                    {tab.source?.digest.slice(0, 6)}
                  </span>
                )}
              </button>
            );
          })
        )}
      </div>

      {/* 2. Document Toolbar */}
      <div className="h-9 bg-slate-50 border-b border-slate-200 flex items-center justify-between px-3.5 text-xs text-slate-600 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {activeTab ? (
            <>
              <span className="font-semibold text-slate-900 truncate text-xs">
                {activeTab.name}
              </span>
              <span className="text-[10px] text-slate-600 font-medium bg-white px-2 py-0.5 rounded border border-slate-200 shadow-2xs">
                {isPdf ? "Tài liệu PDF" : "Hình ảnh"}
              </span>
            </>
          ) : (
            <span className="text-slate-400 text-xs">Chứng từ gốc</span>
          )}
        </div>

        {documentUrl && (
          <div className="flex items-center gap-2">
            <a
              href={documentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-xs font-semibold text-slate-700 hover:text-slate-950 bg-white hover:bg-slate-50 px-2.5 py-1 rounded-md border border-slate-300 shadow-2xs transition-colors cursor-pointer"
              title="Mở tài liệu toàn màn hình trong tab mới"
            >
              Mở tab mới ↗
            </a>
          </div>
        )}
      </div>

      {/* 3. Real Document Viewport (100% Height & Width) */}
      <div className="flex-1 bg-slate-100 overflow-hidden relative flex flex-col">
        {!activeTab || !documentUrl ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-3">
            <div className="max-w-sm space-y-1">
              <h3 className="text-sm font-bold text-slate-800">
                Chưa chọn chứng từ để xem
              </h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Khi nhân viên tải lên hóa đơn điện tử hoặc giấy quyết toán dạng PDF/Ảnh, tài liệu gốc sẽ được hiển thị trực tiếp tại đây.
              </p>
            </div>
            {onFilesSelected && (
              <label className="inline-flex items-center bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold px-4 py-2 rounded cursor-pointer transition-colors shadow-2xs">
                <span>Chọn tệp PDF / Ảnh</span>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.png,.jpg,.jpeg"
                  onChange={(e) => {
                    if (e.target.files) {
                      onFilesSelected(Array.from(e.target.files));
                    }
                  }}
                  className="sr-only"
                />
              </label>
            )}
          </div>
        ) : isPdf ? (
          <iframe
            key={documentUrl}
            src={`${documentUrl}#toolbar=1&navpanes=0`}
            title={activeTab.name}
            className="w-full h-full border-0 bg-white"
          />
        ) : (
          <div className="flex-1 overflow-auto p-4 flex items-center justify-center">
            <img
              src={documentUrl}
              alt={activeTab.name}
              className="max-w-full max-h-full object-contain rounded-lg shadow-md bg-white border border-slate-300"
            />
          </div>
        )}
      </div>
    </section>
  );
}
