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
  | 'ADVANCE_REQUEST_REFUSED'
  | 'SETTLEMENT_REQUEST_REFUSED'
  | 'READY_TO_CLOSE'
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

export interface MoneyIncident {
  kind: 'OVERPAY' | 'WRONG_RECIPIENT';
  excess_vnd: number | null;
  event_ref: string | null;
  payee_ref: string | null;
}

export interface MoneySummary {
  approved_vnd: number | null;
  received_vnd: number | null;
  remaining_vnd: number | null;
  pending_events: number;
  incidents: MoneyIncident[];
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
  // Shared root of the business dossier (B3 root for B3/linked B7/adjustment;
  // own id for standalone B7). Optional for old fixtures; server always sends it.
  dossier_ref?: string | null;
  sources: SourceView[];
  allowed_actions: AllowedAction[];
  money_summary: MoneySummary;
  b3_workflow?: B3WorkflowView | null;
  linked_b7?: LinkedB7View | null;
  b7_workflow?: B7WorkflowView | null;
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
  // 'USER' for cases created via the UI; 'SYSTEM' for eval/verify/seed cases.
  origin: 'USER' | 'SYSTEM';
  dossier_ref?: string | null;
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

// Provider usage: ints, or one level of nested int/null detail objects
// (e.g. prompt_tokens_details.cached_tokens). Mirrors CallTrace.usage.
export type UsageValue = number | { [key: string]: number | null } | null;

export interface CallTrace {
  call_id: string;
  stage: 'read' | 'ocr' | 'extract' | 'match';
  source_id: string | null;
  requested_model: string | null;
  response_model: string | null;
  usage: Record<string, UsageValue> | null;
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

export interface MoneyComponents {
  e: number | null;
  a: number | null;
  ra: number | null;
  p: number | null;
  rp: number | null;
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
  direction: 'COMPANY_TO_EMPLOYEE' | 'EMPLOYEE_TO_COMPANY' | 'BALANCED' | null;
  conditional_results: ConditionalResult[];
  expense_rows: ExpenseRow[];
  checks: CheckResult[];
  issues: Issue[];
  critical_facts: CriticalFact[];
  links: ReportLink[];
  b3: B3Proposal | null;
  claim_comparisons?: B7ClaimComparison[];
  next_step: string;
  source_refs: string[];
}

// --- B3 v1 (b3-intake-v1): verbal assignment intake/report ---------------------

export interface B3EstimateRow {
  row_id: string;
  description: string;
  basis: string | null;
  company_vnd: number | null;
  employee_vnd: number | null;
}

export interface B3Intake {
  schema_version: 'b3-intake-v1';
  intake_method: 'WEB' | 'IMPORT';
  confirmed: boolean;
  destination: string | null;
  trip_start: string | null;
  trip_end: string | null;
  purpose: string | null;
  assignment_note: string | null;
  request_amount_vnd: number | null;
  settlement_due: string | null;
  estimate_rows: B3EstimateRow[];
}

export type B3Readiness =
  | 'DRAFT_CONFIRMATION_REQUIRED'
  | 'NEEDS_INFORMATION'
  | 'NEEDS_AUTHORIZED_REVIEW'
  | 'READY_FOR_ACCOUNTANT_REVIEW';

export interface B3Proposal {
  readiness: B3Readiness;
  intake: B3Intake;
  forecast_company_vnd: number | null;
  forecast_employee_vnd: number | null;
  forecast_total_vnd: number | null;
  work_permission: 'PENDING_DECISION' | 'NEEDS_REVIEW';
  advance_approval: 'PENDING_DECISION' | 'NEEDS_REVIEW';
  accountant_ref: string | null;
  approver_ref: string | null;
  field_refs: Record<string, string[]>;
}

export interface B3Person {
  actor_ref: string;
  role: DemoRole;
  name: string;
  department: string | null;
}

export interface B3Route {
  employee_ref: string;
  accountant_ref: string;
  approver_ref: string;
}

export interface B3DemoContext {
  version: string;
  synthetic: boolean;
  demo_clock: string | null;
  people: B3Person[];
  routes: B3Route[];
}

export interface B3GrantRecord {
  actor_ref: string;
  employee_ref: string;
  work_ref: string | null;
  allow_work: boolean;
  max_budget_vnd: number | null;
  max_advance_vnd: number | null;
  effective_from: string;
  effective_to: string;
  ref: string;
}

export interface B3CoverageRecord {
  employee_ref: string;
  work_ref: string | null;
  from: string;
  to: string;
  complete_prior_history: boolean;
  groups: string[];
  methods: string[];
  missing_ranges: Array<Record<string, unknown>>;
  owner_ref: string;
  origin: string;
  ref: string;
}

export interface B3HistoryRecord {
  event_ref: string;
  employee_ref: string;
  work_ref: string;
  kind: string;
  amount_vnd: number | null;
  event_at: string;
  known_at: string;
  status: string;
  ref: string;
}

export interface B3RunContext {
  version: string;
  synthetic: boolean;
  demo_clock: string | null;
  grants: B3GrantRecord[];
  coverage: B3CoverageRecord[];
  history: B3HistoryRecord[];
}

// --- B3 present-and-approve (b3-intake-v1) ------------------------------------

export type B3WorkflowStatus =
  | 'NOT_PRESENTED' | 'PENDING' | 'RETURNED' | 'REFUSED' | 'APPROVED'
  | 'NEEDS_RECHECK';

export type B3DecisionOutcome = 'APPROVE' | 'RETURN' | 'REFUSE';

export interface B3PresentationView {
  id: string;
  case_id: string;
  basis_report_id: string;
  review_id: string;
  employee_ref: string;
  work_ref: string;
  accountant_ref: string;
  approver_ref: string;
  basis_input_revision: number;
  basis_control_epoch: number;
  basis_signature: string;
  context_signature: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface B3DecisionView {
  id: string;
  case_id: string;
  kind: 'B3_ADVANCE';
  presentation_id: string;
  outcome: B3DecisionOutcome;
  reason: string;
  work_allowed: boolean | null;
  budget_vnd: number | null;
  advance_vnd: number | null;
  basis_report_id: string;
  basis_review_id: string;
  basis_input_revision: number;
  basis_control_epoch: number;
  basis_signature: string;
  context_signature: string;
  employee_ref: string;
  work_ref: string;
  actor_id: string;
  grant_ref: string;
  effective_at: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface B3WorkflowView {
  status: B3WorkflowStatus;
  presentation: B3PresentationView | null;
  decision: B3DecisionView | null;
  basis_current: boolean;
  decision_validity: 'VALID' | 'RECHECK_REQUIRED' | null;
  blocked_reason: string | null;
  accountant_ref: string | null;
  approver_ref: string | null;
  funding?: B3FundingSummary | null;
  advance_events?: B3AdvanceEventView[];
}

export interface B3PresentPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  basis_report_id: string;
  review_id?: string | null;
  review?: { report_id: string; note: string; refs: string[] } | null;
}

export interface B3DecisionPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  presentation_id: string;
  outcome: B3DecisionOutcome;
  reason: string;
  work_allowed?: boolean | null;
  budget_vnd?: number | null;
  advance_vnd?: number | null;
}

// --- B5: advance receipts (actual money to employee) --------------------------

export type B3MoneyFieldName =
  | 'amount_vnd' | 'currency' | 'payer_side' | 'payee_ref' | 'event_at'
  | 'receiver_outcome' | 'event_namespace' | 'event_ref' | 'method';

export type B3AdvanceReportedStatus =
  | 'RECEIVED' | 'PENDING' | 'FAILED' | 'CANCELLED' | 'UNCONFIRMED';

export type B3FundingClassification =
  | 'CONFIRMED_RECEIPT' | 'PENDING' | 'NO_RECEIPT' | 'UNCONFIRMED' | 'CONFLICT';

export type B3FundingIncidentKind =
  | 'OVERPAY' | 'WRONG_RECIPIENT' | 'UNAUTHORIZED_OR_UNALLOCATED'
  | 'AMBIGUOUS_EVENT_REF' | 'CONFLICTING_OUTCOME';

export interface B3MoneyFieldEvidence {
  field: B3MoneyFieldName;
  source_id: string;
  locator: string;
  raw: string | null;
  value: number | string | null;
  read_state: 'READ' | 'UNCLEAR' | 'NOT_FOUND';
  origin: 'HUMAN_SOURCE_REVIEW';
}

export interface B3FundingIncident {
  kind: B3FundingIncidentKind;
  event_ids: string[];
  refs: string[];
  amount_vnd: number | null;
  reason: string;
}

export interface B3AdvanceEventView {
  id: string;
  case_id: string;
  kind: 'ADVANCE_TO_EMPLOYEE';
  decision_id: string | null;
  event_namespace: string | null;
  event_ref: string | null;
  method: 'BANK_TRANSFER' | 'CASH';
  gross_vnd: number | null;
  payer_side: 'COMPANY' | 'EMPLOYEE' | 'OTHER' | 'UNKNOWN';
  payee_ref: string | null;
  event_at: string | null;
  reported_status: B3AdvanceReportedStatus;
  evidence: B3MoneyFieldEvidence[];
  allocation_note: string;
  supersedes_event_id: string | null;
  employee_ref: string;
  work_ref: string;
  classification: B3FundingClassification;
  actor_id: string;
  created_at: string;
  after_money_cutoff: boolean;
  incidents: B3FundingIncident[];
  idempotent_replay: boolean;
}

export interface B3FundingSummary {
  decision_id: string | null;
  approved_vnd: number | null;
  recorded_received_vnd: number | null;
  fulfilled_vnd: number | null;
  remaining_vnd: number | null;
  pending_count: number;
  unknown_count: number;
  incidents: B3FundingIncident[];
  status: 'NOT_RECORDED' | 'PARTIAL' | 'PENDING' | 'UNCONFIRMED'
    | 'FULFILLED' | 'NEEDS_RESOLUTION';
  scope: string;
  as_of: string | null;
}

export interface B3AdvanceEventPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  decision_id: string | null;
  event_namespace: string | null;
  event_ref: string | null;
  method: 'BANK_TRANSFER' | 'CASH';
  gross_vnd: number | null;
  payer_side: 'COMPANY' | 'EMPLOYEE' | 'OTHER' | 'UNKNOWN';
  payee_ref: string | null;
  event_at: string | null;
  reported_status: B3AdvanceReportedStatus;
  evidence: B3MoneyFieldEvidence[];
  allocation_note: string;
  supersedes_event_id: string | null;
}

// --- B6→B7 linked settlement (b7-linked-intake-v1) ---------------------------

export type B7DeclaredPayer = 'PERSONAL' | 'COMPANY' | 'UNKNOWN';
export type B7ClaimStatus = 'MATCHED' | 'CONFLICT' | 'UNRESOLVED';

export interface B7OriginLink {
  origin_case_id: string;
  employee_ref: string;
  work_ref: string;
  created_at: string;
}

export interface B7ClaimRow {
  claim_id: string;
  description: string;
  expense_date: string | null;
  declared_amount_vnd: number | null;
  purpose: string;
  declared_payer: B7DeclaredPayer;
  source_ids: string[];
  payment_statement: string | null;
}

export interface B7LinkedIntake {
  schema_version: 'b7-linked-intake-v1';
  confirmed: boolean;
  expense_rows: B7ClaimRow[];
  note: string | null;
}

export interface LinkedB7View {
  origin: B7OriginLink;
  context_source_id: string | null;
  context_current: boolean;
  blocked_reasons: string[];
  managed_advance_subtotal_vnd: number | null;
}

export interface B7ClaimComparison {
  claim_id: string;
  expense_id: string | null;
  declared_amount_vnd: number | null;
  verified_amount_vnd: number | null;
  payer_declaration: B7DeclaredPayer | null;
  verified_payer: string | null;
  status: B7ClaimStatus;
  refs: string[];
  reason: string;
}

// --- B8: settlement decision (b7-linked-intake-v1) ---------------------------

export type B7WorkflowStatus =
  | 'NOT_PRESENTED' | 'PENDING' | 'RETURNED' | 'REFUSED' | 'APPROVED'
  | 'NEEDS_RECHECK';

export type B7DecisionOutcome = 'APPROVE' | 'RETURN' | 'REFUSE';

export type B7DecisionDirection =
  | 'PAY_EMPLOYEE' | 'COLLECT_FROM_EMPLOYEE' | 'BALANCED';

export interface B7DecisionTarget {
  employee_cost_vnd: number;
  total_work_cost_vnd: number;
  budget_vnd: number;
  signed_net_vnd: number;
  direction: B7DecisionDirection;
  amount_vnd: number;
}

export interface B7PresentationView {
  id: string;
  case_id: string;
  employee_ref: string;
  work_ref: string;
  basis_report_id: string;
  basis_review_id: string;
  accountant_ref: string;
  approver_ref: string;
  basis_input_revision: number;
  control_epoch: number;
  business_signature: string;
  parent_fingerprint: string;
  config_signature: string;
  target: B7DecisionTarget;
  created_at: string;
  idempotent_replay: boolean;
}

export interface B7DecisionView {
  id: string;
  case_id: string;
  kind: 'B7_SETTLEMENT';
  outcome: B7DecisionOutcome;
  reason: string;
  presentation_id: string;
  basis_report_id: string;
  basis_review_id: string;
  employee_ref: string;
  work_ref: string;
  actor_id: string;
  effective_at: string;
  created_at: string;
  basis_input_revision: number;
  control_epoch: number;
  business_signature: string;
  parent_fingerprint: string;
  config_signature: string;
  authority_signature: string;
  target: B7DecisionTarget | null;
  history_baseline: MoneyComponents | null;
  supersedes_decision_id: string | null;
  idempotent_replay: boolean;
}

export interface B7WorkflowView {
  status: B7WorkflowStatus;
  presentation: B7PresentationView | null;
  decision: B7DecisionView | null;
  basis_current: boolean;
  blocked_reasons: string[];
  accountant_ref: string | null;
  approver_ref: string | null;
  fulfillment?: B7FulfillmentSummary | null;
  revalidation?: B7RevalidationView | null;
  current_handoff?: B7HandoffView | null;
  closure?: B7ClosureView | null;
}

// --- B9: settlement fulfillment & closure (b7-linked-intake-v1) ---------------

export type B7MoneyFieldName =
  | 'amount_vnd' | 'currency' | 'payer_ref' | 'payee_ref' | 'event_at'
  | 'receiver_outcome' | 'event_namespace' | 'event_ref' | 'method'
  | 'purpose' | 'work_ref';

export type B7ReportedStatus =
  | 'RECEIVED' | 'PENDING' | 'FAILED' | 'CANCELLED' | 'UNCONFIRMED';

export type B7MoneyPurpose =
  | 'REIMBURSEMENT_RECEIVED' | 'ADVANCE_RETURN' | 'REIMBURSEMENT_RETURN'
  | 'UNKNOWN';

export type B7MoneyClassification =
  | 'CONFIRMED_RECEIPT' | 'PENDING' | 'FAILED' | 'CANCELLED' | 'UNCONFIRMED'
  | 'INCIDENT';

export type B7MoneyIncidentKind =
  | 'WRONG_RECIPIENT' | 'WRONG_PAYER' | 'OVERPAY' | 'CONFLICTING_EVENT'
  | 'UNALLOCATED' | 'REVERSAL' | 'AFTER_CUTOFF' | 'SOURCE_UNRESOLVED';

export interface B7MoneyFieldEvidence {
  field: B7MoneyFieldName;
  source_id: string;
  locator: string;
  raw: string | null;
  value: number | string | null;
  read_state: 'READ' | 'UNCERTAIN' | 'MISSING';
  origin: 'HUMAN_SOURCE_REVIEW';
}

export interface B7MoneyIncident {
  code: B7MoneyIncidentKind;
  event_ids: string[];
  excess_vnd: number | null;
  refs: string[];
  reason: string;
}

export interface B7MoneyEventView {
  id: string;
  case_id: string;
  kind: 'B7_SETTLEMENT_EVENT';
  decision_id: string | null;
  event_namespace: string | null;
  event_ref: string | null;
  method: 'BANK_TRANSFER' | 'CASH';
  gross_vnd: number | null;
  payer_ref: string | null;
  payee_ref: string | null;
  event_at: string | null;
  reported_status: B7ReportedStatus;
  purpose: B7MoneyPurpose;
  evidence: B7MoneyFieldEvidence[];
  allocation_note: string;
  supersedes_event_id: string | null;
  employee_ref: string;
  work_ref: string;
  actor_id: string;
  created_at: string;
  known_at: string | null;
  classification: B7MoneyClassification;
  after_cutoff: boolean;
  incidents: B7MoneyIncident[];
  idempotent_replay: boolean;
}

export interface B7FulfillmentSummary {
  decision_id: string;
  direction: B7DecisionDirection;
  approved_vnd: number;
  recorded_received_vnd: number | null;
  fulfilled_vnd: number | null;
  remaining_vnd: number | null;
  known_remaining_vnd: number | null;
  pending_count: number;
  unknown_count: number;
  incidents: B7MoneyIncident[];
  status: 'WAITING' | 'PARTIAL' | 'FULFILLED' | 'BLOCKED' | 'BALANCED';
  managed_scope: string;
  as_of: string;
  knowledge_cutoff: string;
}

export interface B7RevalidationView {
  original_decision_id: string;
  current_report_id: string;
  status: 'VALID' | 'NEEDS_RECHECK';
  cost_signature: string;
  receipt_history_signature: string;
  qualifying_event_ids: string[];
  blocked_reasons: string[];
  refs: string[];
  created_at: string;
}

export interface B7HandoffView {
  id: string;
  case_id: string;
  decision_id: string;
  report_id: string;
  employee_ref: string;
  work_ref: string;
  actor_id: string;
  direction: string;
  remaining_vnd: number;
  obligation_signature: string;
  business_signature: string;
  receipt_history_signature: string;
  refs: string[];
  created_at: string;
  valid_until: string | null;
  idempotent_replay: boolean;
}

export interface B7ClosureView {
  id: string;
  case_id: string;
  decision_id: string;
  current_report_id: string;
  actor_id: string;
  kind: 'SETTLEMENT_COMPLETE';
  employee_ref: string;
  work_ref: string;
  close_as_of: string;
  knowledge_cutoff: string;
  created_at: string;
  input_revision: number;
  control_epoch: number;
  business_signature: string;
  receipt_history_signature: string;
  parent_fingerprint: string;
  source_refs: string[];
  event_ids: string[];
  original_decision_id: string;
  revalidation_ref: string | null;
  reason: string;
  idempotent_replay: boolean;
}

export interface B7MoneyEventPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  decision_id: string | null;
  event_namespace: string | null;
  event_ref: string | null;
  method: 'BANK_TRANSFER' | 'CASH';
  gross_vnd: number | null;
  payer_ref: string | null;
  payee_ref: string | null;
  event_at: string | null;
  reported_status: B7ReportedStatus;
  purpose: B7MoneyPurpose;
  evidence: B7MoneyFieldEvidence[];
  allocation_note: string;
  supersedes_event_id: string | null;
}

