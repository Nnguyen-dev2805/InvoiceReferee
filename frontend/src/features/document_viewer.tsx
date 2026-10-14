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
      {/* 1. Sleek Integrated Browser-like Tab & Action Bar (h-11) */}
      <div className="h-11 bg-slate-100 border-b border-slate-200 flex items-center justify-between px-2 gap-2 shrink-0">
        <div className="flex items-center gap-1 overflow-x-auto custom-scrollbar h-full pt-1.5 min-w-0">
          {allTabs.length === 0 ? (
            <span className="text-xs text-slate-400 font-medium px-2 py-1">
              Chưa có chứng từ được tải lên
            </span>
          ) : (
            allTabs.map((tab) => {
              const isSelected = activeTab?.id === tab.id;
              const tabIsPdf =
                tab.name.toLowerCase().endsWith(".pdf") ||
                tab.source?.media === "PDF" ||
                tab.file?.type === "application/pdf";
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setSelectedTabId(tab.id)}
                  className={`h-9 px-3 rounded-t-md text-xs flex items-center gap-2 transition-colors shrink-0 cursor-pointer border-t border-x ${
                    isSelected
                      ? "bg-white text-slate-900 font-semibold border-slate-200 shadow-2xs"
                      : "bg-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-200/50 border-transparent font-medium"
                  }`}
                >
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                    isSelected ? "bg-slate-100 text-slate-700" : "bg-slate-200/80 text-slate-500"
                  }`}>
                    {tabIsPdf ? "PDF" : "IMG"}
                  </span>
                  <span className="truncate max-w-[170px]">{tab.name}</span>
                  {tab.isPending && (
                    <span className="text-[10px] text-amber-600 font-normal italic">(chờ nộp)</span>
                  )}
                </button>
              );
            })
          )}
        </div>

        {documentUrl && (
          <div className="shrink-0 pr-1">
            <a
              href={documentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 px-2.5 py-1 rounded border border-slate-200 shadow-2xs transition-colors cursor-pointer"
              title="Mở tài liệu trong tab mới"
            >
              Mở tab mới ↗
            </a>
          </div>
        )}
      </div>

      {/* 2. Document Viewport (100% Height & Width) */}
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
              <label className="w-full max-w-sm border border-dashed border-slate-300 hover:border-slate-500 bg-white hover:bg-slate-50 rounded p-6 text-center flex flex-col items-center justify-center cursor-pointer transition-colors block group">
                <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 group-hover:text-slate-900 group-hover:bg-slate-200 mb-3 transition-colors">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <span className="font-semibold text-slate-800 block text-xs">
                  Nhấn để chọn tệp hoặc kéo thả tài liệu vào đây
                </span>
                <span className="text-[11px] text-slate-500 block mt-1">
                  Hỗ trợ PDF, PNG, JPG
                </span>
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
          <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-slate-900/5">
            <img
              src={documentUrl}
              alt={activeTab.name}
              className="max-w-full max-h-full object-contain rounded shadow-sm bg-white border border-slate-200"
            />
          </div>
        )}
      </div>
    </section>
  );
}
