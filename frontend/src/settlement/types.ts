// Settlement UI contracts mirroring src/invoice_referee/settlement/models.py.
// The backend is the single source of decision logic; these types only shape
// what the API returns.

export type Job = 'B3' | 'B7';
export type DemoRole = 'EMPLOYEE' | 'ACCOUNTANT' | 'APPROVER';
export type CaseStage =
  | 'CHECKING'
  | 'ACCOUNTING_REVIEW'
  | 'AWAITING_DECISION'
  | 'AWAITING_MONEY'
  | 'AWAITING_WORK_SETTLEMENT'
  | 'RESOLVING_OBLIGATIONS'
  | 'REJECTED_REQUEST_ENDED'
  | 'SETTLEMENT_CLOSED';

export interface Submission {
  employee_ref: string;
  work_ref: string;
  job: Job;
  money_as_of: string;
  knowledge_cutoff: string;
  form: Record<string, unknown>;
}

export interface SourceView {
  id: string;
  filename: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  status: 'ACCEPTED';
  uploader_actor_id: string;
  received_at: string;
  supersedes_source_id: string | null;
  provenance: Record<string, unknown>;
}

export interface AllowedAction {
  action: string;
  reason: string;
}

export interface CaseView {
  id: string;
  job: Job;
  case_version: number;
  input_revision: number;
  control_epoch: number;
  stop_active: boolean;
  stage: CaseStage;
  current_run_id: string | null;
  submission: Submission;
  sources: SourceView[];
  allowed_actions: AllowedAction[];
  created_at: string;
  updated_at: string;
}

export interface CaseSummary {
  id: string;
  job: Job;
  employee_ref: string;
  work_ref: string;
  stage: CaseStage;
  case_version: number;
  updated_at: string;
}

export interface AuditEntry {
  id: string;
  case_id: string;
  kind: string;
  operation: string;
  actor_id: string;
  command_key: string;
  occurred_at: string;
  detail: Record<string, unknown>;
}

export interface CreateCasePayload {
  submission: Submission;
  actor_id: string;
  demo_role: DemoRole;
}

export interface ReviseSubmissionPayload extends CreateCasePayload {
  expected_case_version: number;
  reason: string;
}

// --- W02: runs and reports ---------------------------------------------------

export type RunStatus =
  | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT'
  | 'STOPPED' | 'SUPERSEDED' | 'INTERRUPTED';

export interface CallTrace {
  call_id: string;
  stage: 'read' | 'ocr' | 'extract' | 'match';
  source_id: string | null;
  requested_model: string | null;
  response_model: string | null;
  usage: Record<string, number | null> | null;
  ok: boolean;
  error_code: string | null;
  detail: string | null;
  duration_ms: number;
}

export interface RunView {
  id: string;
  case_id: string;
  status: RunStatus;
  mode: string;
  input_revision: number;
  control_epoch: number;
  stage: string | null;
  created_at: string;
  updated_at: string;
  detail: string | null;
  completion: 'COMPLETE' | 'INCOMPLETE' | null;
  trace: CallTrace[];
  idempotent_replay: boolean;
}

export interface ComponentSlot {
  value: number | null;
  state: 'KNOWN' | 'UNKNOWN' | 'PENDING' | 'NOT_APPLICABLE';
  refs: string[];
}

export interface ReportComponents {
  t: ComponentSlot; b: ComponentSlot; e: ComponentSlot; a: ComponentSlot;
  ra: ComponentSlot; p: ComponentSlot; rp: ComponentSlot;
}

export interface ExpenseRow {
  expense_id: string;
  claimed_amount_vnd: number | null;
  eligible_employee_vnd: number | null;
  company_direct_vnd: number | null;
  state: 'ELIGIBLE' | 'PERSONAL_EXCLUDED' | 'COMPANY_DIRECT' | 'UNKNOWN' | 'EXCLUDED';
  refs: string[];
  reason: string;
}

export interface CheckResult {
  rule: string;
  status: 'PASS' | 'FAIL' | 'UNRESOLVED' | 'NOT_APPLICABLE';
  refs: string[];
  reason: string;
}

export interface Issue {
  issue_id: string;
  type: 'FACT' | 'POLICY' | 'AUTHORITY' | 'MONEY_INCIDENT' | 'TECHNICAL' | 'CONTROL';
  owner: 'EMPLOYEE' | 'ACCOUNTANT' | 'APPROVER';
  message: string;
  refs: string[];
  blocked: string | null;
  unresolved: boolean;
}

export interface ConditionalResult {
  condition: string;
  net_vnd: number | null;
}

export interface Report {
  run_id: string;
  job: Job;
  completion: 'COMPLETE' | 'INCOMPLETE';
  mode: string;
  generated_at: string;
  components: ReportComponents;
  calculated_net_vnd: number | null;
  proposed_net_vnd: number | null;
  conditional_results: ConditionalResult[];
  expense_rows: ExpenseRow[];
  checks: CheckResult[];
  issues: Issue[];
  next_step: string;
  source_refs: string[];
}

export interface StartRunPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
}

// --- W04: questions and responses ---------------------------------------------

export interface QuestionView {
  id: string;
  case_id: string;
  issue_id: string;
  owner: 'EMPLOYEE' | 'ACCOUNTANT' | 'APPROVER';
  message: string;
  refs: string[];
  blocked: string | null;
  status: 'OPEN' | 'ANSWERED' | 'RESOLVED' | 'SUPERSEDED';
  created_at: string;
  origin_run_id: string | null;
  answered_at: string | null;
  resolved_run_id: string | null;
}

export interface ResponseView {
  id: string;
  question_id: string;
  case_id: string;
  actor_id: string;
  demo_role: DemoRole;
  content: string;
  source_ids: string[];
  accepted: boolean;
  reason: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface RespondPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  content: string;
  source_ids: string[];
}
