import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as api from "../src/api";
import { Verify } from "../src/features/verify";

const SAMPLE_PASS_REPORT: api.VerifyReportView = {
  suite: "core",
  mode: "RECORDED_REPLAY",
  release: true,
  planned: 4,
  attempted: 4,
  completed: 4,
  passed: 4,
  union_dangerous_miss: 0,
  technical_errors: 0,
  elapsed_ms: 1250,
  run_id: "run-mock-12345",
  started_at: "2026-10-16T12:00:00Z",
  completed_at: "2026-10-16T12:00:01Z",
  versions: {
    code: "2a889d5f6f59",
    config: "default-v1",
    dataset: "locked-v1",
    recording: "kimi-k3-v1",
  },
  rows: [
    {
      root_id: "tc01",
      passed: true,
      actual_route: "ROUTINE",
      expected_route: "ROUTINE",
      actual_amounts: { COLLECT: 760000 },
      expected_amounts: { COLLECT: 760000 },
      failure_reasons: [],
      elapsed_ms: 310,
      question_required: false,
      question_present: false,
      actual_owner: null,
      expected_owner: null,
    },
    {
      root_id: "tc02",
      passed: true,
      actual_route: "ROUTINE",
      expected_route: "ROUTINE",
      actual_amounts: { PAY: 400000 },
      expected_amounts: { PAY: 400000 },
      failure_reasons: [],
      elapsed_ms: 290,
      question_required: false,
      question_present: false,
      actual_owner: null,
      expected_owner: null,
    },
    {
      root_id: "vfy-bal-01",
      passed: true,
      actual_route: "ROUTINE",
      expected_route: "ROUTINE",
      actual_amounts: {},
      expected_amounts: {},
      failure_reasons: [],
      elapsed_ms: 320,
      question_required: false,
      question_present: false,
      actual_owner: null,
      expected_owner: null,
    },
    {
      root_id: "tc06",
      passed: true,
      actual_route: "FACT",
      expected_route: "FACT",
      actual_amounts: {},
      expected_amounts: {},
      failure_reasons: [],
      elapsed_ms: 330,
      question_required: true,
      question_present: true,
      actual_owner: "employee",
      expected_owner: "employee",
    },
  ],
};

