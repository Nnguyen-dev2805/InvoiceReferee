import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Coverage } from "../src/features/coverage";
import type { CaseView } from "../src/types";

const baseCase = (): CaseView => ({
  id: "case:coverage-1",
  version: 7,
  state: "WAITING",
  activity: "activity:proposed:client-meeting",
  employee: "employee:employee-a",
  summary: "Tiếp khách đối tác · 10/10/2026 · Nguyễn An",
  sources: [
    {
      id: "source:statement",
      digest: "a".repeat(64),
      tenant: "tenant:demo",
      media: "PDF",
      storage_key: "tenant/case/source",
      filename: "so-giao-dich.pdf",
    },
  ],
  issues: [],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {},
  audit: [],
  evidence_report: null,
  assessment_ready: true,
  assessment_blocker: null,
  payment_basis: [],
  money_history: [
    {
      id: "money:advance-1",
      external_key: "transfer:FT-1",
      kind: "ADVANCE_RECEIVED",
      scope: "activity:proposed:client-meeting",
      payer: "Công ty An Thịnh",
      payee: "Nguyễn An",
      amount: 4_000_000,
      event_at: "2026-10-05T09:00:00+07:00",
      recorded_at: "2026-10-15T12:00:00+07:00",
      verification_state: "CONFIRMED",
      allocation_state: "ALLOCATED",
      refs: [],
    },
  ],
});

afterEach(() => vi.restoreAllMocks());

describe("Coverage", () => {
  it("submits a scoped history confirmation using attached source refs", async () => {
    const onCase = vi.fn();
    let requestBody: Record<string, unknown> | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        requestBody = JSON.parse(String(init?.body ?? "{}"));
        return new Response(
          JSON.stringify({ case_view: { ...baseCase(), version: 8, coverage_current: true } }),
          { status: 200 },
        );
      }),
    );

    render(<Coverage caseView={baseCase()} onCase={onCase} />);
    const user = userEvent.setup();
    expect(screen.getByText("Ứng thực nhận")).toBeInTheDocument();
    expect(screen.getByText("Công ty An Thịnh → Nguyễn An · 2026-10-05")).toBeInTheDocument();
    expect(screen.getByText("4.000.000 ₫")).toBeInTheDocument();
    expect(screen.queryByText(/ledger:coverage|OBSERVED_UNALLOCATED|#coverage/)).toBeNull();

    await user.type(screen.getByLabelText("Đối chiếu từ ngày"), "2026-10-01");
    await user.type(screen.getByLabelText("Nguồn tiền hoặc quỹ đã kiểm tra"), "Tài khoản ngân hàng công ty");
    await user.type(screen.getByLabelText("Số dư đầu kỳ (VND)"), "0");
    await user.selectOptions(screen.getByLabelText("Chứng từ căn cứ đối chiếu"), "source:statement");
    await user.type(screen.getByLabelText("Trang chứng từ"), "1");
    await user.type(screen.getByLabelText("Đoạn căn cứ trên chứng từ"), "Sổ ngân hàng công ty đã đối chiếu");
    await user.type(screen.getByLabelText("Lý do xác nhận"), "Đã kiểm tra đầy đủ giao dịch trong kỳ đối chiếu cho hồ sơ này.");
    await user.click(screen.getByRole("button", { name: "Xác nhận đã đối chiếu lịch sử tiền" }));

    await waitFor(() => expect(requestBody).not.toBeNull());
    const body = requestBody as unknown as Record<string, unknown>;
    expect(body.start).toBe("2026-10-01T00:00:00+07:00");
    expect(body.funds).toEqual(["Tài khoản ngân hàng công ty"]);
    expect(body.flow_kinds).toEqual([
      "ADVANCE_RECEIVED",
      "REIMBURSEMENT_RECEIVED",
      "EMPLOYEE_RETURN",
      "REVERSAL",
      "OBSERVED_UNALLOCATED",
    ]);
    expect(body.opening_balance).toBe(0);
    expect(body.unallocated_event_ids).toEqual([]);
    expect(body.witness_refs).toEqual([
      {
        source_id: "source:statement",
        source_sha256: "a".repeat(64),
        page: 1,
        exact_quote: "Sổ ngân hàng công ty đã đối chiếu",
      },
    ]);
    expect(body).not.toHaveProperty("as_of");
    expect(onCase).toHaveBeenCalledWith(expect.objectContaining({ version: 8 }));
  });

  it("keeps unallocated events visible and does not present them as zero", () => {
    const view = baseCase();
    view.money_history = [
      {
        ...view.money_history![0],
        id: "money:pending-1",
        kind: "ADVANCE_RECEIVED",
        verification_state: "OBSERVED",
        allocation_state: "UNALLOCATED",
        amount: 1_000_000,
      },
    ];
    render(<Coverage caseView={view} onCase={() => {}} />);
    expect(screen.getByText(/Chứng từ đang chờ xử lý hoặc chưa gắn được giao dịch/)).toBeInTheDocument();
    expect(screen.getByText(/1\.000\.000/)).toBeInTheDocument();
  });

  it("surfaces a paper-declared employee return that has no confirmed receipt event", () => {
    const view = baseCase();
    view.evidence_report = {
      provider_mode: "LIVE",
      data_origin: "LIVE_READ",
      documents: [{
        document_type: "SETTLEMENT_FORM",
        fields: [{ field: "printed_return", state: "FOUND", value: "760.000", refs: [] }],
      }],
      links: [],
      row_matches: [],
      match_findings: [],
    };
    render(<Coverage caseView={view} onCase={() => {}} />);
    expect(screen.getByText(/Giấy quyết toán khai nhân viên hoàn lại 760.000 ₫/)).toBeInTheDocument();
    expect(screen.getByText(/chưa có giao dịch hoàn đã xác minh/)).toBeInTheDocument();
  });
});
