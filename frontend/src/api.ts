// Thin API client. The backend is the single source of decision logic; this
// module only transports requests and surfaces the `{code, message}` envelope.
import type {
  AuditEvent,
  CaseRecord,
  HumanAction,
  PaymentRequest,
  PolicyDto,
  RunRecord,
  StopReply,
  VerifyJob,
} from './types';

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
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
    const message = body && typeof body.message === 'string' ? body.message : 'Yêu cầu thất bại.';
    throw new ApiError(code, message, response.status);
  }
  return body as T;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export function createCase(form: FormData): Promise<CaseRecord> {
  return request<CaseRecord>('/api/cases', { method: 'POST', body: form });
}

export function getCase(id: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/cases/${encodeURIComponent(id)}`);
}

export function listCases(): Promise<CaseRecord[]> {
  return request<CaseRecord[]>('/api/cases');
}

export function startRun(id: string): Promise<RunRecord> {
  return request<RunRecord>(`/api/cases/${encodeURIComponent(id)}/runs`, { method: 'POST' });
}

export function getRun(id: string): Promise<RunRecord> {
  return request<RunRecord>(`/api/runs/${encodeURIComponent(id)}`);
}

export function sendAction(id: string, action: HumanAction): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/actions`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(action),
  });
}

export function addEvidence(
  id: string,
  action: { mode: string; reason: string; issue_id?: string | null },
  files: File[],
  roles: string[],
): Promise<CaseRecord> {
  const form = new FormData();
  form.append('action_json', JSON.stringify(action));
  form.append('roles', JSON.stringify(roles));
  files.forEach((file) => form.append('files', file));
  return request<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/actions`, {
    method: 'POST',
    body: form,
  });
}

export function stopRun(id: string): Promise<StopReply> {
  return request<StopReply>(`/api/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' });
}

export function getHistory(id: string): Promise<AuditEvent[]> {
  return request<AuditEvent[]>(`/api/cases/${encodeURIComponent(id)}/history`);
}

export function getPaymentRequest(id: string): Promise<PaymentRequest | null> {
  return request<PaymentRequest | null>(`/api/cases/${encodeURIComponent(id)}/payment-request`);
}

export function getEvidenceContentUrl(caseId: string, evidenceId: string, download = false): string {
  const base = `/api/cases/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(evidenceId)}/content`;
  return download ? `${base}?download=true` : base;
}

export function getPolicy(): Promise<PolicyDto> {
  return request<PolicyDto>('/api/policy');
}

export function startVerifyRun(suite: string, mode = 'replay'): Promise<VerifyJob> {
  return request<VerifyJob>('/api/verify-runs', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ suite, mode }),
  });
}

export function getVerifyRun(id: string): Promise<VerifyJob> {
  return request<VerifyJob>(`/api/verify-runs/${encodeURIComponent(id)}`);
}
