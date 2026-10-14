import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dashboard } from "../src/features/dashboard";
import type { CaseView } from "../src/types";

const MOCK_CASE_1: CaseView = {
  id: "case:test-1",
  version: 1,
  state: "WAITING",
  summary: "Công tác Hà Nội · 05/10/2026 · Nguyễn Văn A",
  employee: "employee:a",
  sources: [],
  issues: [
    {
      id: "issue:1",
      kind: "FACT",
      field_or_rule: "expense:1:paid_basis",
      owner: "employee",
      status: "OPEN",
      basis: "Hóa đơn demo",
      question: "Nhân viên xác nhận đã tự chi trả khoản này?",
    },
  ],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {
    T: { key: "T", value: 5_000_000, state: "KNOWN" },
    E: { key: "E", value: 5_000_000, state: "KNOWN" },
    A: { key: "A", value: 3_000_000, state: "KNOWN" },
    S: { key: "S", value: 2_000_000, state: "KNOWN" },
  },
  audit: [],
  evidence_report: null,
  assessment_ready: false,
  assessment_blocker: null,
  payment_basis: [],
};

const MOCK_CASE_2: CaseView = {
  id: "case:test-2",
  version: 2,
  state: "READY_TO_EXECUTE",
  summary: "Tiếp khách đối tác · 10/10/2026 · Trần Thị B",
  employee: "employee:b",
  sources: [],
  issues: [],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {
    T: { key: "T", value: 2_500_000, state: "KNOWN" },
    E: { key: "E", value: 2_500_000, state: "KNOWN" },
    A: { key: "A", value: 4_000_000, state: "KNOWN" },
    S: { key: "S", value: -1_500_000, state: "KNOWN" },
  },
  audit: [],
  evidence_report: null,
  assessment_ready: true,
  assessment_blocker: null,
  payment_basis: [],
};

describe("Dashboard component", () => {
  it("renders the empty state when no cases exist", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();

    render(
      <Dashboard
        cases={[]}
        currentRole="employee"
        onSelectCase={onSelect}
        onCreateNew={onCreate}
      />,
    );

    expect(screen.getByText(/Chưa có hồ sơ nào được mở/)).toBeInTheDocument();
  });

  it("renders cases table and employee status tabs", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();

    render(
      <Dashboard
        cases={[MOCK_CASE_1, MOCK_CASE_2]}
        currentRole="employee"
        onSelectCase={onSelect}
        onCreateNew={onCreate}
      />,
    );

    expect(screen.getByText("Hồ sơ quyết toán của tôi")).toBeInTheDocument();
    expect(screen.getByText("Công tác Hà Nội")).toBeInTheDocument();
    expect(screen.getByText("Tiếp khách đối tác")).toBeInTheDocument();
    expect(screen.getByText("+2.000.000 ₫")).toBeInTheDocument();
    expect(screen.getByText("-1.500.000 ₫")).toBeInTheDocument();

    // Check Employee status tab & badge
    expect(screen.getByText("Cần bạn giải trình")).toBeInTheDocument();
  });

  it("calls onSelectCase when a table row is clicked", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();

    render(
      <Dashboard
        cases={[MOCK_CASE_1]}
        currentRole="employee"
        onSelectCase={onSelect}
        onCreateNew={onCreate}
      />,
    );

    const row = screen.getByText("Công tác Hà Nội").closest("tr")!;
    fireEvent.click(row);

    expect(onSelect).toHaveBeenCalledWith(MOCK_CASE_1);
  });

  it("renders Accountant dashboard tabs and titles", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();

    render(
      <Dashboard
        cases={[MOCK_CASE_1, MOCK_CASE_2]}
        currentRole="accountant"
        onSelectCase={onSelect}
        onCreateNew={onCreate}
      />,
    );

    expect(screen.getByText("Bàn làm việc Kế toán")).toBeInTheDocument();
    expect(screen.getByText("Cần chi trả")).toBeInTheDocument();
    expect(screen.getByText("Cần thu hồi")).toBeInTheDocument();
  });

  it("renders Approver dashboard tabs and titles", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();

    render(
      <Dashboard
        cases={[MOCK_CASE_1, MOCK_CASE_2]}
        currentRole="approver"
        onSelectCase={onSelect}
        onCreateNew={onCreate}
      />,
    );

    expect(screen.getByText("Bàn phê duyệt Chi tiêu")).toBeInTheDocument();
    expect(screen.getByText("Chờ phê duyệt")).toBeInTheDocument();
  });
});
