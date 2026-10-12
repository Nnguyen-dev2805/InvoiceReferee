// Technical details slide-over drawer: centralized system logs, policy checks,
// document cross-checks, extracted facts, and run/report trace.
import { useState, useMemo } from 'react';
import { ProcessingDetails } from '../ProcessingDetails';
import { dossierReference, checkLabel, factLabel, formatMoney } from '../displayText';
import { EvidenceLinks } from '../EvidenceLinks';
import { BusinessCrossCheckTable } from '../Report';
import type { CaseView, Report, RunView, SourceView, B3RunContext } from '../types';

interface TechDrawerProps {
  view: CaseView;
  run: RunView | null;
  report: Report | null;
  sources?: SourceView[];
  b3Context?: B3RunContext | null;
  onClose: () => void;
}

function vnd(value: number | null | undefined): string {
  return formatMoney(value, { nullText: '—' });
}

export function TechDrawer({
  view,
  run,
  report,
  sources = [],
  onClose,
}: TechDrawerProps) {
  const [activeTab, setActiveTab] = useState<'checks' | 'crossCheck' | 'facts' | 'system'>('checks');
  const [checkFilter, setCheckFilter] = useState<'ALL' | 'PASS' | 'FAIL' | 'UNRESOLVED' | 'NOT_APPLICABLE'>('ALL');

  const effectiveSources: SourceView[] = sources.length > 0 ? [...sources] : [...(view.sources ?? [])];
  const knownSourceIds = new Set(effectiveSources.map((s) => s.id));
  if (report) {
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
  }

  const refs = (list: string[], label?: string) => (
    <EvidenceLinks refs={list} sources={effectiveSources} label={label} />
  );

  const checks = report?.checks ?? [];
  const passCount = useMemo(() => checks.filter((c) => c.status === 'PASS').length, [checks]);
  const failCount = useMemo(() => checks.filter((c) => c.status === 'FAIL').length, [checks]);
  const unresolvedCount = useMemo(() => checks.filter((c) => c.status === 'UNRESOLVED').length, [checks]);
  const naCount = useMemo(() => checks.filter((c) => c.status === 'NOT_APPLICABLE').length, [checks]);

  const filteredChecks = useMemo(() => {
    if (checkFilter === 'ALL') return checks;
    return checks.filter((c) => c.status === checkFilter);
  }, [checks, checkFilter]);

  return (
    <div className="swiss-tech-drawer-overlay" onClick={onClose}>
      <div
        className="swiss-tech-drawer"
        data-testid="swiss-tech-drawer"
        onClick={(e) => e.stopPropagation()}
        style={{ width: '720px', maxWidth: '95vw', display: 'flex', flexDirection: 'column' }}
      >
        {/* DRAWER TOP BAR */}
        <div className="swiss-drawer-header" style={{ padding: '14px 20px', background: '#ffffff', borderBottom: '1px solid var(--color-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '28px',
              height: '28px',
              borderRadius: '6px',
              background: '#f1f5f9',
              color: '#334155',
            }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            </span>
            <div>
              <h3 className="swiss-drawer-title" style={{ margin: 0, fontSize: '0.98rem', fontWeight: 700 }}>
                Log hệ thống &amp; Kiểm toán (Debug)
              </h3>
              <span style={{ fontSize: '0.78rem', color: 'var(--color-muted-foreground)' }}>
                {dossierReference(view) ?? view.id} · v{view.case_version} (rev {view.input_revision})
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn-icon-subtle"
            onClick={onClose}
            aria-label="Đóng bảng kỹ thuật"
            style={{ fontSize: '1.1rem', padding: '4px 8px', cursor: 'pointer' }}
          >
            ✕
          </button>
        </div>

        {/* DRAWER TABS BAR */}
        <div className="tech-drawer-tab-row" style={{
          display: 'flex',
          gap: '4px',
          padding: '6px 16px 0',
          background: '#f8fafc',
          borderBottom: '1px solid var(--color-border)',
        }}>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'checks' ? 'active' : ''}`}
            onClick={() => setActiveTab('checks')}
            style={{
              padding: '8px 14px',
              fontSize: '0.82rem',
              fontWeight: 600,
              borderBottom: activeTab === 'checks' ? '2px solid #18181b' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === 'checks' ? '#18181b' : '#64748b',
              cursor: 'pointer',
            }}
          >
            Đối soát chính sách ({checks.length})
          </button>

          {report?.b3 && (
            <button
              type="button"
              className={`tab-btn ${activeTab === 'crossCheck' ? 'active' : ''}`}
              onClick={() => setActiveTab('crossCheck')}
              style={{
                padding: '8px 14px',
                fontSize: '0.82rem',
                fontWeight: 600,
                borderBottom: activeTab === 'crossCheck' ? '2px solid #18181b' : '2px solid transparent',
                background: 'transparent',
                color: activeTab === 'crossCheck' ? '#18181b' : '#64748b',
                cursor: 'pointer',
              }}
            >
              Đối chiếu chứng từ
            </button>
          )}

          {Boolean((report?.critical_facts?.length ?? 0) > 0 || (report?.claim_comparisons?.length ?? 0) > 0) && (
            <button
              type="button"
              className={`tab-btn ${activeTab === 'facts' ? 'active' : ''}`}
              onClick={() => setActiveTab('facts')}
              style={{
                padding: '8px 14px',
                fontSize: '0.82rem',
                fontWeight: 600,
                borderBottom: activeTab === 'facts' ? '2px solid #18181b' : '2px solid transparent',
                background: 'transparent',
                color: activeTab === 'facts' ? '#18181b' : '#64748b',
                cursor: 'pointer',
              }}
            >
              Facts ({report?.critical_facts.length ?? 0})
            </button>
          )}

          <button
            type="button"
            className={`tab-btn ${activeTab === 'system' ? 'active' : ''}`}
            onClick={() => setActiveTab('system')}
            style={{
              padding: '8px 14px',
              fontSize: '0.82rem',
              fontWeight: 600,
              borderBottom: activeTab === 'system' ? '2px solid #18181b' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === 'system' ? '#18181b' : '#64748b',
              cursor: 'pointer',
            }}
          >
            Hệ thống &amp; Trace
          </button>
        </div>

        {/* DRAWER CONTENT BODY */}
        <div className="swiss-drawer-body" style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
          {/* TAB 1: ĐỐI SOÁT CHÍNH SÁCH */}
          {activeTab === 'checks' && (
            <div>
              {/* Summary Stats & Filter Pills */}
              <div style={{
                background: '#f8fafc',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
                padding: '12px 16px',
                marginBottom: 'var(--space-3)',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.86rem' }}>
                    Kết quả kiểm tra điều kiện chính sách
                  </span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--color-muted-foreground)' }}>
                    {passCount}/{checks.length} đạt chuẩn
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className={`btn btn-sm ${checkFilter === 'ALL' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 10px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setCheckFilter('ALL')}
                  >
                    Tất cả ({checks.length})
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${checkFilter === 'PASS' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ padding: '2px 10px', fontSize: '0.75rem', borderRadius: '9999px' }}
                    onClick={() => setCheckFilter('PASS')}
                  >
                    Đạt ({passCount})
                  </button>
                  {failCount > 0 && (
                    <button
                      type="button"
                      className={`btn btn-sm ${checkFilter === 'FAIL' ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ padding: '2px 10px', fontSize: '0.75rem', borderRadius: '9999px' }}
                      onClick={() => setCheckFilter('FAIL')}
                    >
                      Không đạt ({failCount})
                    </button>
                  )}
                  {unresolvedCount > 0 && (
                    <button
                      type="button"
                      className={`btn btn-sm ${checkFilter === 'UNRESOLVED' ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ padding: '2px 10px', fontSize: '0.75rem', borderRadius: '9999px' }}
                      onClick={() => setCheckFilter('UNRESOLVED')}
                    >
                      Chờ xử lý ({unresolvedCount})
                    </button>
                  )}
                  {naCount > 0 && (
                    <button
                      type="button"
                      className={`btn btn-sm ${checkFilter === 'NOT_APPLICABLE' ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ padding: '2px 10px', fontSize: '0.75rem', borderRadius: '9999px' }}
                      onClick={() => setCheckFilter('NOT_APPLICABLE')}
                    >
                      Không áp dụng ({naCount})
                    </button>
                  )}
                </div>
              </div>

              {/* Checklist items */}
              {filteredChecks.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--color-muted-foreground)' }}>
                  Không có mục nào trong danh mục lọc này.
                </div>
              ) : (
                <ul className="reasons policy-checks-flat-list" style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', background: '#ffffff' }}>
                  {filteredChecks.map((check) => {
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
              )}
            </div>
          )}

          {/* TAB 2: ĐỐI CHIẾU CHỨNG TỪ */}
          {activeTab === 'crossCheck' && report?.b3 && (
            <div>
              <div style={{ marginBottom: '14px' }}>
                <h4 style={{ margin: '0 0 4px', fontSize: '0.92rem' }}>
                  Bảng đối chiếu nghiệp vụ chứng từ
                </h4>
                <p className="muted" style={{ margin: 0, fontSize: '0.8rem' }}>
                  Hệ thống tự động so khớp giữa Giấy đề nghị tạm ứng và Bảng dự toán chi phí.
                </p>
              </div>
              <BusinessCrossCheckTable
                report={report}
                proposal={report.b3}
                sources={effectiveSources}
                refs={refs}
              />
            </div>
          )}

          {/* TAB 3: FACTS & TRÍCH XUẤT */}
          {activeTab === 'facts' && (
            <div>
              {report?.critical_facts && report.critical_facts.length > 0 && (
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <h4 style={{ margin: '0 0 8px', fontSize: '0.92rem' }}>
                    Dữ liệu trích xuất từ hồ sơ (Critical facts)
                  </h4>
                  <div className="table-responsive">
                    <table className="facts-table-clean">
                      <thead>
                        <tr>
                          <th>Trường dữ liệu</th>
                          <th>Giá trị trích xuất</th>
                          <th>Trạng thái</th>
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
                                    ? 'MÂU THUẪN'
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
              )}

              {Boolean((report?.claim_comparisons?.length ?? 0) > 0) && (
                <div style={{ marginTop: 'var(--space-4)' }}>
                  <h4 style={{ margin: '0 0 8px', fontSize: '0.92rem' }}>
                    Đối chiếu khoản khai &amp; nguồn
                  </h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Khoản khai</th>
                        <th>Số khai</th>
                        <th>Số thực tế</th>
                        <th>Bên trả khai</th>
                        <th>Trạng thái</th>
                        <th>Căn cứ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report!.claim_comparisons!.map((c) => (
                        <tr key={c.claim_id}>
                          <td>{c.claim_id}</td>
                          <td>{vnd(c.declared_amount_vnd)}</td>
                          <td>{vnd(c.verified_amount_vnd)}</td>
                          <td>{c.payer_declaration ?? '—'}</td>
                          <td>{c.status}</td>
                          <td>{refs(c.refs)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: HỆ THỐNG & TRACE */}
          {activeTab === 'system' && (
            <div>
              <div style={{
                background: '#f8fafc',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
                padding: '14px 18px',
                marginBottom: 'var(--space-4)',
                lineHeight: '1.7',
              }}>
                <div><strong>Mã hồ sơ gốc:</strong> <code>{dossierReference(view) ?? '—'}</code></div>
                <div><strong>Mã bản ghi hệ thống:</strong> <code>{view.id}</code></div>
                <div><strong>Mã nhân viên đề nghị:</strong> <code>{view.submission.employee_ref}</code></div>
                <div><strong>Mã công việc:</strong> <code>{view.submission.work_ref}</code></div>
                <div><strong>Phiên bản dữ liệu:</strong> v{view.case_version} (rev {view.input_revision}, epoch {view.control_epoch})</div>
                {run && (
                  <div><strong>Mã lần chạy (Run ID):</strong> <code>{run.id}</code> ({run.mode})</div>
                )}
              </div>

              {run && report && (
                <ProcessingDetails run={run} report={report} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
