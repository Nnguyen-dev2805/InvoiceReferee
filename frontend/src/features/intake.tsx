import { useState } from "react";

import { api, attachSources, errorMessage } from "../api";
import { formatDate, formatVnd } from "../format";
import type { CaseView, SessionPayload } from "../types";

export function Intake({
  session,
  onCase,
}: {
  session: SessionPayload;
  onCase: (view: CaseView) => void;
}) {
  const [mode, setMode] = useState<"existing" | "new">("existing");
  const [activityId, setActivityId] = useState(
    session.activity_catalog[0]?.id ?? "",
  );
  const [newName, setNewName] = useState("");
  const [newDate, setNewDate] = useState("2026-10-06");
  const [newPurpose, setNewPurpose] = useState("");
  const [caseView, setCaseView] = useState<CaseView | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function createCase() {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const activity =
        mode === "existing"
          ? { mode: "existing", activity_id: activityId }
          : {
              mode: "new",
              name: newName,
              occurred_at: new Date(`${newDate}T09:00:00+07:00`).toISOString(),
              declared_purpose: newPurpose,
            };
      const result = await api.createCase(activity);
      setCaseView(result.case_view);
      onCase(result.case_view);
      setStatus("Đã mở hồ sơ cho hoạt động này (cùng hoạt động ⇒ cùng root).");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function attach() {
    if (caseView === null || files.length === 0) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    const count = files.length;
    try {
      const result = await attachSources(caseView.id, files, caseView.version);
      setCaseView(result.case_view);
      onCase(result.case_view);
      setFiles([]);
      setStatus(`Đã đính kèm ${count} chứng từ vào hồ sơ.`);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="intake-title">
      <h2 id="intake-title">Nộp hồ sơ</h2>

      <fieldset>
        <legend>Chọn hoạt động</legend>
        <label>
          <input
            type="radio"
            name="activity-mode"
            value="existing"
            checked={mode === "existing"}
            onChange={() => setMode("existing")}
          />
          Hoạt động có sẵn
        </label>
        <label>
          <input
            type="radio"
            name="activity-mode"
            value="new"
            checked={mode === "new"}
            onChange={() => setMode("new")}
          />
          Hoạt động mới
        </label>
      </fieldset>

      {mode === "existing" ? (
        <p>
          <label htmlFor="activity-select">
            Hoạt động
            <select
              id="activity-select"
              value={activityId}
              onChange={(event) => setActivityId(event.target.value)}
            >
              {session.activity_catalog.map((activity) => (
                <option key={activity.id} value={activity.id}>
                  {activity.name}
                  {activity.occurred_at !== null
                    ? ` · ${formatDate(activity.occurred_at)}`
                    : ""}
                  {activity.budget_amount !== null
                    ? ` · ngân sách ${formatVnd(activity.budget_amount)}`
                    : " · chưa có ngân sách"}
                </option>
              ))}
            </select>
          </label>
        </p>
      ) : (
        <>
          <p>
            <label htmlFor="activity-name">
              Tên hoạt động
              <input
                id="activity-name"
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </label>
          </p>
          <p>
            <label htmlFor="activity-date">
              Ngày
              <input
                id="activity-date"
                type="date"
                value={newDate}
                onChange={(event) => setNewDate(event.target.value)}
              />
            </label>
          </p>
          <p>
            <label htmlFor="activity-purpose">
              Mục đích
              <input
                id="activity-purpose"
                value={newPurpose}
                onChange={(event) => setNewPurpose(event.target.value)}
              />
            </label>
          </p>
        </>
      )}

      <p>
        <button type="button" onClick={() => void createCase()} disabled={busy}>
          Tạo hồ sơ
        </button>
      </p>

      <h3>Chứng từ</h3>
      <p>
        <label htmlFor="source-files">
          Chứng từ (PDF/PNG/JPEG)
          <input
            id="source-files"
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
            onChange={(event) =>
              setFiles(Array.from(event.target.files ?? []))
            }
          />
        </label>
      </p>
      <p>
        <button
          type="button"
          onClick={() => void attach()}
          disabled={busy || caseView === null || files.length === 0}
        >
          Đính kèm
        </button>
      </p>

      {status !== null && (
        <p role="status" aria-live="polite" className="status">
          {status}
        </p>
      )}
      {error !== null && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {caseView !== null && (
        <div className="case-line">
          <p className="summary">{caseView.summary}</p>
          <p className="muted" data-testid="case-code">
            Mã hồ sơ: {caseView.id}
          </p>
        </div>
      )}
    </section>
  );
}
