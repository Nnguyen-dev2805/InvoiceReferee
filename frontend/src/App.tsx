import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from './api';
import { ApiError } from './api';
import type {
  AuditEvent,
  CaseRecord,
  DemoMode,
  HumanAction,
  PaymentRequest,
  PolicyDto,
  RunRecord,
  StopReply,
} from './types';
import { CaseForm } from './CaseForm';
import { CaseDetail } from './CaseDetail';
import { HumanActions } from './HumanActions';
import { Inbox } from './Inbox';
import { VerifyPanel } from './VerifyPanel';
import { KpiSummary } from './KpiSummary';
import { ToastProvider, useToast } from './Toast';
import { MODE_LABEL, MODE_ORDER, runInFlight } from './format';

const POLL_MS = 1000;

function AppContent() {
  const [role, setRole] = useState<DemoMode>('EMPLOYEE');
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [runsByCase, setRunsByCase] = useState<Record<string, RunRecord>>({});
  const [caseRecord, setCaseRecord] = useState<CaseRecord | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [payment, setPayment] = useState<PaymentRequest | null>(null);
  const [policy, setPolicy] = useState<PolicyDto | null>(null);
  const [history, setHistory] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const toast = useToast();

  // Load the case list plus the current run of each case, so the inbox can show
  // role ownership and "processing" state without recomputing any decision.
  const loadCases = useCallback(async () => {
    const list = await api.listCases();
    const runs: Record<string, RunRecord> = {};
    await Promise.all(
      list
        .filter((c) => c.current_run_id)
        .map(async (c) => {
          runs[c.id] = await api.getRun(c.current_run_id as string);
        }),
    );
    setCases(list);
    setRunsByCase(runs);
  }, []);

  useEffect(() => {
    api.getPolicy().then(setPolicy).catch(() => setPolicy(null));
    loadCases().catch((err) =>
      setError(err instanceof Error ? err.message : 'Không tải được danh sách hồ sơ.'),
    );
  }, [loadCases]);

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
            setHistory(await api.getHistory(latest.case_id));
          }
          if (runInFlight(latest.status)) {
            pollRun(runId);
          } else {
            await loadCases(); // run finished: refresh role ownership in the inbox
            toast.info(`Hồ sơ đã hoàn tất lượt xử lý (${latest.status}).`);
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Không tải được trạng thái.');
        }
      }, POLL_MS);
    },
    [stopPolling, loadCases, toast],
  );

  useEffect(() => stopPolling, [stopPolling]);

  async function refresh(record: CaseRecord) {
    setCaseRecord(record);
    setPayment(await api.getPaymentRequest(record.id));
    setHistory(await api.getHistory(record.id));
    if (record.current_run_id) {
      const latest = await api.getRun(record.current_run_id);
      setRun(latest);
      if (runInFlight(latest.status)) pollRun(latest.id);
    }
  }

  async function openCase(caseId: string) {
    setError(null);
    try {
      await refresh(await api.getCase(caseId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không mở được hồ sơ.');
    }
  }

  async function handleCreated(record: CaseRecord) {
    setError(null);
    try {
      const started = await api.startRun(record.id);
      setCaseRecord(record);
      setRun(started);
      toast.success('Nộp hồ sơ thành công! Bắt đầu kiểm tra dữ kiện…');
      pollRun(started.id);
      await loadCases();
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
      toast.info('Đã dừng lượt xử lý hồ sơ.');
    }
    return reply;
  }

  async function handleAction(action: HumanAction) {
    if (!caseRecord) return;
    setError(null);
    const updated = await api.sendAction(caseRecord.id, action);
    toast.success('Đã gửi phản hồi ý kiến xử lý.');
    await refresh(updated);
    await loadCases();
  }

  const [tab, setTab] = useState<'cases' | 'verify'>('cases');

  function closeCase() {
    stopPolling();
    setCaseRecord(null);
    setRun(null);
    setPayment(null);
    setHistory([]);
  }

  return (
    <div className="app">
      <header className="app-head">
        <div className="app-head-top">
          <div>
            <h1>InvoiceReferee</h1>
            <p className="muted">
              Hồ sơ hoàn ứng chi phí công ty — hệ thống tự xử lý thường quy và hỏi người khi cần.
            </p>
          </div>
          <div className="field role-select">
            <label htmlFor="role">Vai trò (demo)</label>
            <select
              id="role"
              value={role}
              onChange={(event) => setRole(event.target.value as DemoMode)}
            >
              {MODE_ORDER.map((option) => (
                <option key={option} value={option}>
                  {MODE_LABEL[option]}
                </option>
              ))}
            </select>
          </div>
        </div>
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

      <nav className="tabs" aria-label="Điều hướng phân hệ">
        <button
          type="button"
          className={`tab-btn ${tab === 'cases' ? 'tab-btn-active' : ''}`}
          onClick={() => setTab('cases')}
          aria-selected={tab === 'cases'}
          role="tab"
        >
          Xử lý hồ sơ
        </button>
        <button
          type="button"
          className={`tab-btn ${tab === 'verify' ? 'tab-btn-active' : ''}`}
          onClick={() => setTab('verify')}
          aria-selected={tab === 'verify'}
          role="tab"
        >
          Kiểm thử hệ thống (Verify)
        </button>
      </nav>

      {tab === 'cases' ? (
        <>
          <KpiSummary cases={cases} role={role} runsByCase={runsByCase} />
          <main className="grid">
            <div className="col">
              {/* Only the employee submits cases; the other roles work the queue. */}
              {role === 'EMPLOYEE' && !caseRecord && (
                <CaseForm onCreate={api.createCase} onCreated={handleCreated} />
              )}
              <Inbox
                cases={cases}
                role={role}
                runsByCase={runsByCase}
                onOpen={openCase}
                selectedCaseId={caseRecord?.id}
              />
            </div>

            <div className="col">
              {caseRecord && (
                <section className="panel" aria-labelledby="claim-heading">
                  <h2 id="claim-heading">Hồ sơ đang xem</h2>
                  <dl className="claim">
                    <dt>Nhân viên</dt>
                    <dd>{caseRecord.claim.employee_id}</dd>
                    <dt>Loại chi phí</dt>
                    <dd>{caseRecord.claim.profile}</dd>
                    <dt>Mục đích</dt>
                    <dd>{caseRecord.claim.purpose}</dd>
                    <dt>Số đề nghị</dt>
                    <dd>
                      {new Intl.NumberFormat('vi-VN').format(
                        caseRecord.claim.requested_amount_vnd ?? 0,
                      )}
                      ₫
                    </dd>
                  </dl>
                  <button type="button" className="btn btn-ghost" onClick={closeCase}>
                    Đóng hồ sơ
                  </button>
                </section>
              )}

              {run && (
                <CaseDetail
                  run={run}
                  onStop={handleStop}
                  caseRecord={caseRecord ?? undefined}
                  paymentRequest={payment}
                  history={history}
                />
              )}
              {run?.result && caseRecord && (
                <HumanActions
                  caseRecord={caseRecord}
                  decision={run.result.decision}
                  onAction={handleAction}
                  currentRole={role}
                  onRoleChange={setRole}
                />
              )}
              {!caseRecord && !run && (
                <section className="panel empty-case-panel">
                  <p
                    className="muted"
                    style={{ margin: 0, textAlign: 'center', padding: 'var(--space-6) 0' }}
                  >
                    Chọn một hồ sơ từ hộp thư để xem chi tiết và thực hiện phê duyệt.
                  </p>
                </section>
              )}
            </div>
          </main>
        </>
      ) : (
        <main className="verify-tab-content">
          <VerifyPanel />
        </main>
      )}
    </div>
  );
}

export function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}
