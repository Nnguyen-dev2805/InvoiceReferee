import type { ActivityLinkSignalView, CaseView, CommandResultView, EmployeeReturnDraftView, SessionPayload } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Lỗi ${response.status}`;
    let code: string | undefined;
    try {
      const problem = (await response.json()) as { detail?: unknown; code?: unknown };
      if (typeof problem.detail === "string") message = problem.detail;
      if (typeof problem.code === "string") code = problem.code;
    } catch {
      // keep the status-based message
    }
    throw new ApiError(response.status, message, code);
  }
  return (await response.json()) as T;
}

export function newCommandId(): string {
  return `cmd:${crypto.randomUUID()}`;
}

export async function request<T>(
  path: string,
  body?: unknown,
  commandId?: string,
  version?: number,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (commandId) headers["X-Command-Id"] = commandId;
  if (version !== undefined) headers["X-Expected-Version"] = String(version);
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
  });
  return parse<T>(response);
}

export const api = {
  session: () => request<SessionPayload>("/api/demo/session"),
  switchPersona: (persona: string) =>
    request<SessionPayload>("/api/demo/persona", { persona }, newCommandId()),
  createCase: (activity: unknown) =>
    request<CommandResultView>("/api/cases", { activity }, newCommandId()),
  getCase: (id: string) => request<CaseView>(`/api/cases/${id}`),
  listCases: () => request<{ cases: CaseView[] }>("/api/cases"),
};

export async function submitCase(
  rootId: string,
  activityId: string | null,
  declaredPurpose: string,
  version: number,
  employeePaidClaims: Array<{
    invoice_reference: string;
    amount: number;
    refs: Array<{ source_id: string; source_sha256: string; page: number; exact_quote: string }>;
    reason: string;
  }> = [],
  declaration: {
    notes?: string | null;
    declared_name?: string | null;
    destination?: string | null;
    trip_start?: string | null;
    trip_end?: string | null;
    declared_advance?: number | null;
    incurred_total?: number | null;
    original_declared_advance?: number | null;
    confirmed_activity_id?: string | null;
  } = {},
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/submit`,
    {
      activity_id: activityId,
      declared_purpose: declaredPurpose,
      employee_paid_claims: employeePaidClaims,
      ...declaration,
    },
    newCommandId(),
    version,
  );
}

export async function answerIssue(
  rootId: string,
  body: {
    issue_id: string;
    basis_id: string;
    answer_kind: string;
    value: string | number | null;
    reason: string;
  },
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/answers`,
    body,
    newCommandId(),
    version,
  );
}

export async function runVerify(
  suite: string,
  mode: string,
): Promise<{
  suite: string;
  mode: string;
  total: number;
  union_dangerous_miss: number;
  release: boolean;
  rows: Array<{
    root_id: string;
    expected_route: string;
    actual_route: string;
    union_dangerous_miss: number;
    correct_auto_completion: number;
    technical_failure: number;
  }>;
}> {
  return request("/api/verify", { suite, mode }, newCommandId());
}

export async function controlCase(
  rootId: string,
  action: "STOP" | "RESUME",
  reason: string,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/control`,
    { action, reason },
    newCommandId(),
  );
}

export async function recordActual(
  rootId: string,
  money: Record<string, unknown>,
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/actuals`,
    { money },
    newCommandId(),
    version,
  );
}

export async function advanceDraft(
  rootId: string,
  files: File[],
  version: number,
  method: "TRANSFER" | "CASH" | null = null,
): Promise<{
  draft: {
    source_id: string;
    draft_id: string;
    amount: number | null;
    payer_name: string | null;
    payee_name: string | null;
    transaction_reference: string | null;
    activity_reference: string | null;
    activity_link_status: "LINKED" | "NEEDS_CONFIRMATION" | "NOT_FOUND" | "CONFLICT";
    matched_activity_id: string | null;
    activity_link_basis: string | null;
    activity_link_signals: ActivityLinkSignalView[];
    activity_link_candidate_count: number;
    instrument_method: "TRANSFER" | "CASH" | null;
    instrument_status: "COMPLETED" | "PENDING" | "FAILED" | "UNKNOWN";
    event_at: string | null;
    missing_fields: string[];
    requires_confirmation: boolean;
    already_recorded: boolean;
    refs: Array<{ source_id: string; source_sha256: string; page: number | null; exact_quote: string }>;
  };
  case_view: CaseView;
}> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const query = method ? `?method=${method}` : "";
  const response = await fetch(`/api/cases/${rootId}/advance/draft${query}`, {
    method: "POST",
    headers: {
      "X-Command-Id": newCommandId(),
      "X-Expected-Version": String(version),
    },
    body: form,
    credentials: "same-origin",
  });
  return parse(response);
}

export async function getAdvanceDraft(
  rootId: string, draftId?: string,
): Promise<Awaited<ReturnType<typeof advanceDraft>>> {
  const query = draftId ? `?draft_id=${encodeURIComponent(draftId)}` : "";
  return request(`/api/cases/${rootId}/advance/draft${query}`);
}

export async function confirmCoverage(
  rootId: string,
  coverage: {
    start: string;
    funds: string[];
    flow_kinds: string[];
    opening_balance: number;
    unallocated_event_ids: string[];
    witness_refs: Array<{
      source_id: string;
      source_sha256: string;
      page: number | null;
      exact_quote: string;
    }>;
    reason: string;
  },
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/coverage`,
    coverage,
    newCommandId(),
    version,
  );
}

