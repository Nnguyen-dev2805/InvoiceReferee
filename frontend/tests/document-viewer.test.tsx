import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DocumentViewer } from "../src/features/document_viewer";
import type { CaseView } from "../src/types";

const MOCK_CASE: CaseView = {
  id: "case:demo",
  version: 1,
  state: "EVIDENCE_READY",
  summary: "Công tác Hà Nội · 05/10/2026 · Nguyễn Văn A",
  sources: [
    {
      id: "source:1",
      digest: "abcdef0123456789",
      tenant: "tenant:demo",
      media: "PDF",
      storage_key: "tenant:demo/case:demo/source:1",
      filename: "giay_quyet_toan.pdf",
    },
    {
      id: "source:2",
      digest: "9876543210fedcba",
      tenant: "tenant:demo",
      media: "IMAGE",
      storage_key: "tenant:demo/case:demo/source:2",
      filename: "hoa_don_vat.png",
    },
  ],
  issues: [],
  problems: [],
  conclusion: null,
  instructions: [],
  actual_money: {},
  audit: [],
  payment_basis: [],
};

describe("DocumentViewer", () => {
  it("renders tabs with filename and format badge without raw commit hashes", () => {
    render(<DocumentViewer caseView={MOCK_CASE} />);

    // Renders the filenames
    expect(screen.getByText("giay_quyet_toan.pdf")).toBeInTheDocument();
    expect(screen.getByText("hoa_don_vat.png")).toBeInTheDocument();

    // Does NOT render raw git commit hashes (e.g. abcdef)
    expect(screen.queryByText("abcdef")).not.toBeInTheDocument();

    // Renders external link button
    expect(screen.getByRole("link", { name: /Mở tab mới/ })).toBeInTheDocument();
  });

  it("renders empty state when no sources or pending files exist", () => {
    render(<DocumentViewer caseView={{ ...MOCK_CASE, sources: [] }} />);
    expect(screen.getByText(/Chưa có chứng từ được tải lên/)).toBeInTheDocument();
    expect(screen.getByText(/Chưa chọn chứng từ để xem/)).toBeInTheDocument();
  });
});
