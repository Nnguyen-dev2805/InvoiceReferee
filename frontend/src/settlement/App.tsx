// Settlement intake UI (W01/W05) + B3 v1 verbal intake (Task 4).
// Create a case, upload sources, reload, open the stored original; B3 v1 flow:
// persona demo → form/lời khai (WEB) hoặc draft từ giấy (IMPORT) → preview →
// confirm → report proposal. Persona chọn ở UI không xác thực danh tính.
import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from './api';
import { ApiError } from './api';
import { B3IntakeForm, emptyB3Intake } from './B3Intake';
import { ActionsPanel } from './Actions';
import { QuestionsPanel } from './Questions';
import { ReportPanel } from './Report';
import { VerifyPanel } from './Verify';
import type {
  B3DemoContext, B3Intake, B3RunContext, AuditEntry, CaseStage, CaseSummary,
  CaseView, DemoRole, Job, QuestionView, Report, RunView,
} from './types';

const STAGE_LABELS: Record<CaseStage, string> = {
  CHECKING: 'Đang kiểm tra nguồn',
  ACCOUNTING_REVIEW: 'Kế toán rà soát',
  AWAITING_DECISION: 'Chờ người có quyền quyết định',
  AWAITING_MONEY: 'Chờ thực nhận tiền',
  AWAITING_WORK_SETTLEMENT: 'Chờ quyết toán công việc',
  RESOLVING_OBLIGATIONS: 'Đang xử lý nghĩa vụ',
  REJECTED_REQUEST_ENDED: 'Yêu cầu bị từ chối đã kết thúc',
  SETTLEMENT_CLOSED: 'Hồ sơ đã đóng',
};

const ROLE_LABELS: Record<DemoRole, string> = {
  EMPLOYEE: 'Nhân viên',
  ACCOUNTANT: 'Kế toán',
  APPROVER: 'Người duyệt (demo)',
};

