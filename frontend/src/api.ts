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
    settlement_type?: "ADVANCE_SETTLEMENT" | "EMPLOYEE_REIMBURSEMENT";
    submission_source?: "PAPER_SCAN" | "DIGITAL_FORM";
    digital_lines?: DigitalExpenseLineInput[];
    no_advance_asserted?: boolean;
    no_advance_reason?: string | null;
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

export interface VerifyRowView {
  root_id: string;
  expected_route: string;
  actual_route: string;
  passed: boolean;
  union_dangerous_miss: number;
  correct_auto_completion: number;
  technical_failure: number;
  failure_reasons: string[];
  expected_amounts: Record<string, number>;
  actual_amounts: Record<string, number>;
  expected_owner: string | null;
  actual_owner: string | null;
  question_required: boolean;
  question_present: boolean;
  question_review?: string;
  actual_issues?: Array<{kind:string; owner:string; field_or_rule?:string; question?:string; refs?:Array<{source_id:string;source_sha256:string;page:number;exact_quote:string}>}>;
  elapsed_ms: number;
}

export interface VerifyReportView {
  status?: "RUNNING" | "NEEDS_RECORDING" | "ERROR" | "COMPLETED";
  question_review?: string;
  run_id: string;
  started_at: string;
  finished_at: string;
  suite: string;
  mode: string;
  planned: number;
  attempted: number;
  completed: number;
  passed: number;
  release: boolean;
  union_dangerous_miss: number;
  dangerous_miss_rate: number | null;
  completion_rate: number | null;
  elapsed_ms: number;
  versions: {
    code: string;
    config: string;
    dataset: string;
    recording: string;
  };
  rows: VerifyRowView[];
}

export async function runVerify(
  suite: "core" | "escalation" | string = "core",
  mode: "RECORDED_REPLAY" | "LIVE" | "STUB" | string = "RECORDED_REPLAY",
): Promise<VerifyReportView> {
  return request<VerifyReportView>("/api/verify", { suite, mode }, newCommandId());
}

