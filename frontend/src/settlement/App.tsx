// Settlement intake UI (W01/W05) + B3 v1 verbal intake (Task 4).
// Create a case, upload sources, reload, open the stored original; B3 v1 flow:
// persona demo → form/lời khai (WEB) hoặc draft từ giấy (IMPORT) → preview →
// confirm → report proposal. Persona chọn ở UI không xác thực danh tính.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as api from './api';
import { ApiError } from './api';
import { B3IntakeForm, emptyB3Intake } from './B3Intake';
import { CaseActionsPanel } from './CaseActionsPanel';
import { QuestionsPanel } from './Questions';
import { ReportPanel } from './Report';
import { ProcessingDetails } from './ProcessingDetails';
import { SourceUploadPanel } from './SourceUploadPanel';
import { DocumentViewer } from './DocumentViewer';
import { AccountingDesk } from './AccountingDesk';
import { ApprovalDesk } from './ApprovalDesk';
import { STAGE_LABELS, formatMoney, roleLabel } from './displayText';
import { formatTripDates, isB3V1Form } from './lib/b3Form';
import { TechDrawer } from './components/TechDrawer';
import { PersonaPicker } from './components/PersonaPicker';
import { CaseListItem } from './components/CaseListItem';
import { HistoryTab } from './components/HistoryTab';
import { CaseHeaderCard } from './components/CaseHeaderCard';
import { useCaseWorkspace } from './useCaseWorkspace';
import type {
  B3DemoContext, B3Intake, CaseSummary, DemoRole,
} from './types';


