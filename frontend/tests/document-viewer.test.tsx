import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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
  it("renders document switcher with filename and format badge without raw commit hashes", async () => {
    render(<DocumentViewer caseView={MOCK_CASE} />);

    // Renders active document filename
    expect(screen.getByText("giay_quyet_toan.pdf")).toBeInTheDocument();

    // Does NOT render raw git commit hashes (e.g. abcdef)
    expect(screen.queryByText("abcdef")).not.toBeInTheDocument();

    // Renders external link button
    expect(screen.getByRole("link", { name: /Mở tab mới/ })).toBeInTheDocument();

    // Opens dropdown to view other documents
    await userEvent.setup().click(screen.getByRole("button", { name: /Chọn chứng từ/ }));
    expect(screen.getByText("hoa_don_vat.png")).toBeInTheDocument();
  });

  it("renders empty state when no sources or pending files exist", () => {
    render(<DocumentViewer caseView={{ ...MOCK_CASE, sources: [] }} />);
    expect(screen.getByText(/Chưa có chứng từ được tải lên/)).toBeInTheDocument();
    expect(screen.getByText(/Chưa chọn chứng từ để xem/)).toBeInTheDocument();
  });

  it("opens the source selected by the advance draft and lets the user switch documents", async () => {
    function Harness() {
      const [selectedSourceId, setSelectedSourceId] = useState("source:2");
      return (
        <DocumentViewer
          caseView={MOCK_CASE}
          selectedSourceId={selectedSourceId}
          onSourceSelected={setSelectedSourceId}
        />
      );
    }

    render(<Harness />);
    expect(screen.getByRole("img", { name: "hoa_don_vat.png" })).toBeInTheDocument();

    // Switches document via previous flipper button
    await userEvent.setup().click(screen.getByRole("button", { name: /Chứng từ trước/ }));
    expect(screen.getByTitle("giay_quyet_toan.pdf")).toBeInTheDocument();

    // Switches document via next flipper button
    await userEvent.setup().click(screen.getByRole("button", { name: /Chứng từ tiếp theo/ }));
    expect(screen.getByRole("img", { name: "hoa_don_vat.png" })).toBeInTheDocument();

    // Switches document via dropdown selection
    await userEvent.setup().click(screen.getByRole("button", { name: /Chọn chứng từ/ }));
    await userEvent.setup().click(screen.getByRole("button", { name: /giay_quyet_toan\.pdf/ }));
    expect(screen.getByTitle("giay_quyet_toan.pdf")).toBeInTheDocument();
  });

  it("renders zoom, rotation, and expand controls when viewing an image document", async () => {
    let toggled = false;
    render(
      <DocumentViewer
        caseView={MOCK_CASE}
        selectedSourceId="source:2"
        isExpanded={false}
        onToggleExpand={() => {
          toggled = true;
        }}
      />,
    );

    // Zoom controls are visible for images
    expect(screen.getByRole("button", { name: "Phóng to ảnh" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thu nhỏ ảnh" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xoay ảnh 90 độ" })).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();

    // Click zoom in
    await userEvent.setup().click(screen.getByRole("button", { name: "Phóng to ảnh" }));
    expect(screen.getByText("125%")).toBeInTheDocument();

    // Click expand toggle
    const expandBtn = screen.getByRole("button", { name: "Mở rộng khung xem" });
    expect(expandBtn).toBeInTheDocument();
    await userEvent.setup().click(expandBtn);
    expect(toggled).toBe(true);
  });
});
