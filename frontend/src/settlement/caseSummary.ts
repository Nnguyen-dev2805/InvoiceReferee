import type { CaseView, DemoRole, Report, RunView } from './types';

export type PrimaryTarget =
  | 'draft-editor'
  | 'issues'
  | 'run-check'
  | 'sources'
  | 'accountant-review'
  | 'advance-decision'
  | 'advance-receipt'
  | 'prepare-settlement'
  | 'settlement-intake'
  | 'settlement-decision'
  | 'settlement-receipt'
  | 'case-history';

export interface UiSummary {
  title: string;
  description: string;
  tone: 'neutral' | 'info' | 'warning' | 'error';
  missingFields: string[];
  primaryTarget: PrimaryTarget | null;
  // Who owns the next step and the label of the navigation CTA. Targets only
  // navigate/focus; they never POST. Financial POST stays behind its own guards.
  nextOwner: DemoRole | null;
  primaryLabel: string | null;
}

export interface SummaryContext {
  role: DemoRole;
  actorId: string;
}

const CLOSED_STAGES = new Set([
  'SETTLEMENT_CLOSED',
  'REJECTED_REQUEST_ENDED',
]);

function makeSummary(
  partial: Omit<UiSummary, 'missingFields' | 'nextOwner' | 'primaryLabel'>
    & Partial<Pick<UiSummary, 'missingFields' | 'nextOwner' | 'primaryLabel'>>,
): UiSummary {
  return {
    missingFields: [],
    nextOwner: null,
    primaryLabel: null,
    ...partial,
  };
}

// A run only speaks for the case when its basis still matches the case view.
// A superseded/older run must not drive the current headline.
function isRunCurrent(view: CaseView, run: RunView | null): boolean {
  return run !== null
    && run.case_id === view.id
    && run.input_revision === view.input_revision
    && run.control_epoch === view.control_epoch;
}

// A report is a snapshot of one run; treat it as current only when it is the
// case's current run. Historical reports must not create current-success.
function isReportCurrent(view: CaseView, report: Report | null): boolean {
  return report !== null && view.current_run_id !== null
    && report.run_id === view.current_run_id;
}

// Resolve the CTA for a state. With a context, only the owning role gets the
// navigation target; other roles see who owns it but no CTA. Without a context
// (legacy three-argument callers) keep the legacy target so existing screens
// keep working until they migrate.
function cta(
  owner: DemoRole,
  target: PrimaryTarget,
  label: string,
  context: SummaryContext | undefined,
  // Legacy (no-context) target. `undefined` keeps the role target; an explicit
  // `null` means the legacy callers expect no CTA for this state.
  legacyTarget?: PrimaryTarget | null,
): Pick<UiSummary, 'primaryTarget' | 'primaryLabel' | 'nextOwner'> {
  if (!context) {
    return {
      primaryTarget: legacyTarget === undefined ? target : legacyTarget,
      primaryLabel: null,
      nextOwner: null,
    };
  }
  if (context.role === owner) {
    return { primaryTarget: target, primaryLabel: label, nextOwner: owner };
  }
  return { primaryTarget: null, primaryLabel: null, nextOwner: owner };
}

