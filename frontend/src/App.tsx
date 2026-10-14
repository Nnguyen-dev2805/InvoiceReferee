import { useCallback, useEffect, useState } from "react";

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

export default function App() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [caseList, setCaseList] = useState<CaseView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const [isDebugOpen, setIsDebugOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("dashboard");

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
          <div className="flex items-center gap-2.5">

            {/* Engineer Benchmark Button */}
            <button
              type="button"
              onClick={() => setIsVerifyOpen(true)}
              className="hidden sm:inline-flex items-center px-2.5 py-1 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 transition-colors cursor-pointer"
              title="Mở công cụ kiểm chuẩn độc lập (Benchmark)"
            >
              Kiểm chuẩn (Verify)
            </button>

            {/* Debug & Audit Trail Button */}
            <button
              type="button"
              onClick={() => setIsDebugOpen(true)}
              className="inline-flex items-center px-2.5 py-1 rounded text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 transition-colors cursor-pointer"
              title="Xem nhật ký kiểm toán và dữ liệu kỹ thuật hồ sơ"
            >
              Debug / Audit
            </button>

            {/* Persona Switcher */}
            <div className="flex items-center bg-white border border-slate-300 rounded px-2.5 py-1 hover:border-slate-400 transition-colors">
              <label htmlFor="persona-select" className="sr-only">
                Vai trò người dùng (Persona)
              </label>
              <select
                id="persona-select"
                aria-label="Vai trò (demo)"
                value={session.session.persona}
                onChange={(event) => void switchPersona(event.target.value)}
                className="text-xs font-medium text-slate-900 bg-transparent focus:outline-none cursor-pointer"
              >
                {session.personas.map((persona) => (
                  <option key={persona.id} value={persona.id}>
                    {persona.actor_name} ({persona.label})
                  </option>
                ))}
              </select>
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
            <div className="w-full max-w-3xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-200">
                <button
                  type="button"
                  onClick={() => setViewMode("dashboard")}
                  className="text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                >
                  ← Quay lại Bàn làm việc
                </button>
                <span className="text-xs font-semibold text-slate-800">
                  Quy trình nộp đề nghị thanh toán mới
                </span>
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
                  <span>Quay lại Bàn làm việc</span>
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
