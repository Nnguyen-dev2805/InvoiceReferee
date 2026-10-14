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

export interface IssueView {
  id: string;
  kind: "FACT" | "POLICY" | "AUTHORITY";
  field_or_rule: string;
  owner: string;
  status: string;
  basis: string;
  question: string;
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
  | "UNSPECIFIED_LEGACY";

export interface PaymentBasisView {
  expense_id: string;
  kind: PaymentBasisKind;
  actor: string | null;
  refs: unknown[];
  rule_id: string | null;
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
