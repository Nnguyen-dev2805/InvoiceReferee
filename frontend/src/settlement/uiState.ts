import type { CaseView, Report, RunView } from './types';

export interface UiSummary {
  title: string;
  description: string;
  tone: 'neutral' | 'info' | 'warning' | 'error';
  missingFields: string[];
  primaryTarget: 'draft-editor' | 'issues' | 'run-check' | null;
}

export function summarizeCase(
  view: CaseView,
  run: RunView | null,
  report: Report | null,
): UiSummary {
  // 1. Prioritize Stop status
  if (view.stop_active) {
    return {
      title: 'Hồ sơ đang tạm dừng xử lý',
      description: 'Hồ sơ đang ở trạng thái tạm dừng; cần bấm "Tiếp tục xử lý" để thực hiện các bước tiếp theo.',
      tone: 'warning',
      missingFields: [],
      primaryTarget: null,
    };
  }

  // 2. Run failures
  if (run && (run.status === 'FAILED' || run.status === 'TIMED_OUT' || run.status === 'INTERRUPTED')) {
    return {
      title: 'Chưa kiểm tra xong do lỗi xử lý',
      description: run.detail ? `Chi tiết: ${run.detail}` : 'Hệ thống gặp sự cố trong quá trình xử lý. Hãy thử lại khi được phép.',
      tone: 'error',
      missingFields: [],
      primaryTarget: 'run-check',
    };
  }

  // 3. Queued or Running
  if (run && run.status === 'QUEUED') {
    return {
      title: 'Đang chờ xử lý',
      description: 'Hồ sơ đã được đưa vào hàng đợi kiểm tra.',
      tone: 'info',
      missingFields: [],
      primaryTarget: null,
    };
  }

  if (run && run.status === 'RUNNING') {
    return {
      title: 'Đang đọc và kiểm tra hồ sơ',
      description: 'Hệ thống đang tiến hành đọc tài liệu và kiểm tra các điều kiện chính sách.',
      tone: 'info',
      missingFields: [],
      primaryTarget: null,
    };
  }

  // 4. B3 Verbal Intake Workflow
  if (view.submission.job === 'B3' || report?.b3) {
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
      const tripNotExtracted =
        !form.destination && !form.purpose;
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

      return {
        title: 'Kiểm tra bản nháp trước khi gửi',
        description,
        tone: missing.length > 0 ? 'warning' : 'info',
        missingFields: missing,
        primaryTarget: 'draft-editor',
      };
    }

    if (report) {
      const unresolvedChecks = report.checks.filter(
        (c) => c.status === 'FAIL' || c.status === 'UNRESOLVED',
      );

      if (report.issues.length > 0) {
        return {
          title: 'Hồ sơ cần bổ sung hoặc làm rõ',
          description: `Còn ${report.issues.length} vấn đề cần làm rõ trước khi tiếp tục.`,
          tone: 'warning',
          missingFields: [],
          primaryTarget: 'issues',
        };
      }

      if (unresolvedChecks.length > 0) {
        return {
          title: 'Kết quả còn điểm cần kiểm tra',
          description: 'Một số điều kiện kiểm tra chưa đủ căn cứ xác nhận từ tài liệu đính kèm.',
          tone: 'warning',
          missingFields: [],
          primaryTarget: 'issues',
        };
      }

      if (report.b3?.readiness === 'READY_FOR_ACCOUNTANT_REVIEW') {
        return {
          title: 'Đủ thông tin để kế toán rà soát',
          description: 'Hồ sơ đủ thông tin để kế toán rà soát; chưa phê duyệt và chưa chi ứng.',
          tone: 'info',
          missingFields: [],
          primaryTarget: null,
        };
      }

      if (report.b3?.readiness === 'NEEDS_INFORMATION') {
        return {
          title: 'Hồ sơ cần bổ sung hoặc làm rõ',
          description: 'Hồ sơ cần bổ sung hoặc làm rõ thông tin.',
          tone: 'warning',
          missingFields: [],
          primaryTarget: 'issues',
        };
      }

      if (report.b3?.readiness === 'NEEDS_AUTHORIZED_REVIEW') {
        return {
          title: 'Cần người có thẩm quyền xem xét',
          description: 'Đề nghị tạm ứng cần người có thẩm quyền xem xét phê duyệt.',
          tone: 'info',
          missingFields: [],
          primaryTarget: null,
        };
      }

      return {
        title: 'Đã có kết quả kiểm tra',
        description: report.next_step || 'Xem chi tiết kết quả kiểm tra bên dưới.',
        tone: 'info',
        missingFields: [],
        primaryTarget: null,
      };
    }
  }

  // 5. B7 Workflow
  if (report) {
    if (report.issues.length > 0) {
      return {
        title: 'Hồ sơ cần bổ sung hoặc làm rõ',
        description: `Còn ${report.issues.length} vấn đề cần làm rõ.`,
        tone: 'warning',
        missingFields: [],
        primaryTarget: 'issues',
      };
    }

    if (report.checks.some((c) => c.status === 'FAIL' || c.status === 'UNRESOLVED')) {
      return {
        title: 'Kết quả còn điểm cần kiểm tra',
        description: 'Một số nội dung kiểm tra chưa đạt hoặc chưa đủ căn cứ xác nhận.',
        tone: 'warning',
        missingFields: [],
        primaryTarget: 'issues',
      };
    }

    return {
      title: 'Đã hoàn tất kiểm tra quy tắc',
      description: 'Các chứng từ và phép tính phù hợp với quy định.',
      tone: 'info',
      missingFields: [],
      primaryTarget: null,
    };
  }

  // 6. Default / No run yet
  return {
    title: 'Chưa kiểm tra hồ sơ',
    description: 'Hãy hoàn tất thông tin hoặc tải tài liệu rồi bấm kiểm tra.',
    tone: 'neutral',
    missingFields: [],
    primaryTarget: 'run-check',
  };
}