const SOURCE_ERROR_CODES = new Set([
  'UNSUPPORTED_FORMAT',
  'FILE_TOO_LARGE',
  'SOURCE_LIMIT_REACHED',
]);

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function nowLocalInput(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

function isB3V1Form(form: Record<string, unknown> | undefined): boolean {
  return form?.schema_version === 'b3-intake-v1';
}

export function App() {
  const [role, setRole] = useState<DemoRole>('EMPLOYEE');
  const [actorId, setActorId] = useState('NV-01');
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [view, setView] = useState<CaseView | null>(null);
  const [history, setHistory] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [questions, setQuestions] = useState<QuestionView[]>([]);
  const [b3RunContext, setB3RunContext] = useState<B3RunContext | null>(null);

  const [job, setJob] = useState<Job>('B7');
  const [employeeRef, setEmployeeRef] = useState('NV-01');
  const [workRef, setWorkRef] = useState('');
  const [purpose, setPurpose] = useState('');
  const [scope, setScope] = useState('');
  const [requestAmount, setRequestAmount] = useState('');
  const [forecastAmount, setForecastAmount] = useState('');
  const [moneyAsOf, setMoneyAsOf] = useState(nowLocalInput());
  const [knowledgeCutoff, setKnowledgeCutoff] = useState(nowLocalInput());

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNote, setUploadNote] = useState('');
  const [revisePurpose, setRevisePurpose] = useState('');
  const [reviseScope, setReviseScope] = useState('');
  const [reviseReason, setReviseReason] = useState('');

  // --- B3 v1 (verbal intake) state -------------------------------------------
  const [demoContext, setDemoContext] = useState<B3DemoContext | null>(null);
  const [demoContextError, setDemoContextError] = useState<string | null>(null);
  const [b3Method, setB3Method] = useState<'WEB' | 'IMPORT'>('WEB');
  const [b3PersonaRef, setB3PersonaRef] = useState('');
  const [b3Intake, setB3Intake] = useState<B3Intake>(emptyB3Intake('WEB'));
  const [b3ReviseIntake, setB3ReviseIntake] = useState<B3Intake | null>(null);
  const [b3ReviseReason, setB3ReviseReason] = useState('');
  const [activeIntakeTab, setActiveIntakeTab] = useState<'B3' | 'B7'>('B3');

  const loadCases = useCallback(async () => {
    try {
      setCases(await api.listCases());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được danh sách hồ sơ.');
    }
  }, []);

  const loadCase = useCallback(async (id: string) => {
    try {
      const next = await api.getCase(id);
      setView(next);
      setHistory(await api.getHistory(id));
      setReport(null);
      setRun(null);
      setB3RunContext(null);
      setQuestions(await api.getQuestions(id));
      if (next.current_run_id) {
        const currentRun = await api.getRun(next.current_run_id);
        setRun(currentRun);
        if (currentRun.status === 'SUCCEEDED') {
          const nextReport = await api.getReport(currentRun.id);
          setReport(nextReport);
          if (nextReport.b3) {
            setB3RunContext(await api.getB3RunContext(currentRun.id));
          }
        }
      }
      setRevisePurpose(String(next.submission.form.purpose ?? ''));
      setReviseScope(String(next.submission.form.scope ?? ''));
      setReviseReason('');
      setB3ReviseIntake(isB3V1Form(next.submission.form)
        ? {...(next.submission.form as unknown as B3Intake)}
        : null);
      setB3ReviseReason('');
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được hồ sơ.');
    }
  }, []);

  useEffect(() => {
    void loadCases();
  }, [loadCases]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const context = await api.getDemoContext();
        if (!cancelled) {
          setDemoContext(context);
          setDemoContextError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setDemoContext(null);
          setDemoContextError(e instanceof ApiError
            ? e.message
            : 'Không tải được company fixture demo.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const employees = useMemo(
    () => (demoContext?.people ?? []).filter((p) => p.role === 'EMPLOYEE'),
    [demoContext]);

  useEffect(() => {
    if (employees.length > 0 && !employees.some((p) => p.actor_ref === b3PersonaRef)) {
      setB3PersonaRef(employees[0].actor_ref);
    }
  }, [employees, b3PersonaRef]);

  useEffect(() => {
    if (b3PersonaRef) {
      setActorId(b3PersonaRef);
      setRole('EMPLOYEE');
    }
  }, [b3PersonaRef]);

  const handleCreate = async () => {
    if (!workRef.trim() || !purpose.trim()) {
      setError('Cần mã công việc và mục đích trước khi tạo hồ sơ.');
      return;
    }
    try {
      const created = await api.createCase({
        submission: {
          employee_ref: employeeRef.trim(),
          work_ref: workRef.trim(),
          job,
          money_as_of: new Date(moneyAsOf).toISOString(),
          knowledge_cutoff: new Date(knowledgeCutoff).toISOString(),
          form: {
            purpose: purpose.trim(),
            scope: scope.trim(),
            ...(job === 'B3' && requestAmount.trim()
              ? { request_amount_vnd: Number(requestAmount) } : {}),
            ...(job === 'B3' && forecastAmount.trim()
              ? { forecast_employee_vnd: Number(forecastAmount) } : {}),
          },
        },
        actor_id: actorId.trim(),
        demo_role: role,
      });
      setView(created);
      setHistory(await api.getHistory(created.id));
      setRevisePurpose(purpose.trim());
      setReviseScope(scope.trim());
      setError(null);
      setSourceError(null);
      await loadCases();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tạo được hồ sơ.');
    }
  };

  const startRunFor = useCallback(async (caseId: string, caseVersion: number) => {
    const started = await api.startRun(caseId, {
      actor_id: actorId.trim(),
      demo_role: role,
      expected_case_version: caseVersion,
    });
    return started;
  }, [actorId, role]);

  // --- B3 v1 handlers ----------------------------------------------------------

  const handleCreateB3 = async () => {
    const intake: B3Intake = {
      ...b3Intake,
      intake_method: b3Method,
      confirmed: b3Method === 'WEB',
    };
    try {
      const created = await api.createB3Case(b3PersonaRef || actorId.trim(), intake);
      setView(created);
      setHistory(await api.getHistory(created.id));
      setReport(null);
      setRun(null);
      setB3RunContext(null);
      setQuestions([]);
      setError(null);
      setSourceError(null);
      await loadCases();
      if (b3Method === 'WEB') {
        await startRunFor(created.id, created.case_version);
        await loadCase(created.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tạo được hồ sơ B3.');
    }
  };

  const handleFillFromDraft = () => {
    if (!report?.b3) return;
    const filled = {...report.b3.intake, confirmed: false};
    // Điền vào form sửa/xác nhận của case đang mở (nơi confirm được gửi);
    // đồng thời cập nhật form bên trái để giữ nhất quán nếu tạo hồ sơ mới.
    setB3ReviseIntake((current) => current === null ? current : filled);
    setB3Intake(filled);
  };

  const handleReviseB3 = async (confirmed: boolean) => {
    if (!view || !b3ReviseIntake) return;
    if (!b3ReviseReason.trim()) {
      setError('Cần lý do sửa/xác nhận để ghi history.');
      return;
    }
    try {
      const intake: B3Intake = {...b3ReviseIntake, confirmed};
      await api.reviseSubmission(view.id, {
        submission: {...view.submission, form: intake as unknown as Record<string, unknown>},
        actor_id: b3PersonaRef || actorId.trim(),
        demo_role: role,
        expected_case_version: view.case_version,
        reason: b3ReviseReason.trim(),
      });
      setError(null);
      setB3ReviseReason('');
      await loadCase(view.id);
      await loadCases();
      if (confirmed) {
        const next = await api.getCase(view.id);
        await startRunFor(view.id, next.case_version);
        await loadCase(view.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không sửa được khai báo B3.');
    }
  };

  const handleUpload = async () => {
    if (!view || !uploadFile) return;
    try {
      await api.addSource(view.id, uploadFile, view.case_version, actorId.trim(), role,
        uploadNote.trim());
      setUploadFile(null);
      setUploadNote('');
      setSourceError(null);
      await loadCase(view.id);
      await loadCases();
    } catch (e) {
      if (e instanceof ApiError && SOURCE_ERROR_CODES.has(e.code)) {
        setSourceError(`Nguồn bị từ chối kỹ thuật (${e.code}): ${e.message}`);
      } else {
        setError(e instanceof Error ? e.message : 'Không tải lên được nguồn.');
      }
    }
  };

  const handleStartRun = async () => {
    if (!view) return;
    try {
      await startRunFor(view.id, view.case_version);
      setError(null);
      await loadCases();
      await loadCase(view.id);  // case_version tăng khi run được accept
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không khởi động được run.');
    }
  };

  const handleRespond = async (questionId: string, draft: { content: string; sourceIds: string[] }) => {
    if (!view) return;
    try {
      await api.respondQuestion(questionId, {
        actor_id: actorId.trim(),
        demo_role: role,
        expected_case_version: view.case_version,
        content: draft.content.trim(),
        source_ids: draft.sourceIds,
      });
      setError(null);
      await loadCase(view.id);  // respond tăng case_version; làm mới view
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không gửi được trả lời.');
    }
  };

  const handleRevise = async () => {
    if (!view) return;
    if (!reviseReason.trim()) {
      setError('Cần lý do sửa để ghi history.');
      return;
    }
    try {
      await api.reviseSubmission(view.id, {
        submission: {
          ...view.submission,
          form: { purpose: revisePurpose.trim(), scope: reviseScope.trim() },
        },
        actor_id: actorId.trim(),
        demo_role: role,
        expected_case_version: view.case_version,
        reason: reviseReason.trim(),
      });
      setError(null);
      await loadCase(view.id);
      await loadCases();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không sửa được khai báo.');
    }
  };

  const runActive = run !== null && (run.status === 'QUEUED' || run.status === 'RUNNING');

  // Quyết định gần nhất từ history (DECISION_RECORDED) làm basis handoff.
  const decisionId = useMemo(() => {
    const recorded = [...history].reverse()
      .find((h) => h.kind === 'DECISION_RECORDED');
    const decision = recorded?.detail?.decision as { id?: string } | undefined;
    return decision?.id ?? null;
  }, [history]);

  const handleAction = async (action: string, perform: () => Promise<unknown>) => {
    if (!view) return;
    try {
      await perform();
      setError(null);
      await loadCase(view.id);  // mọi mutation tăng case_version; làm mới view
      await loadCases();
    } catch (e) {
      setError(e instanceof Error
        ? e.message
        : `Không thực hiện được ${action}.`);
    }
  };

  useEffect(() => {
    if (!run || !runActive) return;
    const timer = setInterval(async () => {
      try {
        const next = await api.getRun(run.id);
        setRun(next);
        if (next.status === 'SUCCEEDED') {
          await loadCase(next.case_id);  // làm mới case_version + report + questions
        } else if (next.status !== 'QUEUED' && next.status !== 'RUNNING' && next.detail) {
          setError(`Run kết thúc với ${next.status}: ${next.detail}`);
          await loadCase(next.case_id);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Không theo dõi được run.');
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [run?.id, runActive]);

  const canStartRun = view !== null
    && view.allowed_actions.some((a) => a.action === 'START_RUN')
    && !runActive;

  const viewIsB3 = view !== null && isB3V1Form(view.submission.form);
  const b3DraftReadyForFill = report?.b3 !== null
    && report?.b3.readiness === 'DRAFT_CONFIRMATION_REQUIRED';

  return (
    <div className="app">
      <header className="app-head">
        <h1>InvoiceReferee</h1>
        <div className="settlement-topbar">
          <div className="field">
            <label htmlFor="demo-role">Vai trò demo</label>
            <select id="demo-role" value={role} onChange={(e) => setRole(e.target.value as DemoRole)}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="actor-id">Mã người thao tác</label>
            <input id="actor-id" value={actorId} onChange={(e) => setActorId(e.target.value)} />
          </div>
        </div>
      </header>

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {sourceError && (
        <div className="notice notice-warn" role="alert">
          {sourceError} — đây là từ chối kỹ thuật của nguồn, không phải kết luận
          nghiệp vụ.
        </div>
      )}

      <div className="grid">
        <section className="col">
          <div className="tab-nav" role="tablist" aria-label="Loại hồ sơ nộp">
            <button
              type="button"
              role="tab"
              aria-selected={activeIntakeTab === 'B3'}
              className={`tab-btn ${activeIntakeTab === 'B3' ? 'active' : ''}`}
              onClick={() => setActiveIntakeTab('B3')}
            >
              Đề nghị tạm ứng (B3)
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeIntakeTab === 'B7'}
              className={`tab-btn ${activeIntakeTab === 'B7' ? 'active' : ''}`}
              onClick={() => setActiveIntakeTab('B7')}
            >
              Quyết toán sau công việc (B7)
            </button>
          </div>

          {activeIntakeTab === 'B3' && (
            <div className="panel" data-testid="b3-intake-panel">
              <h2>B3 — Đề nghị tạm ứng (giao việc bằng lời)</h2>
              {demoContextError && (
                <p className="notice-warn" role="alert">
                  Chưa cấu hình company fixture ({demoContextError}). Trỏ
                  SETTLEMENT_B3_CONTEXT_PATH tới file context (ví dụ gói
                  data/settlement/b3-verbal-v2) rồi restart backend; hệ thống
                  không tự tạo profile/quyền giả.
                </p>
              )}
              {demoContext && (
                <>
                  <div className="field">
                    <label htmlFor="b3-persona">Nhân viên nộp (persona demo)</label>
                    <select id="b3-persona" value={b3PersonaRef}
                            onChange={(e) => setB3PersonaRef(e.target.value)}>
                      {employees.map((person) => (
                        <option key={person.actor_ref} value={person.actor_ref}>
                          {person.name} — {person.department ?? person.actor_ref}
                          {' '}({person.actor_ref})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="b3-method">Cách nộp</label>
                    <select id="b3-method" value={b3Method}
                            onChange={(e) => setB3Method(
                              e.target.value as 'WEB' | 'IMPORT')}>
                      <option value="WEB">WEB — điền form trực tiếp</option>
                      <option value="IMPORT">
                        IMPORT — nộp giấy đề nghị + dự toán, AI đọc thành bản nháp
                      </option>
                    </select>
                  </div>
                  <B3IntakeForm value={b3Intake} onChange={setB3Intake}
                                disabled={false} />
                  <p className="muted">
                    Không nhập người duyệt/mã nội bộ/mốc thời gian trên form nghiệp
                    vụ; backend cấp mã hồ sơ, clocks lấy từ cấu hình.
                  </p>
                  <button className="btn btn-primary" onClick={() => void handleCreateB3()}
                          disabled={!b3PersonaRef}>
                    {b3Method === 'WEB'
                      ? 'Nộp đề nghị B3 (web)'
                      : 'Tạo hồ sơ nháp B3 (chưa xác nhận)'}
                  </button>
                  {b3Method === 'IMPORT' && (
                    <p className="muted">
                      Sau khi tạo nháp: tải hai giấy (đề nghị + dự toán) ở panel
                      Nguồn, bấm "Chạy kiểm tra" để AI đọc bản nháp, xem report
                      rồi quay lại đây điền/ chỉnh và bấm "Xác nhận nộp B3".
                    </p>
                  )}
                </>
              )}
            </div>
          )}

          {activeIntakeTab === 'B7' && (
            <div className="panel">
              <h2>Tạo hồ sơ (B7 / B3 legacy)</h2>
              <div className="field">
                <label htmlFor="job">Loại kiểm tra</label>
                <select id="job" value={job} onChange={(e) => setJob(e.target.value as Job)}>
                  <option value="B7">B7 — Quyết toán sau công việc</option>
                  <option value="B3">B3 — Kiểm tra đề nghị tạm ứng</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="employee-ref">Mã nhân viên</label>
                <input id="employee-ref" value={employeeRef}
                        onChange={(e) => setEmployeeRef(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="work-ref">Mã công việc</label>
                <input id="work-ref" value={workRef} onChange={(e) => setWorkRef(e.target.value)}
                        placeholder="CT-01" />
              </div>
              <div className="field">
                <label htmlFor="purpose">Mục đích công tác</label>
                <input id="purpose" value={purpose} onChange={(e) => setPurpose(e.target.value)}
                        placeholder="Công tác A" />
              </div>
              <div className="field">
                <label htmlFor="scope">Phạm vi</label>
                <input id="scope" value={scope} onChange={(e) => setScope(e.target.value)}
                        placeholder="Vé, khách sạn, tiếp khách trong CT-01" />
              </div>
              {job === 'B3' && (
                <>
                  <div className="field">
                    <label htmlFor="request-amount">Số xin ứng (VND, khai báo — không phải actual)</label>
                    <input id="request-amount" type="number" min="0"
                            value={requestAmount}
                            onChange={(e) => setRequestAmount(e.target.value)}
                            placeholder="2000000" />
                  </div>
                  <div className="field">
                    <label htmlFor="forecast-amount">Dự toán phần nhân viên (VND)</label>
                    <input id="forecast-amount" type="number" min="0"
                            value={forecastAmount}
                            onChange={(e) => setForecastAmount(e.target.value)}
                            placeholder="5000000" />
                  </div>
                </>
              )}
              <div className="field">
                <label htmlFor="money-as-of">Mốc tiền (money_as_of)</label>
                <input id="money-as-of" type="datetime-local" value={moneyAsOf}
                        onChange={(e) => setMoneyAsOf(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="knowledge-cutoff">Mốc kiến thức (knowledge_cutoff)</label>
                <input id="knowledge-cutoff" type="datetime-local" value={knowledgeCutoff}
                        onChange={(e) => setKnowledgeCutoff(e.target.value)} />
              </div>
              <button className="btn btn-primary" onClick={() => void handleCreate()}>
                Tạo hồ sơ
              </button>
            </div>
          )}

          <div className="panel">
            <h2>Hồ sơ</h2>
            {cases.length === 0 && <p className="muted">Chưa có hồ sơ nào.</p>}
            <ul>
              {cases.map((c) => (
                <li key={c.id}>
                  <button className="btn btn-ghost"
                          onClick={() => void loadCase(c.id)}>
                    {c.id} · {c.job} · {c.employee_ref}/{c.work_ref} ·{' '}
                    {STAGE_LABELS[c.stage]} (v{c.case_version})
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <VerifyPanel />
        </section>

        <section className="col">
          {view ? (
            <>
              <div className="panel">
                <h2>Hồ sơ {view.id}</h2>
                <p>
                  <strong>Giai đoạn:</strong> {STAGE_LABELS[view.stage]} · v
                  {view.case_version} (revision {view.input_revision}, epoch{' '}
                  {view.control_epoch})
                </p>
                {viewIsB3 ? (
                  <p>
                    <strong>Đề nghị B3:</strong>{' '}
                    {String(view.submission.form.purpose ?? '')}
                    {view.submission.form.destination
                      ? ` — ${String(view.submission.form.destination)}` : ''}
                    {' · '}
                    {view.submission.form.confirmed
                      ? 'đã xác nhận' : 'draft chưa xác nhận'}
                    {' · '}mã công việc <code>{view.submission.work_ref}</code>
                  </p>
                ) : (
                  <p>
                    <strong>Khai báo:</strong> {String(view.submission.form.purpose ?? '')}
                    {view.submission.form.scope
                      ? ` — phạm vi: ${String(view.submission.form.scope)}`
                      : ''}
                  </p>
                )}
                {view.allowed_actions.length > 0 && (
                  <>
                    <h3>Hành động cho phép</h3>
                    <ul className="reasons">
                      {view.allowed_actions.map((a) => (
                        <li key={a.action}>
                          <strong>{a.action}</strong> — {a.reason}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>

              <div className="panel">
                <h2>Nguồn ({view.sources.length})</h2>
                <div className="field">
                  <label>Thêm nguồn (JPEG/PNG/PDF/CSV/TXT/MD, tối đa 20 MiB)</label>
                  <input type="file"
                          onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)} />
                </div>
                <div className="field">
                  <label htmlFor="upload-note">
                    Ghi chú nguồn (bạn nói file lấy từ đâu — không tự xác thực issuer)
                  </label>
                  <input id="upload-note" value={uploadNote}
                          onChange={(e) => setUploadNote(e.target.value)}
                          placeholder="Ví dụ: sao kê do kế toán export" />
                </div>
                <button className="btn btn-primary" disabled={!uploadFile}
                        onClick={() => void handleUpload()}>
                  Tải lên nguồn
                </button>
                {view.sources.length > 0 && (
                  <table>
                    <thead>
                      <tr>
                        <th>File</th>
                        <th>Loại</th>
                        <th>Dung lượng</th>
                        <th>Mở gốc</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.sources.map((s) => (
                        <tr key={s.id}>
                          <td title={s.sha256}>{s.filename}</td>
                          <td>{s.media_type}</td>
                          <td>{formatBytes(s.size_bytes)}</td>
                          <td>
                            <a href={api.sourceContentUrl(s.id)} target="_blank"
                               rel="noreferrer">Xem</a>
                            {' · '}
                            <a href={api.sourceContentUrl(s.id, true)}>Tải xuống</a>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="panel" data-testid="run-panel">
                <h2>Kiểm tra</h2>
                {run && (
                  <>
                    <p>
                      Run <code>{run.id}</code> — <strong>{run.status}</strong>
                      {run.completion ? ` (${run.completion})` : ''} · chế độ{' '}
                      <strong>{run.mode}</strong>
                      {run.stage ? ` · stage: ${run.stage}` : ''}
                    </p>
                    {run.trace.length > 0 && (
                      <ul className="reasons">
                        {run.trace.map((entry) => (
                          <li key={entry.call_id}>
                            {entry.stage}
                            {entry.source_id ? ` · nguồn ${entry.source_id}` : ''}{' '}
                            — {entry.ok ? 'ok' : `lỗi ${entry.error_code}`}
                            {entry.usage
                              ? ` · tokens: ${entry.usage.total_tokens ?? '?'}`
                              : ' · usage: không có (None)'}
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
                <button className="btn btn-primary" disabled={!canStartRun}
                        onClick={() => void handleStartRun()}>
                  {viewIsB3
                    ? (view.submission.form.confirmed
                        ? 'Gửi kiểm tra B3'
                        : 'Đọc hồ sơ thành bản nháp (preview)')
                    : 'Chạy kiểm tra'}
                </button>
                {!canStartRun && runActive && (
                  <p className="muted">Đang chạy; không nhận run mới cho hồ sơ này.</p>
                )}
                {viewIsB3 && b3DraftReadyForFill && (
                  <div className="field">
                    <button className="btn" onClick={handleFillFromDraft}>
                      Điền form từ bản nháp report
                    </button>
                    <p className="muted">
                      Report vẫn là bản nháp chưa nộp: sau khi chỉnh, bấm
                      "Xác nhận nộp B3" ở panel sửa khai báo để confirm rồi
                      chạy lại.
                    </p>
                  </div>
                )}
              </div>

              {report && <ReportPanel report={report} b3Context={b3RunContext} />}

              <ActionsPanel
                view={view}
                role={role}
                actorId={actorId}
                decisionId={decisionId}
                reportReady={report !== null}
                onAction={handleAction}
              />

              <QuestionsPanel
                questions={questions}
                caseVersion={view.case_version}
                sourceIds={view.sources.map((s) => s.id)}
                role={role}
                onResponded={handleRespond}
              />

              {viewIsB3 && b3ReviseIntake ? (
                <div className="panel" data-testid="b3-revise-panel">
                  <h2>Sửa / xác nhận khai báo B3</h2>
                  <B3IntakeForm value={b3ReviseIntake}
                                onChange={setB3ReviseIntake}
                                disabled={false} />
                  <div className="field">
                    <label htmlFor="b3-revise-reason">Lý do sửa/xác nhận</label>
                    <input id="b3-revise-reason" value={b3ReviseReason}
                           onChange={(e) => setB3ReviseReason(e.target.value)}
                           placeholder="Sửa số xin sau khi xem lại dự toán" />
                  </div>
                  <button className="btn"
                          disabled={!b3ReviseReason.trim()}
                          onClick={() => void handleReviseB3(
                            Boolean(view.submission.form.confirmed))}>
                    Gửi revision (giữ nguyên trạng thái confirm)
                  </button>
                  {!view.submission.form.confirmed && (
                    <button className="btn btn-primary"
                            disabled={!b3ReviseReason.trim()}
                            onClick={() => void handleReviseB3(true)}>
                      Xác nhận nộp B3 (confirm + chạy lại kiểm tra)
                    </button>
                  )}
                  <p className="muted">
                    Sửa không xóa giấy đã nộp: form và giấy khác nhau vẫn là
                    mâu thuẫn phải làm rõ, không lấy form đè nguồn.
                  </p>
                </div>
              ) : (
                <div className="panel">
                  <h2>Sửa khai báo</h2>
                  <div className="field">
                    <label htmlFor="revise-purpose">Mục đích</label>
                    <input id="revise-purpose" value={revisePurpose}
                            onChange={(e) => setRevisePurpose(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="revise-scope">Phạm vi</label>
                    <input id="revise-scope" value={reviseScope}
                            onChange={(e) => setReviseScope(e.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="revise-reason">Lý do sửa</label>
                    <input id="revise-reason" value={reviseReason}
                            onChange={(e) => setReviseReason(e.target.value)} />
                  </div>
                  <button className="btn" onClick={() => void handleRevise()}>
                    Gửi revision
                  </button>
                </div>
              )}

              <div className="panel">
                <h2>History</h2>
                <ul>
                  {history.map((h) => (
                    <li key={h.id}>
                      {new Date(h.occurred_at).toLocaleString('vi-VN')} —{' '}
                      <strong>{h.kind}</strong> bởi {h.actor_id}
                    </li>
                  ))}
                </ul>
              </div>
            </>
          ) : (
            <div className="panel">
              <p className="muted">
                Chọn hoặc tạo một hồ sơ để xem giai đoạn, nguồn và history.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
