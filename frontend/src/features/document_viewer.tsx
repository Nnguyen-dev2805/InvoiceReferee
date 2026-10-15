import { useEffect, useMemo, useRef, useState } from "react";

import type { CaseView, SourceView } from "../types";

export interface DocumentViewerProps {
  caseView: CaseView | null;
  pendingFiles?: File[];
  onFilesSelected?: (files: File[]) => void;
  selectedSourceId?: string | null;
  onSourceSelected?: (sourceId: string) => void;
}

export function DocumentViewer({
  caseView,
  pendingFiles = [],
  onFilesSelected,
  selectedSourceId = null,
  onSourceSelected,
}: DocumentViewerProps) {
  const sources = caseView?.sources ?? [];
  const [selectedTabId, setSelectedTabId] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside or Escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

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

  const activeTab = allTabs.find((t) => t.id === (selectedSourceId ?? selectedTabId)) ?? allTabs[0] ?? null;

  // Navigation indices
  const currentIndex = allTabs.findIndex((t) => t.id === activeTab?.id);
  const safeCurrentIndex = currentIndex >= 0 ? currentIndex : 0;
  const canGoPrev = safeCurrentIndex > 0;
  const canGoNext = safeCurrentIndex < allTabs.length - 1;

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
      {/* 1. Sleek Streamlined Document Switcher Bar (h-11) */}
      <div className="h-11 bg-white border-b border-slate-200 flex items-center justify-between px-3 gap-2 shrink-0 z-20">
        {allTabs.length === 0 ? (
          <span className="text-xs text-slate-400 font-medium px-1">
            Chưa có chứng từ được tải lên
          </span>
        ) : (
          <div className="flex items-center gap-1.5 min-w-0">
            {/* Quick Flipper / Navigation Controls */}
            <div className="flex items-center gap-0.5 shrink-0">
              <button
                type="button"
                aria-label="Chứng từ trước"
                disabled={!canGoPrev}
                onClick={() => {
                  if (canGoPrev) {
                    const prevTab = allTabs[safeCurrentIndex - 1];
                    setSelectedTabId(prevTab.id);
                    if (prevTab.source) onSourceSelected?.(prevTab.source.id);
                  }
                }}
                className="w-7 h-7 flex items-center justify-center rounded text-slate-500 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:pointer-events-none transition-colors cursor-pointer"
                title="Chứng từ trước"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                </svg>
              </button>

              <span className="text-[11px] font-mono font-medium text-slate-400 px-1 shrink-0 tabular-nums">
                {safeCurrentIndex + 1}/{allTabs.length}
              </span>

              <button
                type="button"
                aria-label="Chứng từ tiếp theo"
                disabled={!canGoNext}
                onClick={() => {
                  if (canGoNext) {
                    const nextTab = allTabs[safeCurrentIndex + 1];
                    setSelectedTabId(nextTab.id);
                    if (nextTab.source) onSourceSelected?.(nextTab.source.id);
                  }
                }}
                className="w-7 h-7 flex items-center justify-center rounded text-slate-500 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:pointer-events-none transition-colors cursor-pointer"
                title="Chứng từ tiếp theo"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </button>
            </div>

            <div className="h-4 w-px bg-slate-200 mx-1 shrink-0" />

            {/* Dropdown Selector */}
            <div className="relative min-w-0" ref={dropdownRef}>
              <button
                type="button"
                aria-label={`Chọn chứng từ: ${activeTab?.name ?? ""}`}
                aria-expanded={isDropdownOpen}
                onClick={() => setIsDropdownOpen((prev) => !prev)}
                className={`h-7.5 px-2.5 rounded-md flex items-center gap-2 border text-xs transition-colors cursor-pointer max-w-full ${
                  isDropdownOpen
                    ? "bg-slate-100 border-slate-300 text-slate-900"
                    : "bg-slate-50 hover:bg-slate-100 border-slate-200 hover:border-slate-300 text-slate-800"
                }`}
                title="Nhấn để chọn chứng từ khác trong danh sách"
              >
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-bold shrink-0 uppercase border ${
                    isPdf
                      ? "bg-rose-50 text-rose-700 border-rose-200"
                      : "bg-sky-50 text-sky-700 border-sky-200"
                  }`}
                >
                  {isPdf ? "PDF" : "IMG"}
                </span>
                <span className="font-semibold text-slate-900 truncate max-w-[190px] sm:max-w-[280px]">
                  {activeTab?.name}
                </span>
                {activeTab?.isPending && (
                  <span className="text-[10px] text-amber-600 font-normal italic shrink-0">
                    (chờ nộp)
                  </span>
                )}
                <svg
                  className={`w-3.5 h-3.5 text-slate-400 transition-transform shrink-0 ${
                    isDropdownOpen ? "rotate-180 text-slate-700" : ""
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Popover Dropdown Menu */}
              {isDropdownOpen && (
                <div className="absolute top-full left-0 mt-1.5 w-80 sm:w-96 max-h-80 overflow-y-auto custom-scrollbar bg-white rounded-lg shadow-xl border border-slate-200 py-1.5 z-50 animate-in fade-in duration-100">
                  <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100 mb-1 flex items-center justify-between">
                    <span>Danh sách chứng từ ({allTabs.length})</span>
                    <span className="text-[10px] lowercase text-slate-400 font-normal">chọn để xem</span>
                  </div>
                  {allTabs.map((tab, idx) => {
                    const isSelected = activeTab?.id === tab.id;
                    const tabIsPdf =
                      tab.name.toLowerCase().endsWith(".pdf") ||
                      tab.source?.media === "PDF" ||
                      tab.file?.type === "application/pdf";
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => {
                          setSelectedTabId(tab.id);
                          if (tab.source) onSourceSelected?.(tab.source.id);
                          setIsDropdownOpen(false);
                        }}
                        className={`w-full text-left px-3 py-2 flex items-center justify-between text-xs transition-colors cursor-pointer gap-2 ${
                          isSelected
                            ? "bg-slate-50 text-slate-900 font-semibold"
                            : "text-slate-700 hover:bg-slate-50/80 font-normal"
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold shrink-0 uppercase border ${
                              tabIsPdf
                                ? "bg-rose-50 text-rose-700 border-rose-200"
                                : "bg-sky-50 text-sky-700 border-sky-200"
                            }`}
                          >
                            {tabIsPdf ? "PDF" : "IMG"}
                          </span>
                          <span className="truncate" title={tab.name}>
                            {tab.name}
                          </span>
                          {tab.isPending && (
                            <span className="text-[10px] text-amber-600 font-normal italic shrink-0">
                              (chờ nộp)
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="font-mono text-[10px] text-slate-400">
                            #{idx + 1}
                          </span>
                          {isSelected && (
                            <span className="text-xs text-slate-900 font-bold">✓</span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Right Actions: Mở tab mới */}
        {documentUrl && (
          <div className="shrink-0 flex items-center pl-2">
            <a
              href={documentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="group inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 px-2 py-1 rounded hover:bg-slate-100 transition-colors cursor-pointer"
              title="Mở tài liệu trong tab mới"
              aria-label="Mở tab mới"
            >
              <span className="hidden sm:inline">Mở tab mới</span>
              <svg
                className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-colors shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
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