export interface B7PresentPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  basis_report_id: string;
  review_id?: string | null;
  review?: { report_id: string; note: string; refs: string[] } | null;
  supersedes_decision_id?: string | null;
}

export interface B7DecisionPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  presentation_id: string;
  outcome: B7DecisionOutcome;
  reason: string;
}

export type CriticalFactState =
  'KNOWN' | 'UNKNOWN' | 'CONTRADICTED' | 'UNCLEAR' | 'UNUSABLE';

export interface CriticalFact {
  key: string;
  value: number | string | null;
  state: CriticalFactState;
  refs: string[];
}

export interface ReportLink {
  relation_id: string;
  kind: 'EXPENSE_PAYMENT' | 'SAME_EVENT';
  from_id: string;
  to_id: string;
  portion_vnd: number | null;
  status: 'ESTABLISHED' | 'PROPOSED' | 'UNCLEAR';
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

// --- W05: decision, review, money, control, handoff, closure -------------------

export interface DecisionView {
  id: string;
  case_id: string;
  kind: 'SETTLEMENT';
  amount_vnd: number | null;
  direction: 'PAY_EMPLOYEE' | 'COLLECT_FROM_EMPLOYEE' | 'REFUSE';
  reason: string;
  basis_report_id: string;
  basis_case_version: number;
  basis_input_revision: number;
  exception_of: string | null;
  conditions: string[];
  actor_id: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface ReviewView {
  id: string;
  case_id: string;
  report_id: string;
  note: string;
  refs: string[];
  actor_id: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface MoneyEventView {
  id: string;
  case_id: string;
  event_ref: string;
  kind: 'PAYMENT_TO_EMPLOYEE' | 'PAYMENT_FROM_EMPLOYEE';
  gross_vnd: number;
  decision_id: string | null;
  payee_ref: string;
  event_at: string;
  reported_status: 'RECEIVED' | 'PENDING';
  refs: string[];
  after_cutoff: boolean;
  created_at: string;
  idempotent_replay: boolean;
}

export interface ClosureView {
  id: string;
  case_id: string;
  kind: 'SETTLEMENT_COMPLETE' | 'REJECTED_REQUEST_ENDED';
  basis: string;
  actor_id: string;
  created_at: string;
  idempotent_replay: boolean;
}

export interface DecidePayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  kind: 'SETTLEMENT';
  amount_vnd: number | null;
  direction: DecisionView['direction'];
  reason: string;
  basis_report_id: string;
  conditions: string[];
  exception_of: string | null;
}

export interface ReviewNotePayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  report_id: string;
  note: string;
  refs: string[];
}

export interface MoneyEventPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  event_ref: string;
  kind: MoneyEventView['kind'];
  gross_vnd: number;
  decision_id: string | null;
  payee_ref: string;
  event_at: string;
  reported_status: MoneyEventView['reported_status'];
  refs: string[];
}

