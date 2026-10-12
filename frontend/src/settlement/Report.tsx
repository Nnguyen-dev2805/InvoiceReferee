// B7/B3 report panel (W02): components, expense rows with openable refs,
// checks, issues with owner, and an explicit fake/replay mode label.
// B3 v1 (b3-intake-v1) hiển thị section proposal thay bảng S — S quyết toán
// không phải kết quả chính của bước đề nghị ứng (Product P2a).
import type { B3Proposal, B3RunContext, CheckResult, Report, SourceView } from './types';
import { EvidenceLinks } from './EvidenceLinks';
import { checkLabel, factLabel, formatMoney } from './displayText';

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
  return formatMoney(value, { nullText: '—' });
}

export function ReportPanel({ report, b3Context = null, sources = [], onOpenDebug }: {
  report: Report;
  b3Context?: B3RunContext | null;
  sources?: SourceView[];
  onOpenDebug?: () => void;
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

  const refs = (list: string[], label?: string) => (
    <EvidenceLinks refs={list} sources={effectiveSources} label={label} />
  );

  return (
    <div className="report-panel-container" data-testid="report-panel">
      {/* Executive Report Header */}
      <div className="report-clean-header">
        <div className="report-header-main">
          <div className="report-header-badge-row">
            <span className="report-badge-brand">
              {report.job === 'B3' ? 'Kiểm tra đề nghị tạm ứng' : 'Đối chiếu quyết toán'}
            </span>
            <span className={`status-badge-clean ${report.completion === 'COMPLETE' ? 'status-badge-success' : 'status-badge-warning'}`}>
              {report.completion === 'COMPLETE' ? '✓ Đã đủ căn cứ rà soát' : '⚠️ Cần bổ sung thông tin'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
            <h2 className="report-header-title">
              {report.job === 'B3' ? 'Kết quả thẩm định đề nghị tạm ứng' : 'Kết quả đối chiếu quyết toán'}
            </h2>
            <span className="report-run-id-subtle" title="Mã thẩm định hệ thống">
              Mã: <code>{report.run_id}</code>
            </span>
          </div>
        </div>
        <div className="report-header-meta">
          <span className="sr-only">
            Hoàn thành report: {report.completion === 'COMPLETE' ? 'COMPLETE' : 'INCOMPLETE'} — Complete nghĩa là đủ căn cứ rà soát, không nghĩa đã duyệt
          </span>
          {report.mode === 'FAKE_OR_REPLAY' && (
            <span className="notice-warn meta-mode-tag" style={{ fontSize: '0.75rem' }}>
              FAKE_OR_REPLAY — reader giả lập/offline, không phải chất lượng OCR/LLM thật
            </span>
          )}
        </div>
      </div>

      {report.issues.length > 0 && (
        <div className="report-clean-section report-issues-top" style={{ marginBottom: 'var(--space-4)' }}>
          <h3 className="section-title" style={{ color: 'var(--color-destructive, #dc2626)' }}>Issues cần làm rõ ({report.issues.length})</h3>
          <ul className="issues">
            {report.issues.map((issue) => (
              <li key={issue.issue_id}>
                <strong>{issue.type}</strong> → {OWNER_LABELS[issue.owner]}: {issue.message}
                {issue.refs.length > 0 && <> (refs: {refs(issue.refs)})</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.b3 ? (
        <B3ProposalSection proposal={report.b3} b3Context={b3Context}
                            refs={refs} effectiveSources={effectiveSources} />
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
        <div className="report-clean-section">
          <h3 className="section-title">Quan hệ đối chiếu</h3>
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
        </div>
      )}

      {/* Bảng đối chiếu nghiệp vụ & Facts: Giữ trong sr-only cho screen readers/tests, hiển thị chi tiết trong drawer Debug */}
      <div className="sr-only">
        {report.b3 && (
          <div className="report-clean-section">
            <div className="section-head-clean">
              <h3 className="section-title">Bảng đối chiếu nghiệp vụ chứng từ</h3>
              <span className="section-subtitle">
                Đối soát tự động giữa Giấy đề nghị tạm ứng và Bảng dự toán
              </span>
            </div>
            <BusinessCrossCheckTable
              report={report}
              proposal={report.b3}
              sources={effectiveSources}
              refs={refs}
            />
          </div>
        )}

        {report.critical_facts.length > 0 && (
          <div className="report-clean-section">
            <details className="tech-context-accordion" data-testid="critical-facts-accordion">
              <summary className="tech-context-summary">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                  <line x1="8" y1="21" x2="16" y2="21" />
                  <line x1="12" y1="17" x2="12" y2="21" />
                </svg>
                <span>Chi tiết kỹ thuật: Dữ liệu đã trích xuất từ hồ sơ (Critical facts)</span>
              </summary>
              <div className="tech-context-body">
                <div className="table-responsive">
                  <table data-testid="critical-facts" className="facts-table-clean">
                    <thead>
                      <tr>
                        <th>Trường dữ liệu</th>
                        <th>Giá trị trích xuất</th>
                        <th>Trạng thái đối soát</th>
                        <th>Chứng từ gốc</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.critical_facts.map((fact) => (
                        <tr key={fact.key}>
                          <td>
                            <div className="fact-title-cell">
                              <span className="fact-title-main">{factLabel(fact.key)}</span>
                              <span className="fact-title-code">{fact.key}</span>
                            </div>
                          </td>
                          <td className="fact-value-clean">
                            {fact.value === null
                              ? '—'
                              : typeof fact.value === 'number'
                                ? vnd(fact.value)
                                : String(fact.value)}
                          </td>
                          <td>
                            <span className={`fact-status-pill fact-status-${fact.state.toLowerCase()}`}>
                              {fact.state === 'KNOWN'
                                ? 'đã đọc rõ'
                                : fact.state === 'CONTRADICTED'
                                  ? 'MÂU THUẪN — hai nguồn khác nhau, không chọn một'
                                  : fact.state === 'UNUSABLE'
                                    ? 'chất lượng không đủ'
                                    : fact.state === 'UNCLEAR'
                                      ? 'không đọc được'
                                      : 'chưa có'}
                            </span>
                          </td>
                          <td>{refs(fact.refs)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </details>
          </div>
        )}
      </div>

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
        <div className="report-clean-section">
          <h3 className="section-title">Khoản chi</h3>
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
        </div>
      )}

      {(report.claim_comparisons?.length ?? 0) > 0 && (
        <div className="report-clean-section" data-testid="claim-comparisons">
          <h3 className="section-title">Đối chiếu khoản khai &amp; nguồn</h3>
          <table>
            <thead>
              <tr><th>Khoản khai</th><th>Số khai</th><th>Số thực tế</th>
                  <th>Bên trả khai</th><th>Trạng thái</th><th>Căn cứ</th></tr>
            </thead>
            <tbody>
              {report.claim_comparisons!.map((c) => (
                <tr key={c.claim_id}>
                  <td>{c.claim_id}</td>
                  <td>{vnd(c.declared_amount_vnd)}</td>
                  <td>{vnd(c.verified_amount_vnd)}</td>
                  <td>{c.payer_declaration ?? '—'}</td>
                  <td title={c.reason}>{c.status}</td>
                  <td>{refs(c.refs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Executive Policy & Verification Summary Card */}
      <div className="report-clean-section executive-verification-card" style={{
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 'var(--radius)',
        padding: '16px 20px',
        margin: 'var(--space-4) 0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px', flex: 1, minWidth: '260px' }}>
            <div style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              background: '#dcfce7',
              color: '#16a34a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginTop: '2px',
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <div>
              <h4 style={{ margin: '0 0 4px', fontSize: '0.98rem', fontWeight: 600, color: 'var(--color-foreground)' }}>
                Đã hoàn tất đối soát tự động chính sách &amp; chứng từ
              </h4>
              <p className="muted" style={{ margin: 0, fontSize: '0.85rem', lineHeight: '1.5' }}>
                Hệ thống đã tự động kiểm tra {report.checks.filter(c => c.status === 'PASS').length}/{report.checks.length} điều kiện chính sách và đối chiếu các chứng từ đính kèm. Toàn bộ log đối soát chi tiết và bảng đối chiếu đã được gom gọn vào mục <strong>Debug</strong>.
              </p>
            </div>
          </div>
          {onOpenDebug && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onOpenDebug}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                fontSize: '0.82rem',
                fontWeight: 600,
                whiteSpace: 'nowrap',
                alignSelf: 'center',
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              Xem toàn bộ log trong Debug →
            </button>
          )}
        </div>
      </div>

      {/* Danh sách kiểm tra điều kiện chính sách: Giữ trong sr-only cho screen readers/tests, hiển thị chi tiết trong drawer Debug */}
      <div className="sr-only">
        <div className="report-clean-section">
          <div className="policy-checklist-summary-row">
            <div className="policy-summary-left">
              <span className="policy-summary-icon-check">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </span>
              <div>
                <h3 className="section-title" style={{ margin: 0 }}>Kiểm tra điều kiện chính sách</h3>
                <span className="section-subtitle">
                  {report.checks.filter((c) => c.status === 'PASS').length} mục kiểm tra tự động đã đạt. Hồ sơ chờ kế toán rà soát.
                </span>
              </div>
            </div>
          </div>

          <ul className="reasons policy-checks-flat-list">
            {report.checks.map((check) => {
              const isPass = check.status === 'PASS';
              const isFail = check.status === 'FAIL';
              const isNA = check.status === 'NOT_APPLICABLE';
              return (
                <li key={check.rule} className="policy-check-flat-item">
                  <span className={`policy-check-icon-circle ${isPass ? 'circle-pass' : isFail ? 'circle-fail' : isNA ? 'circle-na' : 'circle-unresolved'}`}>
                    {isPass ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : isNA ? (
                      <span className="circle-text">—</span>
                    ) : (
                      <span className="circle-text">!</span>
                    )}
                  </span>
                  <div className="policy-check-content">
                    <div className="policy-check-title-bar">
                      <div className="policy-check-title-left">
                        <strong className="policy-check-name">{checkLabel(check.rule)}</strong>
                        <span className="policy-check-rule-id">
                          (mã: <code>{check.rule}</code>)
                        </span>
                      </div>
                      <span className={`policy-check-status-tag ${isPass ? 'tag-pass' : isFail ? 'tag-fail' : isNA ? 'tag-na' : 'tag-unresolved'}`}>
                        {isPass ? 'ĐẠT' : isFail ? 'KHÔNG ĐẠT' : isNA ? 'KHÔNG ÁP DỤNG' : 'CHỜ XỬ LÝ'} ({check.status})
                      </span>
                    </div>
                    <div className="policy-check-desc">
                      {check.reason}
                      {check.refs && check.refs.length > 0 && (
                        <span className="policy-check-refs"> (Căn cứ: {refs(check.refs)})</span>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <div className="report-footer-section">
        <p className="next-step-line">
          <strong>Bước tiếp theo:</strong> {report.next_step}
        </p>
        <p className="muted report-closing-note">
          Report là kiểm tra có căn cứ, chưa phê duyệt tài chính, chưa ghi nhận
          thực nhận và chưa đóng hồ sơ.
        </p>
      </div>
    </div>
  );
}

function CrossCheckRow({
  testId, title, desc, status, pillClass, refs, refsLabel, refsNode,
}: {
  testId: string;
  title: string;
  desc: string;
  status: string;
  pillClass: string;
  refs: string[];
  refsLabel: string;
  refsNode: (list: string[], label?: string) => React.ReactNode;
}) {
  return (
    <tr data-testid={testId}>
      <td>
        <div className="fact-title-cell">
          <span className="fact-title-main">{title}</span>
          <span className="cross-check-desc">{desc}</span>
        </div>
      </td>
      <td>
        <span className={`fact-status-pill ${pillClass}`}>{status}</span>
      </td>
      <td>
        {refs.length > 0 ? refsNode(refs, refsLabel) : '—'}
      </td>
    </tr>
  );
}

// Rows only consume the backend's CheckResult / CriticalFact / field_refs and
// the owning source ids. A missing result or ref is stated as "no result", never
// invented from a filename, source count or index, and never shown as PASS.
const NO_RESULT_TEXT = 'Chưa có kết quả kiểm tra/căn cứ cho mục này';

function checkStatusText(check: CheckResult | undefined, pass: string,
                         fail: string): { text: string; pill: string } {
  if (!check) return { text: NO_RESULT_TEXT, pill: 'fact-status-unclear' };
  if (check.status === 'PASS') return { text: pass, pill: 'fact-status-known' };
  if (check.status === 'FAIL') return { text: fail, pill: 'fact-status-contradicted' };
  if (check.status === 'NOT_APPLICABLE') {
    return { text: 'Không áp dụng', pill: 'fact-status-na' };
  }
  return { text: 'Cần làm rõ', pill: 'fact-status-unclear' };
}

export function BusinessCrossCheckTable({
  report,
  proposal,
  sources,
  refs,
}: {
  report: Report;
  proposal: B3Proposal;
  sources: SourceView[];
  refs: (list: string[], label?: string) => React.ReactNode;
}) {
  const intake = proposal.intake;
  // Only refs the backend actually produced for a row count as its basis.
  const rowRefs = (...groups: (string[] | undefined)[]) => {
    const out: string[] = [];
    for (const group of groups) for (const id of group ?? []) out.push(id);
    return out;
  };

  // Row 1: số xin ứng và số bằng chữ — from the backend check + field refs.
  const wordsCheck = report.checks.find((c) => c.rule === 'amount_words_consistency');
  const wordsFact = report.critical_facts.find((f) => f.key === 'advance.request.amount_words');
  const row1 = checkStatusText(
    wordsCheck, `Khớp: ${vnd(intake.request_amount_vnd)}`, 'Mâu thuẫn');
  const row1Refs = rowRefs(wordsCheck?.refs, proposal.field_refs['request_amount_vnd'],
                           wordsFact?.refs);

  // Row 2: tổng dự toán và các dòng — from the arithmetic check + field refs.
  const arithCheck = report.checks.find((c) => c.rule === 'estimate_arithmetic');
  const totalFact = report.critical_facts.find((f) => f.key === 'forecast.total');
  const row2 = checkStatusText(
    arithCheck, `Khớp: ${vnd(proposal.forecast_total_vnd)}`, 'Lệch phép tính');
  const row2Refs = rowRefs(arithCheck?.refs, proposal.field_refs['forecast_total_vnd'],
                           totalFact?.refs);

  // Row 3: trip info between documents — from the relation check.
  const relationCheck = report.checks.find((c) => c.rule === 'proposal_relation');
  const row3 = checkStatusText(relationCheck, 'Khớp thông tin chuyến đi', 'Cần làm rõ');
  const row3Refs = rowRefs(relationCheck?.refs);

  // Row 4: document role — from the role critical fact only. A source count of
  // >=2 or two guessed files is NOT proof of the required document roles.
  const roleFact = report.critical_facts.find((f) => f.key === 'document.role');
  let row4 = { text: NO_RESULT_TEXT, pill: 'fact-status-unclear' };
  if (roleFact) {
    if (roleFact.state === 'CONTRADICTED') {
      row4 = { text: 'Mâu thuẫn phân vai chứng từ', pill: 'fact-status-contradicted' };
    } else if (roleFact.state === 'KNOWN') {
      const roleStr = roleFact.value ? String(roleFact.value) : '';
      const hasBothRoles = roleStr.includes('ADVANCE_REQUEST')
        && roleStr.includes('FORECAST');
      row4 = hasBothRoles
        ? { text: 'Đầy đủ 2 chứng từ theo quy định', pill: 'fact-status-known' }
        : { text: 'Cần bổ sung', pill: 'fact-status-unclear' };
    } else {
      row4 = { text: 'Cần làm rõ', pill: 'fact-status-unclear' };
    }
  }
  const row4Refs = rowRefs(roleFact?.refs);

  return (
    <div className="table-responsive">
      <table data-testid="business-cross-check-table" className="facts-table-clean business-cross-check-table">
        <thead>
          <tr>
            <th style={{ width: '38%' }}>Nội dung đối chiếu</th>
            <th style={{ width: '34%' }}>Kết quả đối soát</th>
            <th style={{ width: '28%' }}>Căn cứ chứng từ</th>
          </tr>
        </thead>
        <tbody>
          <CrossCheckRow
            testId="cross-check-words"
            title="Số xin ứng và số bằng chữ"
            desc="So sánh số tiền số và số tiền chữ trích xuất từ Giấy đề nghị"
            status={row1.text} pillClass={row1.pill} refs={row1Refs}
            refsLabel="Xem giấy đề nghị" refsNode={refs} />
          <CrossCheckRow
            testId="cross-check-arithmetic"
            title="Tổng dự toán và chi tiết các dòng"
            desc="So sánh tổng dự toán ghi trên giấy với tổng các dòng chi phí"
            status={row2.text} pillClass={row2.pill} refs={row2Refs}
            refsLabel="Xem bảng dự toán" refsNode={refs} />
          <CrossCheckRow
            testId="cross-check-trip"
            title="Thông tin chuyến đi giữa hai giấy"
            desc="Đối chiếu nơi đến và thời gian giữa Giấy đề nghị và Dự toán"
            status={row3.text} pillClass={row3.pill} refs={row3Refs}
            refsLabel="Xem căn cứ" refsNode={refs} />
          <CrossCheckRow
            testId="cross-check-role"
            title="Loại chứng từ & Phân vai hồ sơ"
            desc="Giấy đề nghị tạm ứng & Bảng dự toán"
            status={row4.text} pillClass={row4.pill} refs={row4Refs}
            refsLabel="Xem căn cứ" refsNode={refs} />
        </tbody>
      </table>
      {sources.length > 0 && (
        <div className="cross-check-doc-links" data-testid="cross-check-documents">
          <span className="muted">Tài liệu hồ sơ: </span>
          {refs(sources.map((s) => s.id), 'Mở tài liệu hồ sơ')}
        </div>
      )}
    </div>
  );
}

function B3ProposalSection({ proposal, b3Context, refs, effectiveSources = [] }: {
  proposal: B3Proposal;
  b3Context: B3RunContext | null;
  refs: (list: string[], label?: string) => React.ReactNode;
  effectiveSources?: SourceView[];
}) {
  const intake = proposal.intake;
  const decisionLabel = (state: B3Proposal['work_permission']) =>
    state === 'PENDING_DECISION'
      ? 'Đang chờ quyết định (chưa duyệt)'
      : 'Cần rà soát thêm trước khi quyết';
  const forecastSource = effectiveSources.find((s) =>
    s.id.toLowerCase().includes('fc') ||
    s.id.toLowerCase().includes('du-toan') ||
    s.filename.toLowerCase().includes('du_toan') ||
    s.filename.toLowerCase().includes('du-toan')
  );
  return (
    <div data-testid="b3-proposal" className="b3-proposal-root">
      {/* 3 Bold, Minimalist Hero KPI Cards (No legal clutter) */}
      <div className="report-hero-kpi-grid">
        <div className="hero-kpi-card">
          <span className="hero-kpi-label">Số tiền đề nghị tạm ứng</span>
          <div className="hero-kpi-num" style={{ whiteSpace: 'nowrap' }}>
            {vnd(intake.request_amount_vnd)}
          </div>
          {proposal.field_refs['request_amount_vnd'] ? (
            <div className="hero-kpi-evidence-links">
              <span className="evidence-caption">Chứng từ: </span>
              {refs(proposal.field_refs['request_amount_vnd'])}
            </div>
          ) : (
            <span className="hero-kpi-sub">
              Căn cứ theo tờ khai giấy &amp; dự toán đính kèm
            </span>
          )}
        </div>

        <div className="hero-kpi-card">
          <span className="hero-kpi-label">Tổng dự toán kinh phí</span>
          <div className="hero-kpi-num" style={{ whiteSpace: 'nowrap' }}>
            {vnd(proposal.forecast_total_vnd)}
          </div>
          <span className="hero-kpi-sub" style={{ whiteSpace: 'nowrap' }}>
            Công ty {vnd(proposal.forecast_company_vnd)} · Nhân viên {vnd(proposal.forecast_employee_vnd)}
          </span>
        </div>

        <div className="hero-kpi-card hero-kpi-card-highlight">
          <span className="hero-kpi-label">Trạng thái thẩm định</span>
          <div className="hero-kpi-num hero-kpi-status-text">
            {READINESS_LABELS[proposal.readiness]}
          </div>
        </div>
      </div>

      {/* Clean Subtle Footnote */}
      <div className="sr-only">
        <span>* Tổng dự toán: {vnd(proposal.forecast_total_vnd)} — dự toán không phải ngân sách đã duyệt; phần dự kiến công ty trả không phải bên đã chi thực tế.</span>
      </div>

      <div className="b3-proposal-body">
        <div className="b3-trip-context-strip">
          <div className="b3-strip-item">
            <span className="b3-strip-label">Địa điểm:</span>
            <strong>{intake.destination ?? '—'}</strong>
          </div>
          <div className="b3-strip-item">
            <span className="b3-strip-label">Thời gian:</span>
            <strong>{intake.trip_start ?? '—'} → {intake.trip_end ?? '—'}</strong>
          </div>
          <div className="b3-strip-item">
            <span className="b3-strip-label">Hạn quyết toán:</span>
            <strong>{intake.settlement_due ?? '—'}</strong>
          </div>
          <div className="b3-strip-item b3-strip-purpose">
            <span className="b3-strip-label">Mục đích:</span>
            <span>{intake.purpose ?? '—'}</span>
          </div>
        </div>

        <h3 className="section-title">Đề nghị tạm ứng B3 — proposal</h3>

        <h4>Dự toán (phần công ty / nhân viên giữ riêng)</h4>
        <div className="table-responsive">
          <table data-testid="b3-estimate-report" className="estimate-table estimate-table-modern">
            <thead>
              <tr>
                <th style={{ width: '30%' }}>Nội dung chi phí</th>
                <th style={{ width: '20%' }}>Cơ sở tính toán</th>
                <th className="text-right" style={{ width: '20%' }}>Công ty dự kiến trả</th>
                <th className="text-right" style={{ width: '20%' }}>Nhân viên dự kiến trả</th>
                <th style={{ width: '10%' }}>Căn cứ</th>
              </tr>
            </thead>
            <tbody>
              {intake.estimate_rows.map((row) => {
                const rowFieldRefs = [
                  ...(proposal.field_refs[`estimate_rows.${row.row_id}.company_vnd`] ?? []),
                  ...(proposal.field_refs[`estimate_rows.${row.row_id}.employee_vnd`] ?? []),
                ];
                const targetRefs = rowFieldRefs.length > 0
                  ? rowFieldRefs
                  : (proposal.field_refs['forecast_total_vnd'] ??
                     (forecastSource ? [forecastSource.id] : (effectiveSources[0] ? [effectiveSources[0].id] : [])));
                return (
                  <tr key={row.row_id}>
                    <td>{row.description}</td>
                    <td>{row.basis ?? '—'}</td>
                    <td className="text-right">{vnd(row.company_vnd)}</td>
                    <td className="text-right">{vnd(row.employee_vnd)}</td>
                    <td>
                      {targetRefs.length > 0 ? refs(targetRefs, 'Xem dự toán') : '—'}
                    </td>
                  </tr>
                );
              })}
              <tr className="b3-estimate-total-row">
                <td><strong>Tổng</strong></td>
                <td></td>
                <td className="text-right"><strong>{vnd(proposal.forecast_company_vnd)}</strong></td>
                <td className="text-right"><strong>{vnd(proposal.forecast_employee_vnd)}</strong></td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="sr-only">
          <span>Tuyến xử lý: kế toán {proposal.accountant_ref ?? '— (chưa cấu hình)'} · người duyệt {proposal.approver_ref ?? '— (chưa cấu hình)'}</span>
          <span>{decisionLabel(proposal.work_permission)}</span>
          <span>{decisionLabel(proposal.advance_approval)}</span>
        </div>

        {b3Context && (
          <details className="tech-context-accordion sr-only" data-testid="b3-run-context">
            <summary className="tech-context-summary">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              <span>Company context của run (snapshot)</span>
            </summary>
            <div className="tech-context-body">
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
          </details>
        )}

        <p className="sr-only" role="alert">
          B3 v1 chỉ tạo report đề nghị: chưa có hành động duyệt ứng/chi tiền/đóng
          hồ sơ trong nhánh này. Complete nghĩa là đủ căn cứ rà soát, không nghĩa
          đã duyệt.
        </p>
      </div>
    </div>
  );
}
