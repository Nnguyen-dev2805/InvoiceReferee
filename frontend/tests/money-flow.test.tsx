import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Coverage } from "../src/features/coverage";
import { EmployeeReturn } from "../src/features/employee_return";
import { Execution } from "../src/features/execution";
import type { CaseView } from "../src/types";

const baseCase = (): CaseView => ({
  id: "case:money-flow", version: 4, state: "READY_TO_EXECUTE",
  activity: "activity:tc01", employee: "employee:employee-a", summary: "TC01 · 15/10/2026 · Nguyễn An",
  sources: [], issues: [], problems: [], conclusion: null, instructions: [], actual_money: {}, audit: [],
  evidence_report: null, assessment_ready: true, assessment_blocker: null, payment_basis: [],
});

describe("money-flow UI", () => {
  it("does not show a payment form when there is no active PAY instruction", () => {
    render(<Execution caseView={baseCase()} onCase={vi.fn()} />);
    expect(screen.getByTestId("no-active-pay")).toBeInTheDocument();
    expect(screen.queryByLabelText("Số tiền thực chi")).toBeNull();
  });

  it("uploads employee proof and requests a source-bound draft without confirming money", async () => {
    const onCase = vi.fn();
    const view = baseCase();
    view.instructions = [{
      id: "instruction:collect-1", direction: "COLLECT", amount: 760_000, status: "ISSUED",
      basis: "return", fulfilled_amount: 0, remaining: 760_000, execution_state: "NOT_STARTED",
    }];
    view.employee_return_drafts = [];
    let draftRequest: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/sources")) {
        return new Response(JSON.stringify({ case_view: { ...view, version: 5, sources: [{
          id: "source:return", digest: "a".repeat(64), tenant: "tenant:demo", media: "PDF",
          storage_key: "tenant/case/source", filename: "return.pdf",
        }] }, job_id: null, duplicate_command: false }), { status: 200 });
      }
      draftRequest = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ case_view: { ...view, version: 6 }, draft: { draft_id: "draft:return" } }), { status: 200 });
    }));
    const user = userEvent.setup();
    render(<EmployeeReturn caseView={view} onCase={onCase} />);
    await user.selectOptions(screen.getByLabelText("Lệnh thu cần đối chiếu"), "instruction:collect-1");
    await user.upload(screen.getByLabelText("Chứng từ chuyển khoản hoàn trả"), new File(["pdf"], "return.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Tải lên và đọc" }));
    await waitFor(() => expect(draftRequest).not.toBeNull());
    expect(draftRequest).toEqual({ source_id: "source:return", instruction_id: "instruction:collect-1", instrument_method: "TRANSFER" });
    expect(onCase).toHaveBeenCalledTimes(2);
  });

  it("requires accountant confirmation before writing an employee return to the ledger", async () => {
    const view = baseCase();
    view.employee_return_drafts = [{
      draft_id: "draft:return", root_id: view.id, employee: "employee:employee-a", activity: "activity:tc01",
      instruction_id: "instruction:collect-1", source_id: "source:return", source_sha256: "a".repeat(64), source_filename: "return.pdf",
      status: "WAITING_ACCOUNTANT", match_status: "MATCHED", amount: 760_000, payer_name: "Nguyễn An", payee_name: "Công ty",
      transaction_reference: "FT-RETURN-01", external_key: "transfer:FT-RETURN-01", instrument_method: "TRANSFER",
      instrument_status: "COMPLETED", event_at: "2026-10-15T05:00:00Z", instruction_amount: 760_000,
      instruction_remaining: 760_000,
      refs: [{ source_id: "source:return", source_sha256: "a".repeat(64), page: 1, exact_quote: "FT-RETURN-01 760.000" }],
      missing_fields: [], signals: [], uploaded_at: "2026-10-15T06:00:00Z", confirmed_at: null, confirmed_by: null, money_event_id: null,
    }];
    const onCase = vi.fn();
    let requestBody: Record<string, unknown> | null = null;
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      requestBody = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ case_view: { ...view, version: 5 }, job_id: null, duplicate_command: false }), { status: 200 });
    }));
    const user = userEvent.setup();
    render(<Coverage caseView={view} onCase={onCase} />);
    expect(screen.queryByRole("button", { name: "Xác nhận đã đối chiếu lịch sử tiền" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Kế toán xác nhận đã nhận" }));
    await waitFor(() => expect(requestBody).not.toBeNull());
    expect((requestBody?.money as Record<string, unknown>)).toMatchObject({
      external_key: "transfer:FT-RETURN-01", claimed_kind: "EMPLOYEE_RETURN", instruction_id: "instruction:collect-1",
      money_movement_draft_id: "draft:return", amount: 760_000,
    });
    expect(onCase).toHaveBeenCalledOnce();
  });
});
