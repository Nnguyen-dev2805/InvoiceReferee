import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Advance } from "../src/features/advance";
import type { CaseView } from "../src/types";

function caseView(): CaseView {
  return {
    id: "case:1", version: 3, state: "WAITING",
    activity: "activity:uc03-f01", employee: "employee:employee-a",
    summary: "Công tác Hà Nội · 10/10/2026 · Nguyễn An",
    sources: [], issues: [], problems: [], conclusion: null, instructions: [],
    actual_money: {}, audit: [], evidence_report: null,
    assessment_ready: true, assessment_blocker: null, payment_basis: [], activity_acceptances: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("Advance (record advance received)", () => {
  it("rechecks a saved draft without uploading or recording money", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      draft: {
        source_id: "source:saved", draft_id: "draft:saved", amount: 4_000_000,
        payer_name: "Công ty An Thịnh", payee_name: "NGUYỄN MINH AN",
        transaction_reference: "FT-TC01-0001", activity_reference: "TU-TC01",
        instrument_method: "TRANSFER", instrument_status: "COMPLETED",
        event_at: "05/10/2026", missing_fields: [], requires_confirmation: true,
        activity_link_status: "LINKED", matched_activity_id: caseView().activity,
        activity_link_basis: "MULTI_FIELD_MATCH", activity_link_candidate_count: 1,
        activity_link_signals: [{ field: "time", state: "MATCHED", summary: "Ngày hợp lệ.", refs: [] }],
        refs: [],
      }, case_view: caseView(),
    }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const onSourceSelected = vi.fn();
    render(<Advance caseView={caseView()} onCase={() => {}} onSourceSelected={onSourceSelected} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Kiểm tra lại bản nháp đã lưu" }));
    await waitFor(() => expect(screen.getByText("Đã tự liên kết với hồ sơ này")).toBeInTheDocument());
    expect(screen.queryByLabelText("Căn cứ đối chiếu với công việc")).not.toBeInTheDocument();
    expect(onSourceSelected).toHaveBeenCalledWith("source:saved");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/cases/case:1/advance/draft");
  });

  it("reads an uploaded document into a draft and records it with the case scope", async () => {
    const calls: string[] = [];
    let recordBody: Record<string, unknown> | null = null;
    const attachedCase = { ...caseView(), version: 4 };
    const onCase = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push(url);
        if (url.includes("/advance/draft")) {
          return new Response(
            JSON.stringify({
              draft: {
              source_id: "source:1", draft_id: "advance-draft:1", amount: 4_000_000, payer_name: "Công ty InvoiceReferee",
              payee_name: "NGUYỄN MINH AN", transaction_reference: "FT-UC03-F01-0001",
              instrument_method: "TRANSFER", instrument_status: "COMPLETED",
              event_at: "2026-10-05", missing_fields: [], requires_confirmation: true,
              activity_reference: null, activity_link_status: "NOT_FOUND", matched_activity_id: null,
              refs: [{ source_id: "source:1", source_sha256: "a".repeat(64), page: 1, exact_quote: "Đã nhận tiền" }],
              },
              case_view: attachedCase,
            }),
            { status: 200 },
          );
        }
        if (url.includes("/actuals")) {
          recordBody = JSON.parse(String(init?.body ?? "{}")).money;
          return new Response(JSON.stringify({ case_view: caseView() }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(<Advance caseView={caseView()} onCase={onCase} />);
    const user = userEvent.setup();
    const file = new File(["%PDF-1.4 x"], "03-bien-nhan.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Chứng từ ứng"), file);

    await waitFor(() => expect(screen.getByTestId("advance-draft")).toBeInTheDocument());
    expect(onCase).toHaveBeenCalledWith(attachedCase);
    expect((screen.getByLabelText("Số tiền thực nhận") as HTMLInputElement).value).toBe("4000000");
    expect((screen.getByLabelText("Mã giao dịch hoặc số phiếu") as HTMLInputElement).value).toBe("FT-UC03-F01-0001");
    const payer = screen.getByLabelText("Bên chi theo chứng từ");
    expect(payer).toHaveValue("Công ty InvoiceReferee");
    expect(payer).toHaveClass("text-sm");
    const payee = screen.getByLabelText("Người nhận theo chứng từ");
    expect(payee).toHaveValue("NGUYỄN MINH AN");
    expect(payee).toHaveClass("text-sm");

    // A manual link needs its reason, but no duplicate declaration field.
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));
    expect(recordBody).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("xác nhận chứng từ thuộc đúng công việc");
    await user.click(screen.getByLabelText("Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này"));
    await user.type(screen.getByLabelText("Căn cứ đối chiếu với công việc"), "Đối chiếu người nhận và nội dung trên phiếu với hồ sơ tiếp khách này.");
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));

    await waitFor(() => expect(recordBody).not.toBeNull());
    const money = recordBody as unknown as Record<string, unknown>;
    expect(money.claimed_kind).toBe("ADVANCE_RECEIVED");
    expect(money.claimed_scope).toBe("activity:uc03-f01"); // server-scope, not hard-coded
    expect(money.instrument_method).toBe("TRANSFER");
    expect(money.instrument_status).toBe("COMPLETED");
    expect(money.amount).toBe(4_000_000);
    // The transaction identity comes from the voucher — never a minted UUID —
    // and the time/parties come from the source, not the confirm moment.
    expect(money.external_key).toBe("transfer:FT-UC03-F01-0001");
    expect(money.instrument_reference).toBe("FT-UC03-F01-0001");
    expect(money.payer).toBe("Công ty InvoiceReferee");
    expect(money.payee).toBe("NGUYỄN MINH AN");
    expect(money.event_at).toBe("2026-10-05");
    expect(money.advance_draft_id).toBe("advance-draft:1");
    expect(money.activity_link_confirmed).toBe(true);
    expect(money.activity_link_reason).toContain("Đối chiếu người nhận");
    // The client never sets a received/verified state.
    expect(money).not.toHaveProperty("verification_state");
  });

  it("does not record when required source details and manual link remain unresolved", async () => {
    let recordCalled = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/advance/draft")) {
          return new Response(
            JSON.stringify({
              draft: {
              source_id: "s", amount: 4_000_000, payer_name: null, payee_name: "Nguyễn An",
              transaction_reference: "FT-1", instrument_method: "TRANSFER",
              instrument_status: "COMPLETED", event_at: null, missing_fields: [],
              requires_confirmation: true, draft_id: "draft:2", activity_link_status: "NOT_FOUND",
              refs: [{ source_id: "s", source_sha256: "a".repeat(64), page: 1, exact_quote: "x" }],
              },
              case_view: caseView(),
            }),
            { status: 200 },
          );
        }
        if (url.includes("/actuals")) {
          recordCalled = true;
        }
        return new Response("{}", { status: 200 });
      }),
    );
    render(<Advance caseView={caseView()} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ ứng"), new File(["x"], "x.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(screen.getByTestId("advance-draft")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));
    expect(recordCalled).toBe(false);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("requires an explanation only when the accountant completes a missing field", async () => {
    let body: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/actuals")) {
        body = JSON.parse(String(init?.body)).money;
        return new Response(JSON.stringify({ case_view: caseView() }), { status: 200 });
      }
      return new Response(JSON.stringify({ draft: {
        source_id: "s", draft_id: "draft:missing-status", amount: 4_000_000,
        payer_name: "Công ty An Thịnh", payee_name: "NGUYỄN MINH AN",
        transaction_reference: "FT-1", instrument_method: "TRANSFER", instrument_status: "UNKNOWN",
        event_at: "2026-10-05", missing_fields: ["instrument_status"], refs: [],
        requires_confirmation: true, activity_link_status: "LINKED", matched_activity_id: caseView().activity,
      }, case_view: caseView() }), { status: 200 });
    }));
    render(<Advance caseView={caseView()} onCase={() => {}} />);
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Chứng từ ứng"), new File(["x"], "x.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(screen.getByTestId("advance-draft")).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText("Trạng thái theo nguồn"), "COMPLETED");
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));
    expect(body).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("căn cứ bổ sung");
    await user.type(screen.getByLabelText("Căn cứ bổ sung thông tin"), "Đã kiểm tra trên bản gốc: giao dịch hoàn tất.");
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ reason: "Đã kiểm tra trên bản gốc: giao dịch hoàn tất.", completion_claim: null });
  });

  it("shows a multi-field auto-link and keeps only the accountant money confirmation", async () => {
    let recordBody: Record<string, unknown> | null = null;
    const onSourceSelected = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/advance/draft")) {
          return new Response(JSON.stringify({
            draft: {
              source_id: "source:advance",
              draft_id: "advance-draft:multi-field",
              amount: 4_000_000,
              payer_name: "CÔNG TY TNHH GIẢI PHÁP CÔNG NGHỆ AN THỊNH",
              payee_name: "NGUYỄN MINH AN",
              transaction_reference: "FT-TC01-0001",
              activity_reference: "TU-TC01",
              activity_link_status: "LINKED",
              matched_activity_id: "activity:uc03-f01",
              activity_link_basis: "MULTI_FIELD_MATCH",
              activity_link_candidate_count: 1,
              activity_link_signals: [
                { field: "employee", state: "MATCHED", summary: "Người nhận và người đề nghị khớp nhân viên của hồ sơ.", refs: [] },
                { field: "company", state: "MATCHED", summary: "Bên chuyển khớp tổ chức đã cấu hình.", refs: [] },
                { field: "purpose", state: "MATCHED", summary: "Cụm dự án cụ thể khớp giữa biên nhận và giấy quyết toán.", refs: [] },
                { field: "advance_amount", state: "MATCHED", summary: "Tiền thực nhận khớp số ứng khai trên giấy quyết toán.", refs: [] },
                { field: "time", state: "MATCHED", summary: "Ngày chuyển có trước ngày lập giấy.", refs: [] },
                { field: "reference", state: "UNMAPPED", summary: "Mã TU-TC01 chưa ánh xạ; các căn cứ còn lại đã khớp.", refs: [] },
              ],
              instrument_method: "TRANSFER",
              instrument_status: "COMPLETED",
              event_at: "2026-10-05",
              missing_fields: [],
              requires_confirmation: true,
              already_recorded: false,
              refs: [{ source_id: "source:advance", source_sha256: "a".repeat(64), page: 1, exact_quote: "Bên nhận: NGUYỄN MINH AN" }],
            },
            case_view: caseView(),
          }), { status: 200 });
        }
        if (url.includes("/actuals")) {
          recordBody = JSON.parse(String(init?.body ?? "{}")).money;
          return new Response(JSON.stringify({ case_view: caseView() }), { status: 200 });
        }
        return new Response("{}", { status: 200 });
      }),
    );

    render(
      <Advance
        caseView={caseView()}
        onCase={() => {}}
        onSourceSelected={onSourceSelected}
      />,
    );
    const user = userEvent.setup();
    await user.upload(
      screen.getByLabelText("Chứng từ ứng"),
      new File(["%PDF-1.4 x"], "03-bien-nhan-chuyen-khoan.pdf", { type: "application/pdf" }),
    );

    await waitFor(() => expect(screen.getByTestId("advance-draft")).toBeInTheDocument());
    expect(onSourceSelected).toHaveBeenCalledWith("source:advance");
    expect(screen.getByText("Đã tự liên kết với hồ sơ này")).toBeInTheDocument();
    expect(screen.getByText("Cụm dự án cụ thể khớp giữa biên nhận và giấy quyết toán.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Tôi xác nhận chứng từ ứng thuộc công việc trong hồ sơ này")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Căn cứ đối chiếu với công việc")).not.toBeInTheDocument();

    expect(screen.queryByLabelText("Xác nhận của kế toán")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Xác nhận ghi nhận" }));
    await waitFor(() => expect(recordBody).not.toBeNull());
    expect(recordBody).toMatchObject({
      claimed_kind: "ADVANCE_RECEIVED",
      activity_link_confirmed: true,
      activity_link_reason: null,
      completion_claim: null,
    });
  });
});
