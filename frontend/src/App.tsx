import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "./api";
import { Dossier } from "./features/dossier";
import { Intake } from "./features/intake";
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
      setCaseView(null);
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
          <Intake session={session} onCase={setCaseView} />
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