export function App() {
  // One demo user drives both the submitter and the actor at command time; role
  // is derived from the chosen person, never an independent picker.
  const [selectedActorRef, setSelectedActorRef] = useState('');
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The workspace hook owns the verified load/poll lifecycle (view/run/report/
  // questions/history/b3Context) with a request generation, so a late response
  // for case A cannot overwrite case B.
  const {
    workspace, error: workspaceError, load: loadWorkspace,
  } = useCaseWorkspace(selectedCaseId);
  const view = workspace?.view ?? null;
  const history = workspace?.history ?? [];
  const run = workspace?.run ?? null;
  const report = workspace?.report ?? null;
  const questions = workspace?.questions ?? [];
  const b3RunContext = workspace?.b3Context ?? null;

  const [purpose, setPurpose] = useState('');
  const [scope, setScope] = useState('');

  const [revisePurpose, setRevisePurpose] = useState('');
  const [reviseScope, setReviseScope] = useState('');
  const [reviseReason, setReviseReason] = useState('');

  // --- B3 v1 (verbal intake) state -------------------------------------------
  const [demoContext, setDemoContext] = useState<B3DemoContext | null>(null);
  const [demoContextError, setDemoContextError] = useState<string | null>(null);
  const [b3Method, setB3Method] = useState<'WEB' | 'IMPORT'>('WEB');
  const [b3Intake, setB3Intake] = useState<B3Intake>(emptyB3Intake('WEB'));
  const [b3ReviseIntake, setB3ReviseIntake] = useState<B3Intake | null>(null);
  const [b3ReviseReason, setB3ReviseReason] = useState('');
  const [activeIntakeTab, setActiveIntakeTab] = useState<'B3' | 'B7'>('B3');
  const [b7PathMode, setB7PathMode] = useState<'linked' | 'direct'>('linked');
  const [caseTab, setCaseTab] = useState<'report' | 'draft' | 'sources' | 'questions' | 'history'>('report');
  const [caseSearch, setCaseSearch] = useState('');
  const [stageFilter, setStageFilter] = useState<'ALL' | 'CHECKING' | 'DECISION_MONEY' | 'AWAITING_DECISION' | 'CLOSED'>('ALL');
  const [isCreatingB3, setIsCreatingB3] = useState(false);
  const [importFiles, setImportFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [copiedCaseId, setCopiedCaseId] = useState(false);
  const [showTechDrawer, setShowTechDrawer] = useState(false);
  const [activeDocSourceId, setActiveDocSourceId] = useState<string | null>(null);
  const [isUploadingSource, setIsUploadingSource] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [workbenchMode, setWorkbenchMode] = useState<'split' | 'doc' | 'form'>('split');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleCopyCaseId = useCallback(async (id: string) => {
    try {
      if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(id);
      }
    } catch {
      // Bỏ qua lỗi sao chép trong môi trường không cấp quyền clipboard
    }
    setCopiedCaseId(true);
    setTimeout(() => setCopiedCaseId(false), 2000);
  }, []);

  // People from the company fixture, with a stable suffix for duplicate names
  // (by people order) so the picker label is unique without using codes.
  const people = useMemo(() => {
    const raw = demoContext?.people ?? [];
    const seen = new Map<string, number>();
    return raw.map((p) => {
      const base = `${p.name} — ${roleLabel(p.role)}`;
      const count = (seen.get(base) ?? 0) + 1;
      seen.set(base, count);
      return { person: p, label: count > 1 ? `${base} (${count})` : base };
    });
  }, [demoContext]);

  // Default to the first person once the context loads; keep a valid selection.
  useEffect(() => {
    if (people.length === 0) return;
    if (!people.some((p) => p.person.actor_ref === selectedActorRef)) {
      setSelectedActorRef(people[0].person.actor_ref);
    }
  }, [people, selectedActorRef]);

  const selectedPerson = useMemo(
    () => demoContext?.people.find((p) => p.actor_ref === selectedActorRef) ?? null,
    [demoContext, selectedActorRef]);
  // Role/actor are derived from the chosen person, never an independent picker.
  const role: DemoRole = selectedPerson?.role ?? 'EMPLOYEE';
  const actorId = selectedActorRef;
  const identityReady = selectedPerson !== null;

  // Switching demo user with an unsaved draft must be explicit: cancel keeps
  // the current actor/draft/queue; accept clears the draft and un-uploaded queue
  // (persisted sources are never touched).
  const handlePersonChange = (nextRef: string) => {
    if (nextRef === selectedActorRef) return;
    const hasDraft = Boolean(b3Intake && (b3Intake.destination || b3Intake.purpose
      || b3Intake.request_amount_vnd || (b3Intake.estimate_rows?.length ?? 0) > 0));
    const hasQueue = importFiles.length > 0;
    if ((hasDraft || hasQueue)
        && !window.confirm('Chuyển người dùng sẽ bỏ bản nháp chưa lưu. Bạn có muốn tiếp tục?')) {
      return;
    }
    if (isCreatingB3 || isUploadingSource) return;  // don't switch mid-import
    setSelectedActorRef(nextRef);
    setStageFilter('ALL');
    setB3Intake(emptyB3Intake(b3Method));
    setImportFiles([]);
    setSelectedCaseId(null);
  };

  const filteredCases = useMemo(() => {
    let list = cases;
    if (role === 'EMPLOYEE') {
      list = actorId.trim() ? list.filter((c) => c.employee_ref === actorId.trim()) : list;
    } else if (role === 'ACCOUNTANT') {
      list = list.filter((c) => c.confirmed !== false);
      if (stageFilter === 'CHECKING') {
        list = list.filter((c) => c.stage === 'CHECKING' || c.stage === 'ACCOUNTING_REVIEW');
      } else if (stageFilter === 'DECISION_MONEY') {
        list = list.filter((c) =>
          c.stage === 'AWAITING_DECISION' ||
          c.stage === 'AWAITING_MONEY' ||
          c.stage === 'AWAITING_WORK_SETTLEMENT' ||
          c.stage === 'RESOLVING_OBLIGATIONS'
        );
      } else if (stageFilter === 'CLOSED') {
        list = list.filter((c) =>
          c.stage === 'SETTLEMENT_CLOSED' ||
          c.stage === 'REJECTED_REQUEST_ENDED'
        );
      }
    } else if (role === 'APPROVER') {
      list = list.filter((c) => c.confirmed !== false);
      if (stageFilter === 'AWAITING_DECISION') {
        list = list.filter((c) => c.stage === 'AWAITING_DECISION');
      } else if (stageFilter === 'DECISION_MONEY') {
        list = list.filter((c) =>
          c.stage === 'AWAITING_MONEY' ||
          c.stage === 'AWAITING_WORK_SETTLEMENT' ||
          c.stage === 'RESOLVING_OBLIGATIONS'
        );
      } else if (stageFilter === 'CLOSED') {
        list = list.filter((c) =>
          c.stage === 'SETTLEMENT_CLOSED' ||
          c.stage === 'REJECTED_REQUEST_ENDED'
        );
      }
    }

    const q = caseSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter((c) =>
      c.id.toLowerCase().includes(q) ||
      c.work_ref.toLowerCase().includes(q) ||
      c.employee_ref.toLowerCase().includes(q) ||
      (STAGE_LABELS[c.stage] ?? '').toLowerCase().includes(q)
    );
  }, [cases, caseSearch, role, actorId, stageFilter]);

  const handleAddImportFiles = (files: FileList | File[] | null) => {
    if (!files) return;
    const incoming = Array.from(files);
    if (incoming.length === 0) return;
    // Append every selected file: same name+size does not prove same bytes, so
    // dropping one would silently lose a real document.
    setImportFiles((prev) => [...prev, ...incoming]);
  };

  const handleRemoveImportFile = (index: number) => {
    setImportFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const loadCases = useCallback(async () => {
    try {
      setCases(await api.listCases());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được danh sách hồ sơ.');
    }
  }, []);

  const handleDeleteCase = async (id: string) => {
    if (!window.confirm(`Xoá hẳn hồ sơ ${id} khỏi hệ thống? Thao tác không thể hoàn tác.`)) {
      return;
    }
    try {
      await api.deleteCase(id);
      if (view?.id === id) setSelectedCaseId(null);
      await loadCases();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không xoá được hồ sơ.');
    }
  };

  const loadCase = useCallback(async (id: string) => {
    const summary = cases.find((c) => c.id === id);
    if ((role === 'ACCOUNTANT' || role === 'APPROVER') && summary?.confirmed === false) {
      setSelectedCaseId(null);
      return;
    }
    // Select the case (drives the workspace hook) and await the guarded load so
    // callers can read the committed workspace right after.
    setSelectedCaseId(id);
    await loadWorkspace(id);
  }, [cases, role, loadWorkspace]);

  // Derive the tab + revise/draft fields from the committed workspace (so a
  // case switch resets them consistently with the loaded data).
  useEffect(() => {
    if (!workspace) return;
    const next = workspace.view;
    const b3Form = isB3V1Form(next.submission.form)
      ? (next.submission.form as unknown as B3Intake)
      : null;
    if ((role === 'ACCOUNTANT' || role === 'APPROVER') && b3Form && !b3Form.confirmed) {
      setSelectedCaseId(null);
      return;
    }
    setRevisePurpose(String(next.submission.form.purpose ?? ''));
    setReviseScope(String(next.submission.form.scope ?? ''));
    setReviseReason('');
    const isUnconfirmedDraft = b3Form !== null
      && !b3Form.confirmed
      && !b3Form.destination
      && !b3Form.purpose
      && (!b3Form.estimate_rows || b3Form.estimate_rows.length === 0);
    const draftToUse = isUnconfirmedDraft && workspace.report?.b3?.intake
      ? { ...workspace.report.b3.intake, confirmed: false }
      : b3Form;
    setB3ReviseIntake(draftToUse);
    setB3ReviseReason('');
    if (workspace.questions.length > 0) {
      setCaseTab('questions');
    } else if (b3Form && !b3Form.confirmed) {
      setCaseTab('draft');
    } else {
      setCaseTab('report');
    }
  }, [workspace]);

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

  const handleCreateStandaloneB7 = async () => {
    if (!identityReady) {
      setError('Chưa tải được người dùng demo.');
      return;
    }
    if (!purpose.trim() || !scope.trim()) {
      setError('Cần mục đích và phạm vi trước khi tạo hồ sơ.');
      return;
    }
    try {
      const created = await api.createStandaloneB7(actorId.trim(), {
        purpose: purpose.trim(), scope: scope.trim(),
      });
      setSelectedCaseId(created.id);
      await loadCase(created.id);
      setRevisePurpose(purpose.trim());
      setReviseScope(scope.trim());
      setError(null);
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
    setIsCreatingB3(true);
    try {
      const created = await api.createB3Case(actorId.trim(), intake);
      setSelectedCaseId(created.id);
      await loadCase(created.id);
      setError(null);
      await loadCases();
      if (b3Method === 'WEB') {
        await startRunFor(created.id, created.case_version);
        await loadCase(created.id);
      } else if (b3Method === 'IMPORT' && importFiles.length > 0) {
        let currentCase = created;
        for (const file of importFiles) {
          try {
            await api.addSource(
              currentCase.id,
              file,
              currentCase.case_version,
              actorId.trim(),
              role,
              `Tệp đề nghị B3 (${file.name})`,
            );
            currentCase = await api.getCase(currentCase.id);
          } catch (fileErr) {
            setError(`Tải lên tệp "${file.name}" không thành công: ${fileErr instanceof Error ? fileErr.message : String(fileErr)}. Hồ sơ ${created.id} đã được tạo.`);
            await loadCase(currentCase.id);
            await loadCases();
            return;
          }
        }
        setImportFiles([]);
        await startRunFor(currentCase.id, currentCase.case_version);
        await loadCase(currentCase.id);
        await loadCases();
      } else {
        await loadCase(created.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tạo được hồ sơ B3.');
    } finally {
      setIsCreatingB3(false);
    }
  };

  const handleReviseB3 = async (confirmed: boolean) => {
    if (!view || !b3ReviseIntake) return;
    const isFirstConfirm = confirmed && !view.submission.form.confirmed;
    const reason = b3ReviseReason.trim()
      || (isFirstConfirm ? 'Xác nhận bản nháp từ tài liệu đính kèm' : !confirmed ? 'Lưu bản nháp đề nghị tạm ứng' : '');
    if (!reason) {
      setError('Cần lý do sửa/xác nhận để ghi history.');
      return;
    }
    try {
      const intake: B3Intake = {...b3ReviseIntake, confirmed};
      await api.reviseSubmission(view.id, {
        submission: {...view.submission, form: intake as unknown as Record<string, unknown>},
        actor_id: actorId.trim(),
        demo_role: role,
        expected_case_version: view.case_version,
        reason,
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

  // Dedicated prepare-settlement: use the returned child id directly instead of
  // reloading the parent and making the employee hunt for the new child case.
  const handlePrepareSettlement = async (caseId?: string, expectedVersion?: number) => {
    const targetId = caseId ?? view?.id;
    const targetVersion = expectedVersion ?? view?.case_version;
    if (!targetId) return;
    try {
      const child = await api.prepareLinkedB7(targetId, {
        actor_id: actorId.trim(),
        demo_role: role,
        expected_case_version: targetVersion ?? 1,
      });
      setError(null);
      await loadCases();
      await loadCase(child.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không mở được hồ sơ quyết toán.');
    }
  };

  const handleUploadWorkbenchSource = async (files: FileList | File[]) => {
    if (!view) return;
    try {
      setIsUploadingSource(true);
      for (const file of Array.from(files)) {
        await api.addSource(
          view.id,
          file,
          view.case_version,
          actorId.trim(),
          role,
          '',
        );
      }
      await loadCase(view.id);
      await loadCases();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Không tải được tệp đính kèm.');
    } finally {
      setIsUploadingSource(false);
    }
  };

  const canStartRun = view !== null
    && view.allowed_actions.some((a) => a.action === 'START_RUN')
    && !runActive;

  const viewIsB3 = view !== null && (view.job === 'B3' || isB3V1Form(view.submission.form));

  const b3EligibleCases = useMemo(() => {
    return cases.filter((c) => {
      const isMyCase = role !== 'EMPLOYEE' || c.employee_ref === actorId.trim();
      const isConfirmed = c.confirmed !== false;
      const isNotClosed = c.stage !== 'SETTLEMENT_CLOSED' && c.stage !== 'REJECTED_REQUEST_ENDED';
      const isNotRefused = c.stage !== 'ADVANCE_REQUEST_REFUSED' && c.stage !== 'SETTLEMENT_REQUEST_REFUSED';
      return c.job === 'B3' && isMyCase && isConfirmed && isNotClosed && isNotRefused;
    });
  }, [cases, role, actorId]);

  const latestReview = useMemo(() => {
    return history.filter(
      (h) => h.kind === 'REVIEW_RECORDED' || h.operation === 'RECORD_REVIEW'
    ).slice(-1)[0] ?? null;
  }, [history]);

  const b3WorkflowPending = viewIsB3
    && view?.b3_workflow?.status === 'PENDING';

  const getActorName = useCallback((ref: string) => {
    return demoContext?.people.find((p) => p.actor_ref === ref)?.name || ref;
  }, [demoContext]);

  const jobTitlePrefix = viewIsB3 ? 'Đề nghị tạm ứng' : 'Quyết toán';
  const mainTitle = view ? jobTitlePrefix : '';

  const sublineText = useMemo(() => {
    if (!view) return '';
    const form = (view.submission.form || {}) as Record<string, unknown>;
    const parts: string[] = [];
    if (form.destination) {
      parts.push(String(form.destination));
    }
    const tripDates = formatTripDates(form.trip_start, form.trip_end);
    if (tripDates) {
      parts.push(tripDates);
    }
    if (parts.length === 0) {
      if (form.request_amount_vnd != null) {
        parts.push(`Đề nghị ${formatMoney(Number(form.request_amount_vnd))}`);
      } else if (view.money_summary?.approved_vnd != null) {
        parts.push(`Đã duyệt ${formatMoney(Number(view.money_summary.approved_vnd))}`);
      } else if (view.submission.work_ref && view.submission.work_ref !== view.id) {
        parts.push(`Công việc: ${view.submission.work_ref}`);
      } else {
        parts.push('Chờ hoàn thiện thông tin');
      }
    }
    return parts.join(' · ');
  }, [view]);

  return (
    <div className="app">
      <header className="app-head">
        <div className="app-brand">
          <h1 className="app-brand-heading">InvoiceReferee</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {view && (
            <>
              <button
                type="button"
                className={`btn ${workbenchMode === 'form' ? 'btn-primary' : 'btn-secondary'} btn-sm`}
                data-testid="toggle-full-form-btn"
                onClick={() => setWorkbenchMode(workbenchMode === 'form' ? 'split' : 'form')}
                title={workbenchMode === 'form' ? 'Chia đôi màn hình để xem cùng chứng từ' : 'Ẩn cột chứng từ để chỉ xem toàn bộ biểu mẫu'}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  height: '36px',
                  borderRadius: 'var(--radius)',
                }}
              >
                {workbenchMode === 'form' ? (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <line x1="12" y1="3" x2="12" y2="21" />
                    </svg>
                    Xem cùng chứng từ
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <polyline points="15 3 21 3 21 9" />
                      <polyline points="9 21 3 21 3 15" />
                      <line x1="21" y1="3" x2="14" y2="10" />
                      <line x1="3" y1="21" x2="10" y2="14" />
                    </svg>
                    Chỉ xem toàn bộ biểu mẫu
                  </>
                )}
              </button>

              <button
                type="button"
                className="btn btn-secondary btn-sm"
                data-testid="debug-btn"
              onClick={() => setShowTechDrawer(true)}
              title="Mở bảng log hệ thống & kiểm toán (Debug)"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                fontSize: '0.82rem',
                fontWeight: 600,
                whiteSpace: 'nowrap',
                height: '36px',
                borderRadius: 'var(--radius)',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              Debug
            </button>
          </>
        )}
          <PersonaPicker
            role={role}
            selectedPersonName={selectedPerson?.name ?? null}
            selectedActorRef={selectedActorRef}
            people={people.map(({ person, label }) => ({
              actorRef: person.actor_ref, label,
            }))}
            onChange={handlePersonChange}
          />
        </div>
      </header>

      {error && <div className="notice notice-error" role="alert">{error}</div>}
      {workspaceError && !error && (
        <div className="notice notice-error" role="alert">{workspaceError}</div>
      )}

      <div className={`grid grid-master-detail ${sidebarCollapsed && view !== null ? 'sidebar-collapsed' : ''}`}>
        {/* ==================================================================
            CỘT TRÁI (SIDEBAR CÓ HỖ TRỢ THU GỌN)
            ================================================================== */}
        {sidebarCollapsed && view !== null ? (
          <section className="col col-sidebar is-collapsed">
            <button
              type="button"
              className="btn-toggle-sidebar btn-expand-sidebar"
              onClick={() => setSidebarCollapsed(false)}
              title="Mở rộng danh sách hồ sơ"
              aria-label="Mở rộng danh sách hồ sơ"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="13 17 18 12 13 7" />
                <polyline points="6 17 11 12 6 7" />
              </svg>
              <span className="collapsed-badge">{filteredCases.length}</span>
            </button>
            {role === 'EMPLOYEE' && (
              <button
                type="button"
                className="btn btn-primary btn-mini-new-case"
                onClick={() => setSelectedCaseId(null)}
                title="Tạo hồ sơ mới"
                aria-label="Tạo hồ sơ mới"
              >
                +
              </button>
            )}
          </section>
        ) : (
          <section className="col col-sidebar">
            {/* Nút Tạo hồ sơ mới cho Nhân viên, hoặc Nút Bàn làm việc cho Kế toán / Người duyệt */}
            {role === 'EMPLOYEE' ? (
              <div className="new-case-banner">
                <button
                  type="button"
                  className={`btn ${view === null ? 'btn-primary btn-new-case-active' : ''}`}
                  style={{ width: '100%', justifyContent: 'center', gap: '6px' }}
                  onClick={() => setSelectedCaseId(null)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  Tạo hồ sơ mới
                </button>
              </div>
            ) : (
              <div className="new-case-banner">
                <button
                  type="button"
                  className={`btn ${view === null ? 'btn-primary btn-new-case-active' : 'btn-outline-secondary'}`}
                  style={{ width: '100%', justifyContent: 'center', gap: '6px' }}
                  onClick={() => setSelectedCaseId(null)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="7" height="7"/>
                    <rect x="14" y="3" width="7" height="7"/>
                    <rect x="14" y="14" width="7" height="7"/>
                    <rect x="3" y="14" width="7" height="7"/>
                  </svg>
                  {role === 'ACCOUNTANT' ? 'Bàn làm việc Kế toán' : 'Bàn làm việc Người duyệt'}
                </button>
              </div>
            )}

            {/* Danh sách 24 hồ sơ có bộ lọc tìm kiếm nhanh và thanh cuộn độc lập */}
            <div className="panel case-list-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <h2 style={{ margin: 0, fontSize: '1.05rem' }}>
                    {role === 'EMPLOYEE' ? 'Hồ sơ của tôi' : 'Danh sách hồ sơ'}
                  </h2>
                  {filteredCases.length > 0 && <span className="badge">{filteredCases.length}</span>}
                </div>
                {view !== null && (
                  <button
                    type="button"
                    className="btn-toggle-sidebar"
                    onClick={() => setSidebarCollapsed(true)}
                    title="Thu gọn danh sách để mở rộng khu vực làm việc"
                    aria-label="Thu gọn danh sách hồ sơ"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="11 17 6 12 11 7" />
                      <polyline points="18 17 13 12 18 7" />
                    </svg>
                  </button>
                )}
              </div>

            {role === 'EMPLOYEE' ? null : cases.length > 0 ? (
              role === 'ACCOUNTANT' ? (
                <div className="case-stage-filter-pills" style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: 'var(--space-2)' }}>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'ALL' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('ALL')}
                  >
                    Tất cả
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'CHECKING' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('CHECKING')}
                  >
                    Cần rà soát
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'DECISION_MONEY' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('DECISION_MONEY')}
                  >
                    Chờ duyệt / Chi
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'CLOSED' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('CLOSED')}
                  >
                    Đã đóng
                  </button>
                </div>
              ) : (
                <div className="case-stage-filter-pills" style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: 'var(--space-2)' }}>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'ALL' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('ALL')}
                  >
                    Tất cả
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'AWAITING_DECISION' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('AWAITING_DECISION')}
                  >
                    Chờ phê duyệt
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'DECISION_MONEY' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('DECISION_MONEY')}
                  >
                    Đã duyệt / Chi
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${stageFilter === 'CLOSED' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 8px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setStageFilter('CLOSED')}
                  >
                    Đã đóng
                  </button>
                </div>
              )
            ) : null}

            {cases.length > 5 && (
              <div className="case-search-box">
                <input
                  type="text"
                  className="case-search-input"
                  placeholder="Tìm mã hồ sơ, nhân viên..."
                  value={caseSearch}
                  onChange={(e) => setCaseSearch(e.target.value)}
                />
              </div>
            )}

            {cases.length === 0 ? (
              <div className="case-empty-state" data-testid="case-empty-state">
                <p className="case-empty-title">
                  {role === 'EMPLOYEE'
                    ? 'Bạn chưa có hồ sơ nào'
                    : 'Không có hồ sơ'}
                </p>
              </div>
            ) : filteredCases.length === 0 ? (
              <div className="case-empty-state" data-testid="case-empty-state">
                <p className="case-empty-title">Không tìm thấy hồ sơ</p>
                <p className="case-empty-desc">Không có hồ sơ nào phù hợp với bộ lọc hiện tại.</p>
              </div>
            ) : (
              <div className="case-list-scrollable">
                <div className="case-list">
                  {filteredCases.map((c) => {
                    const isActive = c.id === view?.id;
                    const actorName = demoContext?.people.find(
                      (p) => p.actor_ref === c.employee_ref
                    )?.name;
                    return (
                      <CaseListItem
                        key={c.id}
                        item={c}
                        isActive={isActive}
                        actorName={actorName}
                        onOpen={(id) => void loadCase(id)}
                        onDelete={(id) => void handleDeleteCase(id)}
                      />
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </section>
        )}

        {/* ==================================================================
            CỘT PHẢI (WORKSPACE: FORM TẠO HỒ SƠ HOẶC CHI TIẾT HỒ SƠ ĐANG XEM)
            ================================================================== */}
        {view === null ? (
          <section className="col col-main">
            {role === 'ACCOUNTANT' && (
              <AccountingDesk
                cases={cases}
                getActorName={getActorName}
                stageLabels={STAGE_LABELS}
                onSelectCase={(id) => void loadCase(id)}
              />
            )}

            {role === 'APPROVER' && (
              <ApprovalDesk
                cases={cases}
                getActorName={getActorName}
                stageLabels={STAGE_LABELS}
                onSelectCase={(id) => void loadCase(id)}
              />
            )}

            {role === 'EMPLOYEE' && (
              <div className="intake-form-container">

              <div className="tab-nav" role="tablist" aria-label="Loại hồ sơ nộp">
              <button
                type="button"
                role="tab"
                aria-selected={activeIntakeTab === 'B3'}
                className={`tab-btn ${activeIntakeTab === 'B3' ? 'active' : ''}`}
                onClick={() => setActiveIntakeTab('B3')}
              >
                Đề nghị tạm ứng
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeIntakeTab === 'B7'}
                className={`tab-btn ${activeIntakeTab === 'B7' ? 'active' : ''}`}
                onClick={() => setActiveIntakeTab('B7')}
              >
                Quyết toán sau công việc
              </button>
            </div>

            {activeIntakeTab === 'B3' && (
              <div className="panel" data-testid="b3-intake-panel">
                <h2>Đề nghị tạm ứng</h2>
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
                      <label htmlFor="b3-method">Cách nộp</label>
                      <select id="b3-method" value={b3Method}
                              onChange={(e) => setB3Method(
                                e.target.value as 'WEB' | 'IMPORT')}>
                        <option value="WEB">Điền thông tin trực tiếp</option>
                        <option value="IMPORT">
                          Đính kèm hồ sơ & dự toán
                        </option>
                      </select>
                    </div>

                    {b3Method === 'IMPORT' && (
                      <div className="import-upload-card" data-testid="b3-import-upload-card">
                        <div
                          className={`dropzone ${isDragging ? 'dropzone-active' : ''}`}
                          onDragOver={(e) => {
                            e.preventDefault();
                            setIsDragging(true);
                          }}
                          onDragLeave={() => setIsDragging(false)}
                          onDrop={(e) => {
                            e.preventDefault();
                            setIsDragging(false);
                            if (e.dataTransfer.files) {
                              handleAddImportFiles(e.dataTransfer.files);
                            }
                          }}
                          onClick={() => fileInputRef.current?.click()}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              fileInputRef.current?.click();
                            }
                          }}
                        >
                          <input
                            ref={fileInputRef}
                            id="b3-import-file-input"
                            data-testid="b3-import-file-input"
                            type="file"
                            multiple
                            accept="image/*,application/pdf,.csv,.txt,.md"
                            style={{ display: 'none' }}
                            onChange={(e) => {
                              handleAddImportFiles(e.target.files);
                              e.target.value = '';
                            }}
                          />
                          <div className="dropzone-icon">
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                              <polyline points="17 8 12 3 7 8" />
                              <line x1="12" y1="3" x2="12" y2="15" />
                            </svg>
                          </div>
                          <div className="dropzone-text">
                            <strong>Chọn hoặc kéo thả tệp đính kèm</strong>
                            <span className="dropzone-subtext">PDF, hình ảnh, CSV</span>
                          </div>
                        </div>

                        {importFiles.length > 0 && (
                          <div className="attached-files-box" style={{ marginTop: 'var(--space-3)' }}>
                            <div className="attached-files-header">
                              <strong>Đã chọn {importFiles.length} tệp đính kèm:</strong>
                              <button
                                type="button"
                                className="btn-clear-all"
                                onClick={() => setImportFiles([])}
                              >
                                Xóa tất cả
                              </button>
                            </div>
                            <ul className="attached-files-list">
                              {importFiles.map((file, idx) => (
                                <li key={`${file.name}-${idx}`} className="attached-file-item">
                                  <span className="file-icon">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                                      <polyline points="14 2 14 8 20 8" />
                                    </svg>
                                  </span>
                                  <span className="file-name" title={file.name}>
                                    {file.name}
                                  </span>
                                  <span className="file-size">({(file.size / 1024).toFixed(0)} KB)</span>
                                  <button
                                    type="button"
                                    className="btn-remove-file"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleRemoveImportFile(idx);
                                    }}
                                    title="Gỡ tệp này"
                                    aria-label={`Xóa tệp ${file.name}`}
                                  >
                                    ✕
                                  </button>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                      </div>
                    )}

                    {b3Method === 'WEB' && (
                      <B3IntakeForm value={b3Intake} onChange={setB3Intake}
                                    disabled={false} />
                    )}
                    <button
                      className="btn btn-primary"
                      style={{ marginTop: 'var(--space-6)' }}
                      onClick={() => void handleCreateB3()}
                      disabled={!identityReady || isCreatingB3}
                    >
                      {isCreatingB3
                        ? 'Đang tạo hồ sơ...'
                        : b3Method === 'WEB' ? (
                          <>
                            <span>Gửi đề nghị tạm ứng</span>
                            <span className="sr-only">Nộp đề nghị B3 (web)</span>
                          </>
                        ) : (importFiles.length > 0 ? (
                          <>
                            <span>Gửi đề nghị tạm ứng</span>
                            <span className="sr-only">Tải lên & Tạo hồ sơ nháp B3</span>
                          </>
                        ) : (
                          <>
                            <span>Gửi đề nghị tạm ứng</span>
                            <span className="sr-only">Tạo hồ sơ nháp B3 (chưa xác nhận)</span>
                          </>
                        ))}
                    </button>
                  </>
                )}
              </div>
            )}

            {activeIntakeTab === 'B7' && (
              <div className="panel" data-testid="b7-create-panel">
                {b3EligibleCases.length > 0 ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: 'var(--space-4)', flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={`swiss-btn ${b7PathMode === 'linked' ? 'swiss-btn-primary' : 'swiss-btn-secondary'}`}
                        onClick={() => setB7PathMode('linked')}
                      >
                        Quyết toán từ hồ sơ tạm ứng ({b3EligibleCases.length})
                      </button>
                      <button
                        type="button"
                        className={`swiss-btn ${b7PathMode === 'direct' ? 'swiss-btn-primary' : 'swiss-btn-secondary'}`}
                        onClick={() => setB7PathMode('direct')}
                      >
                        Tự chi tiền túi (Không tạm ứng)
                      </button>
                    </div>

                    {b7PathMode === 'linked' ? (
                      <div className="b7-linked-section">
                        <p className="muted" style={{ fontSize: '0.88rem', margin: '0 0 var(--space-3)' }}>
                          Hệ thống tìm thấy các hồ sơ tạm ứng khả dụng. Chọn hồ sơ để mở quyết toán và tự động đối soát chênh lệch:
                        </p>
                        <div className="b7-eligible-cards" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          {b3EligibleCases.map((b3Case) => (
                            <div key={b3Case.id} className="b7-eligible-item">
                              <div className="b7-eligible-item-info">
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                  <span className="case-id-badge-code" style={{ fontSize: '0.85rem' }}>
                                    {b3Case.id}
                                  </span>
                                  <span className="case-stage-pill" style={{ fontSize: '0.75rem' }}>
                                    {STAGE_LABELS[b3Case.stage]}
                                  </span>
                                </div>
                                <div style={{ fontSize: '0.84rem', color: 'var(--color-muted-foreground)' }}>
                                  Mã công việc: <code style={{ fontWeight: 600, color: 'var(--color-foreground)' }}>{b3Case.work_ref}</code>
                                </div>
                              </div>
                              <button
                                type="button"
                                className="swiss-btn swiss-btn-primary swiss-btn-sm"
                                style={{ whiteSpace: 'nowrap' }}
                                onClick={() => void handlePrepareSettlement(b3Case.id, b3Case.case_version)}
                              >
                                Mở quyết toán liên kết →
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="b7-direct-section" style={{ maxWidth: '640px' }}>
                        <p className="muted" style={{ fontSize: '0.88rem', margin: '0 0 var(--space-3)' }}>
                          Dành cho chuyến công tác tự chi trả bằng tiền túi, không có khoản tạm ứng trước của công ty:
                        </p>
                        <div className="b7-direct-form" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                          <div className="field">
                            <label htmlFor="purpose">Mục đích công tác</label>
                            <input
                              id="purpose"
                              value={purpose}
                              onChange={(e) => setPurpose(e.target.value)}
                            />
                          </div>
                          <div className="field">
                            <label htmlFor="scope">Phạm vi chi phí</label>
                            <input
                              id="scope"
                              value={scope}
                              onChange={(e) => setScope(e.target.value)}
                            />
                          </div>
                          <button
                            type="button"
                            className="btn btn-primary"
                            style={{ marginTop: 'var(--space-2)', alignSelf: 'flex-start' }}
                            disabled={!identityReady || !purpose.trim() || !scope.trim()}
                            onClick={() => void handleCreateStandaloneB7()}
                          >
                            Tạo hồ sơ quyết toán
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="b7-standalone-container" style={{ maxWidth: '640px' }}>
                    <div className="b7-direct-form" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                      <div className="field">
                        <label htmlFor="purpose">Mục đích công tác</label>
                        <input
                          id="purpose"
                          value={purpose}
                          onChange={(e) => setPurpose(e.target.value)}
                        />
                      </div>
                      <div className="field">
                        <label htmlFor="scope">Phạm vi chi phí</label>
                        <input
                          id="scope"
                          value={scope}
                          onChange={(e) => setScope(e.target.value)}
                        />
                      </div>

                      <button
                        type="button"
                        className="btn btn-primary"
                        style={{ marginTop: 'var(--space-2)', alignSelf: 'flex-start' }}
                        disabled={!identityReady || !purpose.trim() || !scope.trim()}
                        onClick={() => void handleCreateStandaloneB7()}
                      >
                        Tạo hồ sơ quyết toán
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            </div>
          )}
        </section>
        ) : (
          <section className="col col-main case-detail-col">
            {/* Case Header Card */}
            <CaseHeaderCard
              view={view}
              viewIsB3={viewIsB3}
              role={role}
              actorId={actorId}
              mainTitle={mainTitle}
              sublineText={sublineText}
              b3WorkflowPending={b3WorkflowPending}
              latestReview={latestReview}
              copiedCaseId={copiedCaseId}
              onCopyCaseId={(id) => void handleCopyCaseId(id)}
              onOpenTech={() => setShowTechDrawer(true)}
              workbenchMode={workbenchMode}
              onWorkbenchModeChange={setWorkbenchMode}
              onBackToDesk={() => setSelectedCaseId(null)}
            />

            {/* Contextual Notice: Bổ sung câu hỏi giải trình */}
            {questions.length > 0 && (() => {
              const myPending = questions.filter(q => q.owner === role && q.status === 'OPEN');
              const otherPending = questions.filter(q => q.owner !== role && q.status === 'OPEN');
              const answered = questions.filter(q => q.status === 'ANSWERED');

              if (myPending.length > 0) {
                return (
                  <div className="case-notice-bar case-notice-warning">
                    <div className="case-notice-body">
                      <svg className="icon-notice" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <div>
                        <strong>Bạn có {myPending.length} câu hỏi cần giải trình</strong>
                        <span className="case-notice-subtext">Cần cung cấp thông tin hoặc tài liệu bổ sung để giải quyết vấn đề.</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCaseTab('questions')}
                    >
                      Trả lời câu hỏi ({myPending.length})
                    </button>
                  </div>
                );
              }

              if (otherPending.length > 0) {
                return (
                  <div className="case-notice-bar case-notice-info">
                    <div className="case-notice-body">
                      <svg className="icon-notice" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                      </svg>
                      <div>
                        <strong>Đang chờ vai trò khác giải trình ({otherPending.length} câu hỏi)</strong>
                        <span className="case-notice-subtext">Đã phân công cho {Array.from(new Set(otherPending.map(q => roleLabel(q.owner)))).join(', ')}.</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCaseTab('questions')}
                    >
                      Xem câu hỏi ({questions.length})
                    </button>
                  </div>
                );
              }

              if (answered.length > 0) {
                return (
                  <div className="case-notice-bar case-notice-info">
                    <div className="case-notice-body">
                      <svg className="icon-notice" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <div>
                        <strong>Đã gửi phản hồi ({answered.length} câu hỏi) — Chờ kiểm tra lại</strong>
                        <span className="case-notice-subtext">Phản hồi đã được ghi nhận; kết quả sẽ cập nhật sau lần chạy kiểm tra kế tiếp.</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setCaseTab('questions')}
                    >
                      Xem câu hỏi ({questions.length})
                    </button>
                  </div>
                );
              }

              return null;
            })()}



            {/* WORKBENCH SPLIT-SCREEN LAYOUT */}
            <div className={`workbench-split mode-${workbenchMode}`} data-testid="workbench-split">
              {/* CỘT TRÁI: DOCUMENT VIEWER */}
              <div className="workbench-doc-pane">
                <DocumentViewer
                  sources={view.sources}
                  selectedSourceId={activeDocSourceId}
                  onSelectSource={setActiveDocSourceId}
                  onUpload={handleUploadWorkbenchSource}
                  isUploading={isUploadingSource}
                  onToggleFormOnly={() => setWorkbenchMode('form')}
                />
              </div>

              {/* CỘT PHẢI: FORM / REPORT / TABS */}
              <div className="workbench-content-pane">
                {workbenchMode === 'form' && (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 14px',
                    marginBottom: 'var(--space-3)',
                    background: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderRadius: 'var(--radius)',
                    fontSize: '0.82rem',
                  }}>
                    <span style={{ color: '#475569', display: 'inline-flex', alignItems: 'center', gap: '6px', fontWeight: 500 }}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <rect x="3" y="3" width="18" height="18" rx="2" />
                      </svg>
                      Đang xem toàn bộ biểu mẫu (Đã ẩn cột chứng từ)
                    </span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setWorkbenchMode('split')}
                      style={{ padding: '3px 10px', fontSize: '0.78rem' }}
                    >
                      ◫ Xem cùng chứng từ
                    </button>
                  </div>
                )}

                {/* Case Tabs Navigation */}
                <div className="case-tabs-nav" role="tablist" aria-label="Các phần chi tiết của hồ sơ">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={caseTab === 'report'}
                    className={`case-tab-btn ${caseTab === 'report' ? 'case-tab-active' : ''}`}
                    onClick={() => setCaseTab('report')}
                  >
                    Kết quả &amp; Báo cáo
                  </button>
                  {viewIsB3 ? (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={caseTab === 'draft'}
                      className={`case-tab-btn ${caseTab === 'draft' ? 'case-tab-active' : ''}`}
                      onClick={() => setCaseTab('draft')}
                    >
                      Bản nháp B3
                      {!view.submission.form.confirmed && (
                        <span className="tab-count-badge badge-warning">Chưa gửi</span>
                      )}
                    </button>
                  ) : (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={caseTab === 'draft'}
                      className={`case-tab-btn ${caseTab === 'draft' ? 'case-tab-active' : ''}`}
                      onClick={() => setCaseTab('draft')}
                    >
                      Sửa khai báo
                    </button>
                  )}
                  <button
                    type="button"
                    role="tab"
                    aria-selected={caseTab === 'sources'}
                    className={`case-tab-btn ${caseTab === 'sources' ? 'case-tab-active' : ''}`}
                    onClick={() => setCaseTab('sources')}
                  >
                    Nguồn chứng từ
                    <span className="tab-count-badge">{view.sources.length}</span>
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={caseTab === 'questions'}
                    className={`case-tab-btn ${caseTab === 'questions' ? 'case-tab-active' : ''}`}
                    onClick={() => setCaseTab('questions')}
                  >
                    Câu hỏi
                    {(() => {
                      const myCount = questions.filter(q => q.owner === role && q.status === 'OPEN').length;
                      if (myCount > 0) {
                        return <span className="tab-count-badge badge-danger">{myCount}</span>;
                      }
                      if (questions.length > 0) {
                        return <span className="tab-count-badge">{questions.length}</span>;
                      }
                      return <span className="tab-count-badge">0</span>;
                    })()}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={caseTab === 'history'}
                    className={`case-tab-btn ${caseTab === 'history' ? 'case-tab-active' : ''}`}
                    onClick={() => setCaseTab('history')}
                  >
                    Lịch sử
                  </button>
                </div>

            {/* TAB 1: Kết quả & Báo cáo */}
            <div style={{ display: caseTab === 'report' ? 'block' : 'none' }}>
              {!report ? (
                <div className="panel" data-testid="run-panel" style={{ textAlign: 'center', padding: 'var(--space-8) var(--space-4)', marginBottom: 'var(--space-4)' }}>
                  <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 'var(--space-2)' }}>
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.5 }}>
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                  </div>
                  <h3 style={{ margin: '0 0 var(--space-2)' }}>Chưa có báo cáo kết quả</h3>
                  <p className="muted" style={{ maxWidth: '500px', margin: '0 auto var(--space-4)', fontSize: '0.9rem' }}>
                    {runActive
                      ? 'Hệ thống đang tiến hành đọc tài liệu và kiểm tra các điều kiện chính sách. Báo cáo kết quả sẽ hiển thị ngay khi hoàn tất.'
                      : (viewIsB3 && !view.submission.form.confirmed
                          ? 'Hồ sơ đã tải lên tài liệu đính kèm. Nhấn nút bên dưới để hệ thống trích xuất thông tin thành bản nháp.'
                          : 'Nhấn nút bên dưới để hệ thống tiến hành đối soát chính sách và đưa ra báo cáo đề xuất.')}
                  </p>
                  <div>
                    <button
                      className="btn btn-primary"
                      disabled={!canStartRun}
                      onClick={() => void handleStartRun()}
                    >
                      {viewIsB3
                        ? (view.submission.form.confirmed
                            ? 'Gửi kiểm tra B3'
                            : 'Đọc hồ sơ thành bản nháp (preview)')
                        : 'Chạy kiểm tra'}
                    </button>
                  </div>
                  {!canStartRun && runActive && (
                    <p className="muted" style={{ margin: 'var(--space-2) 0 0', fontSize: '0.85rem' }}>
                      Đang xử lý dữ liệu hồ sơ...
                    </p>
                  )}
                </div>
              ) : (
                <div data-testid="run-panel" style={{ marginBottom: 'var(--space-4)' }}>
                  <span className="sr-only">
                    {run?.mode === 'FAKE_OR_REPLAY'
                      ? 'Chế độ mô phỏng/replay — không phải chất lượng OCR/LLM thật'
                      : (run?.mode ? `Chế độ: ${run.mode}` : '')}
                  </span>
                  <ProcessingDetails run={run} report={report} />

                  <ReportPanel
                    report={report}
                    b3Context={b3RunContext}
                    sources={view.sources}
                    onOpenDebug={() => setShowTechDrawer(true)}
                  />
                </div>
              )}

              <CaseActionsPanel
                view={view}
                role={role}
                actorId={actorId}
                decisionId={decisionId}
                reportReady={report !== null}
                report={report}
                history={history}
                onAction={handleAction}
                people={demoContext?.people}
                receiptSources={demoContext?.receipt_sources}
                onPrepareSettlement={handlePrepareSettlement}
                onStartRun={handleStartRun}
                onOpenCase={(caseId) => void loadCase(caseId)}
              />
            </div>

            {/* TAB 2: Khai báo & Bản nháp */}
            <div style={{ display: caseTab === 'draft' ? 'block' : 'none' }}>
              {viewIsB3 && b3ReviseIntake && (
                <div className="panel" data-testid="b3-revise-panel">
                  <div style={{ marginBottom: 'var(--space-3)' }}>
                    <h2 style={{ margin: 0 }}>
                      {view.submission.form.confirmed
                        ? 'Sửa khai báo đề nghị B3'
                        : 'Kiểm tra & Xác nhận bản nháp B3'}
                    </h2>
                  </div>
                  <B3IntakeForm
                    value={b3ReviseIntake}
                    onChange={setB3ReviseIntake}
                    disabled={role !== 'EMPLOYEE'}
                  />
                  {role === 'EMPLOYEE' && Boolean(view.submission.form.confirmed) && (
                    <div className="field" style={{ marginTop: 'var(--space-3)' }}>
                      <label htmlFor="b3-revise-reason">Lý do điều chỉnh thông tin</label>
                      <input
                        id="b3-revise-reason"
                        value={b3ReviseReason}
                        onChange={(e) => setB3ReviseReason(e.target.value)}
                        placeholder="Ví dụ: Bổ sung chi phí công tác theo kế hoạch mới..."
                      />
                    </div>
                  )}
                  {role === 'EMPLOYEE' ? (
                    <div className="btn-group" style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
                      {!view.submission.form.confirmed ? (
                        <>
                          <button
                            type="button"
                            className="btn btn-primary"
                            onClick={() => void handleReviseB3(true)}
                          >
                            Xác nhận và gửi đề nghị
                          </button>
                          <button
                            type="button"
                            className="btn"
                            onClick={() => void handleReviseB3(false)}
                          >
                            Lưu bản nháp (chưa gửi)
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={!b3ReviseReason.trim()}
                          onClick={() => void handleReviseB3(true)}
                        >
                          Cập nhật khai báo
                        </button>
                      )}
                    </div>
                  ) : !view.submission.form.confirmed ? (
                    <div className="notice notice-warning" style={{ marginTop: 'var(--space-2)', fontSize: '0.86rem' }}>
                      Hồ sơ đang ở trạng thái bản nháp của nhân viên (chưa nộp). Kế toán / Người duyệt chỉ xem tham khảo, không thể gửi hoặc sửa bản nháp thay nhân viên.
                    </div>
                  ) : null}
                </div>
              )}

              {!viewIsB3 && (
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
            </div>

            {/* TAB 3: Nguồn chứng từ */}
            <div style={{ display: caseTab === 'sources' ? 'block' : 'none' }}>
              <SourceUploadPanel
                key={view.id}
                view={view}
                role={role}
                actorId={actorId}
                onChanged={async (caseId) => {
                  await loadCase(caseId);
                  await loadCases();
                }}
                onError={setError}
              />
            </div>

            {/* TAB 4: Câu hỏi */}
            <div style={{ display: caseTab === 'questions' ? 'block' : 'none' }}>
              <QuestionsPanel
                questions={questions}
                caseVersion={view.case_version}
                sourceIds={view.sources.map((s) => s.id)}
                sources={view.sources}
                role={role}
                onResponded={handleRespond}
              />
            </div>

            {/* TAB 5: Lịch sử & Kỹ thuật */}
            <div style={{ display: caseTab === 'history' ? 'block' : 'none' }}>
              <HistoryTab view={view} viewIsB3={viewIsB3} run={run} history={history} />
            </div>
          </div>
        </div>

        {/* TECHNICAL DETAILS DRAWER */}
        {showTechDrawer && (
          <TechDrawer
            view={view}
            run={run}
            report={report}
            sources={view.sources}
            b3Context={b3RunContext}
            onClose={() => setShowTechDrawer(false)}
          />
        )}
      </section>
        )}
      </div>
    </div>
  );
}
