import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Intake } from "../src/features/intake";
import type { CaseView, SessionPayload } from "../src/types";

// One primary action: "Nộp hồ sơ" must upload any pending files and then
// submit. Regression for the bug where files selected but not "attached" were
// silently dropped, so the case reached the server with zero evidence.

const SESSION: SessionPayload = {
  session: {
    session_id: "session:1",
    tenant: "tenant:demo",
    persona: "employee",
    actor_id: "employee:employee-a",
    actor_name: "Nguyễn Văn A",
  },
  personas: [],
  activity_catalog: [
    { id: "activity:travel-a", name: "Công tác Hà Nội", occurred_at: null, purpose: "x", status: "AUTHORIZED", budget_amount: 8_000_000 },
  ],
  mode: "LIVE",
  diagnostics: {
    mode: "LIVE", python: "3.12", context_digest: "x", context_origin: "SIMULATED",
    frontend_built: true, missing_live_settings: [],
  },
};

function caseView(version: number, sources: number): CaseView {
  return {
    id: "case:1", version, state: "DRAFT",
    summary: "Công tác Hà Nội · 06/10/2026 · Nguyễn Văn A",
    sources: Array.from({ length: sources }, (_, i) => ({
      id: `source:${i}`, digest: "a".repeat(64), tenant: "tenant:demo",
      media: "PDF", storage_key: `k${i}`,
    })),
    issues: [], problems: [], conclusion: null, instructions: [],
    actual_money: {}, audit: [], evidence_report: null,
    assessment_ready: true, assessment_blocker: null,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("Intake submit uploads pending files", () => {
  it("does not render a separate 'Đính kèm' button", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Intake session={SESSION} onCase={() => {}} />);
    expect(screen.queryByRole("button", { name: "Đính kèm" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nộp hồ sơ" })).toBeInTheDocument();
  });

  it("uploads the selected file then submits, in that order", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        calls.push(`${method} ${url}`);
        if (url.endsWith("/api/cases")) {
          return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
        }
        if (url.endsWith("/sources")) {
          return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
        }
        if (url.endsWith("/submit")) {
          return new Response(JSON.stringify({ case_view: caseView(3, 1) }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Tạo hồ sơ" }));
    const file = new File(["%PDF-1.4 x"], "hd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/Chứng từ/), file);
    await user.click(screen.getByRole("button", { name: "Nộp hồ sơ" }));

    await waitFor(() => {
      expect(calls.some((c) => c.endsWith("/sources"))).toBe(true);
      expect(calls.some((c) => c.endsWith("/submit"))).toBe(true);
    });
    // The upload must happen BEFORE the submit.
    expect(calls.findIndex((c) => c.endsWith("/sources"))).toBeLessThan(
      calls.findIndex((c) => c.endsWith("/submit")),
    );
  });
});
