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
    assessment_ready: true, assessment_blocker: null, payment_basis: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("Advance (record advance received)", () => {
  it("reads an uploaded document into a draft and records it with the case scope", async () => {
    const calls: string[] = [];
    let recordBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        calls.push(url);
        if (url.includes("/advance/draft")) {
          return new Response(
            JSON.stringify({
              source_id: "source:1", amount: 4_000_000, payer_name: "Công ty InvoiceReferee",
              payee_name: "Nguyễn An", transaction_reference: "FT-UC03-F01-0001",
              instrument_method: "TRANSFER", instrument_status: "COMPLETED",
              event_at: "2026-10-05", missing_fields: [], requires_confirmation: true,
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

    render(<Advance caseView={caseView()} onCase={() => {}} />);
    const user = userEvent.setup();
    const file = new File(["%PDF-1.4 x"], "03-bien-nhan.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Chứng từ ứng"), file);

    await waitFor(() => expect(screen.getByTestId("advance-draft")).toBeInTheDocument());
    expect((screen.getByLabelText("Số tiền thực nhận") as HTMLInputElement).value).toBe("4000000");
    expect((screen.getByLabelText("Mã giao dịch hoặc số phiếu") as HTMLInputElement).value).toBe("FT-UC03-F01-0001");

    // The accountant must add a responsible confirmation before recording.
    await user.type(screen.getByLabelText("Xác nhận của kế toán"), "Đã kiểm tra và giao đủ tiền");
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
    expect(money.payee).toBe("Nguyễn An");
    expect(money.event_at).toBe("2026-10-05");
    // The client never sets a received/verified state.
    expect(money).not.toHaveProperty("verification_state");
  });

  it("does not record without the accountant's responsible confirmation", async () => {
    let recordCalled = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/advance/draft")) {
          return new Response(
            JSON.stringify({
              source_id: "s", amount: 4_000_000, payer_name: null, payee_name: "Nguyễn An",
              transaction_reference: "FT-1", instrument_method: "TRANSFER",
              instrument_status: "COMPLETED", event_at: null, missing_fields: [],
              requires_confirmation: true,
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
});
