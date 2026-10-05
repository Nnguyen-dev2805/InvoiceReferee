import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './api';
import { ApiError } from './api';
import type {
  CaseRecord,
  HumanAction,
  PaymentRequest,
  PolicyDto,
  RunRecord,
  StopReply,
} from './types';
import { CaseForm } from './CaseForm';
import { CaseDetail } from './CaseDetail';
import { HumanActions } from './HumanActions';
import { VerifyPanel } from './VerifyPanel';
import { runInFlight } from './format';

const POLL_MS = 1000;

export function App() {
  const [caseRecord, setCaseRecord] = useState<CaseRecord | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [payment, setPayment] = useState<PaymentRequest | null>(null);
  const [policy, setPolicy] = useState<PolicyDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    api.getPolicy().then(setPolicy).catch(() => setPolicy(null));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Poll only while the run is in flight; stop on terminal state or unmount.
  const pollRun = useCallback(
    (runId: string) => {
      stopPolling();
      pollRef.current = window.setTimeout(async () => {
        try {
          const latest = await api.getRun(runId);
          setRun(latest);
          if (latest.case_id) {
            const record = await api.getCase(latest.case_id);
            setCaseRecord(record);
            setPayment(await api.getPaymentRequest(latest.case_id));
          }
          if (runInFlight(latest.status)) pollRun(runId);
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Không tải được trạng thái.');
        }
      }, POLL_MS);
    },
    [stopPolling],
  );

  useEffect(() => stopPolling, [stopPolling]);

  async function refresh(record: CaseRecord) {
    setCaseRecord(record);
    setPayment(await api.getPaymentRequest(record.id));
    if (record.current_run_id) {
      const latest = await api.getRun(record.current_run_id);
      setRun(latest);
      if (runInFlight(latest.status)) pollRun(latest.id);
    }
  }

  async function handleCreated(record: CaseRecord) {
    setError(null);
    try {
      const started = await api.startRun(record.id);
      setCaseRecord(record);
      setRun(started);
      pollRun(started.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không chạy được hồ sơ.');
    }
  }

  async function handleStop(): Promise<StopReply> {
    if (!run) throw new Error('Chưa có lượt xử lý.');
    const reply = await api.stopRun(run.id);
    if (reply.status !== 'ALREADY_COMPLETED') {
      const latest = await api.getRun(run.id);
      setRun(latest);
      if (caseRecord) setCaseRecord(await api.getCase(caseRecord.id));
    }
    return reply;
  }

  async function handleAction(action: HumanAction) {
    if (!caseRecord) return;
    setError(null);
    const updated = await api.sendAction(caseRecord.id, action);
    await refresh(updated);
  }

  async function handleActivatePolicy(reason: string) {
    setPolicy(await api.activatePolicy(reason));
  }

  return (
    <div className="app">
      <header className="app-head">
        <h1>InvoiceReferee</h1>
        <p className="muted">
          Hồ sơ hoàn ứng chi phí công ty — hệ thống tự xử lý thường quy và hỏi người khi cần.
        </p>
        {policy && (
          <p className="policy-line">
            Policy demo <strong>{policy.version}</strong> ·{' '}
            {policy.active ? 'đã kích hoạt' : 'chưa kích hoạt'} · hạn mức tự động{' '}
            {new Intl.NumberFormat('vi-VN').format(policy.auto_approval_max)}₫
          </p>
        )}
      </header>

      {error && (
        <div className="notice notice-error" role="alert">
          <span>{error}</span>
        </div>
      )}

      <main className="grid">
        <div className="col">
          {!caseRecord && <CaseForm onCreate={api.createCase} onCreated={handleCreated} />}
          {caseRecord && (
            <section className="panel" aria-labelledby="claim-heading">
              <h2 id="claim-heading">Hồ sơ đang xử lý</h2>
              <dl className="claim">
                <dt>Nhân viên</dt><dd>{caseRecord.claim.employee_id}</dd>
                <dt>Loại chi phí</dt><dd>{caseRecord.claim.profile}</dd>
                <dt>Mục đích</dt><dd>{caseRecord.claim.purpose}</dd>
                <dt>Số đề nghị</dt>
                <dd>{new Intl.NumberFormat('vi-VN').format(caseRecord.claim.requested_amount_vnd ?? 0)}₫</dd>
              </dl>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  stopPolling();
                  setCaseRecord(null);
                  setRun(null);
                  setPayment(null);
                }}
              >
                Nộp hồ sơ khác
              </button>
            </section>
          )}
        </div>

        <div className="col">
          {run && (
            <CaseDetail
              run={run}
              onStop={handleStop}
              caseRecord={caseRecord ?? undefined}
              paymentRequest={payment}
              policyActive={policy?.active ?? true}
              onActivatePolicy={handleActivatePolicy}
            />
          )}
          {run?.result && run.result.decision.issues.length > 0 && caseRecord && (
            <HumanActions
              caseRecord={caseRecord}
              decision={run.result.decision}
              onAction={handleAction}
            />
          )}
          <VerifyPanel />
        </div>
      </main>
    </div>
  );
}
