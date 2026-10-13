import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { roleWorkspaces } from "../src/roles";

// UX01 (plan R6): each persona gets its own workspace; one form must not serve
// all three roles. The mapping is server-aligned (backend still enforces).

describe("role workspaces", () => {
  it("employee sees intake and questions, not money recording", () => {
    const panels = roleWorkspaces("employee");
    expect(panels).toContain("intake");
    expect(panels).toContain("questions");
    expect(panels).not.toContain("execution");
  });

  it("accountant sees approval, execution and controls", () => {
    const panels = roleWorkspaces("accountant");
    expect(panels).toContain("approval");
    expect(panels).toContain("execution");
    expect(panels).toContain("controls");
    expect(panels).not.toContain("intake");
  });

  it("approver sees approval, questions and controls", () => {
    const panels = roleWorkspaces("approver");
    expect(panels).toContain("approval");
    expect(panels).toContain("questions");
    expect(panels).toContain("controls");
    expect(panels).not.toContain("execution");
  });

  it("the three workspaces are distinct", () => {
    const employee = roleWorkspaces("employee").join(",");
    const accountant = roleWorkspaces("accountant").join(",");
    const approver = roleWorkspaces("approver").join(",");
    expect(new Set([employee, accountant, approver]).size).toBe(3);
  });
});
