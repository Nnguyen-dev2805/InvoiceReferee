// Thin settlement API client. Only transports requests and surfaces the
// `{code, message}` envelope; no decision logic lives here.
import type {
  AuditEntry,
  B3AdvanceEventPayload,
  B3AdvanceEventView,
  B3DecisionPayload,
  B3DecisionView,
  B3DemoContext,
  B3Intake,
  B3PresentPayload,
  B3PresentationView,
  B3RunContext,
  B7DecisionPayload,
  B7DecisionView,
  B7HandoffView,
  B7LinkedIntake,
  B7MoneyEventPayload,
  B7MoneyEventView,
  B7PresentPayload,
  B7PresentationView,
  B7RevalidationView,
  B7ClosureView,
  CaseSummary,
  CaseView,
  ClosurePayload,
  ClosureView,
  ControlPayload,
  CreateCasePayload,
  DecidePayload,
  DecisionView,
  DemoRole,
  HandoffPayload,
  MoneyEventPayload,
  MoneyEventView,
  QuestionView,
  Report,
  RespondPayload,
  ResponseView,
  ReviewNotePayload,
  ReviewView,
  ReviseSubmissionPayload,
  RunView,
  SourceView,
  StartRunPayload,
  VerifySuiteReport,
} from './types';

export class ApiError extends Error {
  code: string;
  status: number;
  currentCaseVersion: number | null;
  constructor(code: string, message: string, status: number,
             currentCaseVersion: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.currentCaseVersion = currentCaseVersion;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError('NETWORK_ERROR', 'Không kết nối được tới máy chủ.', 0);
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const code = body && typeof body.code === 'string' ? body.code : 'HTTP_ERROR';
    const message =
      body && typeof body.message === 'string' ? body.message : 'Yêu cầu thất bại.';
    const version =
      body && typeof body.current_case_version === 'number'
        ? body.current_case_version
        : null;
    throw new ApiError(code, message, response.status, version);
  }
  return body as T;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export function createCase(payload: CreateCasePayload): Promise<CaseView> {
  return request<CaseView>('/api/cases', {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function listCases(): Promise<CaseSummary[]> {
  return request<CaseSummary[]>('/api/cases');
}

export function getCase(id: string): Promise<CaseView> {
  return request<CaseView>(`/api/cases/${encodeURIComponent(id)}`);
}

export function deleteCase(id: string): Promise<void> {
  return request<void>(`/api/cases/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function reviseSubmission(id: string, payload: ReviseSubmissionPayload): Promise<CaseView> {
  return request<CaseView>(`/api/cases/${encodeURIComponent(id)}/submission`, {
    method: 'PATCH',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function addSource(
  caseId: string,
  file: File,
  expectedCaseVersion: number,
  actorId: string,
  demoRole: string,
  note: string,
): Promise<SourceView> {
  const form = new FormData();
  form.append('file', file);
  form.append('actor_id', actorId);
  form.append('demo_role', demoRole);
  form.append('expected_case_version', String(expectedCaseVersion));
  if (note) form.append('note', note);
  return request<SourceView>(`/api/cases/${encodeURIComponent(caseId)}/sources`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: form,
  });
}

export function sourceContentUrl(sourceId: string, download = false): string {
  return `/api/sources/${encodeURIComponent(sourceId)}/content${download ? '?download=true' : ''}`;
}

export function getHistory(caseId: string): Promise<AuditEntry[]> {
  return request<AuditEntry[]>(`/api/cases/${encodeURIComponent(caseId)}/history`);
}

export function startRun(caseId: string, payload: StartRunPayload): Promise<RunView> {
  return request<RunView>(`/api/cases/${encodeURIComponent(caseId)}/runs`, {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: string): Promise<RunView> {
  return request<RunView>(`/api/runs/${encodeURIComponent(runId)}`);
}

export function getReport(runId: string): Promise<Report> {
  return request<Report>(`/api/runs/${encodeURIComponent(runId)}/report`);
}

export function getQuestions(caseId: string): Promise<QuestionView[]> {
  return request<QuestionView[]>(`/api/cases/${encodeURIComponent(caseId)}/questions`);
}

export function respondQuestion(
  questionId: string,
  payload: RespondPayload,
): Promise<ResponseView> {
  return request<ResponseView>(
    `/api/questions/${encodeURIComponent(questionId)}/responses`, {
      method: 'POST',
      headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(payload),
    });
}

// --- W05: decision, review, money, control, handoff, closure -------------------

function postCommand<T>(path: string, payload: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}

export function decide(caseId: string, payload: DecidePayload): Promise<DecisionView> {
  return postCommand<DecisionView>(
    `/api/cases/${encodeURIComponent(caseId)}/decisions`, payload);
}

export function review(caseId: string, payload: ReviewNotePayload): Promise<ReviewView> {
  return postCommand<ReviewView>(
    `/api/cases/${encodeURIComponent(caseId)}/reviews`, payload);
}

export function recordMoney(
  caseId: string,
  payload: MoneyEventPayload,
): Promise<MoneyEventView> {
  return postCommand<MoneyEventView>(
    `/api/cases/${encodeURIComponent(caseId)}/money-events`, payload);
}

export interface ControlResult {
  case_id: string;
  action: 'STOP' | 'RESUME';
  reason: string;
  stop_active: boolean;
  control_epoch: number;
  case_version: number;
  actor_id: string;
  created_at: string;
  idempotent_replay?: boolean;
}

export function controlCase(
  caseId: string,
  payload: ControlPayload,
): Promise<ControlResult> {
  return postCommand<ControlResult>(
    `/api/cases/${encodeURIComponent(caseId)}/control`, payload);
}

export interface HandoffResult {
  id: string;
  case_id: string;
  decision_id: string;
  report_id: string;
  actor_id: string;
  created_at: string;
  idempotent_replay?: boolean;
}

export function handoff(
  caseId: string,
  payload: HandoffPayload,
): Promise<HandoffResult> {
  return postCommand<HandoffResult>(
    `/api/cases/${encodeURIComponent(caseId)}/handoffs`, payload);
}

export function closeCase(caseId: string, payload: ClosurePayload): Promise<ClosureView> {
  return postCommand<ClosureView>(
    `/api/cases/${encodeURIComponent(caseId)}/closures`, payload);
}

// --- W06: evaluation / Verify ---------------------------------------------------

export function getDemoContext(): Promise<B3DemoContext> {
  return request<B3DemoContext>('/api/demo-context');
}

export function createB3Case(
  actorId: string,
  intake: B3Intake,
): Promise<CaseView> {
  return request<CaseView>('/api/b3-cases', {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ actor_id: actorId, intake }),
  });
}

export function getB3RunContext(runId: string): Promise<B3RunContext> {
  return request<B3RunContext>(
    `/api/runs/${encodeURIComponent(runId)}/b3-context`);
}

export function presentB3(
  caseId: string,
  payload: B3PresentPayload,
): Promise<B3PresentationView> {
  return postCommand<B3PresentationView>(
    `/api/cases/${encodeURIComponent(caseId)}/b3-presentations`, payload);
}

export function decideB3(
  caseId: string,
  payload: B3DecisionPayload,
): Promise<B3DecisionView> {
  return postCommand<B3DecisionView>(
    `/api/cases/${encodeURIComponent(caseId)}/b3-decisions`, payload);
}

export function uploadB3AdvanceProof(
  caseId: string,
  file: File,
  expectedCaseVersion: number,
  actorId: string,
  demoRole: string,
  note: string,
): Promise<SourceView> {
  const form = new FormData();
  form.append('file', file);
  form.append('actor_id', actorId);
  form.append('demo_role', demoRole);
  form.append('expected_case_version', String(expectedCaseVersion));
  if (note) form.append('note', note);
  return request<SourceView>(
    `/api/cases/${encodeURIComponent(caseId)}/b3-advance-proofs`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: form,
    });
}

export function recordB3Advance(
  caseId: string,
  payload: B3AdvanceEventPayload,
): Promise<B3AdvanceEventView> {
  return postCommand<B3AdvanceEventView>(
    `/api/cases/${encodeURIComponent(caseId)}/b3-advance-events`, payload);
}

export function prepareLinkedB7(
  parentCaseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number },
): Promise<CaseView> {
  return postCommand<CaseView>(
    `/api/cases/${encodeURIComponent(parentCaseId)}/settlements`, payload);
}

export function reviseLinkedB7(
  childCaseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number; intake: B7LinkedIntake },
): Promise<CaseView> {
  return request<CaseView>(
    `/api/cases/${encodeURIComponent(childCaseId)}/settlement-submission`, {
      method: 'PUT',
      headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(payload),
    });
}

export function recordB7CompanyPacket(
  childCaseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number; packet: unknown },
): Promise<CaseView> {
  return postCommand<CaseView>(
    `/api/cases/${encodeURIComponent(childCaseId)}/settlement-company-context`,
    payload);
}

export function refreshLinkedB7Context(
  childCaseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number },
): Promise<CaseView> {
  return postCommand<CaseView>(
    `/api/cases/${encodeURIComponent(childCaseId)}/settlement-context/refresh`,
    payload);
}

export function presentB7(
  childCaseId: string,
  payload: B7PresentPayload,
): Promise<B7PresentationView> {
  return postCommand<B7PresentationView>(
    `/api/cases/${encodeURIComponent(childCaseId)}/settlement-presentations`,
    payload);
}

export function decideB7(
  childCaseId: string,
  payload: B7DecisionPayload,
): Promise<B7DecisionView> {
  return postCommand<B7DecisionView>(
    `/api/cases/${encodeURIComponent(childCaseId)}/settlement-decisions`,
    payload);
}

// --- B9: settlement fulfillment & closure -------------------------------------

export function uploadB7Proof(
  caseId: string,
  file: File,
  expectedCaseVersion: number,
  actorId: string,
  demoRole: string,
  note: string,
): Promise<SourceView> {
  const form = new FormData();
  form.append('file', file);
  form.append('actor_id', actorId);
  form.append('demo_role', demoRole);
  form.append('expected_case_version', String(expectedCaseVersion));
  if (note) form.append('note', note);
  return request<SourceView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-money-proofs`, {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: form,
    });
}

export function recordB7Money(
  caseId: string,
  payload: B7MoneyEventPayload,
): Promise<B7MoneyEventView> {
  return postCommand<B7MoneyEventView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-money-events`, payload);
}

export function refreshB7MoneyContext(
  caseId: string,
  payload: { actor_id: string; demo_role: DemoRole; expected_case_version: number },
): Promise<CaseView> {
  return postCommand<CaseView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-money-context/refresh`,
    payload);
}

export function revalidateB7(
  caseId: string,
  payload: { actor_id: string; demo_role: DemoRole; expected_case_version: number },
): Promise<B7RevalidationView> {
  return postCommand<B7RevalidationView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-revalidations`, payload);
}

export function handoffB7(
  caseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number; decision_id: string; reason: string },
): Promise<B7HandoffView> {
  return postCommand<B7HandoffView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-handoffs`, payload);
}

export function closeB7(
  caseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number; decision_id: string;
             current_report_id: string; reason: string },
): Promise<B7ClosureView> {
  return postCommand<B7ClosureView>(
    `/api/cases/${encodeURIComponent(caseId)}/settlement-closures`, payload);
}

export function prepareB7Adjustment(
  closedCaseId: string,
  payload: { actor_id: string; demo_role: DemoRole;
             expected_case_version: number; reason: string },
): Promise<CaseView> {
  return postCommand<CaseView>(
    `/api/cases/${encodeURIComponent(closedCaseId)}/settlement-adjustments`,
    payload);
}

export function runSettlementVerify(
  packets: string[] | null,
): Promise<VerifySuiteReport> {
  return request<VerifySuiteReport>('/api/verify/settlement/run', {
    method: 'POST',
    headers: { ...JSON_HEADERS, 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ packets }),
  });
}