export function summarizeCase(
  view: CaseView,
  run: RunView | null,
  report: Report | null,
  context?: SummaryContext,
): UiSummary {
  const runCurrent = isRunCurrent(view, run);
  const reportCurrent = isReportCurrent(view, report);

  // 1. Stop takes priority: no next step until resumed.
  if (view.stop_active) {
    return makeSummary({
      title: 'Hồ sơ đang tạm dừng xử lý',
      description: 'Hồ sơ đang ở trạng thái tạm dừng; cần bấm "Tiếp tục xử lý" để thực hiện các bước tiếp theo.',
      tone: 'warning',
      primaryTarget: null,
    });
  }

  // 2. A *current* run failure. An old failed run does not erase a receipt or
  // decision that already happened.
  if (runCurrent && run
    && (run.status === 'FAILED' || run.status === 'TIMED_OUT' || run.status === 'INTERRUPTED')) {
    return makeSummary({
      title: 'Chưa kiểm tra xong do lỗi xử lý',
      description: run.detail
        ? `Chi tiết: ${run.detail}`
        : 'Hệ thống gặp sự cố trong quá trình xử lý. Hãy thử lại khi được phép.',
      tone: 'error',
      primaryTarget: 'run-check',
    });
  }

  // 3. Current run in flight.
  if (runCurrent && run && run.status === 'QUEUED') {
    return makeSummary({
      title: 'Đang chờ xử lý',
      description: 'Hồ sơ đã được đưa vào hàng đợi kiểm tra.',
      tone: 'info',
      primaryTarget: null,
    });
  }
  if (runCurrent && run && run.status === 'RUNNING') {
    return makeSummary({
      title: 'Đang đọc và kiểm tra hồ sơ',
      description: 'Hệ thống đang tiến hành đọc tài liệu và kiểm tra các điều kiện chính sách.',
      tone: 'info',
      primaryTarget: null,
    });
  }

  // 4. Closed: current progress is history, never re-derived from a report.
  if (CLOSED_STAGES.has(view.stage)) {
    return makeSummary({
      title: 'Hồ sơ đã đóng',
      description: 'Quyết toán đã đóng; xem lịch sử và report lưu lại. Nguồn mới có ảnh hưởng sẽ mở hồ sơ điều chỉnh liên kết.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'case-history', 'Xem lịch sử & điều chỉnh', context, null),
    });
  }

  // 5. B7 linked settlement (the child case) — project from the typed workflow.
  const b7 = view.b7_workflow ?? null;
  const linked = view.linked_b7 ?? null;
  if (linked || b7) {
    const b7Summary = projectB7(report, reportCurrent, b7, linked, context);
    if (b7Summary) return b7Summary;
  }

  // 6. B3 advance intake/approval/receipt — project from workflow + stage.
  if (view.submission.job === 'B3' || report?.b3) {
    const b3Summary = projectB3(view, report, reportCurrent, context);
    if (b3Summary) return b3Summary;
  }

  // 7. Current report blockers/success (B7 non-linked or fallback).
  if (reportCurrent && report) {
    if (report.issues.length > 0) {
      return makeSummary({
        title: 'Hồ sơ cần bổ sung hoặc làm rõ',
        description: `Còn ${report.issues.length} vấn đề cần làm rõ.`,
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }

    if (report.checks.some((c) => c.status === 'FAIL' || c.status === 'UNRESOLVED')) {
      return makeSummary({
        title: 'Kết quả còn điểm cần kiểm tra',
        description: 'Một số nội dung kiểm tra chưa đạt hoặc chưa đủ căn cứ xác nhận.',
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }

    return makeSummary({
      title: 'Đã hoàn tất kiểm tra quy tắc',
      description: 'Các chứng từ và phép tính phù hợp với quy định.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'accountant-review', 'Rà soát và trình', context, null),
    });
  }

  // 8. Stage fallback when no current report/workflow is available.
  return stageFallback(view, context);
}

function projectB7(
  report: Report | null,
  reportCurrent: boolean,
  b7: CaseView['b7_workflow'] | null,
  linked: CaseView['linked_b7'] | null,
  context?: SummaryContext,
): UiSummary | null {
  const decision = b7?.decision ?? null;
  const fulfillment = b7?.fulfillment ?? null;

  // Blocker: stale context / basis not current — accountant must refresh.
  if (linked && linked.context_current === false) {
    return makeSummary({
      title: 'Dữ liệu công ty đã cũ',
      description: 'Ngữ cảnh công ty không còn khớp với hồ sơ tạm ứng hiện hành; kế toán cần làm mới ngữ cảnh trước khi chạy lại.',
      tone: 'warning',
      ...cta('ACCOUNTANT', 'settlement-intake', 'Làm mới ngữ cảnh công ty', context),
    });
  }

  if (decision && decision.outcome === 'APPROVE') {
    if (fulfillment) {
      if (fulfillment.status === 'FULFILLED' || fulfillment.status === 'BALANCED') {
        return makeSummary({
          title: 'Quyết toán đã đủ điều kiện đóng',
          description: fulfillment.status === 'BALANCED'
            ? 'Quyết toán cân bằng (0 đồng); đủ gate để đóng mà không tạo sự kiện tiền 0.'
            : 'Đã đối chiếu đủ nghĩa vụ; kế toán kiểm tra lại và đóng hồ sơ.',
          tone: 'info',
          ...cta('ACCOUNTANT', 'settlement-receipt', 'Đóng hồ sơ quyết toán', context),
        });
      }
      if (fulfillment.status === 'BLOCKED' || (fulfillment.incidents?.length ?? 0) > 0) {
        return makeSummary({
          title: 'Cần xử lý vướng mắc chi/thu',
          description: 'Còn sự kiện tiền chưa khớp (sai bên nhận/bên trả, chưa phân bổ, quá hạn); kế toán xử lý trước khi đóng.',
          tone: 'warning',
          ...cta('ACCOUNTANT', 'settlement-receipt', 'Xử lý đối chiếu chi/thu', context),
        });
      }
      return makeSummary({
        title: 'Quyết toán đã duyệt — chờ đối chiếu chi/thu',
        description: 'Kế toán ghi nhận sự kiện tiền thực tế theo nguồn; receipt đúng làm giảm số còn lại nhưng không hủy quyết định.',
        tone: 'info',
        ...cta('ACCOUNTANT', 'settlement-receipt', 'Đối chiếu chi/thu', context),
      });
    }
    return makeSummary({
      title: 'Quyết toán đã duyệt',
      description: 'Quyết toán đã được duyệt; kế toán ghi nhận chi/thu thực tế.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'settlement-receipt', 'Đối chiếu chi/thu', context),
    });
  }

  if (b7?.status === 'PENDING') {
    return makeSummary({
      title: 'Chờ người có quyền quyết định quyết toán',
      description: 'Kế toán đã trình kết quả quyết toán; người có quyền xem và quyết định.',
      tone: 'info',
      ...cta('APPROVER', 'settlement-decision', 'Xem và quyết định', context),
    });
  }

  if (b7?.status === 'REFUSED') {
    return makeSummary({
      title: 'Quyết toán bị từ chối',
      description: 'Quyết toán bị từ chối; nghĩa vụ tiền vẫn được giữ, không tự đóng.',
      tone: 'warning',
      ...cta('ACCOUNTANT', 'settlement-receipt', 'Xem nghĩa vụ còn lại', context),
    });
  }

  if (b7?.status === 'RETURNED' || b7?.status === 'NEEDS_RECHECK') {
    return makeSummary({
      title: 'Cần kiểm lại quyết toán',
      description: 'Basis hoặc dữ liệu đã thay đổi; kế toán cần kiểm lại và trình lại.',
      tone: 'warning',
      ...cta('ACCOUNTANT', 'settlement-intake', 'Kiểm lại & trình', context),
    });
  }

  // Report-based fallback for the child before it has been presented.
  if (reportCurrent && report) {
    if (report.issues.length > 0) {
      return makeSummary({
        title: 'Hồ sơ quyết toán cần bổ sung hoặc làm rõ',
        description: `Còn ${report.issues.length} vấn đề cần làm rõ.`,
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }
    if (report.checks.some((c) => c.status === 'FAIL' || c.status === 'UNRESOLVED')) {
      return makeSummary({
        title: 'Kết quả còn điểm cần kiểm tra',
        description: 'Một số nội dung kiểm tra chưa đạt hoặc chưa đủ căn cứ xác nhận.',
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }
    return makeSummary({
      title: 'Đủ thông tin để kế toán rà soát quyết toán',
      description: 'Hồ sơ quyết toán đủ thông tin để kế toán rà soát; chưa phê duyệt.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'accountant-review', 'Rà soát và trình', context, null),
    });
  }

  return makeSummary({
    title: 'Hồ sơ quyết toán chưa có kết quả',
    description: 'Chưa có report hiện hành; kế toán cung cấp ngữ cảnh công ty rồi chạy kiểm tra.',
    tone: 'neutral',
    ...cta('ACCOUNTANT', 'settlement-intake', 'Chuẩn bị & chạy kiểm tra', context),
  });
}

function projectB3(
  view: CaseView,
  report: Report | null,
  reportCurrent: boolean,
  context?: SummaryContext,
): UiSummary | null {
  const workflow = view.b3_workflow ?? null;
  const decision = workflow?.decision ?? null;
  const funding = workflow?.funding ?? null;

  // Approved advance: distinguish "not yet received" from "received, awaiting
  // settlement". This is what the old report-readiness path got wrong.
  if (decision && decision.outcome === 'APPROVE') {
    const received = funding?.status === 'FULFILLED'
      || view.stage === 'AWAITING_WORK_SETTLEMENT';
    if (received) {
      return makeSummary({
        title: 'Đã nhận ứng — chờ nộp quyết toán',
        description: 'Nhân viên đã nhận đủ tiền ứng; chuẩn bị hồ sơ quyết toán chi phí thực tế.',
        tone: 'info',
        ...cta('EMPLOYEE', 'prepare-settlement', 'Chuẩn bị hồ sơ quyết toán', context),
      });
    }
    return makeSummary({
      title: 'Ứng đã duyệt — chờ ghi nhận nhận đủ',
      description: 'Ứng đã được duyệt; kế toán ghi nhận tiền thực nhận. Phê duyệt không phải đã nhận tiền.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'advance-receipt', 'Ghi nhận tiền ứng thực tế', context),
    });
  }

  // Receipt recorded and the stage advanced past AWAITING_MONEY even when the
  // workflow projection is absent (older data): still show the correct state.
  if (view.stage === 'AWAITING_WORK_SETTLEMENT') {
    return makeSummary({
      title: 'Đã nhận ứng — chờ nộp quyết toán',
      description: 'Nhân viên đã nhận đủ tiền ứng; chuẩn bị hồ sơ quyết toán chi phí thực tế.',
      tone: 'info',
      ...cta('EMPLOYEE', 'prepare-settlement', 'Chuẩn bị hồ sơ quyết toán', context),
    });
  }

  if (workflow?.status === 'PENDING') {
    return makeSummary({
      title: 'Chờ người có quyền quyết định đề nghị ứng',
      description: 'Kế toán đã trình đề nghị tạm ứng; người có quyền xem và quyết định.',
      tone: 'info',
      ...cta('APPROVER', 'advance-decision', 'Xem và quyết định', context),
    });
  }

  if (view.stage === 'AWAITING_MONEY') {
    return makeSummary({
      title: 'Chờ ghi nhận tiền ứng thực nhận',
      description: 'Ứng đã được duyệt; kế toán ghi nhận số tiền nhân viên thực nhận.',
      tone: 'info',
      ...cta('ACCOUNTANT', 'advance-receipt', 'Ghi nhận tiền ứng thực tế', context),
    });
  }

  if (view.stage === 'ADVANCE_REQUEST_REFUSED' || view.stage === 'SETTLEMENT_REQUEST_REFUSED') {
    return makeSummary({
      title: 'Đề nghị tạm ứng bị từ chối',
      description: 'Đề nghị bị từ chối; nghĩa vụ tiền (nếu có) vẫn được xử lý, không tự đóng hồ sơ.',
      tone: 'warning',
      ...cta('ACCOUNTANT', 'case-history', 'Xem lịch sử', context),
    });
  }

  // Draft / confirmation states (report not yet confirmed or not current).
  const isConfirmed = Boolean(view.submission.form?.confirmed);
  const form = ((report?.b3?.intake ?? view.submission.form) || {}) as Record<string, unknown>;

  if (!isConfirmed) {
    const missing: string[] = [];
    if (!form.destination) missing.push('Nơi đến');
    if (!form.purpose) missing.push('Mục đích công tác');
    if (form.request_amount_vnd === null || form.request_amount_vnd === undefined) {
      missing.push('Số tiền đề nghị tạm ứng');
    }
    if (!form.settlement_due) missing.push('Hạn thanh toán tạm ứng');

    // Distinguish "extraction did not find the field" from "the employee
    // omitted it": a null trip field means the document did not yield it,
    // not that the submitter failed to declare it.
    const tripNotExtracted = !form.destination && !form.purpose;
    const nonTripMissing = missing.filter(
      (name) => name !== 'Nơi đến' && name !== 'Mục đích công tác',
    );
    let description: string;
    if (tripNotExtracted) {
      description = nonTripMissing.length > 0
        ? `Chưa trích được Nơi đến và Mục đích công tác từ tài liệu. Cần bổ sung: ${nonTripMissing.join(', ')}.`
        : 'Chưa trích được Nơi đến và Mục đích công tác từ tài liệu. Vui lòng kiểm tra và bổ sung trước khi gửi.';
    } else if (missing.length > 0) {
      description = `AI đã đọc tài liệu. Còn thiếu: ${missing.join(', ')}.`;
    } else {
      description = 'Kiểm tra lại toàn bộ thông tin đề nghị trước khi gửi duyệt.';
    }

    return makeSummary({
      title: 'Kiểm tra bản nháp trước khi gửi',
      description,
      tone: missing.length > 0 ? 'warning' : 'info',
      missingFields: missing,
      ...cta('EMPLOYEE', 'draft-editor', 'Kiểm tra bản nháp', context, 'draft-editor'),
    });
  }

  if (reportCurrent && report) {
    const unresolvedChecks = report.checks.filter(
      (c) => c.status === 'FAIL' || c.status === 'UNRESOLVED',
    );

    if (report.issues.length > 0) {
      return makeSummary({
        title: 'Hồ sơ cần bổ sung hoặc làm rõ',
        description: `Còn ${report.issues.length} vấn đề cần làm rõ trước khi tiếp tục.`,
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }

    if (unresolvedChecks.length > 0) {
      return makeSummary({
        title: 'Kết quả còn điểm cần kiểm tra',
        description: 'Một số điều kiện kiểm tra chưa đủ căn cứ xác nhận từ tài liệu đính kèm.',
        tone: 'warning',
        ...cta('ACCOUNTANT', 'issues', 'Xem việc cần làm rõ', context, 'issues'),
      });
    }

    if (report.b3?.readiness === 'READY_FOR_ACCOUNTANT_REVIEW') {
      return makeSummary({
        title: 'Đủ thông tin để kế toán rà soát',
        description: 'Hồ sơ đủ thông tin để kế toán rà soát; chưa phê duyệt và chưa chi ứng.',
        tone: 'info',
        ...cta('ACCOUNTANT', 'accountant-review', 'Rà soát và trình', context, null),
      });
    }

    if (report.b3?.readiness === 'NEEDS_INFORMATION') {
      return makeSummary({
        title: 'Hồ sơ cần bổ sung hoặc làm rõ',
        description: 'Hồ sơ cần bổ sung hoặc làm rõ thông tin.',
        tone: 'warning',
        ...cta('EMPLOYEE', 'draft-editor', 'Bổ sung thông tin', context, 'issues'),
      });
    }

    if (report.b3?.readiness === 'NEEDS_AUTHORIZED_REVIEW') {
      return makeSummary({
        title: 'Cần người có thẩm quyền xem xét',
        description: 'Đề nghị tạm ứng cần người có thẩm quyền xem xét phê duyệt.',
        tone: 'info',
        ...cta('APPROVER', 'advance-decision', 'Xem và quyết định', context, null),
      });
    }

    return makeSummary({
      title: 'Đã có kết quả kiểm tra',
      description: report.next_step || 'Xem chi tiết kết quả kiểm tra bên dưới.',
      tone: 'info',
      primaryTarget: null,
    });
  }

  return null;
}

function stageFallback(view: CaseView, context?: SummaryContext): UiSummary {
  switch (view.stage) {
    case 'AWAITING_DECISION':
      return makeSummary({
        title: 'Chờ người có quyền quyết định',
        description: 'Kết quả đã được trình; người có quyền xem và quyết định.',
        tone: 'info',
        ...cta('APPROVER', 'settlement-decision', 'Xem và quyết định', context),
      });
    case 'AWAITING_MONEY':
      return makeSummary({
        title: 'Chờ ghi nhận tiền thực tế',
        description: 'Đã có quyết định; kế toán ghi nhận chi/thu thực tế.',
        tone: 'info',
        ...cta('ACCOUNTANT', 'settlement-receipt', 'Ghi nhận chi/thu', context),
      });
    case 'AWAITING_WORK_SETTLEMENT':
      return makeSummary({
        title: 'Đã nhận ứng — chờ nộp quyết toán',
        description: 'Chuẩn bị hồ sơ quyết toán chi phí thực tế.',
        tone: 'info',
        ...cta('EMPLOYEE', 'prepare-settlement', 'Chuẩn bị hồ sơ quyết toán', context),
      });
    case 'ACCOUNTING_REVIEW':
      return makeSummary({
        title: 'Kế toán rà soát hồ sơ',
        description: 'Kế toán rà soát kết quả và trình người có quyền.',
        tone: 'info',
        ...cta('ACCOUNTANT', 'accountant-review', 'Rà soát và trình', context),
      });
    default:
      break;
  }

  if (context) {
    return makeSummary({
      title: 'Chưa kiểm tra hồ sơ',
      description: 'Hãy hoàn tất thông tin hoặc tải tài liệu rồi bấm kiểm tra.',
      tone: 'neutral',
      primaryTarget: 'run-check',
    });
  }

  return makeSummary({
    title: 'Chưa kiểm tra hồ sơ',
    description: 'Hãy hoàn tất thông tin hoặc tải tài liệu rồi bấm kiểm tra.',
    tone: 'neutral',
    primaryTarget: 'run-check',
  });
}