export interface ControlPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  action: 'STOP' | 'RESUME';
  reason: string;
}

export interface HandoffPayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  decision_id: string;
}

export interface ClosurePayload {
  actor_id: string;
  demo_role: DemoRole;
  expected_case_version: number;
  kind: ClosureView['kind'];
  basis: string;
}

// --- W06: evaluation / Verify ---------------------------------------------------

export interface VerifyCheck {
  axis: string;
  expected: unknown;
  actual: unknown;
  ok: boolean;
  note: string;
}

export interface VerifyCaseResult {
  case_id: string;
  job: Job;
  phase: 'INITIAL' | 'AFTER_FOLLOWUP';
  family_id: string;
  dataset_role: string;
  verdict: 'PASS' | 'FAIL' | 'INCONCLUSIVE';
  checks: VerifyCheck[];
  run_id: string | null;
  run_status: string | null;
  mode: string;
  needs_resolution_expected: boolean;
  technical: boolean;
  first_pass_routine_expected: boolean | null;
  timestamp: string;
}

export interface VerifyMetrics {
  n_routine: number;
  n_needs: number;
  fn: number;
  fp: number;
  u_routine: number;
  u_needs: number;
  fn_interval: [number, number] | null;
  fp_interval: [number, number] | null;
  routine_completion: string;
}

export interface VerifySuiteReport {
  suite: string;
  timestamp: string;
  mode: string;
  source_hash: string;
  config_hash: string;
  results: VerifyCaseResult[];
  metrics: VerifyMetrics;
  notes: string[];
}
