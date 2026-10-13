import type { CaseView, CommandResultView, SessionPayload } from "./types";

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
  activityId: string,
  declaredPurpose: string,
  version: number,
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/submit`,
    { activity_id: activityId, declared_purpose: declaredPurpose },
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
): Promise<CommandResultView> {
  return request<CommandResultView>(
    `/api/cases/${rootId}/actuals`,
    { money },
    newCommandId(),
  );
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

export function errorMessage(cause: unknown): string {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof Error) return cause.message;
  return String(cause);
}
