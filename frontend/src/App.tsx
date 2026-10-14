import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";
import { Approval } from "./features/approval";
import { Controls } from "./features/controls";
import { Dossier } from "./features/dossier";
import { Execution } from "./features/execution";
import { Intake } from "./features/intake";
import { Questions } from "./features/questions";
import { Verify } from "./features/verify";
import { roleWorkspaces } from "./roles";
import type { CaseView, SessionPayload } from "./types";

export default function App() {
  const [session, setSession] = useState<SessionPayload | null>(null);
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    try {
      setSession(await api.session());
      return true;
    } catch (cause) {
      setError(errorMessage(cause));
      return false;
    }
  }, []);

  // A reload must not lose the dossier: the case lives in the DB, so after the
  // session cookie is established we restore the most recently updated case the
  // session can see. Sequencing matters — /api/cases needs the session cookie
  // that /api/demo/session sets, or a fresh browser gets a 401.
  const restoreLatestCase = useCallback(async () => {
    try {
      const { cases } = await api.listCases();
      if (cases.length > 0) {
        const latest = cases.reduce((best, candidate) =>
          candidate.version >= best.version ? candidate : best,
        );
        setCaseView(latest);
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
      // Keep the loaded case: it is tenant-scoped and visible to every persona,
      // so the accountant can act on what the employee just submitted.
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  return (
    <div className="app min-h-screen bg-slate-50 text-slate-800 font-['Geist',-apple-system,BlinkMacSystemFont,sans-serif] flex flex-col">
      <header className="h-12 border-b border-slate-200 bg-white flex items-center justify-between px-4 text-xs select-none shrink-0 z-20">
        {/* Left: Brand Identity & Business Context Breadcrumb */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-slate-900 flex items-center justify-center text-white shadow-xs">
              <span className="material-symbols-outlined text-[14px]" aria-hidden="true">receipt_long</span>
            </div>
            <h1 className="font-semibold text-slate-900 text-xs tracking-tight">InvoiceReferee</h1>
          </div>

          <span className="text-slate-300 font-light select-none">/</span>

          {caseView !== null ? (
            <div className="flex items-center gap-2">
              <span className="text-slate-800 font-medium font-['JetBrains_Mono'] text-xs">
                {caseView.id.startsWith("case:") ? (
                  <span>
                    Hồ sơ <strong className="text-slate-900 font-semibold font-['JetBrains_Mono']">#{caseView.id.slice(5, 13)}</strong>
                  </span>
                ) : (
                  caseView.id
                )}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10.5px] font-medium ${
                  caseView.state === "READY_TO_EXECUTE"
                    ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                    : caseView.state === "WAITING"
                    ? "bg-amber-50 text-amber-700 border border-amber-200"
                    : caseView.state === "STOPPED"
                    ? "bg-rose-50 text-rose-700 border border-rose-200"
                    : "bg-slate-100 text-slate-700 border border-slate-200"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    caseView.state === "READY_TO_EXECUTE"
                      ? "bg-emerald-500"
                      : caseView.state === "WAITING"
                      ? "bg-amber-500"
                      : caseView.state === "STOPPED"
                      ? "bg-rose-500"
                      : "bg-slate-400"
                  }`}
                ></span>
                <span>
                  {caseView.state === "READY_TO_EXECUTE"
                    ? "Sẵn sàng duyệt"
                    : caseView.state === "WAITING"
                    ? "Chờ xử lý ngoại lệ"
                    : caseView.state === "DRAFT"
                    ? "Bản nháp"
                    : caseView.state === "STOPPED"
                    ? "Tạm dừng (§6)"
                    : caseView.state === "SETTLED"
                    ? "Đã đối soát"
                    : caseView.state}
                </span>
              </span>
            </div>
          ) : (
            <span className="text-slate-400 font-normal text-xs">Chưa mở hồ sơ</span>
          )}
        </div>

        {/* Center: System Workspaces Navigation */}
        <nav aria-label="Phân hệ làm việc" className="hidden md:flex items-center gap-1 bg-slate-100/70 p-0.5 rounded-lg border border-slate-200/60">
          <span className="px-3 py-1 rounded-md text-xs font-semibold bg-white text-slate-900 shadow-xs flex items-center gap-1.5 cursor-default">
            <span className="material-symbols-outlined text-sm text-slate-700" aria-hidden="true">dashboard</span>
            <span>Bàn làm việc</span>
          </span>
          <span className="px-3 py-1 rounded-md text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors flex items-center gap-1.5 cursor-default">
            <span className="material-symbols-outlined text-sm text-slate-400" aria-hidden="true">fact_check</span>
            <span>Hồ sơ đối soát</span>
          </span>
          <span className="px-3 py-1 rounded-md text-xs font-medium text-slate-500 hover:text-slate-800 transition-colors flex items-center gap-1.5 cursor-default">
            <span className="material-symbols-outlined text-sm text-slate-400" aria-hidden="true">policy</span>
            <span>Chính sách tài chính</span>
          </span>
        </nav>

        {/* Right: Environment Status & Unified Actor Control */}
        {session === null ? (
          <p className="text-slate-400 text-xs">Đang kết nối…</p>
        ) : (
          <div className="flex items-center gap-2.5">
            <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10.5px] font-semibold font-['JetBrains_Mono'] ${
              session.mode === "LIVE"
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                : "bg-blue-50 text-blue-700 border border-blue-200"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${session.mode === "LIVE" ? "bg-emerald-500" : "bg-blue-500"}`}></span>
              <span>{session.mode}</span>
            </span>

            <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5 shadow-xs hover:border-slate-300 transition-colors">
              <label htmlFor="persona-select" className="sr-only">
                Vai trò (demo)
              </label>
              <div className="flex items-center gap-2 pl-2 pr-1.5 py-0.5">
                <span className="w-5 h-5 rounded-full bg-slate-900 text-white flex items-center justify-center font-bold text-[10px] shrink-0">
                  {session.session.actor_name.slice(0, 1)}
                </span>
                <div className="relative flex items-center">
                  <select
                    id="persona-select"
                    aria-label="Vai trò (demo)"
                    value={session.session.persona}
                    onChange={(event) => void switchPersona(event.target.value)}
                    className="text-xs font-medium text-slate-800 bg-transparent pr-5 focus:outline-none cursor-pointer appearance-none"
                  >
                    {session.personas.map((persona) => (
                      <option key={persona.id} value={persona.id}>
                        {persona.actor_name} ({persona.label})
                      </option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined text-slate-400 text-sm absolute right-0 pointer-events-none" aria-hidden="true">
                    unfold_more
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
      </header>

      {error !== null && (
        <div className="max-w-7xl mx-auto w-full px-4 pt-3">
          <p role="alert" className="error p-2.5 rounded bg-rose-50 text-rose-800 border border-rose-200 text-xs">
            {error}
          </p>
        </div>
      )}

      {session !== null && (
        <main className="max-w-7xl mx-auto w-full p-4 grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1">
          <div className="space-y-4">
            {roleWorkspaces(session.session.persona).includes("intake") && (
              <Intake session={session} onCase={setCaseView} />
            )}
            {roleWorkspaces(session.session.persona).includes("questions") && (
              <Questions caseView={caseView} onCase={setCaseView} />
            )}
            {roleWorkspaces(session.session.persona).includes("approval") && (
              <Approval caseView={caseView} />
            )}
            {roleWorkspaces(session.session.persona).includes("execution") && (
              <Execution caseView={caseView} onCase={setCaseView} />
            )}
            {roleWorkspaces(session.session.persona).includes("controls") && (
              <Controls caseView={caseView} onCase={setCaseView} />
            )}
            <Verify />
          </div>
          <div className="space-y-4">
            <Dossier caseView={caseView} />
          </div>
        </main>
      )}

    </div>
  );
}