export interface SettlementExpenseItem {
  description: string;
  invoice_no?: string;
  amount: number;
  source_filename?: string;
  status?: string;
  matched_invoice?: string;
  suggested_invoice?: string;
  seller?: string;
}

export interface SettlementInvoiceItem {
  filename: string;
  invoice_no: string | null;
  seller: string | null;
  amount: number | null;
}

export interface SettlementLinkCandidate {
  activity_id: string;
  name: string;
  basis: string | null;
  amount: number | null;
  occurred_at: string | null;
  employee: string | null;
}

export interface SettlementLink {
  status: "LINKED" | "NEEDS_CONFIRMATION" | "NOT_FOUND" | "CONFLICT";
  activity_id: string | null;
  basis: string | null;
  candidates: SettlementLinkCandidate[];
  reasons: string[];
  conflicting_fields: string[];
  owner: string | null;
  requires_confirmation: boolean;
  inherited: boolean;
}

export interface SettlementDraftResponse {
  declared_name: string | null;
  destination: string | null;
  activity_name: string | null;
  trip_start: string | null;
  trip_end: string | null;
  occurred_at: string | null;
  declared_purpose: string | null;
  incurred_total: number | null;
  declared_advance: number | null;
  expenses: SettlementExpenseItem[];
  warnings: string[];
  arithmetic_findings?: SettlementArithmeticFinding[];
  invoices: SettlementInvoiceItem[];
  field_states?: Record<string, string>;
  provider_mode?: string | null;
  data_origin?: string | null;
  link?: SettlementLink | null;
}

export interface SettlementArithmeticFinding {
  code: string;
  basis: string;
  question: string;
  refs: unknown[];
}

export async function settlementDraft(
  rootId: string,
  files: File[],
): Promise<SettlementDraftResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const response = await fetch(`/api/cases/${rootId}/settlement/draft`, {
    method: "POST",
    headers: { "X-Command-Id": newCommandId() },
    body: form,
    credentials: "same-origin",
  });
  return parse<SettlementDraftResponse>(response);
}

export async function getSettlementDraft(
  rootId: string,
): Promise<SettlementDraftResponse> {
  const response = await fetch(`/api/cases/${rootId}/settlement/draft`, {
    method: "GET",
    headers: { "X-Command-Id": newCommandId() },
    credentials: "same-origin",
  });
  return parse<SettlementDraftResponse>(response);
}

export async function attachSources(
  rootId: string,
  files: File[],
  version: number,
): Promise<CommandResultView> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const response = await fetch(`/api/cases/${rootId}/sources`, {
    method: "POST",
    headers: {
      "X-Command-Id": newCommandId(),
      "X-Expected-Version": String(version),
    },
    body: form,
    credentials: "same-origin",
  });
  return parse<CommandResultView>(response);
}

export async function readEmployeeReturnDraft(
  rootId: string,
  sourceId: string,
  instructionId: string,
  version: number,
): Promise<{ case_view: CaseView; draft: EmployeeReturnDraftView }> {
  return request(
    `/api/cases/${rootId}/return-draft`,
    { source_id: sourceId, instruction_id: instructionId, instrument_method: "TRANSFER" },
    newCommandId(),
    version,
  );
}

export function errorMessage(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}
