export type MoneyState = "KNOWN" | "UNKNOWN" | "CONFLICT";

export interface MoneyFact {
  key: string;
  value: number | null;
  state: MoneyState;
}

export type CaseState =
  | "DRAFT"
  | "PROCESSING"
  | "EVIDENCE_READY"
  | "WAITING"
  | "TECHNICAL_ERROR"
  | "READY_TO_EXECUTE"
  | "SETTLED"
  | "STOPPED";

export interface SourceView {
  id: string;
  digest: string;
  tenant: string;
  media: "PDF" | "PNG" | "JPEG";
  storage_key: string;
  filename: string | null;
}

export interface EvidenceRefView {
  source_id: string;
  source_sha256: string;
  page: number | null;
  exact_quote: string;
  bbox?: [number, number, number, number] | null;
}

export interface IssueView {
  id: string;
  kind: "FACT" | "POLICY" | "AUTHORITY";
  field_or_rule: string;
  owner: string;
  status: string;
  basis: string;
  question: string;
  refs?: EvidenceRefView[];
}

export interface InstructionView {
  id: string;
  direction: "PAY" | "COLLECT";
  amount: number;
  status: string;
  basis: string;
  fulfilled_amount: number;
  remaining: number;
  execution_state: string;
}

export interface EvidenceReport {
  provider_mode: string | null;
  data_origin: string | null;
  documents: unknown[];
  links: unknown[];
  row_matches: unknown[];
  match_findings: unknown[];
}

export type PaymentBasisKind =
  | "INDEPENDENT_PAYMENT"
  | "FINANCIAL_CONFIRMATION"
  | "EMPLOYEE_PAID_INVOICE"
  | "EMPLOYEE_DECLARATION_Q32"
  | "ALTERNATIVE_ACCEPTED"
  | "UNSPECIFIED_LEGACY";

export interface PaymentBasisView {
  expense_id: string;
  kind: PaymentBasisKind;
  actor: string | null;
  refs: unknown[];
  rule_id: string | null;
}

export interface ActivityAcceptanceView {
  root_id: string;
  employee: string;
  activity: string;
  advance_external_key: string;
  advance_draft_id: string;
  actor: string;
  accepted_at: string;
  link_basis: "DOCUMENT_REFERENCE" | "ACCOUNTANT_CONFIRMATION" | "MULTI_FIELD_MATCH" | "TRANSACTION_IDENTITY";
  reason: string;
  refs: unknown[];
  link_signals: ActivityLinkSignalView[];
}

export interface ActivityLinkSignalView {
  field: string;
  state: string;
  summary: string;
  refs: unknown[];
}

export interface MoneyHistoryView {
  id: string;
  external_key: string;
  kind: string;
  scope: string;
  payer: string;
  payee: string;
  amount: number;
  event_at: string;
  recorded_at: string;
  verification_state: string;
  allocation_state: string;
  refs: unknown[];
}

export interface CoverageRecordView {
  context_ledger_fingerprint?: string | null;
  scope: string;
  employee: string | null;
  start: string;
  as_of: string;
  funds: string[];
  flow_kinds: string[];
  opening_balance: MoneyFact | null;
  ledger_version: string | null;
  witness_refs: unknown[];
  source: string;
  actor: string | null;
  recorded_at: string | null;
  reason: string | null;
  unallocated_event_ids: string[];
}

export interface EmployeeReturnDraftView {
  draft_id: string;
  root_id: string;
  employee: string;
  activity: string;
  instruction_id: string;
  source_id: string;
  source_sha256: string;
  source_filename: string;
  status: "WAITING_ACCOUNTANT" | "CONFIRMED";
  match_status: "MATCHED" | "OVERPAY" | "NEEDS_REVIEW" | "CONFLICT" | "NOT_COMPLETED" | "STALE" | "ALREADY_RECORDED";
  amount: number | null;
  payer_name: string | null;
  payee_name: string | null;
  transaction_reference: string | null;
  external_key: string | null;
  instrument_method: "TRANSFER" | "CASH" | null;
  instrument_status: "COMPLETED" | "PENDING" | "FAILED" | "UNKNOWN";
  event_at: string | null;
  instruction_amount: number;
  instruction_remaining: number;
  refs: Array<{ source_id: string; source_sha256: string; page: number | null; exact_quote: string }>;
  missing_fields: string[];
  signals: Array<{ field: string; state: string; summary: string; refs: unknown[] }>;
  uploaded_at: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
  money_event_id: string | null;
}

export interface CaseView {
  id: string;
  version: number;
  state: CaseState;
  activity?: string | null;
  employee?: string | null;
  summary: string;
  sources: SourceView[];
  issues: IssueView[];
  problems: unknown[];
  conclusion: unknown | null;
  instructions: InstructionView[];
  actual_money: Record<string, MoneyFact>;
  audit: string[];
  evidence_report: EvidenceReport | null;
  assessment_ready: boolean;
  assessment_blocker: string | null;
  payment_basis: PaymentBasisView[];
  activity_acceptances?: ActivityAcceptanceView[];
  coverage_record?: CoverageRecordView | null;
  coverage_current?: boolean;
  money_history?: MoneyHistoryView[];
  employee_return_drafts?: EmployeeReturnDraftView[];
  // Technical/debug trace references (§9); shown only in the debug area.
  trace_refs?: string[];
}

export interface CommandResultView {
  case_view: CaseView;
  job_id: string | null;
  duplicate_command: boolean;
}

export interface CatalogActivity {
  id: string;
  name: string;
  occurred_at: string | null;
  purpose: string;
  status: "AUTHORIZED" | "PROPOSED";
  budget_amount: number | null;
  // Server-owned business profile (T1): TRAVEL or WORK_EXPENSE.
  profile?: string;
}

export interface PersonaView {
  id: "employee" | "accountant" | "approver";
  label: string;
  actor_id: string;
  actor_name: string;
}

export interface Diagnostics {
  mode: string;
  python: string;
  context_digest: string | null;
  context_origin: string | null;
  frontend_built: boolean;
  missing_live_settings: string[];
}

export interface SessionPayload {
  session: {
    session_id: string;
    tenant: string;
    persona: string;
    actor_id: string;
    actor_name: string;
  };
  personas: PersonaView[];
  activity_catalog: CatalogActivity[];
  mode: string;
  diagnostics: Diagnostics;
}
