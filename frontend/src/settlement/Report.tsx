// B7/B3 report panel (W02): components, expense rows with openable refs,
// checks, issues with owner, and an explicit fake/replay mode label.
// B3 v1 (b3-intake-v1) hiển thị section proposal thay bảng S — S quyết toán
// không phải kết quả chính của bước đề nghị ứng (Product P2a).
import type { B3Proposal, B3RunContext, Report, SourceView } from './types';
import { EvidenceLinks } from './EvidenceLinks';
import { checkLabel } from './uiCopy';

const COMPONENT_LABELS: Record<string, string> = {
  t: 'T — tổng chi công việc',
  b: 'B — ngân sách được duyệt',
  e: 'E — phần nhân viên được chấp nhận',
  a: 'A — ứng đã thực nhận',
  ra: 'RA — công ty đã nhận hoàn ứng',
  p: 'P — hoàn ứng đã thực nhận',
  rp: 'RP — công ty đã nhận hoàn hoàn ứng',
};

const OWNER_LABELS: Record<string, string> = {
  EMPLOYEE: 'Nhân viên',
  ACCOUNTANT: 'Kế toán',
  APPROVER: 'Người duyệt',
};

const STATE_LABELS: Record<string, string> = {
  ELIGIBLE: 'Được chấp nhận',
  PERSONAL_EXCLUDED: 'Cá nhân — loại khỏi T/E',
  COMPANY_DIRECT: 'Công ty trả trực tiếp',
  UNKNOWN: 'Chưa đủ căn cứ',
  EXCLUDED: 'Loại',
};

const READINESS_LABELS: Record<B3Proposal['readiness'], string> = {
  DRAFT_CONFIRMATION_REQUIRED: 'Cần nhân viên xác nhận bản nháp',
  NEEDS_INFORMATION: 'Còn thiếu thông tin / mâu thuẫn cần làm rõ',
  NEEDS_AUTHORIZED_REVIEW: 'Cần người có quyền xem xét (work/B/advance)',
  READY_FOR_ACCOUNTANT_REVIEW: 'Đủ để kế toán rà soát',
};

function vnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('vi-VN')} VND`;
}

export function ReportPanel({ report, b3Context = null, sources = [] }: {
  report: Report;
  b3Context?: B3RunContext | null;
  sources?: SourceView[];
}) {
  const effectiveSources: SourceView[] = [...sources];
  const knownSourceIds = new Set(sources.map((s) => s.id));
  for (const id of report.source_refs) {
    if (!knownSourceIds.has(id)) {
      effectiveSources.push({
        id,
        filename: id,
        media_type: 'unknown',
        sha256: '',
        size_bytes: 0,
        status: 'ACCEPTED',
        uploader_actor_id: '',
        received_at: '',
        supersedes_source_id: null,
        provenance: {},
      });
      knownSourceIds.add(id);
    }
  }

  const refs = (list: string[]) => (
    <EvidenceLinks refs={list} sources={effectiveSources} />
  );

  return (
    <div className="panel" data-testid="report-panel">
      <h2>Report {report.run_id}</h2>
      <p>
        <strong>Hoàn thành report:</strong>{' '}
        <span className={report.completion === 'COMPLETE' ? 'status-succeeded' : 'status-failed'}>
          {report.completion === 'COMPLETE' ? 'COMPLETE' : 'INCOMPLETE'}
        </span>
        {' · '}
        <strong>Chế độ nguồn:</strong>{' '}
        <span className="notice-warn">
          {report.mode === 'FAKE_OR_REPLAY'
            ? 'FAKE_OR_REPLAY — reader giả lập/offline, không phải chất lượng OCR/LLM thật'
            : report.mode}
        </span>
      </p>

      {report.b3 ? (
        <B3ProposalSection proposal={report.b3} b3Context={b3Context}
                            refs={refs} />
      ) : (
        <>
          <h3>Components (S = E − (A − RA) − (P − RP))</h3>
          <table>
            <thead>
              <tr><th>Thành phần</th><th>Giá trị</th><th>Trạng thái</th><th>Refs</th></tr>
            </thead>
            <tbody>
              {(['t', 'b', 'e', 'a', 'ra', 'p', 'rp'] as const).map((key) => {
                const slot = report.components[key];
                return (
                  <tr key={key}>
                    <td>{COMPONENT_LABELS[key]}</td>
                    <td>{vnd(slot.value)}</td>
                    <td>{slot.state === 'KNOWN' ? 'đủ căn cứ' : slot.state === 'UNKNOWN' ? 'chưa rõ' : slot.state}</td>
                    <td>{refs(slot.refs)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p>
            <strong>Calculated:</strong> {vnd(report.calculated_net_vnd)} ·{' '}
            <strong>Proposed (chưa duyệt, chưa chi):</strong> {vnd(report.proposed_net_vnd)}
            {report.direction && (
              <>
                {' · '}
                <strong>Chiều tiền:</strong>{' '}
                {report.direction === 'COMPANY_TO_EMPLOYEE'
                  ? 'công ty chi cho nhân viên'
                  : report.direction === 'EMPLOYEE_TO_COMPANY'
                    ? 'nhân viên hoàn lại công ty'
                    : 'cân bằng (S = 0)'}
              </>
            )}
          </p>
        </>
      )}

      {report.links.length > 0 && (
        <>
          <h3>Quan hệ đối chiếu</h3>
          <table data-testid="report-links">
            <thead>
              <tr><th>Quan hệ</th><th> Từ → tới</th><th>Phần</th><th>Trạng thái</th></tr>
            </thead>
            <tbody>
              {report.links.map((link) => (
                <tr key={link.relation_id}>
                  <td>{link.kind}</td>
                  <td><code>{link.from_id}</code> → <code>{link.to_id}</code></td>
                  <td>{vnd(link.portion_vnd)}</td>
                  <td>{link.status === 'ESTABLISHED'
                    ? 'đã xác lập'
                    : `${link.status} — chưa dùng làm căn cứ tiền`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {report.critical_facts.length > 0 && (
        <>
          <h3>Critical facts (chất lượng nguồn)</h3>
          <table data-testid="critical-facts">
            <thead>
              <tr><th>Fact</th><th>Giá trị</th><th>Trạng thái</th><th>Refs</th></tr>
            </thead>
            <tbody>
              {report.critical_facts.map((fact) => (
                <tr key={fact.key}>
                  <td><code>{fact.key}</code></td>
                  <td>{fact.value === null
                    ? '—'
                    : typeof fact.value === 'number'
                      ? vnd(fact.value)
                      : String(fact.value)}</td>
                  <td>{fact.state === 'KNOWN'
                    ? 'đã đọc rõ'
                    : fact.state === 'CONTRADICTED'
                      ? 'MÂU THUẪN — hai nguồn khác nhau, không chọn một'
                      : fact.state === 'UNUSABLE'
                        ? 'chất lượng không đủ'
                        : fact.state === 'UNCLEAR'
                          ? 'không đọc được'
                          : 'chưa có'}</td>
                  <td>{refs(fact.refs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {report.conditional_results.length > 0 && (
        <ul className="reasons">
          {report.conditional_results.map((c) => (
            <li key={c.condition}>
              Điều kiện: {c.condition} → net {vnd(c.net_vnd)} (kịch bản, không phải số đã duyệt)
            </li>
          ))}
        </ul>
      )}

      {report.expense_rows.length > 0 && (
        <>
          <h3>Khoản chi</h3>
          <table>
            <thead>
              <tr><th>Khoản</th><th>Khai báo</th><th>Nhân viên</th><th>Công ty trực tiếp</th><th>Trạng thái</th><th>Căn cứ</th></tr>
            </thead>
            <tbody>
              {report.expense_rows.map((row) => (
                <tr key={row.expense_id}>
                  <td>{row.expense_id}</td>
                  <td>{vnd(row.claimed_amount_vnd)}</td>
                  <td>{vnd(row.eligible_employee_vnd)}</td>
                  <td>{vnd(row.company_direct_vnd)}</td>
                  <td title={row.reason}>{STATE_LABELS[row.state] ?? row.state}</td>
                  <td>{refs(row.refs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Mục kiểm tra</h3>
      <ul className="reasons">
        {report.checks.map((check) => (
          <li key={check.rule}>
            <strong>{checkLabel(check.rule)}</strong> ({check.rule}): {check.status} — {check.reason}
          </li>
        ))}
      </ul>

      {report.issues.length > 0 && (
        <>
          <h3>Issues cần làm rõ</h3>
          <ul className="issues">
            {report.issues.map((issue) => (
              <li key={issue.issue_id}>
                <strong>{issue.type}</strong> → {OWNER_LABELS[issue.owner]}: {issue.message}
                {issue.refs.length > 0 && <> (refs: {refs(issue.refs)})</>}
              </li>
            ))}
          </ul>
        </>
      )}

      <p>
        <strong>Bước tiếp theo:</strong> {report.next_step}
      </p>
      <p className="muted">
        Report là kiểm tra có căn cứ, chưa phê duyệt tài chính, chưa ghi nhận
        thực nhận và chưa đóng hồ sơ.
      </p>
    </div>
  );
}

function B3ProposalSection({ proposal, b3Context, refs }: {
  proposal: B3Proposal;
  b3Context: B3RunContext | null;
  refs: (list: string[]) => React.ReactNode;
}) {
  const intake = proposal.intake;
  const decisionLabel = (state: B3Proposal['work_permission']) =>
    state === 'PENDING_DECISION'
      ? 'Đang chờ quyết định (chưa duyệt)'
      : 'Cần rà soát thêm trước khi quyết';
  return (
    <div data-testid="b3-proposal">
      <h3>Đề nghị tạm ứng B3 — proposal</h3>
      <p>
        <strong>Trạng thái:</strong> {READINESS_LABELS[proposal.readiness]}{' '}
        (<code>{proposal.readiness}</code>)
      </p>
      <p>
        <strong>Số xin ứng:</strong> {vnd(intake.request_amount_vnd)}{' '}
        {proposal.field_refs['request_amount_vnd'] &&
          <>— căn cứ: {refs(proposal.field_refs['request_amount_vnd'])}</>}
      </p>
      <p>
        <strong>Công tác:</strong> {intake.destination ?? '—'} ·{' '}
        {intake.trip_start ?? '—'} → {intake.trip_end ?? '—'} ·{' '}
        hạn quyết toán {intake.settlement_due ?? '—'}
        {' · '}<strong>Mục đích:</strong> {intake.purpose ?? '—'}
      </p>

      <h4>Dự toán (phần công ty / nhân viên giữ riêng)</h4>
      <table data-testid="b3-estimate-report">
        <thead>
          <tr><th>Nội dung</th><th>Cơ sở</th><th>Công ty</th><th>Nhân viên</th><th>Căn cứ</th></tr>
        </thead>
        <tbody>
          {intake.estimate_rows.map((row) => (
            <tr key={row.row_id}>
              <td>{row.description}</td>
              <td>{row.basis ?? '—'}</td>
              <td>{vnd(row.company_vnd)}</td>
              <td>{vnd(row.employee_vnd)}</td>
              <td>
                {refs([
                  ...(proposal.field_refs[`estimate_rows.${row.row_id}.company_vnd`] ?? []),
                  ...(proposal.field_refs[`estimate_rows.${row.row_id}.employee_vnd`] ?? []),
                ])}
              </td>
            </tr>
          ))}
          <tr>
            <td><strong>Tổng</strong></td>
            <td></td>
            <td><strong>{vnd(proposal.forecast_company_vnd)}</strong></td>
            <td><strong>{vnd(proposal.forecast_employee_vnd)}</strong></td>
            <td></td>
          </tr>
        </tbody>
      </table>
      <p>
        <strong>Tổng dự toán:</strong> {vnd(proposal.forecast_total_vnd)} —
        dự toán không phải ngân sách đã duyệt; phần dự kiến công ty trả không
        phải actual payer.
      </p>

      <h4>Nội dung cần người có quyền quyết định</h4>
      <ul className="reasons">
        <li>
          <strong>Cho phép công tác (work):</strong> {decisionLabel(proposal.work_permission)}
        </li>
        <li>
          <strong>Duyệt ngân sách (B):</strong> {decisionLabel(proposal.work_permission)}
        </li>
        <li>
          <strong>Duyệt ứng:</strong> {decisionLabel(proposal.advance_approval)}
        </li>
      </ul>
      <p>
        <strong>Tuyến xử lý:</strong> kế toán {proposal.accountant_ref ?? '— (chưa cấu hình)'}{' '}
        · người duyệt {proposal.approver_ref ?? '— (chưa cấu hình)'} (readonly theo
        cấu hình công ty, không nhập trên form).
      </p>

      {b3Context && (
        <div data-testid="b3-run-context">
          <h4>Company context của run (snapshot)</h4>
          <p className="muted">
            {b3Context.synthetic
              ? `Fixture mô phỏng "${b3Context.version}"${
                  b3Context.demo_clock
                    ? ` — mốc mô phỏng ${b3Context.demo_clock}`
                    : ''}`
              : `Context "${b3Context.version}"`}
          </p>
          <ul className="reasons">
            {b3Context.grants.map((grant) => (
              <li key={grant.ref}>
                <code>{grant.ref}</code>: {grant.actor_ref} được phép work={
                  grant.allow_work ? 'có' : 'không'}, ngân sách ≤{' '}
                {vnd(grant.max_budget_vnd)}, ứng ≤ {vnd(grant.max_advance_vnd)}{' '}
                cho {grant.employee_ref}
                {grant.work_ref ? ` (work ${grant.work_ref})` : ' (mọi work)'}
              </li>
            ))}
            {b3Context.coverage.map((record) => (
              <li key={record.ref}>
                <code>{record.ref}</code>: coverage {record.employee_ref}
                {record.work_ref ? ` (work ${record.work_ref})` : ' (mọi work)'}{' '}
                {record.from} → {record.to}
                {record.complete_prior_history
                  ? ' — gồm mở sổ/tồn trước kỳ' : ' — không gồm số dư đầu kỳ'}
                {' '}(owner {record.owner_ref})
              </li>
            ))}
            {b3Context.history.length === 0
              ? <li>Lịch sử company-side: trống (theo coverage đã khai báo).</li>
              : b3Context.history.map((event) => (
                <li key={event.event_ref}>
                  <code>{event.event_ref}</code>: {event.kind}/{event.status}{' '}
                  {vnd(event.amount_vnd)} — {event.event_at} (work {event.work_ref})
                </li>
              ))}
          </ul>
        </div>
      )}

      <p className="notice-warn" role="alert">
        B3 v1 chỉ tạo report đề nghị: chưa có hành động duyệt ứng/chi tiền/đóng
        hồ sơ trong nhánh này. Complete nghĩa là đủ căn cứ rà soát, không nghĩa
        đã duyệt.
      </p>
    </div>
  );
}