const SAMPLE_FAIL_REPORT: api.VerifyReportView = {
  ...SAMPLE_PASS_REPORT,
  release: false,
  passed: 3,
  union_dangerous_miss: 1,
  rows: [
    ...SAMPLE_PASS_REPORT.rows.slice(0, 3),
    {
      root_id: "tc06",
      passed: false,
      actual_route: "ROUTINE",
      expected_route: "FACT",
      actual_amounts: { COLLECT: 60000 },
      expected_amounts: {},
      failure_reasons: ["route_mismatch: actual=ROUTINE expected=FACT"],
      elapsed_ms: 350,
      question_required: true,
      question_present: false,
      actual_owner: null,
      expected_owner: "employee",
    },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Verify Component", () => {
  it("renders initial state with 'Chưa chạy' badge and controls when no prior run exists", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);

    render(<Verify />);

    expect(screen.getByRole("heading", { name: "Kiểm chuẩn Benchmark" })).toBeInTheDocument();
    expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Chưa chạy");
    expect(screen.getByTestId("run-core-btn")).toHaveTextContent("Chạy Core4 (4 ca)");
    expect(screen.getByTestId("run-escalation-btn")).toHaveTextContent("Chạy Escalation5 (5 ca)");

    const replayRadio = screen.getByLabelText(/Replay đã ghi sẵn/);
    const liveRadio = screen.getByLabelText(/LIVE/);
    expect(replayRadio).toBeChecked();
    expect(liveRadio).not.toBeChecked();

    // Verify forbidden buzzwords are NOT present
    expect(screen.queryByText(/Sẵn sàng sản xuất/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Production Ready/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Thực thi xuất sắc/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Toàn bộ hệ thống hoàn hảo/i)).not.toBeInTheDocument();
  });

  it("loads and displays existing report on mount", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(SAMPLE_PASS_REPORT);

    render(<Verify />);

    await waitFor(() => {
      expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Đạt bộ kiểm thử này");
    });

    expect(screen.getByTestId("verify-report")).toBeInTheDocument();
    expect(screen.getByText("tc01")).toBeInTheDocument();
    expect(screen.getByText("tc02")).toBeInTheDocument();
    expect(screen.getByText("vfy-bal-01")).toBeInTheDocument();
    expect(screen.getByText("tc06")).toBeInTheDocument();
    expect(screen.getAllByText("ĐẠT")).toHaveLength(4);
  });

  it("runs Core4 in RECORDED_REPLAY mode", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);
    const runSpy = vi.spyOn(api, "runVerify").mockResolvedValue(SAMPLE_PASS_REPORT);

    render(<Verify />);
    const user = userEvent.setup();

    await user.click(screen.getByTestId("run-core-btn"));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalledWith("core", "RECORDED_REPLAY");
      expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Đạt bộ kiểm thử này");
    });
  });

  it("runs Escalation5 in RECORDED_REPLAY mode", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);
    const runSpy = vi.spyOn(api, "runVerify").mockResolvedValue(SAMPLE_PASS_REPORT);

    render(<Verify />);
    const user = userEvent.setup();

    await user.click(screen.getByTestId("run-escalation-btn"));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalledWith("escalation", "RECORDED_REPLAY");
    });
  });

  it("shows live warning dialog when LIVE mode is selected, cancels on 'Hủy'", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);
    const runSpy = vi.spyOn(api, "runVerify");

    render(<Verify />);
    const user = userEvent.setup();

    await user.click(screen.getByLabelText(/LIVE/));
    await user.click(screen.getByTestId("run-core-btn"));

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(/Cảnh báo sử dụng Quota LIVE/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hủy" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(runSpy).not.toHaveBeenCalled();
  });

  it("confirms LIVE run when warning is accepted", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);
    const runSpy = vi.spyOn(api, "runVerify").mockResolvedValue(SAMPLE_PASS_REPORT);

    render(<Verify />);
    const user = userEvent.setup();

    await user.click(screen.getByLabelText(/LIVE/));
    await user.click(screen.getByTestId("run-escalation-btn"));

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Xác nhận chạy LIVE" }));

    await waitFor(() => {
      expect(runSpy).toHaveBeenCalledWith("escalation", "LIVE");
    });
  });

  it("displays 'Không đạt' and failure reasons when release gate fails", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(SAMPLE_FAIL_REPORT);

    render(<Verify />);

    await waitFor(() => {
      expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Không đạt");
    });

    expect(screen.getByText("KHÔNG ĐẠT")).toBeInTheDocument();
    expect(screen.getByText(/route_mismatch: actual=ROUTINE expected=FACT/)).toBeInTheDocument();
  });

  it("displays 'Lỗi thực thi' when runVerify throws an error", async () => {
    vi.spyOn(api, "getLastVerify").mockResolvedValue(null);
    vi.spyOn(api, "runVerify").mockRejectedValue(new Error("Mất kết nối máy chủ"));

    render(<Verify />);
    const user = userEvent.setup();

    await user.click(screen.getByTestId("run-core-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Lỗi thực thi");
      expect(screen.getByRole("alert")).toHaveTextContent("Mất kết nối máy chủ");
    });
  });
});

it("does not show success when real replay recordings are missing", async()=>{
 vi.spyOn(api,"getLastVerify").mockResolvedValue({...SAMPLE_FAIL_REPORT,status:"NEEDS_RECORDING",passed:0,completed:0});
 render(<Verify/>);
 await waitFor(()=>expect(screen.getByTestId("verify-status-badge")).toHaveTextContent("Chưa có recording thật phù hợp"));
 expect(screen.queryByText("Đạt bộ kiểm thử này")).toBeNull();
});
