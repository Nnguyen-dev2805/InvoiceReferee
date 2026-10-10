// Actions panel (W05): decision, review, actual money, Stop/resume, handoff and
// closure. Approval is not receipt: approved/received/remaining and incidents
// are shown separately; gross events are never clipped to the approved amount.
import { useState } from 'react';
import * as api from './api';
import type { CaseView, DemoRole } from './types';

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
  onAction: (action: string, run: () => Promise<unknown>) => Promise<void>;
}

export function ActionsPanel({
  view,
  role,
  actorId,
  decisionId,
  reportReady,
  onAction,
}: ActionsProps) {
  const summary = view.money_summary;
  const closed = view.stage === 'SETTLEMENT_CLOSED'
    || view.stage === 'REJECTED_REQUEST_ENDED';
  // B3 v1 là nhánh intake/report: không quảng cáo decision/money/handoff/
  // closure; backend cũng chặn bằng B3_REPORT_ONLY.
  const b3V1 = (view.submission.form as Record<string, unknown>)
    ?.schema_version === 'b3-intake-v1';

  const [decisionDirection, setDecisionDirection] =
    useState<'PAY_EMPLOYEE' | 'COLLECT_FROM_EMPLOYEE' | 'REFUSE'>('PAY_EMPLOYEE');
  const [decisionAmount, setDecisionAmount] = useState('');
  const [decisionReason, setDecisionReason] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [eventRef, setEventRef] = useState('');
  const [eventKind, setEventKind] =
    useState<'PAYMENT_TO_EMPLOYEE' | 'PAYMENT_FROM_EMPLOYEE'>(
      'PAYMENT_TO_EMPLOYEE');
  const [gross, setGross] = useState('');
  const [payee, setPayee] = useState(view.submission.employee_ref);
  const [eventAt, setEventAt] = useState(nowLocalInput());
  const [eventStatus, setEventStatus] = useState<'RECEIVED' | 'PENDING'>(
    'RECEIVED');
  const [controlReason, setControlReason] = useState('');
  const [closureKind, setClosureKind] =
    useState<'SETTLEMENT_COMPLETE' | 'REJECTED_REQUEST_ENDED'>(
      'SETTLEMENT_COMPLETE');
  const [closureBasis, setClosureBasis] = useState('');

  const canDecide = reportReady && view.current_run_id !== null
    && !closed && !view.stop_active;
  const canReview = reportReady && view.current_run_id !== null && !closed;
  const canRecordMoney = !closed;
  const canHandoff = decisionId !== null && !closed && !view.stop_active;

  return (
    <div className="panel" data-testid="actions-panel">
      <h2>Hành động nghiệp vụ</h2>
      <p className="muted">
        Quyết định thuộc người có quyền, thực nhận do kế toán ghi, đóng hồ sơ là
        hành động riêng; hệ thống không chuyển tiền.
      </p>

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

      {closed ? (
        <p className="muted">
          Hồ sơ đã kết thúc ({view.stage}); chỉ đọc lại history và report.
        </p>
      ) : (
        <>
          {b3V1 ? (
            <p className="notice-warn" role="alert">
              Hồ sơ B3 v1 chỉ tạo report đề nghị; duyệt work/B/advance, ghi
              tiền và bàn giao là lifecycle riêng chưa mở ở nhánh này
              (backend chặn B3_REPORT_ONLY).
            </p>
          ) : (
          <div className="field">
            <h3>Quyết định (người duyệt)</h3>
            {role !== 'APPROVER' && (
              <p className="notice-warn" role="alert">
                Vai hiện tại không phải APPROVER; quyết định sẽ bị từ chối
                BEYOND_AUTHORITY.
              </p>
            )}
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
            <button className="btn" disabled={!canDecide || !decisionReason.trim()}
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
          )}

          <div className="field">
            <h3>Rà soát kế toán (không phải phê duyệt)</h3>
            <label htmlFor="review-note">Ghi chú rà soát</label>
            <input id="review-note" value={reviewNote}
                   onChange={(e) => setReviewNote(e.target.value)}
                   placeholder="Đã đối chiếu bảng và mở nguồn gốc." />
            <button className="btn" disabled={!canReview || !reviewNote.trim()}
                    onClick={() => void onAction('REVIEW', async () => {
                      return api.review(view.id, {
                        actor_id: actorId.trim(),
                        demo_role: role,
                        expected_case_version: view.case_version,
                        report_id: view.current_run_id ?? '',
                        note: reviewNote.trim(),
                        refs: [],
                      });
                    })}>
              Ghi review
            </button>
          </div>

          {!b3V1 && (
          <div className="field">
            <h3>Sự kiện tiền thực tế</h3>
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
            <button className="btn"
                    disabled={!canRecordMoney || !eventRef.trim() || !gross}
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
                        refs: [],
                      });
                    })}>
              Ghi sự kiện tiền
            </button>
          </div>
          )}

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
