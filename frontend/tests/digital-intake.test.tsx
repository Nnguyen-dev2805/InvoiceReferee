import { describe, expect, it } from "vitest";

import { draftValidationError, toDigitalDeclarationInput } from "../src/features/digital_intake";

function line(over: Record<string, unknown> = {}) {
  return {
    clientId: "L01",
    description: "Nhân công sửa chữa",
    category: "",
    expense_date: "2026-10-09",
    amount: "1500000",
    evidence_status: "ALTERNATIVE" as const,
    alternative_type: "PAYMENT_PROOF",
    exception_reason: "Nhà cung cấp không xuất hóa đơn",
    note: "",
    files: [],
    attachedIds: ["source:acc", "source:trf"],
    ...over,
  };
}

describe("digital draft validation (client pre-check; server re-validates)", () => {
  it("accepts a complete self-expense form", () => {
    expect(
      draftValidationError("EMPLOYEE_REIMBURSEMENT", "Sửa máy in", "Tự chi", [line()]),
    ).toBeNull();
  });

  it("requires a reason for alternative lines (never derived from note)", () => {
    expect(
      draftValidationError("EMPLOYEE_REIMBURSEMENT", "Sửa máy in", "Tự chi", [
        line({ exception_reason: "", note: "Biên bản nghiệm thu và chuyển khoản" }),
      ]),
    ).toMatch(/lý do thiếu/);
  });

  it("requires the no-advance reason for self-expense", () => {
    expect(
      draftValidationError("EMPLOYEE_REIMBURSEMENT", "Sửa máy in", "", [line()]),
    ).toMatch(/không nhận tạm ứng/);
  });

  it("maps stable item ids and file source ids (never bare filenames)", () => {
    const input = toDigitalDeclarationInput("Sửa máy in", "EMPLOYEE_REIMBURSEMENT", "Tự chi", [
      line(),
      line({ clientId: "L02", description: "Linh kiện", amount: "2700000", evidence_status: "ORIGINAL", exception_reason: "", attachedIds: ["source:inv"] }),
    ]);
    expect(input.digital_lines.map((l) => l.item_id)).toEqual(["L01", "L02"]);
    expect(input.digital_lines[0].source_ids).toEqual(["source:acc", "source:trf"]);
    expect(input.no_advance_asserted).toBe(true);
  });
});
