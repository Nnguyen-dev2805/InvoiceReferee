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
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    const body = document.body.textContent ?? "";
    expect(body).not.toContain("Công tác Hà Nội");
    expect(screen.getByText("Ứng nhân viên kê khai:")).toBeInTheDocument();
    expect(screen.getByText("Tổng trên giấy (chưa xác minh):")).toBeInTheDocument();
  });

  it("shows the sourced row-total contradiction and labels the printed total as unresolved", async () => {
    const basis = "Hai dòng chi 2000000 + 1000000 = 3000000 VND, nhưng tổng in trên giấy là 3500000 VND (lệch 500000 VND).";
    const question = "Hai khoản chi cộng thành 3.000.000 đ, nhưng tổng trên giấy là 3.500.000 đ. Vui lòng làm rõ khoản thiếu hoặc cung cấp giấy quyết toán đã sửa.";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 2) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null,
        trip_start: null, trip_end: null, occurred_at: null,
        declared_purpose: "Chi phí tiếp khách phục vụ dự án",
        incurred_total: 3500000, declared_advance: 4000000,
        expenses: [
          { description: "Chi phí tiếp khách", invoice_no: "00000501", amount: 2000000 },
          { description: "Chi phí phòng họp", invoice_no: "00000501", amount: 1000000 },
        ],
        warnings: [basis],
        arithmetic_findings: [{
          code: "settlement-line-total", basis, question,
          refs: [
            { source_id: "source:0", source_sha256: "a".repeat(64), page: 1, exact_quote: "Tổng cộng: 3.500.000 đ" },
            { source_id: "source:0", source_sha256: "a".repeat(64), page: 1, exact_quote: "Tiếp khách 2.000.000 đ" },
            { source_id: "source:0", source_sha256: "a".repeat(64), page: 1, exact_quote: "Phòng họp 1.000.000 đ" },
          ],
        }],
        invoices: [],
      }), { status: 200 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));

    expect(await screen.findByText(question)).toBeInTheDocument();
    expect(screen.getByText("Tổng cộng: 3.500.000 đ")).toBeInTheDocument();
    expect(screen.getByText("Tiếp khách 2.000.000 đ")).toBeInTheDocument();
    expect(screen.getByText("Phòng họp 1.000.000 đ")).toBeInTheDocument();
    expect(screen.getByText("Tổng trên giấy (chưa xác minh):")).toBeInTheDocument();
    expect(screen.getByText("Chưa xác định")).toBeInTheDocument();
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
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
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
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    expect(screen.getAllByText("Chưa đọc được").length).toBeGreaterThan(0);
    expect(document.body.textContent ?? "").not.toContain("Cân bằng");
  });

  it("sends the confirmed draft (no activity pick, merged purpose, notes) on submit", async () => {
    let submitBody: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null, trip_start: null, trip_end: null,
        occurred_at: null, declared_purpose: "Chi phí tiếp khách", incurred_total: 3240000, declared_advance: 4000000,
        expenses: [], warnings: [], invoices: [],
        link: { status: "NOT_FOUND", activity_id: null, basis: null, candidates: [], reasons: ["Không tìm thấy hồ sơ khớp."], conflicting_fields: [], owner: null, requires_confirmation: false, inherited: false },
      }), { status: 200 });
      if (url.endsWith("/submit")) {
        submitBody = JSON.parse(String(init?.body ?? "{}"));
        return new Response(JSON.stringify({ case_view: caseView(3, 1, "PROCESSING") }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    // No standing-activity dropdown in the normal flow; one merged content field.
    expect(screen.queryByLabelText("Hoạt động của hồ sơ")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Nội dung đề nghị quyết toán:")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Ứng nhân viên kê khai:"));
    await user.type(screen.getByLabelText("Ứng nhân viên kê khai:"), "4500000");
    await user.type(screen.getByLabelText(/Ghi chú của nhân viên/), "Đã kiểm tra hóa đơn");
    await user.click(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }));
    await waitFor(() => expect(submitBody).not.toBeNull());
    const body = submitBody as unknown as Record<string, unknown>;
    // The backend owns the link: no activity choice is sent.
    expect(body.activity_id).toBeNull();
    expect(body.confirmed_activity_id).toBeNull();
    expect(body.declared_advance).toBe(4_500_000);
    expect(body.original_declared_advance).toBe(4_000_000);
    expect(body.notes).toBe("Đã kiểm tra hóa đơn");
  });

  it("asks which advance the dossier settles when the link is weak", async () => {
    let submitBody: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 1) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null, trip_start: null, trip_end: null,
        occurred_at: null, declared_purpose: "Tạm ứng đi công tác", incurred_total: 3240000, declared_advance: 4000000,
        expenses: [], warnings: [], invoices: [],
        link: {
          status: "NEEDS_CONFIRMATION", activity_id: null, basis: null,
          candidates: [
            { activity_id: "activity:adv-1", name: "Tạm ứng 1", basis: "WEAK_SIMILARITY", amount: 4000000, occurred_at: "2026-10-01", employee: "employee:a" },
            { activity_id: "activity:adv-2", name: "Tạm ứng 2", basis: "WEAK_SIMILARITY", amount: 4000000, occurred_at: "2026-10-02", employee: "employee:a" },
          ],
          reasons: ["Chỉ có căn cứ yếu."], conflicting_fields: [], owner: "employee",
          requires_confirmation: true, inherited: false,
        },
      }), { status: 200 });
      if (url.endsWith("/submit")) {
        submitBody = JSON.parse(String(init?.body ?? "{}"));
        return new Response(JSON.stringify({ case_view: caseView(3, 1, "PROCESSING") }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByText("Hồ sơ này quyết toán cho khoản tạm ứng nào?")).toBeInTheDocument());
    // Submitting without a choice is refused client-side.
    await user.click(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(submitBody).toBeNull();
    // Confirming one candidate forwards only the confirmation.
    await user.click(screen.getByLabelText(/Tạm ứng 2/));
    await user.click(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" }));
    await waitFor(() => expect(submitBody).not.toBeNull());
    const body = submitBody as unknown as Record<string, unknown>;
    expect(body.activity_id).toBeNull();
    expect(body.confirmed_activity_id).toBe("activity:adv-2");
  });

  it("resumes an existing draft case directly into the review step", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/settlement/draft")) {
        return new Response(JSON.stringify({
          declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null, trip_start: null, trip_end: null,
          occurred_at: null, declared_purpose: "Chi phí tiếp khách", incurred_total: 3240000, declared_advance: 4000000,
          expenses: [{ description: "Chi phí tiếp khách", invoice_no: "00000101", amount: 3240000, status: "CLEAR" }],
          warnings: [], invoices: [],
        }), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }));

    const existingDraft = caseView(2, 2, "DRAFT");
    render(<Intake session={SESSION} onCase={() => {}} existingCase={existingDraft} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument();
      expect(screen.getByText("Bản nháp hồ sơ quyết toán")).toBeInTheDocument();
      expect(screen.getByText("Chi phí tiếp khách")).toBeInTheDocument();
    });
  });
});

