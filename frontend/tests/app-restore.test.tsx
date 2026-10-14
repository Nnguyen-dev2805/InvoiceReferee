import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";
import type { CaseView } from "../src/types";

// A reload must not lose an in-flight dossier: on mount the app restores the
// most recent case from the server (the case itself lives in the DB, not in
// React state). Regression for the "reload → hồ sơ biến mất" bug.

const SESSION = {
  session: {
    session_id: "session:1",
    tenant: "tenant:demo",
    persona: "employee",
    actor_id: "employee:employee-a",
    actor_name: "Nguyễn Văn A",
  },
  personas: [
    { id: "employee", label: "Nhân viên", actor_id: "employee:employee-a", actor_name: "Nguyễn Văn A" },
  ],
  activity_catalog: [
    { id: "activity:travel-a", name: "Công tác Hà Nội", occurred_at: "2026-10-05T09:00:00Z", purpose: "x", status: "AUTHORIZED", budget_amount: 8_000_000 },
  ],
  mode: "LIVE",
  diagnostics: {
    mode: "LIVE",
    python: "3.12",
    context_digest: "abc",
    context_origin: "SIMULATED",
    frontend_built: true,
    missing_live_settings: [],
  },
};

const CASE: CaseView = {
  id: "case:ebd86f7f",
  version: 3,
  state: "EVIDENCE_READY",
  summary: "Công tác Hà Nội · 05/10/2026 · Nguyễn Văn A",
  sources: [],
  issues: [],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {},
  audit: [],
  evidence_report: { provider_mode: "LIVE", data_origin: "LIVE_READ", documents: [], links: [], row_matches: [], match_findings: [] },
  assessment_ready: false,
  assessment_blocker: "EVIDENCE_ASSESSMENT_PENDING",
  payment_basis: [],
};

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.endsWith(path)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App case restore on reload", () => {
  it("restores the most recent case from the server on mount", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/demo/session": SESSION,
        "/api/cases": { cases: [CASE] },
      }),
    );

    render(<App />);

    await waitFor(() => {
      // The dossier is populated with the restored case, not the empty state.
      expect(screen.getByText(CASE.summary)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Chưa có hồ sơ nào được mở/)).not.toBeInTheDocument();
  });

  it("shows the empty state when the server has no cases", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/demo/session": SESSION,
        "/api/cases": { cases: [] },
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Chưa có hồ sơ nào được mở/)).toBeInTheDocument();
    });
  });

  it("lists cases only after the session cookie is established", async () => {
    const order: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/demo/session")) {
          order.push("session");
          // A slow session: cases must not be requested before this resolves.
          await new Promise((r) => setTimeout(r, 30));
          return new Response(JSON.stringify(SESSION), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/cases")) {
          order.push("cases");
          return new Response(JSON.stringify({ cases: [CASE] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(CASE.summary)).toBeInTheDocument();
    });
    expect(order).toEqual(["session", "cases"]);
  });
});
