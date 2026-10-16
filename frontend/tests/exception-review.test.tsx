import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExceptionReview, OcrRegionView } from "../src/features/exception_review";
import type { CaseView, IssueView } from "../src/types";

vi.mock("../src/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api")>();
  return {
    ...actual,
    exceptionPreview: vi.fn(),
    decideIssues: vi.fn(),
    refuseException: vi.fn(),
    errorMessage: (cause: unknown) => String(cause),
  };
});

import { decideIssues, exceptionPreview, refuseException } from "../src/api";

const issue: IssueView = {
  id: "issue:policy:1",
  kind: "POLICY",
  field_or_rule: "expense:2:missing_evidence",
  owner: "accountant",
  status: "OPEN",
  basis: "Khoản 'Nhân công' đã đủ dữ kiện nhưng thiếu hóa đơn gốc. Lý do khai: Không xuất hóa đơn.",
  question: "Xác nhận bằng chứng thay thế có được chấp nhận?",
  refs: [
    {
      source_id: "source:trf", source_sha256: "a".repeat(64), page: 1,
      exact_quote: "Số tiền: 1500000", bbox: [60, 960, 620, 1010],
    },
    {
      source_id: "source:acc", source_sha256: "b".repeat(64), page: 1,
      exact_quote: "Trị giá: 1500000",
    },
  ],
};

function caseView(): CaseView {
  return {
    id: "case:1", version: 4, state: "WAITING", summary: "TC18",
    activity: "activity:tc18", employee: "employee:employee-a",
    sources: [
      { id: "source:trf", digest: "a".repeat(64), tenant: "t", media: "PDF", storage_key: "k1", filename: "chuyen_khoan.pdf" },
      { id: "source:acc", digest: "b".repeat(64), tenant: "t", media: "PDF", storage_key: "k2", filename: "nghiem_thu.pdf" },
    ],
    issues: [issue], problems: [], conclusion: null, instructions: [],
    actual_money: {}, audit: [], evidence_report: null,
    assessment_ready: true, assessment_blocker: null, payment_basis: [],
  };
}

afterEach(() => vi.clearAllMocks());

describe("ExceptionReview (accountant)", () => {
  it("shows amount, grants and both decisions when covered", async () => {
    vi.mocked(exceptionPreview).mockResolvedValue({
      issue_id: issue.id, rule_id: "expense:missing_required_evidence",
      expense_id: "expense:2", amount: 1500000, covered: true,
      grants: [{ id: "g:except-sim", max_amount: 2000000, effective_from: "2026-10-01", effective_to: null }],
    });
    vi.mocked(decideIssues).mockResolvedValue({ case_view: caseView(), job_id: null, duplicate_command: false });
    render(<ExceptionReview issue={issue} caseView={caseView()} onCase={() => {}} />);
    await waitFor(() => expect(screen.getByText(/1\.500\.000/)).toBeInTheDocument());
    expect(screen.getByText(/g:except-sim/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chấp nhận ngoại lệ" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Không chấp nhận" })).toBeEnabled();
    // Two-sided refs render; the boxed one shows the OCR region image.
    expect(screen.getByAltText(/Vùng OCR cần kiểm tra/)).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Lý do quyết định/), "Đủ căn cứ thay thế");
    await user.click(screen.getByRole("button", { name: "Chấp nhận ngoại lệ" }));
    await waitFor(() => expect(decideIssues).toHaveBeenCalled());
    const body = vi.mocked(decideIssues).mock.calls[0][1];
    expect(body.actions).toEqual(["EXCEPT_POLICY"]);
    expect(body.amount).toBe(1500000);
  });

  it("disables accept without covering grant but keeps refuse", async () => {
    vi.mocked(exceptionPreview).mockResolvedValue({
      issue_id: issue.id, rule_id: "expense:missing_required_evidence",
      expense_id: "expense:2", amount: 1500000, covered: false, grants: [],
    });
    vi.mocked(refuseException).mockResolvedValue({ case_view: caseView(), job_id: null, duplicate_command: false });
    render(<ExceptionReview issue={issue} caseView={caseView()} onCase={() => {}} />);
    await waitFor(() => expect(screen.getByText(/chưa có grant EXCEPT_POLICY/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Chấp nhận ngoại lệ" })).toBeDisabled();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Lý do quyết định/), "Chưa đủ căn cứ");
    await user.click(screen.getByRole("button", { name: "Không chấp nhận" }));
    await waitFor(() => expect(refuseException).toHaveBeenCalled());
  });
});

describe("OcrRegionView", () => {
  it("falls back to quote + original link without a bbox (never invents one)", () => {
    const ref = issue.refs![1];
    render(<OcrRegionView caseView={caseView()} reference={ref} onSourceSelected={() => {}} />);
    expect(screen.getByText(/Trị giá: 1500000/)).toBeInTheDocument();
    expect(screen.getByText(/Không có vùng bbox/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