export async function getLastVerify(): Promise<VerifyReportView | null> {
  return request<VerifyReportView | null>("/api/verify/last");
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

export async function markExecution(rootId: string, body: {
  instruction_id: string; execution_state: "OPEN" | "CLOSED_CONFIRMED" | "UNKNOWN";
  refs: Array<{source_id: string; source_sha256: string; page: number; exact_quote: string}>;
  reason: string;
}, version: number): Promise<CommandResultView> {
  return request(`/api/cases/${rootId}/mark-execution`, body, newCommandId(), version);
}

export async function recheckMoneyHistory(rootId: string, version: number): Promise<CommandResultView> {
  return request(`/api/cases/${rootId}/money-history/recheck`, {reason: "Kế toán đã đối chiếu các giao dịch đã ghi nhận cho đúng hồ sơ; không xác nhận toàn bộ lịch sử ngân hàng."}, newCommandId(), version);
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
  description: string | null;
  invoice_no?: string;
  amount: number | null;
  amount_state?: string;
  description_state?: string;
  source_filename?: string;
  status?: string;
  matched_invoice?: string;
  suggested_invoice?: string;
  dispute?: ReconciliationFinding | null;
  seller?: string;
  evidence_files?: SettlementEvidenceFile[];
  exception_reason?: string | null;
}

export interface SettlementEvidenceFile {
  filename: string | null;
  document_id: string;
  document_type: string | null;
  link_status: string;
}

export interface ReconciliationFindingRef {
  source_id: string;
  source_sha256: string;
  page: number | null;
  exact_quote: string;
}

export interface ReconciliationFinding {
  code: string;
  item_ids?: string[];
  document_id: string;
  document_filename: string | null;
  paper_source_id?: string | null;
  document_source_id?: string | null;
  status: string;
  paper_amount: number | null;
  document_total: number | null;
  difference: number | null;
  basis: string;
  question: string;
  refs: ReconciliationFindingRef[];
  blocking: boolean;
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
  incurred_total_basis?: "PRINTED_TOTAL" | "ROW_SUM" | null;
  declared_advance: number | null;
  expenses: SettlementExpenseItem[];
  warnings: string[];
  arithmetic_findings?: SettlementArithmeticFinding[];
  invoices: SettlementInvoiceItem[];
  field_states?: Record<string, string>;
  provider_mode?: string | null;
  data_origin?: string | null;
  processing_status?: "ready" | "technical_incomplete" | "needs_supplement" | null;
  reconciliation_findings?: ReconciliationFinding[];
  link?: SettlementLink | null;
}

export interface SettlementArithmeticFinding {
  code: string;
  basis: string;
  question: string;
  refs: Array<{
    source_id: string;
    source_sha256: string;
    page: number | null;
    exact_quote: string;
  }>;
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

/** Role-aware draft read (16/10/2026): paper box + evidence box stay distinct. */
export async function settlementDraftByRole(
  rootId: string,
  paper: File[],
  evidence: File[],
): Promise<SettlementDraftResponse> {
  const form = new FormData();
  for (const file of paper) form.append("paper", file);
  for (const file of evidence) form.append("evidence", file);
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
  uploadRole?: "paper" | "evidence",
): Promise<CommandResultView> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (uploadRole) form.append("upload_role", uploadRole);
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

export interface DigitalExpenseLineInput {
  item_id: string;
  description: string;
  category?: string | null;
  expense_date: string;
  amount: number;
  evidence_status: "ORIGINAL" | "ALTERNATIVE" | "NO_EVIDENCE";
  alternative_type?: string | null;
  exception_reason?: string | null;
  note?: string | null;
  source_ids: string[];
}

export interface DigitalDeclarationInput {
  declared_purpose: string;
  settlement_type: "ADVANCE_SETTLEMENT" | "EMPLOYEE_REIMBURSEMENT";
  digital_lines: DigitalExpenseLineInput[];
  no_advance_asserted: boolean;
  no_advance_reason?: string | null;
}

export async function saveDigitalDeclaration(
  rootId: string,
  declaration: DigitalDeclarationInput,
): Promise<{ revision: number; canonical_hash: string }> {
  return request<{ revision: number; canonical_hash: string }>(
    `/api/cases/${rootId}/declaration/digital`,
    declaration,
    newCommandId(),
  );
}

export async function readDigitalDraft(
  rootId: string,
): Promise<SettlementDraftResponse> {
  return request<SettlementDraftResponse>(
    `/api/cases/${rootId}/digital/draft`,
    {},
    newCommandId(),
  );
}

export async function refuseException(
  rootId: string,
  body: { issue_ids: string[]; reason: string },
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/decisions/refuse`,
    body,
    newCommandId(),
    version,
  );
}

export async function decideIssues(
  rootId: string,
  body: {
    issue_ids: string[];
    basis_id: string;
    actions: string[];
    effect_scope: string;
    amount?: number | null;
    reason: string;
  },
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/decisions`,
    body,
    newCommandId(),
    version,
  );
}

export interface ExceptionPreview {
  basis_id?: string;
  case_version?: number;
  issue_id: string;
  rule_id: string | null;
  expense_id: string | null;
  amount: number | null;
  covered: boolean;
  grants: Array<{
    id: string;
    max_amount: number;
    effective_from: string;
    effective_to: string | null;
  }>;
}

export async function exceptionPreview(
  rootId: string,
  issueId: string,
): Promise<ExceptionPreview> {
  const response = await fetch(
    `/api/cases/${rootId}/exceptions/preview?issue_id=${encodeURIComponent(issueId)}`,
    { headers: { "X-Command-Id": newCommandId() }, credentials: "same-origin" },
  );
  return parse<ExceptionPreview>(response);
}

export function ocrPreviewUrl(
  rootId: string,
  sourceId: string,
  page: number | null,
  bbox: [number, number, number, number],
): string {
  const params = new URLSearchParams({
    page: String(page ?? 1),
    x0: String(bbox[0]),
    y0: String(bbox[1]),
    x1: String(bbox[2]),
    y1: String(bbox[3]),
  });
  return `/api/cases/${rootId}/sources/${encodeURIComponent(sourceId)}/ocr-preview?${params}`;
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
