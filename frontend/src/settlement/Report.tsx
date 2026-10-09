// B7/B3 report panel (W02): components, expense rows with openable refs,
// checks, issues with owner, and an explicit fake/replay mode label.
import type { Report } from './types';
import { sourceContentUrl } from './api';

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

function vnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('vi-VN')} VND`;
}

export function ReportPanel({ report }: { report: Report }) {
  const sourceIds = new Set(report.source_refs);
  const refs = (list: string[]) => (
    <span className="reasons">
      {list.map((ref) =>
        sourceIds.has(ref) ? (
          <a key={ref} href={sourceContentUrl(ref)} target="_blank" rel="noreferrer">
            {ref}
          </a>
        ) : (
          <code key={ref}>{ref}</code>
        ),
      )}
    </span>
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

      <h3>Checks</h3>
      <ul className="reasons">
        {report.checks.map((check) => (
          <li key={check.rule}>
            <strong>{check.rule}</strong>: {check.status} — {check.reason}
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
