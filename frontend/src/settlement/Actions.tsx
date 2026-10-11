// Actions panel (W05): decision, review, actual money, Stop/resume, handoff and
// closure. Approval is not receipt: approved/received/remaining and incidents
// are shown separately; gross events are never clipped to the approved amount.
import { useEffect, useState } from 'react';
import * as api from './api';
import { B3ApprovalPanel } from './B3Approval';
import { B3FundingPanel } from './B3Funding';
import { B7IntakePanel } from './B7Intake';
import { B7CompanyContextPanel } from './B7CompanyContext';
import { B7ApprovalPanel } from './B7Approval';
import { B7FundingPanel } from './B7Funding';
import type { AuditEntry, CaseView, DemoRole, Report } from './types';

function formatVnd(value: number | null): string {
  return value === null ? '—' : `${value.toLocaleString('vi-VN')} VND`;
}

function nowLocalInput(): string {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

interface ActionsProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  decisionId: string | null;
  reportReady: boolean;
  report?: Report | null;
  history?: AuditEntry[];
  onAction: (action: string, run: () => Promise<unknown>) => Promise<void>;
}

export function ActionsPanel({
  view,
  role,
  actorId,
  decisionId,
  reportReady,
  report,
  history,
  onAction,
}: ActionsProps) {
  const summary = view.money_summary;
  const closed = view.stage === 'SETTLEMENT_CLOSED'
    || view.stage === 'REJECTED_REQUEST_ENDED';
  // B3 v1 là nhánh intake/report: không quảng cáo decision/money/handoff/
  // closure; backend cũng chặn bằng B3_REPORT_ONLY.
  const b3V1 = view.job === 'B3'
    || (view.submission.form as Record<string, unknown>)?.schema_version === 'b3-intake-v1';

  const suggestedAmount = report?.proposed_net_vnd !== null && report?.proposed_net_vnd !== undefined
    ? String(Math.abs(report.proposed_net_vnd))
    : '';
  const suggestedDirection = report?.direction === 'EMPLOYEE_TO_COMPANY'
    ? 'COLLECT_FROM_EMPLOYEE'
    : 'PAY_EMPLOYEE';

  const [decisionDirection, setDecisionDirection] =
    useState<'PAY_EMPLOYEE' | 'COLLECT_FROM_EMPLOYEE' | 'REFUSE'>(suggestedDirection);
  const [decisionAmount, setDecisionAmount] = useState(suggestedAmount);
  const [decisionReason, setDecisionReason] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewRefs, setReviewRefs] = useState<string[]>([]);
  const [eventRef, setEventRef] = useState('');
  const [eventKind, setEventKind] =
    useState<'PAYMENT_TO_EMPLOYEE' | 'PAYMENT_FROM_EMPLOYEE'>('PAYMENT_TO_EMPLOYEE');
  const [gross, setGross] = useState('');
  const [payee, setPayee] = useState(view.submission.employee_ref);
  const [eventAt, setEventAt] = useState(nowLocalInput());
  const [eventStatus, setEventStatus] = useState<'RECEIVED' | 'PENDING'>('RECEIVED');
  const [receiptRefs, setReceiptRefs] = useState<string[]>([]);
  const [controlReason, setControlReason] = useState('');
  const [closureKind, setClosureKind] =
    useState<'SETTLEMENT_COMPLETE' | 'REJECTED_REQUEST_ENDED'>('SETTLEMENT_COMPLETE');
  const [closureBasis, setClosureBasis] = useState('');

  // Keep suggested decision amount updated when report arrives
  useEffect(() => {
    if (report?.proposed_net_vnd !== null && report?.proposed_net_vnd !== undefined && !decisionAmount) {
      setDecisionAmount(String(Math.abs(report.proposed_net_vnd)));
    }
    if (report?.direction && decisionDirection === 'PAY_EMPLOYEE') {
      setDecisionDirection(
        report.direction === 'EMPLOYEE_TO_COMPANY' ? 'COLLECT_FROM_EMPLOYEE' : 'PAY_EMPLOYEE'
      );
    }
  }, [report]);

  const canDecide = reportReady && view.current_run_id !== null
    && !closed && !view.stop_active;
  const canReview = reportReady && view.current_run_id !== null && !closed;
  const canRecordMoney = !closed;
  const canHandoff = decisionId !== null && !closed && !view.stop_active;

  // Tìm bản ghi review gần nhất của kế toán để trình người duyệt / hiển thị tóm tắt
  const latestReview = history?.filter(
    (h) => h.kind === 'REVIEW_RECORDED' || h.operation === 'RECORD_REVIEW'
  ).slice(-1)[0];

  const latestReviewNote = latestReview
    ? String(
        latestReview.detail?.note ??
        (latestReview.detail?.review as Record<string, unknown> | undefined)?.note ??
        ''
      )
    : '';
  const latestReviewReportId = latestReview
    ? String(
        latestReview.detail?.report_id ??
        (latestReview.detail?.review as Record<string, unknown> | undefined)?.report_id ??
        view.current_run_id ??
        ''
      )
    : '';
  const latestReviewTime = latestReview?.occurred_at
    ? (() => {
        try {
          const d = new Date(latestReview.occurred_at);
          return isNaN(d.getTime()) ? latestReview.occurred_at : d.toLocaleString('vi-VN');
        } catch {
          return latestReview.occurred_at;
        }
      })()
    : '';

  return (
    <div className="panel" data-testid="actions-panel">
      <h2>Hành động nghiệp vụ</h2>
      <p className="muted">
        Quyết định thuộc người có quyền, thực nhận do kế toán ghi, đóng hồ sơ là
        hành động riêng; hệ thống không chuyển tiền.
      </p>

      {b3V1 && (
        <B3ApprovalPanel
          view={view}
          report={report ?? null}
          history={history ?? []}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {b3V1 && view.b3_workflow?.decision?.outcome === 'APPROVE' && (
        <B3FundingPanel
          view={view}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {b3V1 && view.b3_workflow?.decision?.outcome === 'APPROVE'
        && role === 'EMPLOYEE'
        && actorId.trim() === view.submission.employee_ref && (
        <div className="field" data-testid="b7-prepare-block">
          <h3>Quyết toán</h3>
          <p className="muted">
            Mở hồ sơ quyết toán liên kết cho công việc này để khai chi phí thực tế.
          </p>
          <button className="btn btn-primary"
                  onClick={() => void onAction('B7_PREPARE',
                    () => api.prepareLinkedB7(view.id, {
                      actor_id: actorId.trim(), demo_role: role,
                      expected_case_version: view.case_version,
                    }))}>
            Chuẩn bị hồ sơ quyết toán
          </button>
        </div>
      )}

      {view.linked_b7 && (
        <B7IntakePanel
          view={view}
          report={report ?? null}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {view.linked_b7 && (
        <B7CompanyContextPanel
          view={view}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {view.linked_b7 && (
        <B7ApprovalPanel
          view={view}
          report={report ?? null}
          history={history ?? []}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {view.linked_b7 && view.b7_workflow?.decision?.outcome === 'APPROVE' && (
        <B7FundingPanel
          view={view}
          role={role}
          actorId={actorId}
          onAction={onAction}
        />
      )}

      {/* Tình trạng tiền chỉ áp dụng cho B7, ẩn trên B3 */}
      {!b3V1 && (
        <>
          <h3>Tình trạng tiền</h3>
          <ul className="reasons" data-testid="money-summary">
            <li>
              <strong>Đã duyệt (approved):</strong> {formatVnd(summary?.approved_vnd ?? null)}
            </li>
            <li>
              <strong>Thực nhận (received):</strong> {formatVnd(summary?.received_vnd ?? null)}
              {(summary?.pending_events ?? 0) > 0 &&
                ` — còn ${summary.pending_events} sự kiện PENDING`}
            </li>
            <li>
              <strong>Còn lại (remaining):</strong> {formatVnd(summary?.remaining_vnd ?? null)}
            </li>
          </ul>
          {(summary?.incidents?.length ?? 0) > 0 && (
            <div className="notice notice-warn" role="alert">
              {summary.incidents.map((incident, index) => (
                <p key={index}>
                  Incident <strong>{incident.kind}</strong>
                  {incident.excess_vnd !== null
                    ? ` — vượt mức duyệt ${formatVnd(incident.excess_vnd)}` : ''}
                  {incident.event_ref ? ` — sự kiện ${incident.event_ref}` : ''}
                  {incident.payee_ref ? ` — người nhận ${incident.payee_ref}` : ''}
                  ; giữ gross, không tự sửa thành đúng.
                </p>
              ))}
            </div>
          )}
        </>
      )}

      {closed ? (
        <p className="muted">
          Hồ sơ đã kết thúc ({view.stage}); chỉ đọc lại history và report.
        </p>
      ) : role === 'EMPLOYEE' ? (
        <div className="notice notice-info" role="status" style={{ marginTop: 'var(--space-4)' }}>
          <p>
            👤 <strong>Góc nhìn Nhân viên:</strong> Bạn đang theo dõi tiến độ hồ sơ của mình.
            Các thao tác rà soát kế toán, phê duyệt và thanh toán do Người có thẩm quyền và Kế toán thực hiện.
          </p>
        </div>
      ) : (
        <>
          {role === 'ACCOUNTANT' ? (
            /* ================= GIAO DIỆN KẾ TOÁN (KT01, KT02, KT03) ================= */
            <>
              {/* 1. Rà soát kế toán ưu tiên hàng đầu (B7; B3 dùng panel trình duyệt) */}
              {!b3V1 && (
              <div className="field" id="accountant-review-section">
                <h3>Rà soát kế toán (không phải phê duyệt)</h3>
                <p className="muted" style={{ fontSize: '0.85rem' }}>
                  Kế toán đối soát các bảng tính với chứng từ gốc và ghi nhận ý kiến trước khi trình duyệt.
                </p>

                {latestReview && (
                  <div className="review-summary-card" data-testid="accountant-review-summary">
                    <div className="review-summary-line">
                      <strong>Kế toán đã rà soát</strong> · <span>{latestReview.actor_id}</span> · <span>{latestReviewTime}</span> · <span>Ghi chú: <em>"{latestReviewNote}"</em></span> · <span>Căn cứ report <code>{latestReviewReportId || '—'}</code></span>
                    </div>
                  </div>
                )}

                <label htmlFor="review-note">Ghi chú rà soát</label>
                <input id="review-note" value={reviewNote}
                       onChange={(e) => setReviewNote(e.target.value)}
                       placeholder="Đã đối chiếu bảng và mở nguồn gốc." />
                {view.sources.length > 0 && (
                  <div style={{ marginTop: 'var(--space-2)' }}>
                    <label>Tài liệu căn cứ rà soát</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      {view.sources.map((src) => (
                        <label key={src.id} className="helper" style={{ fontSize: '0.85rem' }}>
                          <input
                            type="checkbox"
                            checked={reviewRefs.includes(src.id)}
                            onChange={(e) => {
                              setReviewRefs(e.target.checked
                                ? [...reviewRefs, src.id]
                                : reviewRefs.filter(id => id !== src.id));
                            }}
                          />{' '}
                          {src.filename} (<code>{src.id}</code>)
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                <button className="btn btn-primary" disabled={!canReview || !reviewNote.trim()}
                        style={{ marginTop: 'var(--space-2)' }}
                        onClick={() => void onAction('REVIEW', async () => {
                          return api.review(view.id, {
                            actor_id: actorId.trim(),
                            demo_role: role,
                            expected_case_version: view.case_version,
                            report_id: view.current_run_id ?? '',
                            note: reviewNote.trim(),
                            refs: reviewRefs,
                          });
                        })}>
                  Lưu kết quả rà soát
                </button>
                {!reviewNote.trim() && (
                  <p className="review-hint" data-testid="review-note-hint">
                    Vui lòng nhập ghi chú rà soát để lưu kết quả.
                  </p>
                )}
              </div>
              )}

              {/* 2. Cảnh báo quyền phê duyệt cho Kế toán (chỉ hiển thị cho B7; ẩn form quyết định của Approver khỏi góc nhìn Kế toán trên B3) */}
              {!b3V1 && (
                <div className="field" style={{ opacity: 0.85 }}>
                  <h3>Quyết định (người duyệt)</h3>
                  <p className="notice-warn" role="alert">
                    Vai hiện tại không phải APPROVER; quyết định sẽ bị từ chối
                    BEYOND_AUTHORITY.
                  </p>
                  <p className="muted" style={{ fontSize: '0.85rem' }}>
                    Thẩm quyền ban hành quyết định chi/thu thuộc về Người duyệt (APPROVER).
                    Sau khi Người duyệt ban hành quyết định, Kế toán sẽ thực hiện ghi nhận sự kiện thực tế bên dưới.
                  </p>
                </div>
              )}


              {/* 3. Sự kiện tiền thực tế (Biên nhận / Phiếu chi) - Chỉ hiện cho B7 */}
              {!b3V1 && (
                <div className="field">
                  <h3>Sự kiện tiền thực tế (Biên nhận / Phiếu chi)</h3>
                  <div style={{ padding: 'var(--space-3)', background: 'var(--color-muted, #f1f5f9)', borderRadius: 'var(--radius)', marginBottom: 'var(--space-3)', fontSize: '0.85rem' }}>
                    <div><strong>Căn cứ quyết định duyệt:</strong> {decisionId ? `Quyết định ${decisionId}` : 'Chưa có quyết định được duyệt'}</div>
                    <div style={{ marginTop: '2px', color: 'var(--color-muted-foreground)' }}>
                      Đã duyệt: <strong>{formatVnd(summary?.approved_vnd ?? null)}</strong> · Thực nhận: <strong>{formatVnd(summary?.received_vnd ?? null)}</strong> · Còn lại: <strong>{formatVnd(summary?.remaining_vnd ?? null)}</strong>
                    </div>
                  </div>

                  <label htmlFor="event-ref">Mã sự kiện (event_ref, duy nhất)</label>
                  <input id="event-ref" value={eventRef}
                         onChange={(e) => setEventRef(e.target.value)}
                         placeholder="EV-01" />
                  <label htmlFor="event-kind">Loại</label>
                  <select id="event-kind" value={eventKind}
                          onChange={(e) => setEventKind(
                            e.target.value as 'PAYMENT_TO_EMPLOYEE'
                              | 'PAYMENT_FROM_EMPLOYEE')}>
                    <option value="PAYMENT_TO_EMPLOYEE">Chi cho nhân viên</option>
                    <option value="PAYMENT_FROM_EMPLOYEE">Nhận từ nhân viên</option>
                  </select>
                  <label htmlFor="event-gross">Số gross (VND, giữ nguyên)</label>
                  <input id="event-gross" type="number" min="0" value={gross}
                         onChange={(e) => setGross(e.target.value)} />
                  <label htmlFor="event-payee">Người nhận</label>
                  <input id="event-payee" value={payee}
                         onChange={(e) => setPayee(e.target.value)} />
                  <label htmlFor="event-at">Thời điểm sự kiện</label>
                  <input id="event-at" type="datetime-local" value={eventAt}
                         onChange={(e) => setEventAt(e.target.value)} />
                  <label htmlFor="event-status">Trạng thái khai báo</label>
                  <select id="event-status" value={eventStatus}
                          onChange={(e) => setEventStatus(
                            e.target.value as 'RECEIVED' | 'PENDING')}>
                    <option value="RECEIVED">Đã thực nhận</option>
                    <option value="PENDING">Đang chờ (không tính vào received)</option>
                  </select>

                  {view.sources.length > 0 && (
                    <div style={{ marginTop: 'var(--space-2)' }}>
                      <label>Chứng từ thanh toán đính kèm</label>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        {view.sources.map((src) => (
                          <label key={src.id} className="helper" style={{ fontSize: '0.85rem' }}>
                            <input
                              type="checkbox"
                              checked={receiptRefs.includes(src.id)}
                              onChange={(e) => {
                                setReceiptRefs(e.target.checked
                                  ? [...receiptRefs, src.id]
                                  : receiptRefs.filter(id => id !== src.id));
                              }}
                            />{' '}
                            {src.filename} (<code>{src.id}</code>)
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  <button className="btn"
                          disabled={!canRecordMoney || !eventRef.trim() || !gross}
                          style={{ marginTop: 'var(--space-3)' }}
                          onClick={() => void onAction('RECORD_MONEY', async () => {
                            return api.recordMoney(view.id, {
                              actor_id: actorId.trim(),
                              demo_role: role,
                              expected_case_version: view.case_version,
                              event_ref: eventRef.trim(),
                              kind: eventKind,
                              gross_vnd: Number(gross),
                              decision_id: decisionId,
                              payee_ref: payee.trim(),
                              event_at: new Date(eventAt).toISOString(),
                              reported_status: eventStatus,
                              refs: receiptRefs,
                            });
                          })}>
                    Ghi sự kiện tiền
                  </button>
                </div>
              )}
            </>
          ) : b3V1 ? (
            /* ================= NGƯỜI DUYỆT B3 V1 ================= */
            null
          ) : (
            /* ================= GIAO DIỆN NGƯỜI DUYỆT (AP01, AP02, AP03) ================= */
            <>
              {/* 1. Gói trình phê duyệt & Tóm tắt đề xuất */}
              <div className="field">
                <div style={{ padding: 'var(--space-3)', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 'var(--radius)', marginBottom: 'var(--space-3)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <strong>Gói trình phê duyệt</strong>
                    <span className="badge" style={{ background: '#dcfce7', color: '#15803d' }}>
                      Quyền hạn: APPROVER hợp lệ
                    </span>
                  </div>
                  <div style={{ fontSize: '0.88rem', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div>Số tiền đề xuất từ Report: <strong>{formatVnd(report?.proposed_net_vnd ?? null)}</strong></div>
                    <div>Chiều tiền đề xuất: <strong>{report?.direction === 'EMPLOYEE_TO_COMPANY' ? 'Thu lại từ nhân viên' : report?.direction === 'COMPANY_TO_EMPLOYEE' ? 'Duyệt chi cho nhân viên' : 'Cân bằng (0 VND)'}</strong></div>
                    <div>Căn cứ báo cáo: <code>{view.current_run_id ?? '—'}</code></div>
                  </div>
                </div>

                {/* 2. Ý kiến rà soát của Kế toán */}
                <div style={{ padding: 'var(--space-3)', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 'var(--radius)', marginBottom: 'var(--space-3)' }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                    Ý kiến rà soát của Kế toán
                  </div>
                  {latestReview ? (
                    <div style={{ fontSize: '0.85rem' }}>
                      <div>Kế toán: <strong>{latestReview.actor_id}</strong> ({latestReviewTime})</div>
                      <div>Ghi chú: <em>"{latestReviewNote}"</em></div>
                      {Array.isArray(latestReview.detail?.refs) && latestReview.detail.refs.length > 0 && (
                        <div>Căn cứ tài liệu: <code>{latestReview.detail.refs.join(', ')}</code></div>
                      )}
                      {latestReviewReportId && (
                        <div>Căn cứ report: <code>{latestReviewReportId}</code></div>
                      )}
                    </div>
                  ) : (
                    <div style={{ fontSize: '0.85rem', color: 'var(--color-muted-foreground)' }}>
                      Chưa có bản ghi rà soát kế toán chính thức cho hồ sơ này.
                    </div>
                  )}
                </div>

                {/* 3. Form ban hành quyết định */}
                <h3>Quyết định (người duyệt)</h3>
                <label htmlFor="decision-direction">Loại quyết định</label>
                <select id="decision-direction" value={decisionDirection}
                        onChange={(e) => setDecisionDirection(
                          e.target.value as 'PAY_EMPLOYEE' | 'COLLECT_FROM_EMPLOYEE'
                            | 'REFUSE')}>
                  <option value="PAY_EMPLOYEE">Duyệt chi cho nhân viên</option>
                  <option value="COLLECT_FROM_EMPLOYEE">
                    Thu lại từ nhân viên (S âm — nhân viên hoàn)
                  </option>
                  <option value="REFUSE">Từ chối (không duyệt số tiền)</option>
                </select>
                {decisionDirection !== 'REFUSE' && (
                  <>
                    <label htmlFor="decision-amount">Số tiền duyệt/thu (VND)</label>
                    <input id="decision-amount" type="number" min="0"
                           value={decisionAmount}
                           onChange={(e) => setDecisionAmount(e.target.value)} />
                  </>
                )}
                <label htmlFor="decision-reason">Lý do</label>
                <input id="decision-reason" value={decisionReason}
                       onChange={(e) => setDecisionReason(e.target.value)}
                       placeholder="Duyệt theo report R-…; không đè số report." />
                <button className="btn btn-primary" disabled={!canDecide || !decisionReason.trim()}
                        style={{ marginTop: 'var(--space-2)' }}
                        onClick={() => void onAction('DECIDE', async () => {
                          return api.decide(view.id, {
                            actor_id: actorId.trim(),
                            demo_role: role,
                            expected_case_version: view.case_version,
                            kind: 'SETTLEMENT',
                            amount_vnd: decisionDirection !== 'REFUSE'
                              ? Number(decisionAmount) : null,
                            direction: decisionDirection,
                            reason: decisionReason.trim(),
                            basis_report_id: view.current_run_id ?? '',
                            conditions: [],
                            exception_of: null,
                          });
                        })}>
                  Ghi quyết định (basis {view.current_run_id ?? '—'})
                </button>
              </div>
            </>
          )}

          {/* Điều khiển Stop / Resume dùng chung */}
          <div className="field">
            <h3>Stop / Resume</h3>
            <label htmlFor="control-reason">Lý do control</label>
            <input id="control-reason" value={controlReason}
                   onChange={(e) => setControlReason(e.target.value)} />
            <button className="btn"
                    disabled={view.stop_active || !controlReason.trim()}
                    onClick={() => void onAction('STOP', async () => {
                      return api.controlCase(view.id, {
                        actor_id: actorId.trim(),
                        demo_role: role,
                        expected_case_version: view.case_version,
                        action: 'STOP',
                        reason: controlReason.trim(),
                      });
                    })}>
              Stop hồ sơ
            </button>
            <button className="btn" disabled={!view.stop_active}
                    onClick={() => void onAction('RESUME', async () => {
                      return api.controlCase(view.id, {
                        actor_id: actorId.trim(),
                        demo_role: role,
                        expected_case_version: view.case_version,
                        action: 'RESUME',
                        reason: controlReason.trim(),
                      });
                    })}>
              Resume (epoch {view.control_epoch} → {view.control_epoch + 1})
            </button>
          </div>

          {canHandoff && !b3V1 && (
            <div className="field">
              <h3>Bàn giao thủ quỹ (stage A)</h3>
              <button className="btn"
                      onClick={() => void onAction('HANDOFF', async () => {
                        return api.handoff(view.id, {
                          actor_id: actorId.trim(),
                          demo_role: role,
                          expected_case_version: view.case_version,
                          decision_id: decisionId ?? '',
                        });
                      })}>
                Tạo handoff cho quyết định {decisionId}
              </button>
            </div>
          )}

          {!b3V1 && (
          <div className="field">
            <h3>Đóng hồ sơ</h3>
            <label htmlFor="closure-kind">Kiểu đóng</label>
            <select id="closure-kind" value={closureKind}
                    onChange={(e) => setClosureKind(
                      e.target.value as 'SETTLEMENT_COMPLETE'
                        | 'REJECTED_REQUEST_ENDED')}>
              <option value="SETTLEMENT_COMPLETE">Quyết toán hoàn tất</option>
              <option value="REJECTED_REQUEST_ENDED">
                Yêu cầu bị từ chối — kết thúc
              </option>
            </select>
            <label htmlFor="closure-basis">Căn cứ đóng</label>
            <input id="closure-basis" value={closureBasis}
                   onChange={(e) => setClosureBasis(e.target.value)}
                   placeholder="S=0 theo report; remaining 0; không còn incident." />
            <button className="btn" disabled={!closureBasis.trim()}
                    onClick={() => void onAction('CLOSE_CASE', async () => {
                      return api.closeCase(view.id, {
                        actor_id: actorId.trim(),
                        demo_role: role,
                        expected_case_version: view.case_version,
                        kind: closureKind,
                        basis: closureBasis.trim(),
                      });
                    })}>
              Đóng hồ sơ
            </button>
          </div>
          )}
        </>
      )}
    </div>
  );
}
