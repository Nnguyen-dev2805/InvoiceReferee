// Case workspace lifecycle: owns the verified load/poll of one case's data
// (view/run/report/questions/history/b3Context) with a request generation so a
// late response for case A can never overwrite case B. App keeps persona/case
// navigation/global actions; the workspace view renders the tabs/layout.
import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './api';
import type {
  AuditEntry, B3RunContext, CaseView, QuestionView, Report, RunView,
} from './types';

export interface CaseWorkspace {
  view: CaseView;
  run: RunView | null;
  report: Report | null;
  questions: QuestionView[];
  history: AuditEntry[];
  b3Context: B3RunContext | null;
}

export interface UseCaseWorkspace {
  workspace: CaseWorkspace | null;
  loading: boolean;
  error: string | null;
  // Fetch one case and commit it (guarded by generation). Awaitable so callers
  // can refresh after a mutation and read the committed state.
  load: (id: string) => Promise<void>;
  // Commit a workspace the caller already fetched (keeps the generation guard).
  applyWorkspace: (ws: CaseWorkspace) => void;
}

async function fetchWorkspace(id: string): Promise<CaseWorkspace> {
  const view = await api.getCase(id);
  const [history, questions] = await Promise.all([
    api.getHistory(id), api.getQuestions(id),
  ]);
  let run: RunView | null = null;
  let report: Report | null = null;
  let b3Context: B3RunContext | null = null;
  if (view.current_run_id) {
    run = await api.getRun(view.current_run_id);
    if (run.status === 'SUCCEEDED') {
      report = await api.getReport(run.id);
      if (report.b3) b3Context = await api.getB3RunContext(run.id);
    }
  }
  return { view, run, report, questions, history, b3Context };
}

export function useCaseWorkspace(caseId: string | null): UseCaseWorkspace {
  const [workspace, setWorkspace] = useState<CaseWorkspace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const genRef = useRef(0);
  const caseIdRef = useRef<string | null>(null);

  const load = useCallback(async (id: string) => {
    const gen = genRef.current + 1;
    genRef.current = gen;
    caseIdRef.current = id;
    const isCurrent = () => genRef.current === gen && caseIdRef.current === id;
    setLoading(true);
    try {
      const ws = await fetchWorkspace(id);
      if (!isCurrent()) return;
      setWorkspace(ws);
      setError(null);
    } catch (e) {
      if (!isCurrent()) return;
      setError(e instanceof Error ? e.message : 'Không tải được hồ sơ.');
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, []);

  // Load whenever the selected case changes; clear the old workspace so a case
  // B render never shows case A's report/run.
  useEffect(() => {
    if (caseId === null) {
      genRef.current += 1;
      caseIdRef.current = null;
      setWorkspace(null);
      setError(null);
      setLoading(false);
      return;
    }
    if (caseIdRef.current === caseId && workspace?.view.id === caseId) return;
    setWorkspace(null);
    void load(caseId);
  }, [caseId, load]);

  const applyWorkspace = useCallback((ws: CaseWorkspace) => {
    genRef.current += 1;
    caseIdRef.current = ws.view.id;
    setWorkspace(ws);
    setError(null);
  }, []);

  // Poll the active run; ignore a late poll once the case changed.
  const runId = workspace?.run?.id ?? null;
  const runActive = workspace?.run !== null
    && (workspace?.run?.status === 'QUEUED' || workspace?.run?.status === 'RUNNING');
  useEffect(() => {
    if (!runId || !runActive) return;
    const polledGen = genRef.current;
    const polledCase = caseIdRef.current;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const next = await api.getRun(runId);
        if (cancelled || genRef.current !== polledGen
            || caseIdRef.current !== polledCase) return;
        setWorkspace((prev) => (prev ? { ...prev, run: next } : prev));
        if (next.status === 'SUCCEEDED'
            || (next.status !== 'QUEUED' && next.status !== 'RUNNING')) {
          if (polledCase) await load(polledCase);
        }
      } catch {
        // transient poll error: keep the last known state
      }
    }, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runId, runActive, load]);

  return { workspace, loading, error, load, applyWorkspace };
}
