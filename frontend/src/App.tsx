import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "./api";
import { Advance } from "./features/advance";
import { Approval } from "./features/approval";
import { Controls } from "./features/controls";
import { Dashboard } from "./features/dashboard";
import { DocumentViewer } from "./features/document_viewer";
import { Dossier } from "./features/dossier";
import { Execution } from "./features/execution";
import { Intake } from "./features/intake";
import { Questions } from "./features/questions";
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
  const [caseList, setCaseList] = useState<CaseView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [isPersonaOpen, setIsPersonaOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("dashboard");
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
                setViewMode("detail");
              }}
              onCreateNew={() => setViewMode("intake")}
            />
          </main>
        ) : viewMode === "intake" ? (
          <main className="h-[calc(100vh-48px)] overflow-y-auto custom-scrollbar p-6 bg-slate-50 flex justify-center flex-1">
            <div className="w-full max-w-5xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                <button
                  type="button"
                  onClick={() => setViewMode("dashboard")}
                  className="text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                >
                  ← Quay lại
                </button>
              </div>
              <Intake
                session={session}
                onCase={(newCase) => {
                  setCaseView(newCase);
                  setViewMode("detail");
                  void restoreLatestCase();
                }}
              />
            </div>
          </main>
        ) : (
          /* DUAL-PANE SPLIT WORKSPACE (calc(100vh - 48px)) */
          <main className="h-[calc(100vh-48px)] flex flex-col md:flex-row overflow-hidden flex-1">
            {/* LEFT PANE: Document & Evidence Inspector (50%) */}
            <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-hidden flex flex-col">
              <DocumentViewer caseView={caseView} />
            </div>

            {/* RIGHT PANE: Role-Based Action & Audit Workspace (50%) */}
            <div className="w-full md:w-1/2 h-1/2 md:h-full overflow-y-auto custom-scrollbar p-5 space-y-5 bg-slate-50/80">
              {/* Back to Dashboard bar */}
              <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                <button
                  type="button"
                  onClick={() => setViewMode("dashboard")}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                >
                  <span className="text-slate-400">←</span>
                  <span>Quay lại</span>
                </button>
                <div className="flex items-center gap-2">
                  {caseList.length > 1 && caseView !== null && (
                    <div className="flex items-center bg-white border border-slate-300 rounded-lg px-2.5 py-1 shadow-2xs hover:border-slate-400 transition-colors">
                      <label htmlFor="detail-case-select" className="sr-only">
                        Chọn hồ sơ khác
                      </label>
                      <select
                        id="detail-case-select"
                        value={caseView.id}
                        onChange={(e) => {
                          const found = caseList.find((c) => c.id === e.target.value);
                          if (found) setCaseView(found);
                        }}
                        className="text-xs font-mono-nums font-semibold text-slate-800 bg-transparent focus:outline-none cursor-pointer"
                      >
                        {caseList.map((c) => (
                          <option key={c.id} value={c.id}>
                            Hồ sơ #{c.id.replace("case:", "").slice(0, 8)} (v{c.version})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  {activePanels.includes("intake") && (
                    <button
                      type="button"
                      onClick={() => setViewMode("intake")}
                      className="inline-flex items-center px-3 py-1 rounded-lg text-xs font-semibold text-white bg-slate-950 hover:bg-slate-800 shadow-2xs transition-colors cursor-pointer"
                      title="Tạo hồ sơ quyết toán mới"
                    >
                      + Tạo hồ sơ mới
                    </button>
                  )}
                </div>
              </div>

              {/* 1. Dossier (Bảng đối soát tài chính & Lịch sử) */}
              {activePanels.includes("dossier") && (
                <Dossier
                  caseView={caseView}
                  hideIssues={activePanels.includes("questions") && (caseView?.issues.length ?? 0) > 0}
                />
              )}

              {/* 2. Questions Workspace */}
              {activePanels.includes("questions") && (
                <Questions
                  caseView={caseView}
                  onCase={(newCase) => {
                    setCaseView(newCase);
                    void restoreLatestCase();
                  }}
                  currentRole={currentRole}
                />
              )}

              {/* 3. Approval Workspace */}
              {activePanels.includes("approval") && (
                <Approval caseView={caseView} />
              )}

              {/* 4. Advance Workspace */}
              {activePanels.includes("advance") && (
                <Advance
                  caseView={caseView}
                  onCase={(newCase) => {
                    setCaseView(newCase);
                    void restoreLatestCase();
                  }}
                />
              )}

              {/* 5. Execution Workspace */}
              {activePanels.includes("execution") && (
                <Execution
                  caseView={caseView}
                  onCase={(newCase) => {
                    setCaseView(newCase);
                    void restoreLatestCase();
                  }}
                />
              )}

              {/* 6. Controls Workspace */}
              {activePanels.includes("controls") && (
                <Controls
                  caseView={caseView}
                  onCase={(newCase) => {
                    setCaseView(newCase);
                    void restoreLatestCase();
                  }}
                />
              )}
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
