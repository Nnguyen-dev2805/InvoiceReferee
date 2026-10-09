// Thin settlement API client. Only transports requests and surfaces the
// `{code, message}` envelope; no decision logic lives here.
import type {
  AuditEntry,
  CaseSummary,
  CaseView,
  CreateCasePayload,
  QuestionView,
  Report,
  RespondPayload,
  ResponseView,
  ReviseSubmissionPayload,
  RunView,
  SourceView,
  StartRunPayload,
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
