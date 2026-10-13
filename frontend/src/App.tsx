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
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }, []);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

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
    <div className="app">
      <header>
        <h1>InvoiceReferee — Quyết toán chi phí</h1>
        {session === null ? (
          <p>Đang kết nối…</p>
        ) : (
          <div className="session-bar">
            <label htmlFor="persona-select">
              Vai trò (demo)
              <select
                id="persona-select"
                value={session.session.persona}
                onChange={(event) => void switchPersona(event.target.value)}
              >
                {session.personas.map((persona) => (
                  <option key={persona.id} value={persona.id}>
                    {persona.label} — {persona.actor_name}
                  </option>
                ))}
              </select>
            </label>
            <span className={`chip mode-${session.mode.toLowerCase()}`}>
              Chế độ: {session.mode}
            </span>
            <span className="muted">Người dùng: {session.session.actor_name}</span>
          </div>
        )}
      </header>

      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {session !== null && (
        <main>
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
          <Dossier caseView={caseView} />
        </main>
      )}

      {session !== null && (
        <footer>
          <details>
            <summary>Chẩn đoán chế độ/cấu hình</summary>
            <ul>
              <li>Chế độ: {session.diagnostics.mode}</li>
              <li>Python: {session.diagnostics.python}</li>
              <li>
                Context demo: {session.diagnostics.context_origin ?? "chưa import"} ·{" "}
                {(session.diagnostics.context_digest ?? "").slice(0, 12)}…
              </li>
              <li>
                Frontend build: {session.diagnostics.frontend_built ? "có" : "chưa"}
              </li>
              <li>
                Thiếu cấu hình LIVE:{" "}
                {session.diagnostics.missing_live_settings.length === 0
                  ? "không"
                  : session.diagnostics.missing_live_settings.join(", ")}
              </li>
            </ul>
          </details>
        </footer>
      )}
    </div>
  );
}
