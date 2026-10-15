import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "./api";
import { Advance } from "./features/advance";
import { Approval } from "./features/approval";
import { Controls } from "./features/controls";
import { Dashboard } from "./features/dashboard";
import { DocumentViewer } from "./features/document_viewer";
import { CaseStateBadge, Dossier } from "./features/dossier";
import { Execution } from "./features/execution";
import { EmployeeReturn } from "./features/employee_return";
import { Intake } from "./features/intake";
import { Questions, roleMatchesOwner } from "./features/questions";
import { Verify } from "./features/verify";
import { DebugModal } from "./features/debug_modal";
import { roleWorkspaces } from "./roles";
import type { CaseView, SessionPayload } from "./types";

export type ViewMode = "dashboard" | "detail" | "intake";

function cleanActorName(name: string): string {
  return name.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

const ROLE_LABELS: Record<string, string> = {
  employee: "Nhân viên",
  accountant: "Kế toán",
  approver: "Người phê duyệt",
};

export default function App() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [caseList, setCaseList] = useState<CaseView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [isPersonaOpen, setIsPersonaOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("dashboard");
  const [detailTab, setDetailTab] = useState<"dossier" | "issues" | "cashflow" | "return">("dossier");
  const personaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (personaRef.current && !personaRef.current.contains(event.target as Node)) {
        setIsPersonaOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsPersonaOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  const loadSession = useCallback(async () => {
    try {
      setSession(await api.session());
      return true;
    } catch (cause) {
      setError(errorMessage(cause));
      return false;
    }
  }, []);

  const restoreLatestCase = useCallback(async () => {
    try {
      const { cases } = await api.listCases();
      setCaseList(cases);
      if (cases.length > 0) {
        setCaseView((prev) => {
          if (prev) {
            const found = cases.find((c) => c.id === prev.id);
            if (found) return found;
          }
          return cases.reduce((best, candidate) =>
            candidate.version >= best.version ? candidate : best,
          );
        });
      }
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, []);

  useEffect(() => {
    void (async () => {
      if (await loadSession()) {
        await restoreLatestCase();
      }
    })();
  }, [loadSession, restoreLatestCase]);

  async function switchPersona(persona: string) {
    try {
      setSession(await api.switchPersona(persona));
      setViewMode("dashboard");
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  const currentRole = session?.session.persona ?? "employee";
  const activePanels = roleWorkspaces(currentRole);
  const activeDetailTab =
    (currentRole !== "accountant" && detailTab === "cashflow") ||
    (currentRole !== "employee" && detailTab === "return")
      ? "dossier"
      : detailTab;
  const activeCollectsCount =
    caseView?.instructions.filter(
      (item) => item.direction === "COLLECT" && ["ISSUED", "PARTIAL"].includes(item.status) && item.remaining > 0,
    ).length ?? 0;
  const myIssuesCount =
    caseView?.issues.filter((issue) =>
      roleMatchesOwner(currentRole, issue.owner, issue.kind),
    ).length ?? 0;

  return (
    <div className="app h-screen flex flex-col bg-slate-50 text-slate-800 font-sans overflow-hidden select-none">
      {/* 1. Header (48px / h-12) */}
      <header className="h-12 border-b border-slate-200 bg-white flex items-center justify-between px-4 text-xs select-none shrink-0 z-20">
        {/* Left: Brand / Home Link */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setViewMode("dashboard")}
            className="font-bold text-slate-900 text-sm tracking-tight hover:opacity-80 transition-opacity cursor-pointer flex items-center gap-1.5"
          >
            <span>InvoiceReferee</span>
          </button>
        </div>

        {/* Right: Actions & Persona Dropdown */}
        {session === null ? (
          <p className="text-slate-400 text-xs">Đang kết nối…</p>
        ) : (
          <div className="flex items-center gap-2">
            {/* Engineer Benchmark Button */}
            <button
              type="button"
              onClick={() => setIsVerifyOpen(true)}
              className="hidden sm:inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors cursor-pointer"
              title="Kiểm chuẩn độc lập"
            >
              Kiểm chuẩn
            </button>

            {/* Audit Trail Button */}
            <button
              type="button"
              onClick={() => setIsDebugOpen(true)}
              className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium text-slate-600 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors cursor-pointer"
              title="Nhật ký kiểm toán"
            >
              Kiểm toán
            </button>

            {/* Custom Persona Switcher Dropdown */}
            <div className="relative" ref={personaRef}>
              {/* Accessible hidden select for backward-compatibility & testing */}
              <label htmlFor="persona-select" className="sr-only">
                Vai trò người dùng (Persona)
              </label>
              <select
                id="persona-select"
                aria-label="Vai trò (demo)"
                value={session.session.persona}
                onChange={(event) => void switchPersona(event.target.value)}
                className="sr-only"
                tabIndex={-1}
              >
                {session.personas.map((persona) => (
                  <option key={persona.id} value={persona.id}>
                    {cleanActorName(persona.actor_name)} ({persona.label})
                  </option>
                ))}
              </select>

              {/* Persona Trigger Button */}
              {(() => {
                const currentPersonaId = session.session.persona;
                const roleLabel = ROLE_LABELS[currentPersonaId] ?? currentPersonaId;
                const currentName = cleanActorName(session.session.actor_name);
                return (
                  <button
                    type="button"
                    onClick={() => setIsPersonaOpen(!isPersonaOpen)}
                    className="flex items-center gap-1.5 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 rounded-md px-2.5 py-1 text-xs font-medium text-slate-800 transition-colors cursor-pointer"
                    aria-expanded={isPersonaOpen}
                    aria-haspopup="true"
                    title="Chuyển đổi vai trò"
                  >
                    <span className="font-semibold text-slate-900">{currentName}</span>
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-500 font-normal">{roleLabel}</span>
                    <span className="text-slate-400 text-[10px] ml-0.5">▾</span>
                  </button>
                );
              })()}

              {/* Persona Popover Menu */}
              {isPersonaOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-64 bg-white border border-slate-200 rounded-lg shadow-lg p-1 z-50 select-none">
                  <div className="space-y-0.5">
                    {session.personas.map((persona) => {
                      const isCurrent = persona.id === session.session.persona;
                      const name = cleanActorName(persona.actor_name);
                      const role = ROLE_LABELS[persona.id] ?? persona.label;
                      return (
                        <button
                          key={persona.id}
                          type="button"
                          onClick={() => {
                            void switchPersona(persona.id);
                            setIsPersonaOpen(false);
                          }}
                          className={`w-full text-left px-2.5 py-1.5 rounded-md flex items-center justify-between transition-colors cursor-pointer text-xs ${
                            isCurrent
                              ? "bg-slate-100 text-slate-950 font-medium"
                              : "hover:bg-slate-50 text-slate-700 font-normal"
                          }`}
                        >
                          <span className={isCurrent ? "font-semibold text-slate-900" : "text-slate-800"}>
                            {name}
                          </span>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className="text-[11px] text-slate-400 font-normal">{role}</span>
                            <span className="w-3 text-right text-slate-900 text-xs font-bold">
                              {isCurrent ? "✓" : ""}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </header>

      {/* Global Error Notice */}
      {error !== null && (
        <div className="bg-rose-50 border-b border-rose-200 px-4 py-2 text-rose-800 text-xs flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-600 hover:text-rose-900 cursor-pointer font-semibold ml-4"
          >
            Đóng
          </button>
        </div>
      )}

      {/* 2. MAIN VIEW SWITCHER */}
      {session !== null && (
        viewMode === "dashboard" ? (
          <main className="h-[calc(100vh-48px)] flex flex-col overflow-hidden flex-1">
            <Dashboard
              cases={caseList}
              currentRole={currentRole}
              onSelectCase={(c) => {
                setCaseView(c);
                setDetailTab("dossier");
                if (c.state === "DRAFT" && currentRole === "employee") {
                  setViewMode("intake");
                } else {
                  setViewMode("detail");
                }
              }}
              onCreateNew={() => {
                setCaseView(null);
                setViewMode("intake");
              }}
            />
          </main>
        ) : viewMode === "intake" ? (
          <Intake
            session={session}
            onBack={() => setViewMode("dashboard")}
            existingCase={caseView?.state === "DRAFT" ? caseView : null}
            onCase={(newCase) => {
              setCaseView(newCase);
              setViewMode("detail");
              void restoreLatestCase();
            }}
          />
        ) : (
          /* DUAL-PANE SPLIT WORKSPACE (calc(100vh - 48px)) */
          <main className="h-[calc(100vh-48px)] flex flex-col md:flex-row overflow-hidden flex-1">
            {/* LEFT PANE: Document & Evidence Inspector (50%) */}
            <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-hidden flex flex-col">
              <DocumentViewer
                caseView={caseView}
                selectedSourceId={selectedSourceId}
                onSourceSelected={setSelectedSourceId}
              />
            </div>

            {/* RIGHT PANE: Role-Based Action & Audit Workspace (50%) */}
            <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-hidden flex flex-col bg-white">
              {/* Sleek Subheader Bar (h-11) */}
              <div className="h-11 border-b border-slate-200 px-5 flex items-center justify-between shrink-0 bg-white z-10">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setViewMode("dashboard")}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 transition-colors cursor-pointer"
                  >
                    <span className="font-mono">←</span>
                    <span>Quay lại</span>
                  </button>
                  <span className="text-slate-300">/</span>
                  {caseView && (
                    <div className="flex items-center gap-2.5">
                      <h2 className="text-xs font-semibold text-slate-900 flex items-center gap-1.5">
                        <span>Hồ sơ đối soát</span>
                        {caseList.length > 1 ? (
                          <div className="relative inline-flex items-center">
                            <label htmlFor="detail-case-select" className="sr-only">
                              Chọn hồ sơ khác
                            </label>
                            <select
                              id="detail-case-select"
                              value={caseView.id}
                              onChange={(e) => {
                                const found = caseList.find((c) => c.id === e.target.value);
                                if (found) {
                                  setCaseView(found);
                                  if (found.state === "DRAFT" && currentRole === "employee") {
                                    setViewMode("intake");
                                  }
                                }
                              }}
                              className="text-xs font-mono-nums font-semibold text-slate-900 bg-transparent hover:bg-slate-100 rounded px-1.5 py-0.5 focus:outline-none cursor-pointer transition-colors"
                            >
                              {caseList.map((c) => (
                                <option key={c.id} value={c.id}>
                                  #{c.id.replace("case:", "").slice(0, 8)} (v{c.version})
                                </option>
                              ))}
                            </select>
                          </div>
                        ) : (
                          <span className="font-mono-nums font-semibold text-slate-900">
                            #{caseView.id.replace("case:", "").slice(0, 8)}{" "}
                            <span className="text-slate-400 font-normal">(v{caseView.version})</span>
                          </span>
                        )}
                      </h2>
                      <CaseStateBadge state={caseView.state} />
                    </div>
                  )}
                </div>

                {/* Subheader Action Controls (Dừng hồ sơ / Tiếp tục) */}
                {activePanels.includes("controls") && (
                  <Controls
                    caseView={caseView}
                    onCase={(newCase) => {
                      setCaseView(newCase);
                      void restoreLatestCase();
                    }}
                    currentRole={currentRole}
                  />
                )}
              </div>

              {/* Role Workspace Tabs (Unified for all personas) */}
              <div className="border-b border-slate-200 bg-white px-5 flex items-center gap-6 text-xs shrink-0 select-none">
                {/* Tab 1: Đối soát chi phí */}
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeDetailTab === "dossier"}
                  onClick={() => setDetailTab("dossier")}
                  className={`py-2.5 font-medium border-b-2 text-xs transition-colors cursor-pointer flex items-center gap-2 ${
                    activeDetailTab === "dossier"
                      ? "border-slate-900 text-slate-950 font-semibold"
                      : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                  }`}
                >
                  <span>Đối soát chi phí</span>
                </button>

                {/* Tab 2: Vấn đề cần xử lý */}
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeDetailTab === "issues"}
                  onClick={() => setDetailTab("issues")}
                  className={`py-2.5 font-medium border-b-2 text-xs transition-colors cursor-pointer flex items-center gap-2 ${
                    activeDetailTab === "issues"
                      ? "border-slate-900 text-slate-950 font-semibold"
                      : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                  }`}
                >
                  <span>Vấn đề cần xử lý</span>
                  {myIssuesCount > 0 ? (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono-nums font-semibold bg-amber-100 text-amber-900 border border-amber-300/80">
                      {myIssuesCount}
                    </span>
                  ) : (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono-nums font-medium bg-slate-100 text-slate-500">
                      0
                    </span>
                  )}
                </button>

                {/* Tab for Employee: Nộp chứng từ hoàn trả */}
                {currentRole === "employee" && (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeDetailTab === "return"}
                    onClick={() => setDetailTab("return")}
                    className={`py-2.5 font-medium border-b-2 text-xs transition-colors cursor-pointer flex items-center gap-2 ${
                      activeDetailTab === "return"
                        ? "border-slate-900 text-slate-950 font-semibold"
                        : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                    }`}
                  >
                    <span>Nộp chứng từ hoàn trả</span>
                    {activeCollectsCount > 0 && (
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-mono-nums font-semibold bg-amber-100 text-amber-900 border border-amber-300/80">
                        {activeCollectsCount}
                      </span>
                    )}
                  </button>
                )}

                {/* Tab 3: Sổ cái & Dòng tiền (Chỉ kế toán có thẩm quyền ghi sổ tiền) */}
                {currentRole === "accountant" && (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeDetailTab === "cashflow"}
                    onClick={() => setDetailTab("cashflow")}
                    className={`py-2.5 font-medium border-b-2 text-xs transition-colors cursor-pointer flex items-center gap-2 ${
                      activeDetailTab === "cashflow"
                        ? "border-slate-900 text-slate-950 font-semibold"
                        : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                    }`}
                  >
                    <span>Sổ cái & Dòng tiền</span>
                  </button>
                )}
              </div>

              {/* Scrollable Canvas for Workspaces */}
              <div className="flex-1 overflow-y-auto custom-scrollbar p-6 space-y-6">
                {/* DRAFT Resumption Banner */}
                {caseView?.state === "DRAFT" && (
                  <div className="bg-amber-50/80 border border-amber-200 rounded p-3.5 text-xs flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                        <strong className="text-amber-950 font-semibold text-xs">
                          Hồ sơ này đang ở dạng Bản nháp và chưa được nộp.
                        </strong>
                      </div>
                      <p className="text-amber-800 text-[11px] leading-relaxed">
                        Chứng từ đã tải lên và trích xuất sẵn. Hãy mở lại bản nháp để kiểm tra và xác nhận nộp hồ sơ.
                      </p>
                    </div>
                    {currentRole === "employee" && (
                      <button
                        type="button"
                        onClick={() => setViewMode("intake")}
                        className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded text-xs transition-colors cursor-pointer shrink-0"
                      >
                        Tiếp tục nộp hồ sơ →
                      </button>
                    )}
                  </div>
                )}

                {/* TAB 1: Đối soát chi phí */}
                {activeDetailTab === "dossier" && (
                  <>
                    <Dossier
                      caseView={caseView}
                      hideIssues={true}
                    />

                    {activePanels.includes("approval") && (
                      <Approval caseView={caseView} />
                    )}
                  </>
                )}

                {/* TAB 2: Vấn đề cần xử lý */}
                {activeDetailTab === "issues" && (
                  <>
                    {(caseView?.issues.length ?? 0) > 0 ? (
                      <Questions
                        caseView={caseView}
                        onCase={(newCase) => {
                          setCaseView(newCase);
                          void restoreLatestCase();
                        }}
                        currentRole={currentRole}
                      />
                    ) : (
                      <div className="py-12 px-4 text-center space-y-2 select-none">
                        <div className="w-8 h-8 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto text-sm font-bold border border-emerald-200">
                          ✓
                        </div>
                        <h3 className="text-sm font-semibold text-slate-900">
                          Không có vấn đề cần xử lý
                        </h3>
                        <p className="text-xs text-slate-500 max-w-sm mx-auto">
                          Tất cả căn cứ chi tiêu, người nhận và số liệu đối soát đều đã được xác thực hợp lệ.
                        </p>
                      </div>
                    )}
                  </>
                )}

                {/* TAB: Nộp chứng từ hoàn trả (Chỉ nhân viên) */}
                {activeDetailTab === "return" && currentRole === "employee" && (
                  <EmployeeReturn
                    caseView={caseView}
                    onCase={(newCase) => {
                      setCaseView(newCase);
                      void restoreLatestCase();
                    }}
                  />
                )}

                {/* TAB 3: Sổ cái & Dòng tiền (Chỉ kế toán có thẩm quyền ghi sổ tiền) */}
                {activeDetailTab === "cashflow" && currentRole === "accountant" && (
                  <div className="max-w-3xl space-y-6">
                    {activePanels.includes("advance") && (
                      <Advance
                        caseView={caseView}
                        onCase={(newCase) => {
                          setCaseView(newCase);
                          void restoreLatestCase();
                        }}
                        onSourceSelected={setSelectedSourceId}
                      />
                    )}

                    {activePanels.includes("execution") && (
                      <Execution
                        caseView={caseView}
                        onCase={(newCase) => {
                          setCaseView(newCase);
                          void restoreLatestCase();
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          </main>
        )
      )}

      {/* Benchmark Verification Modal */}
      <Verify isOpen={isVerifyOpen} onClose={() => setIsVerifyOpen(false)} />

      {/* Debug & Audit Trail Modal */}
      <DebugModal caseView={caseView} isOpen={isDebugOpen} onClose={() => setIsDebugOpen(false)} />
    </div>
  );
}
