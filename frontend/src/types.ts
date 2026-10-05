// API contract types for the InvoiceReferee frontend.
//
// These mirror the FastAPI DTOs from `src/invoice_referee/api/app.py`
// (`_case_dto`, `_run_dto`, `_result_dto`, `_evidence_dto`, `_payment_dto`,
// `_event_dto`, `_policy_dto`, `_stop_dto`) and the ledger enum values. The
// frontend holds NO decision logic: it only renders what the backend returns.

export type Profile = 'TRAVEL' | 'CLIENT_MEAL' | 'WORK_PURCHASE' | 'OTHER';
export type PurposeType = 'BUSINESS' | 'PERSONAL' | 'UNKNOWN';
export type PayerType = 'PERSONAL' | 'COMPANY' | 'ADVANCE' | 'VENDOR' | 'UNKNOWN';
export type EvidenceRole = 'PRIMARY_BILL' | 'GOODS_RECEIPT' | 'CONTEXT';
export type DemoMode = 'EMPLOYEE' | 'REVIEWER' | 'APPROVER' | 'POLICY_OWNER';
export type ExecutionStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'STOP_REQUESTED'
  | 'STOPPED'
  | 'SUCCEEDED'
  | 'FAILED';
export type WorkflowState =
  | 'DRAFT'
  | 'REVIEWING'
  | 'WAITING_INPUT'
  | 'WAITING_APPROVAL'
  | 'REQUEST_CREATED'
  | 'REJECTED'
  | 'STOPPED'
  | 'TECHNICAL_ERROR';
export type DecisionAction =
  | 'CREATE_PAYMENT_REQUEST'
  | 'REQUEST_INFO'
  | 'ESCALATE'
  | 'REJECT'
  | 'NONE';
export type CompletionBasis = 'ROUTINE_AUTO' | 'HUMAN_AUTHORIZED';
export type IssueClass = 'FACTUAL_UNKNOWN' | 'OUTSIDE_POLICY' | 'BEYOND_AUTHORITY';
export type StopStatus = 'STOP_REQUESTED' | 'STOPPED' | 'ALREADY_COMPLETED';
export type HumanActionKind =
  | 'SUPPLY_DECLARATION'
  | 'ADD_EVIDENCE'
  | 'PROPOSE_CORRECTION'
  | 'CONFIRM_FIELD'
  | 'CONFIRM_MAPPING'
  | 'GRANT_POLICY_EXCEPTION'
  | 'APPROVE_AMOUNT'
  | 'DENY'
  | 'STOP'
  | 'OVERRIDE';

export interface Claim {
  employee_id: string;
  profile: Profile;
  purpose_type: PurposeType;
  purpose: string;
  trip: string;
  requested_amount_vnd: number | null;
  payer_type: PayerType;
  received_full: boolean | null;
}

export interface EvidenceDto {
  id: string;
  case_id: string;
  role: EvidenceRole;
  original_name: string;
  sha256: string;
  mime: string;
  size: number;
}

export interface CaseRecord {
  id: string;
  case_version: number;
  claim: Claim;
  current_run_id: string | null;
  workflow_state: WorkflowState;
  evidence: EvidenceDto[];
  // Owner modes with an OPEN issue in the current run (role inbox filter).
  open_owner_modes: DemoMode[];
}

export interface SourceRef {
  evidence_id: string;
  page_index: number;
  block_id: string;
  locator: string;
  raw_value: string;
}

export interface CheckResult {
  rule_id: string;
  status: 'PASS' | 'FAIL' | 'UNKNOWN' | 'NOT_APPLICABLE';
  dependencies: string[];
  refs: SourceRef[];
  reason: string;
  issue_ids: string[];
}

export interface Issue {
  id: string;
  stable_key: string;
  issue_class: IssueClass;
  owner_mode: DemoMode;
  question: string;
  refs: SourceRef[];
  blockers: string[];
  status: 'OPEN' | 'RESOLVED' | 'DENIED';
}

export interface Decision {
  action: DecisionAction;
  completion_basis: CompletionBasis | null;
  accepted_amount_vnd: number | null;
  checks: CheckResult[];
  issues: Issue[];
  reasons: string[];
  technical_code: string | null;
}

export interface StageIdentity {
  stage: string;
  request_hash: string;
  prompt_version: string;
  model_id: string;
  schema_version: string;
  provider: string;
}

export interface PipelineResult {
  decision: Decision;
  bundle: Record<string, unknown>;
  artifacts: string[];
  identities: StageIdentity[];
  stage_durations_ms: Record<string, number>;
  provider_calls: number;
  repair_calls: number;
}

export interface RunRecord {
  id: string;
  case_id: string;
  input_hash: string;
  case_version: number;
  status: ExecutionStatus;
  stop_requested: boolean;
  stage: string;
  started_at: string;
  finished_at: string | null;
  policy_version: string;
  threshold_version: string;
  identities: StageIdentity[];
  result: PipelineResult | null;
}

export interface StopReply {
  status: StopStatus;
  run_id: string;
}

export interface PaymentRequest {
  id: string;
  case_id: string;
  run_id: string;
  payee: string;
  amount_vnd: number;
  currency: 'VND';
  completion_basis: CompletionBasis;
  status: 'CREATED' | 'SUPERSEDED' | 'REVOKED';
  policy_version: string;
}

export interface AuditEvent {
  id: string;
  case_id: string | null;
  run_id: string | null;
  case_version: number | null;
  timestamp: string;
  kind: string;
  stage: string;
  reason: string;
  refs: SourceRef[];
  payload: Record<string, unknown>;
}

export interface PolicyDto {
  version: string;
  origin: string;
  activation_id: string | null;
  active: boolean;
  currency: string;
  auto_approval_max: number;
  standard_policy_max: number;
  inventory_date_gap_days: number;
  comparison_money_tolerance: string;
  normalized_unit_price_tolerance: string;
  word_review_threshold: string;
  threshold_version: string;
}

export interface HumanAction {
  case_version: number;
  issue_id: string | null;
  mode: DemoMode;
  kind: HumanActionKind;
  payload: Record<string, unknown>;
  reason: string;
}

export interface VerifyResult {
  case_id: string;
  run_id: string | null;
  verdict: 'PASS' | 'FAIL' | 'INCONCLUSIVE';
  mode: string;
  elapsed_ms: number;
  expected: { action: string; owners: string[]; reason: string };
  actual: Record<string, unknown>;
  timestamp: string;
}

export interface VerifyReport {
  id: string;
  mode: string;
  results: VerifyResult[];
  metrics: Record<string, unknown>;
}

export interface VerifyJob {
  id: string;
  status: ExecutionStatus;
  completed_count: number;
  total_count: number;
  report: VerifyReport | null;
}