describe("Intake draft dispute (cross-document conflict)", () => {
  it("shows the 900000/700000/200000 dispute at the row with both-side evidence buttons", async () => {
    const dispute = {
      code: "row-amount-disputed",
      item_ids: ["ITEM-001"],
      document_id: "source:receipt:1-1:COLLECTION_RECEIPT",
      document_filename: "phieu_thu_di_chuyen.pdf",
      paper_source_id: "source:paper",
      document_source_id: "source:receipt",
      status: "AMOUNT_DISPUTED",
      paper_amount: 900000,
      document_total: 700000,
      difference: 200000,
      basis: "Kê khai 900000 nhưng chứng từ chỉ chứng minh 700000 (lệch 200000); số tiền đang tranh chấp.",
      question: "Xác nhận/sửa số tiền.",
      refs: [],
      blocking: true,
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 2) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null,
        trip_start: null, trip_end: null, occurred_at: null,
        declared_purpose: "Hoàn ứng chi phí công tác tỉnh",
        incurred_total: 4140000, declared_advance: 5000000,
        expenses: [{
          description: "Di chuyển nội thành", invoice_no: "PT-251026-016", amount: 900000,
          status: "DISPUTED", suggested_invoice: "phieu_thu_di_chuyen.pdf", dispute,
        }],
        warnings: [], invoices: [], reconciliation_findings: [dispute],
      }), { status: 200 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "evidence.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    expect(screen.getByText(/số tiền đang tranh chấp/)).toBeInTheDocument();
    expect(screen.getAllByText(/phieu_thu_di_chuyen\.pdf/).length).toBeGreaterThanOrEqual(2);
    const body = document.body.textContent ?? "";
    expect(body).toContain("900.000");
    expect(body).toContain("700.000");
    expect(body).toContain("200.000");
    expect(screen.queryByText("✓")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Xem phieu_thu_di_chuyen/ }));
  });
});

