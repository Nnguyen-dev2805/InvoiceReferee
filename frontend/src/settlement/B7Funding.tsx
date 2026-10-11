// B9 settlement-fulfillment panel (b7-linked-intake-v1).
//
// The accountant records ACTUAL settlement money (company pays the employee;
// the employee returns an advance/reimbursement) from a retained source, then
// reconciles it against the approved decision. Approval != receipt != closure.
// The backend owns classification/sums/remaining/rights; this panel never
// calculates them or transfers money.
import { useMemo, useState } from 'react';
import * as api from './api';
import type {
  B7MoneyPurpose, B7ReportedStatus, CaseView, DemoRole,
} from './types';

function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('vi-VN')} đ`;
}

const EVIDENCE_FIELDS = [
  'amount_vnd', 'currency', 'payer_ref', 'payee_ref', 'event_at',
  'receiver_outcome', 'event_namespace', 'event_ref', 'method', 'purpose',
] as const;

interface B7FundingProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
}

export function B7FundingPanel({ view, role, actorId, onAction }: B7FundingProps) {
  const workflow = view.b7_workflow ?? null;
  const decision = workflow?.decision ?? null;
  const fulfillment = workflow?.fulfillment ?? null;
  const revalidation = workflow?.revalidation ?? null;
  const handoff = workflow?.current_handoff ?? null;
  const closure = workflow?.closure ?? null;
  const approved = decision?.outcome === 'APPROVE' ? decision.target : null;
  const direction = approved?.direction ?? null;
  const isAccountant = role === 'ACCOUNTANT';
  const payable = Boolean(approved) && direction !== 'BALANCED';

  const [gross, setGross] = useState('');
  const [method, setMethod] =
    useState<'BANK_TRANSFER' | 'CASH'>('BANK_TRANSFER');
  const [status, setStatus] = useState<B7ReportedStatus | ''>('');
  const [purpose, setPurpose] = useState<B7MoneyPurpose | ''>('');
  const [payee, setPayee] = useState('');
  const [payer, setPayer] = useState('');
  const [namespace, setNamespace] = useState('');
  const [eventRef, setEventRef] = useState('');
  const [eventAt, setEventAt] = useState('');
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [proofId, setProofId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const grossNum = gross.trim() === '' ? null : Number(gross);
  const canRecord = useMemo(() => {
    if (!isAccountant || !payable) return false;
    if (grossNum === null || !Number.isFinite(grossNum) || grossNum <= 0) return false;
    if (status === '' || purpose === '') return false;
    if (!note.trim()) return false;
    if (status === 'RECEIVED') {
      if (!payee.trim() || !payer.trim() || !namespace.trim() || !eventRef.trim()) {
        return false;
      }
    }
    return true;
  }, [isAccountant, payable, grossNum, status, purpose, note, payee, payer,
      namespace, eventRef]);

  if (!workflow) return null;

  const evidence = () => {
    if (!proofId) return [];
    const values: Record<string, string | number | null> = {
      amount_vnd: grossNum, currency: 'VND', payer_ref: payer.trim() || null,
      payee_ref: payee.trim() || null, event_at: eventAt || null,
      receiver_outcome: status || null,
      event_namespace: namespace.trim() || null,
      event_ref: eventRef.trim() || null, method, purpose: purpose || null,
    };
    return EVIDENCE_FIELDS.filter((f) => values[f] !== null
      && values[f] !== undefined).map((f) => ({
      field: f, source_id: proofId, locator: f, raw: String(values[f]),
      value: values[f] as number | string, read_state: 'READ' as const,
      origin: 'HUMAN_SOURCE_REVIEW' as const,
    }));
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await onAction('B7_SETTLEMENT_PROOF', async () => {
        const src = await api.uploadB7Proof(
          view.id, file, view.case_version, actorId.trim(), role, note.trim());
        setProofId(src.id);
        return src;
      });
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      await onAction('B7_RECORD_MONEY', () =>
        api.recordB7Money(view.id, {
          actor_id: actorId.trim(), demo_role: role,
          expected_case_version: view.case_version,
          decision_id: decision?.id ?? null,
          event_namespace: namespace.trim() || null,
          event_ref: eventRef.trim() || null, method, gross_vnd: grossNum,
          payer_ref: payer.trim() || null, payee_ref: payee.trim() || null,
          event_at: eventAt ? new Date(eventAt).toISOString() : null,
          reported_status: status as B7ReportedStatus,
          purpose: purpose as B7MoneyPurpose,
          evidence: evidence(),
          allocation_note: note.trim(), supersedes_event_id: null,
        }));
    } finally {
      setSubmitting(false);
    }
  };

  // --- Closed: read-only banner + accountant adjustment ----------------------
  if (closure) {
    return (
      <div className="panel" data-testid="b7-funding-panel">
        <h2>Quyết toán đã đóng</h2>
        <ul className="reasons">
          <li><strong>Đóng lúc (as-of):</strong> {closure.close_as_of}</li>
          <li><strong>Quyết định gốc:</strong> <code>{closure.original_decision_id}</code></li>
          <li><strong>Lý do:</strong> {closure.reason}</li>
        </ul>
        {isAccountant && (
          <div className="field">
            <label htmlFor="b7-adjust-reason">Lý do mở hồ sơ điều chỉnh</label>
            <input id="b7-adjust-reason" value={reason}
                   onChange={(e) => setReason(e.target.value)}
                   placeholder="Có khoản chi/nguồn mới sau khi đóng." />
            <button className="btn" disabled={!reason.trim()}
                    onClick={() => void onAction('B7_ADJUSTMENT', () =>
                      api.prepareB7Adjustment(view.id, {
                        actor_id: actorId.trim(), demo_role: role,
                        expected_case_version: view.case_version,
                        reason: reason.trim(),
                      }))}>
              Tạo hồ sơ điều chỉnh
            </button>
          </div>
        )}
      </div>
    );
  }

  if (!approved) return null;

  const remainingLabel = direction === 'COLLECT_FROM_EMPLOYEE'
    ? 'Còn phải thu từ nhân viên' : 'Còn phải chi cho nhân viên';

  return (
    <div className="panel" data-testid="b7-funding-panel">
      <h2>Đối chiếu chi/thu quyết toán</h2>
      <p className="muted">
        Kế toán đọc chứng từ và ghi sự kiện tiền đã xảy ra; hệ thống{' '}
        <strong>không</strong> chuyển tiền và không tự xác thực ngân hàng.
        Phê duyệt không phải đã nhận.
      </p>

      <ul className="reasons" data-testid="b7-fulfillment-summary">
        <li><strong>Đã duyệt:</strong> {formatVnd(fulfillment?.approved_vnd ?? approved.amount_vnd)}</li>
        <li>
          <strong>{direction === 'COLLECT_FROM_EMPLOYEE'
            ? 'Công ty đã nhận' : 'Đã đối chiếu thực nhận'}:</strong>{' '}
          {formatVnd(fulfillment?.recorded_received_vnd ?? null)}
        </li>
        <li><strong>{remainingLabel}:</strong> {formatVnd(fulfillment?.remaining_vnd ?? null)}</li>
        <li><strong>Trạng thái:</strong> {fulfillment?.status ?? '—'}</li>
        {fulfillment && fulfillment.pending_count > 0 && (
          <li>{fulfillment.pending_count} sự kiện đang chờ (chưa tính vào thực nhận)</li>
        )}
      </ul>

      {revalidation && (
        <p className="muted" data-testid="b7-revalidation">
          Kiểm tra lại: <strong>{revalidation.status}</strong>
          {revalidation.blocked_reasons.length > 0
            ? ` — ${revalidation.blocked_reasons.join('; ')}` : ''}
        </p>
      )}

      {fulfillment && fulfillment.incidents.length > 0 && (
        <div className="notice notice-warn" role="alert" data-testid="b7-fulfillment-incidents">
          {fulfillment.incidents.map((incident, index) => (
            <p key={index}>
              <strong>{incident.code}</strong>
              {incident.excess_vnd !== null ? ` — ${formatVnd(incident.excess_vnd)}` : ''}
              {': '}{incident.reason}
            </p>
          ))}
        </div>
      )}

      {handoff && (
        <div className="field" data-testid="b7-handoff">
          <h3>Gói bàn giao</h3>
          <p className="muted">
            Còn phải thực hiện <strong>{formatVnd(handoff.remaining_vnd)}</strong> ·{' '}
            {handoff.direction} · gói <code>{handoff.id}</code>
          </p>
        </div>
      )}

      {isAccountant && (
        <>
          {payable && (
          <div className="field">
            <h3>Chứng từ &amp; sự kiện tiền</h3>
            <label htmlFor="b7-proof-file">Chứng từ (biên nhận ngân hàng / biên nhận cash)</label>
            <input id="b7-proof-file" type="file" disabled={uploading}
                   onChange={(e) => {
                     const file = e.target.files?.[0];
                     if (file) void handleUpload(file);
                   }} />
            {proofId && (
              <p className="muted">Đã đính kèm chứng từ <code>{proofId}</code></p>
            )}

            <label htmlFor="b7-money-gross">Số tiền nguồn ghi (VND)</label>
            <input id="b7-money-gross" type="number" min="0" value={gross}
                   onChange={(e) => setGross(e.target.value)} />

            <label htmlFor="b7-money-method">Phương thức</label>
            <select id="b7-money-method" value={method}
                    onChange={(e) => setMethod(
                      e.target.value as 'BANK_TRANSFER' | 'CASH')}>
              <option value="BANK_TRANSFER">Chuyển khoản</option>
              <option value="CASH">Tiền mặt</option>
            </select>

            <label htmlFor="b7-money-status">Kết quả giao dịch (theo nguồn)</label>
            <select id="b7-money-status" value={status}
                    onChange={(e) => setStatus(e.target.value as B7ReportedStatus)}>
              <option value="">— Chọn theo nguồn —</option>
              <option value="RECEIVED">Đã nhận (RECEIVED)</option>
              <option value="PENDING">Đang chờ (PENDING)</option>
              <option value="FAILED">Thất bại (FAILED)</option>
              <option value="CANCELLED">Đã hủy (CANCELLED)</option>
              <option value="UNCONFIRMED">Chưa xác định (UNCONFIRMED)</option>
            </select>

            <label htmlFor="b7-money-purpose">Nguồn nghĩa vụ</label>
            <select id="b7-money-purpose" value={purpose}
                    onChange={(e) => setPurpose(e.target.value as B7MoneyPurpose)}>
              <option value="">— Chọn theo nghĩa vụ —</option>
              <option value="REIMBURSEMENT_RECEIVED">Công ty trả thêm (P)</option>
              <option value="ADVANCE_RETURN">Nhân viên hoàn ứng (RA)</option>
              <option value="REIMBURSEMENT_RETURN">Nhân viên trả lại hoàn trả (RP)</option>
              <option value="UNKNOWN">Chưa rõ (giữ vướng mắc)</option>
            </select>

            <label htmlFor="b7-money-payer">Bên trả (đọc từ nguồn)</label>
            <input id="b7-money-payer" value={payer}
                   onChange={(e) => setPayer(e.target.value)}
                   placeholder="COMPANY hoặc mã nhân viên" />

            <label htmlFor="b7-money-payee">Bên nhận (đọc từ nguồn)</label>
            <input id="b7-money-payee" value={payee}
                   onChange={(e) => setPayee(e.target.value)}
                   placeholder="Điền đúng như nguồn, không mặc định theo nhân viên" />

            <label htmlFor="b7-money-namespace">Không gian giao dịch (namespace)</label>
            <input id="b7-money-namespace" value={namespace}
                   onChange={(e) => setNamespace(e.target.value)}
                   placeholder="BANK:DEMO-ACCOUNT" />

            <label htmlFor="b7-money-ref">Mã giao dịch (event_ref)</label>
            <input id="b7-money-ref" value={eventRef}
                   onChange={(e) => setEventRef(e.target.value)} />

            <label htmlFor="b7-money-time">Thời điểm giao dịch</label>
            <input id="b7-money-time" type="datetime-local" value={eventAt}
                   onChange={(e) => setEventAt(e.target.value)} />

            <label htmlFor="b7-money-note">Ghi chú đối chiếu</label>
            <input id="b7-money-note" value={note}
                   onChange={(e) => setNote(e.target.value)}
                   placeholder="Đối chiếu giao dịch với đúng quyết định/công việc." />

            <button className="btn btn-primary"
                    disabled={!canRecord || submitting || uploading}
                    onClick={() => void submit()}>
              Ghi nhận kết quả thực tế
            </button>
          </div>
          )}

          <div className="field">
            <button className="btn" disabled={submitting}
                    onClick={() => void onAction('B7_REFRESH_MONEY', () =>
                      api.refreshB7MoneyContext(view.id, {
                        actor_id: actorId.trim(), demo_role: role,
                        expected_case_version: view.case_version,
                      }))}>
              Cập nhật đối chiếu tiền và kiểm tra lại
            </button>
            <button className="btn" disabled={submitting}
                    onClick={() => void onAction('B7_REVALIDATE', () =>
                      api.revalidateB7(view.id, {
                        actor_id: actorId.trim(), demo_role: role,
                        expected_case_version: view.case_version,
                      }))}>
              Kiểm tra lại quyết định
            </button>
            {payable && (
              <button className="btn" disabled={submitting || !fulfillment
                || fulfillment.remaining_vnd === null || fulfillment.remaining_vnd <= 0}
                      onClick={() => void onAction('B7_HANDOFF', () =>
                        api.handoffB7(view.id, {
                          actor_id: actorId.trim(), demo_role: role,
                          expected_case_version: view.case_version,
                          decision_id: decision?.id ?? '',
                          reason: 'Bàn giao phần còn lại',
                        }))}>
                Xem gói bàn giao
              </button>
            )}
            <button className="btn" disabled={submitting}
                    onClick={() => void onAction('B7_CLOSE', () =>
                      api.closeB7(view.id, {
                        actor_id: actorId.trim(), demo_role: role,
                        expected_case_version: view.case_version,
                        decision_id: decision?.id ?? '',
                        current_report_id: view.current_run_id ?? '',
                        reason: note.trim() || 'Đủ căn cứ, hết nghĩa vụ',
                      }))}>
              Đóng hồ sơ quyết toán
            </button>
          </div>
        </>
      )}

      {!isAccountant && (
        <p className="muted">
          {role === 'EMPLOYEE'
            ? `Bạn cần ${direction === 'COLLECT_FROM_EMPLOYEE' ? 'hoàn lại' : 'nhận'} `
              + `${formatVnd(fulfillment?.remaining_vnd ?? approved.amount_vnd)}; `
              + 'tiến độ do kế toán đối chiếu.'
            : 'Người duyệt xem quyết định và lịch sử; không thao tác ghi tiền.'}
        </p>
      )}
    </div>
  );
}
