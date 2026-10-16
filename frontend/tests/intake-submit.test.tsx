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

function caseView(version: number, sources: number, filename = "hd.pdf"): CaseView {
  return {
    id: "case:1", version, state: "DRAFT",
    summary: "Công tác Hà Nội · 06/10/2026 · Nguyễn Văn A",
    sources: Array.from({ length: sources }, (_, i) => ({
      id: `source:${i}`, digest: "a".repeat(64), tenant: "tenant:demo",
      media: "PDF", storage_key: `k${i}`, filename,
    })),
    issues: [], problems: [], conclusion: null, instructions: [],
    actual_money: {}, audit: [], evidence_report: null,
    assessment_ready: true, assessment_blocker: null, payment_basis: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("Intake submit uploads pending files", () => {
  it("does not render a separate 'Đính kèm' button", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<Intake session={SESSION} onCase={() => {}} />);
    expect(screen.queryByRole("button", { name: "Đính kèm" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đọc chứng từ" })).toBeInTheDocument();
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
        if (url.endsWith("/settlement/draft")) {
          return new Response(JSON.stringify({
            declared_name: "Nguyễn Văn A",
            destination: "Hà Nội",
            activity_name: "Công tác Hà Nội",
            trip_start: "06/10/2026",
            trip_end: "10/10/2026",
            occurred_at: "2026-10-06",
            declared_purpose: "Công tác",
            incurred_total: 3240000,
            declared_advance: 4000000,
            expenses: [{ description: "Bữa ăn", invoice_no: "IR26101001", amount: 3240000, status: "CLEAR" }],
            warnings: [],
            invoices: [],
          }), { status: 200 });
        }
        if (url.endsWith("/submit")) {
          return new Response(JSON.stringify({ case_view: caseView(3, 1) }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();

    const file = new File(["%PDF-1.4 x"], "hd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), file);
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }));

    await waitFor(() => {
      expect(calls.some((c) => c.endsWith("/sources"))).toBe(true);
      expect(calls.some((c) => c.endsWith("/submit"))).toBe(true);
    });
    // The upload must happen BEFORE the submit.
    expect(calls.findIndex((c) => c.endsWith("/sources"))).toBeLessThan(
      calls.findIndex((c) => c.endsWith("/submit")),
    );
  });

  // Temporarily skipped: personal claim section removed from intake UI per user instruction ("bỏ chi tiết bằng cá nhân đi, lát tôi sẽ thêm sau")
  it.skip("sends a typed paid-claim with the server source id and a real quote", async () => {
    let submitBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/cases")) {
          return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
        }
        if (url.endsWith("/sources")) {
          return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
        }
        if (url.endsWith("/submit")) {
          submitBody = JSON.parse(String(init?.body ?? "{}"));
          return new Response(JSON.stringify({ case_view: caseView(3, 1) }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Tạo hồ sơ" }));
    const file = new File(["%PDF-1.4 x"], "hd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), file);
    await user.type(screen.getByLabelText(/Số hóa đơn/), "IR26101001");
    await user.type(screen.getByLabelText(/Số tiền/), "3240000");
    // Pick the document by its display name (the pending file).
    await user.selectOptions(screen.getByLabelText(/Chứng từ cho khoản này/), "hd.pdf");
    await user.type(screen.getByLabelText(/Trích đoạn/), "3.240.000 đ");
    await user.click(screen.getByRole("button", { name: "Nộp hồ sơ" }));

    await waitFor(() => expect(submitBody).not.toBeNull());
    const claims = (submitBody as unknown as { employee_paid_claims: Array<Record<string, unknown>> })
      .employee_paid_claims;
    expect(claims).toHaveLength(1);
    expect(claims[0].invoice_reference).toBe("IR26101001");
    expect(claims[0].amount).toBe(3_240_000);
    // The ref uses the SERVER source id (not a reconstructed filename) and a
    // real quote (never the placeholder "nhân viên xác nhận").
    const refs = claims[0].refs as Array<Record<string, unknown>>;
    expect(refs[0].source_id).toBe("source:0");
    expect(refs[0].exact_quote).toBe("3.240.000 đ");
    expect(refs[0].exact_quote).not.toBe("nhân viên xác nhận");
    // The client never supplies the actor/verifier the server owns.
    expect(claims[0]).not.toHaveProperty("actor");
    expect(claims[0]).not.toHaveProperty("verified_by");
  });

  it.skip("does not send a claim when no document is selected", async () => {
    let submitBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/cases")) {
          return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
        }
        if (url.endsWith("/sources")) {
          return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
        }
        if (url.endsWith("/submit")) {
          submitBody = JSON.parse(String(init?.body ?? "{}"));
          return new Response(JSON.stringify({ case_view: caseView(3, 1) }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Tạo hồ sơ" }));
    const file = new File(["%PDF-1.4 x"], "hd.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), file);
    await user.type(screen.getByLabelText(/Số hóa đơn/), "IR26101001");
    await user.type(screen.getByLabelText(/Số tiền/), "3240000");
    // No document selected, no quote -> the claim is not sent (never default to
    // the first document).
    await user.click(screen.getByRole("button", { name: "Nộp hồ sơ" }));
    await waitFor(() => expect(submitBody).not.toBeNull());
    const claims = (submitBody as unknown as { employee_paid_claims: unknown[] }).employee_paid_claims;
    expect(claims).toHaveLength(0);
  });
});