describe("Intake draft alternative evidence (TC18)", () => {
  it("shows an alternative-supported row without a green tick", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/cases")) return new Response(JSON.stringify({ case_view: caseView(1, 0) }), { status: 200 });
      if (url.endsWith("/sources")) return new Response(JSON.stringify({ case_view: caseView(2, 2) }), { status: 200 });
      if (url.endsWith("/settlement/draft")) return new Response(JSON.stringify({
        declared_name: "NGUYỄN MINH AN", destination: null, activity_name: null,
        trip_start: null, trip_end: null, occurred_at: null,
        declared_purpose: "Sửa chữa máy in",
        incurred_total: 4200000, declared_advance: 5000000,
        expenses: [{
          description: "Nhân công sửa chữa", invoice_no: "BBNT-181026-02", amount: 1500000,
          status: "ALTERNATIVE", matched_invoice: "nghiem_thu.pdf", dispute: null,
        }],
        warnings: [], invoices: [], reconciliation_findings: [],
      }), { status: 200 });
      return new Response("{}", { status: 200 });
    }));
    render(<Intake session={SESSION} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "paper.pdf", { type: "application/pdf" }));
    await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"), new File(["%PDF-1.4"], "evidence.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Đọc chứng từ" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Xác nhận và nộp hồ sơ" })).toBeInTheDocument());
    expect(screen.getByText(/Bằng chứng thay thế/)).toBeInTheDocument();
    expect(screen.getByText(/nghiem_thu\.pdf/)).toBeInTheDocument();
    expect(screen.queryByText("✓")).not.toBeInTheDocument();
  });
});

it("keeps self-expense type and no-advance declaration when submitting paper", async () => {
 localStorage.clear();
 let submitted:Record<string,unknown>|null=null;
 vi.stubGlobal("fetch",vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);
  if(url.endsWith("/api/cases"))return new Response(JSON.stringify({case_view:caseView(1,0)}));
  if(url.endsWith("/sources"))return new Response(JSON.stringify({case_view:caseView(2,2)}));
  if(url.endsWith("/settlement/draft"))return new Response(JSON.stringify({declared_name:"NGUYỄN MINH AN",declared_purpose:"Sửa máy in",incurred_total:1000000,declared_advance:0,expenses:[],warnings:[],invoices:[]}));
  if(url.endsWith("/submit")){submitted=JSON.parse(String(init?.body));return new Response(JSON.stringify({case_view:caseView(3,2,"WAITING")}));}
  return new Response("{}");
 }));
 render(<Intake session={SESSION} onCase={()=>{}}/>);const user=userEvent.setup();
 await user.click(screen.getByText("Nhân viên tự chi"));
 await user.type(screen.getByLabelText("Lý do không nhận tạm ứng"),"Tự thanh toán trước, không nhận ứng");
 await user.upload(screen.getByLabelText("Đơn quyết toán (PDF/DOC/DOCX/PNG/JPEG)"),new File(["pdf"],"self.pdf",{type:"application/pdf"}));
 await user.upload(screen.getByLabelText("Hóa đơn chứng từ kèm theo (PDF/DOC/DOCX/PNG/JPEG)"),new File(["pdf"],"inv.pdf",{type:"application/pdf"}));
 await user.click(screen.getByRole("button",{name:"Đọc chứng từ"}));
 await user.click(await screen.findByRole("button",{name:"Xác nhận và nộp hồ sơ"}));
 await waitFor(()=>expect(submitted).not.toBeNull());
 expect(submitted).toMatchObject({settlement_type:"EMPLOYEE_REIMBURSEMENT",submission_source:"PAPER_SCAN",no_advance_asserted:true});
 localStorage.clear();
});
