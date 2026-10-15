import { render, screen } from "@testing-library/react";
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
  it("shows the source calendar day in Vietnam rather than the stored UTC day", () => {
    const view = baseCase();
    view.money_history![0].event_at = "2026-10-04T17:00:00Z";
    render(<Coverage caseView={view} onCase={() => {}} />);
    expect(screen.getByText("Công ty An Thịnh → Nguyễn An · 05/10/2026")).toBeInTheDocument();
  });

  it("shows recorded money without any separate history confirmation", () => {
    render(<Coverage caseView={baseCase()} onCase={() => {}} />);
    expect(screen.getByText("4.000.000 ₫")).toBeInTheDocument();
    expect(screen.queryByLabelText("Đối chiếu từ ngày")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Xác nhận lịch sử ban đầu" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Kế toán xác nhận đã nhận" })).toBeNull();
  });

  it("does not request another history confirmation for current tracked money", () => {
    const view = baseCase();
    view.coverage_current = true;
    render(<Coverage caseView={view} onCase={() => {}} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Xác nhận lịch sử ban đầu" })).toBeNull();
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
    expect(screen.queryByRole("checkbox")).toBeNull();
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
