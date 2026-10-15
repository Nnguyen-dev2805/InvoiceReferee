import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { answerIssue } from "../src/api";
import { Questions } from "../src/features/questions";
import type { CaseView } from "../src/types";

vi.mock("../src/api", () => ({
  answerIssue: vi.fn(),
  errorMessage: (cause: unknown) => String(cause),
}));

const issue = {
  id: "issue:fact:payer:invoice-1",
  kind: "FACT" as const,
  field_or_rule: "expense:IR26101001:employee_paid",
  owner: "employee",
  status: "OPEN",
  basis: "Hóa đơn IR26101001 ghi nhận chi phí 3.240.000 VND.",
  question: "Bạn trực tiếp thanh toán bao nhiêu cho hóa đơn IR26101001?",
};

const caseView: CaseView = {
  id: "case:1",
  version: 4,
  state: "WAITING",
  summary: "Hồ sơ quyết toán",
  sources: [],
  issues: [issue],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {},
  audit: [],
  evidence_report: null,
  assessment_ready: true,
  assessment_blocker: null,
  payment_basis: [],
};

afterEach(() => vi.clearAllMocks());

describe("invoice-scoped employee-paid answer", () => {
  it("collects an exact VND amount and a responsible reason without a payer dropdown", async () => {
    vi.mocked(answerIssue).mockResolvedValue({
      case_view: caseView,
      job_id: null,
      duplicate_command: false,
    });
    const onCase = vi.fn();

    render(<Questions caseView={caseView} onCase={onCase} currentRole="employee" />);

    expect(screen.getByText(/Bạn trực tiếp thanh toán bao nhiêu/)).toBeInTheDocument();
    expect(screen.queryByText(/ngân sách hoạt động|vượt ngân sách/i)).not.toBeInTheDocument();

    const amount = screen.getByLabelText(
      "Số tiền VND nhân viên trực tiếp thanh toán cho hóa đơn IR26101001",
    );
    expect(amount).toHaveAttribute("type", "number");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    const submit = screen.getByRole("button", { name: "Gửi giải trình" });
    expect(submit).toBeDisabled();
    fireEvent.change(amount, { target: { value: "3240000" } });
    fireEvent.change(screen.getByLabelText("Lý do / xác nhận cụ thể"), {
      target: { value: "Tôi trực tiếp thanh toán hóa đơn IR26101001." },
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => {
      expect(answerIssue).toHaveBeenCalledWith(
        "case:1",
        expect.objectContaining({
          issue_id: issue.id,
          value: "3240000",
          reason: "Tôi trực tiếp thanh toán hóa đơn IR26101001.",
        }),
        4,
      );
    });
    expect(onCase).toHaveBeenCalledWith(caseView);
  });

  it("routes history coverage to the structured accountant form instead of free text", () => {
    const coverageIssue = {
      id: "issue:fact:history",
      kind: "FACT" as const,
      field_or_rule: "ledger:coverage",
      owner: "accountant",
      status: "OPEN",
      basis: "Thiếu lịch sử đối chiếu ứng/hoàn cho scope này.",
      question: "Xác minh coverage lịch sử (scope/thời gian/loại dòng tiền).",
    };
    const view = { ...caseView, issues: [coverageIssue] };
    render(<Questions caseView={view} onCase={() => {}} currentRole="accountant" />);

    expect(screen.getByText(/Không áp dụng giải trình bằng văn bản tự do/)).toBeInTheDocument();
    expect(screen.getByText(/Sổ cái & Dòng tiền/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tới xác nhận lịch sử tiền" })).toBeNull();
    expect(screen.queryByLabelText("Nội dung giải trình / xác nhận:")).toBeNull();
    expect(screen.queryByRole("button", { name: "Gửi giải trình" })).toBeNull();
  });

  it("shows the exact source quotations attached to a blocking arithmetic FACT", () => {
    const rowTotalIssue = {
      ...issue,
      id: "issue:fact:arithmetic:row-total",
      field_or_rule: "expense:arithmetic:line_total",
      basis: "Dòng tiếp khách và phòng họp cộng 3.000.000 đ, tổng in 3.500.000 đ.",
      question: "Hai khoản chi cộng thành 3.000.000 đ, nhưng tổng trên giấy là 3.500.000 đ. Vui lòng làm rõ.",
      refs: [{
        source_id: "source:report", source_sha256: "a".repeat(64), page: 1,
        exact_quote: "Tiếp khách 2.000.000 đ",
      }],
    };
    const view = {
      ...caseView,
      sources: [{
        id: "source:report", digest: "a".repeat(64), tenant: "tenant:demo" as const,
        media: "PDF" as const, storage_key: "k/report", filename: "report_hoan_ung.pdf",
      }],
      issues: [rowTotalIssue],
    };

    render(<Questions caseView={view} onCase={() => {}} currentRole="employee" />);

    expect(screen.getByLabelText("Trích dẫn nguồn cho căn cứ")).toHaveTextContent(/report_hoan_ung\.pdf.*trang 1/);
    expect(screen.getByText("Tiếp khách 2.000.000 đ")).toBeInTheDocument();
  });
});
