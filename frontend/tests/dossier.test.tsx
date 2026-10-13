import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Dossier } from "../src/features/dossier";
import type { CaseView } from "../src/types";

// A literal view fixture (contracts §9): no workflow, no network. It shows a
// known money figure, an unknown one, a rule-backed issue and an effect.
const VIEW: CaseView = {
  id: "case:demo",
  version: 3,
  state: "WAITING",
  summary: "Công tác Hà Nội · 05/10/2026 · Nguyễn Văn A",
  sources: [
    {
      id: "source:1",
      digest: "abcdef0123456789",
      tenant: "tenant:demo",
      media: "PDF",
      storage_key: "tenant:demo/case:demo/source:1",
    },
  ],
  issues: [
    {
      id: "issue:policy:budget",
      kind: "POLICY",
      field_or_rule: "budget:B",
      owner: "approver",
      status: "OPEN",
      basis: "Tổng chi 10.000.000 vượt ngân sách 8.000.000.",
      question: "Quyết định ngoại lệ vượt ngân sách (giữ nguyên số thực chi).",
    },
  ],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {
    T: { key: "projection:T", value: 10_000_000, state: "KNOWN" },
    E: { key: "projection:E", value: 5_000_000, state: "KNOWN" },
    A: { key: "projection:A", value: null, state: "UNKNOWN" },
  },
  audit: ["2026-10-13 · employee:employee-a · CREATE_DRAFT"],
};

describe("Dossier", () => {
  it("renders known, unknown, rule and effect in Vietnamese", () => {
    render(<Dossier caseView={VIEW} />);

    // Known money figure, formatted.
    expect(screen.getByTestId("money-Tổng chi công việc")).toHaveTextContent(
      "10.000.000",
    );
    // Unknown figure: explicit, never a fabricated zero.
    expect(screen.getByTestId("money-Ứng thực nhận")).toHaveTextContent(
      "Chưa xác minh",
    );
    // Rule-backed issue with its owner and basis.
    expect(screen.getByText(/Chính sách/)).toBeInTheDocument();
    expect(
      screen.getByText(/Căn cứ: Tổng chi 10.000.000 vượt ngân sách 8.000.000/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Người xử lý: approver/)).toBeInTheDocument();
  });

  it("shows an empty state when no case is open", () => {
    render(<Dossier caseView={null} />);
    expect(screen.getByText(/Chưa có hồ sơ nào được mở/)).toBeInTheDocument();
  });
});
