import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Intake } from "../src/features/intake";
import type { CaseView, SessionPayload } from "../src/types";

// W5: the draft is read from real documents; a failure shows an error with retry
// and never invents demo facts; unknown money stays unknown; the confirmed draft
// (edits + notes + activity) is what the server persists.

const SESSION: SessionPayload = {
  session: {
    session_id: "session:1", tenant: "tenant:demo", persona: "employee",
    actor_id: "employee:employee-a", actor_name: "NGUYỄN MINH AN",
  },
  personas: [],
  activity_catalog: [
    { id: "activity:tc01", name: "Tiếp khách dự án", occurred_at: "2026-10-10", purpose: "Chi phí tiếp khách", status: "AUTHORIZED", budget_amount: 8_000_000, profile: "WORK_EXPENSE" },
  ],
  mode: "LIVE",
  diagnostics: { mode: "LIVE", python: "3.12", context_digest: "x", context_origin: "SIMULATED", frontend_built: true, missing_live_settings: [] },
};

function caseView(version: number, sources: number, state = "DRAFT"): CaseView {
  return {
    id: "case:1", version, state, summary: "Tiếp khách dự án",
    sources: Array.from({ length: sources }, (_, i) => ({
      id: `source:${i}`, digest: "a".repeat(64), tenant: "tenant:demo",
      media: "PDF", storage_key: `k${i}`, filename: `f${i}.pdf`,
    })),
    issues: [], problems: [], conclusion: null, instructions: [],
    actual_money: {}, audit: [], evidence_report: null,
    assessment_ready: true, assessment_blocker: null, payment_basis: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("Intake draft (W5)", () => {
  it("shows a draft read from the report with no fabricated trip", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 2) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null,
        trip_start: null, trip_end: null, occurred_at: null,
        declared_purpose: "Chi phí tiếp khách phục vụ dự án Nâng cấp văn phòng 2026",
        incurred_total: 3240000, declared_advance: 4000000,
        expenses: [{ description: "Chi phí tiếp khách", invoice_no: "00000101", amount: 3240000, status: "CLEAR", matched_invoice: "hoa_don_dien_tu.pdf" }],
        warnings: [], invoices: [],
      }), { status: 200 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ (PDF/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    const body = document.body.textContent ?? "";
    expect(body).not.toContain("Công tác Hà Nội");
    expect(screen.getByText("Ứng nhân viên kê khai:")).toBeInTheDocument();
    expect(screen.getByText("Tổng chi phí kê khai:")).toBeInTheDocument();
  });

  it("shows an error and keeps files on read failure; never invents facts", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({ detail: "provider down" }), { status: 500 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ (PDF/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Xác nhận và nộp hồ sơ" })).not.toBeInTheDocument();
    // The file is preserved for a retry.
    expect(screen.getByText(/report\.pdf/)).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toContain("3.240.000");
  });

  it("keeps unknown money unknown and does not show a false balance", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null,
        trip_start: null, trip_end: null, occurred_at: null, declared_purpose: "x",
        incurred_total: null, declared_advance: null, expenses: [], warnings: ["Chưa đọc được tổng chi phí"], invoices: [],
      }), { status: 200 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ (PDF/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    expect(screen.getAllByText("Chưa đọc được").length).toBeGreaterThan(0);
    expect(document.body.textContent ?? "").not.toContain("Cân bằng");
  });

  it("sends the confirmed draft (activity + advance + notes) on submit", async () => {
    let submitBody: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null, trip_start: null, trip_end: null,
        occurred_at: null, declared_purpose: "Chi phí tiếp khách", incurred_total: 3240000, declared_advance: 4000000,
        expenses: [], warnings: [], invoices: [],
      }), { status: 200 });
      if (url.endsWith("/submit")) {
        submitBody = JSON.parse(String(init?.body ?? "{}"));
        return new Response(JSON.stringify({ case_view: caseView(3, 1, "PROCESSING") }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ (PDF/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Hoạt động của hồ sơ"), "activity:tc01");
    await user.clear(screen.getByLabelText("Ứng nhân viên kê khai:"));
    await user.type(screen.getByLabelText("Ứng nhân viên kê khai:"), "4500000");
    await user.type(screen.getByLabelText(/Ghi chú của nhân viên/), "Đã kiểm tra hóa đơn");
    await user.click(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }));
    await waitFor(() => expect(submitBody).not.toBeNull());
    const body = submitBody as unknown as Record<string, unknown>;
    expect(body.activity_id).toBe("activity:tc01");
    expect(body.declared_advance).toBe(4_500_000);
    expect(body.original_declared_advance).toBe(4_000_000);
    expect(body.notes).toBe("Đã kiểm tra hóa đơn");
  });
});
