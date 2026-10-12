import type { CaseRecord, DemoMode, RunRecord } from './types';
import { MODE_LABEL, formatVnd } from './format';

interface KpiSummaryProps {
  cases: CaseRecord[];
  role: DemoMode;
  runsByCase: Record<string, RunRecord>;
}

export function KpiSummary({ cases, role, runsByCase }: KpiSummaryProps) {
  // 1. Pending tasks for current role
  const pendingForRole = cases.filter((c) => c.open_owner_modes.includes(role)).length;

  // 2. Pending approval amount (VND)
  const pendingApprovalCases = cases.filter(
    (c) => c.workflow_state === 'WAITING_APPROVAL' || c.open_owner_modes.includes('APPROVER'),
  );
  const totalPendingAmountVnd = pendingApprovalCases.reduce((sum, c) => {
    return sum + (c.claim.requested_amount_vnd ?? 0);
  }, 0);

  // 3. Cases requiring human clarification or outside policy
  const issuesCasesCount = cases.filter(
    (c) => c.workflow_state === 'WAITING_INPUT' || c.open_owner_modes.length > 0,
  ).length;

  // 4. Routine auto completion rate
  let completedCount = 0;
  let routineAutoCount = 0;
  Object.values(runsByCase).forEach((run) => {
    const basis = run.result?.decision?.completion_basis;
    if (run.status === 'SUCCEEDED' && basis) {
      completedCount++;
      if (basis === 'ROUTINE_AUTO') {
        routineAutoCount++;
      }
    }
  });

  const autoRateText =
    completedCount > 0 ? `${Math.round((routineAutoCount / completedCount) * 100)}%` : '—';

  return (
    <section className="kpi-summary" aria-label="Chỉ số vận hành">
      <div className="kpi-card kpi-card-primary">
        <span className="kpi-label">Hồ sơ chờ ({MODE_LABEL[role]})</span>
        <span className="kpi-value">{pendingForRole}</span>
        <span className="kpi-subtext">Cần bạn xử lý ngay</span>
      </div>

      <div className="kpi-card kpi-card-success">
        <span className="kpi-label">Tổng tiền chờ xuất ngân</span>
        <span className="kpi-value">{formatVnd(totalPendingAmountVnd)}</span>
        <span className="kpi-subtext">{pendingApprovalCases.length} hồ sơ đủ điều kiện</span>
      </div>

      <div className="kpi-card kpi-card-warning">
        <span className="kpi-label">Cần làm rõ / Bất thường</span>
        <span className="kpi-value">{issuesCasesCount}</span>
        <span className="kpi-subtext">Hồ sơ mở câu hỏi</span>
      </div>

      <div className="kpi-card kpi-card-neutral">
        <span className="kpi-label">Tự động thường quy</span>
        <span className="kpi-value">{autoRateText}</span>
        <span className="kpi-subtext">
          {routineAutoCount}/{completedCount} lượt tự động
        </span>
      </div>
    </section>
  );
}
