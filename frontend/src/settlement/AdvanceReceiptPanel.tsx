// B5 advance-receipt panel (b3-intake-v1).
//
// The accountant records an ACTUAL advance money event with human-source
// evidence — approval is not receipt. This panel never transfers money and
// never derives "received" from approval; it only captures the accountant's
// source-read fields. The backend owns classification/sums/stage.
//
// Two method branches (BANK_TRANSFER / CASH) capture the facts each source
// actually proves. A receipt is not recordable until the proof source is
// attached and the method-specific receiver condition is read.
import { useMemo, useState } from 'react';
import * as api from './api';
import { formatMoney } from './displayText';
import type {
  B3AdvanceReportedStatus, B3BankReceiptDetails, B3CashReceiptDetails,
  B3Person, B3ReceiptDetails, B3ReceiptSource, CaseView, DemoRole, SourceView,
} from './types';

function formatVnd(value: number | null | undefined): string {
  return formatMoney(value, { nullText: '—' });
}

// Fields always read from the source; method-specific ones are appended.
const CORE_EVIDENCE_FIELDS = [
  'amount_vnd', 'currency', 'payer_side', 'payee_ref', 'event_at',
  'receiver_outcome', 'event_namespace', 'event_ref', 'method',
  'receiver_name',
] as const;

const OTHER_PAYEE = 'OTHER';
const NONE_PAYEE = '__NONE__';

interface AdvanceReceiptProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
  people?: B3Person[];
  receiptSources?: B3ReceiptSource[];
}

export function AdvanceReceiptPanel({
  view, role, actorId, onAction, people = [], receiptSources = [],
}: AdvanceReceiptProps) {
  const workflow = view.b3_workflow ?? null;
  const decision = workflow?.decision ?? null;
  const funding = workflow?.funding ?? null;
  const events = workflow?.advance_events ?? [];
  const approved = decision?.advance_vnd ?? null;

  const [gross, setGross] = useState('');
  const [method, setMethod] =
    useState<'BANK_TRANSFER' | 'CASH'>('BANK_TRANSFER');
  const [outcome, setOutcome] = useState<B3AdvanceReportedStatus | ''>('');
  const [recipient, setRecipient] = useState('');
  const [receiverName, setReceiverName] = useState('');
  const [senderSide, setSenderSide] =
    useState<'COMPANY' | 'OTHER' | 'UNKNOWN'>('COMPANY');
  const [namespace, setNamespace] = useState('');
  const [eventRef, setEventRef] = useState('');
  const [eventAt, setEventAt] = useState('');
  const [note, setNote] = useState('');
  // Bank-only
  const [proofScope, setProofScope] =
    useState<B3BankReceiptDetails['proof_scope']>('UNCONFIRMED');
  // Cash-only
  const [voucherNumber, setVoucherNumber] = useState('');
  const [handedBy, setHandedBy] = useState('');
  const [acknowledgement, setAcknowledgement] =
    useState<B3CashReceiptDetails['acknowledgement']>('UNCONFIRMED');

  const [proofId, setProofId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isAccountant = role === 'ACCOUNTANT';
  const payable = decision?.outcome === 'APPROVE';

  const methodSources = useMemo(
    () => receiptSources.filter((s) => s.method === method),
    [receiptSources, method]);

  const grossNum = gross.trim() === '' ? null : Number(gross);
  const payeeRef = recipient === OTHER_PAYEE ? OTHER_PAYEE
    : recipient === NONE_PAYEE ? null : recipient || null;

  const canRecord = useMemo(() => {
    if (!isAccountant || !payable) return false;
    if (grossNum === null || !Number.isFinite(grossNum) || grossNum <= 0) return false;
    if (outcome === '') return false;
    if (!note.trim()) return false;
    if (outcome === 'RECEIVED') {
      // A confirmed receipt needs the proof source attached and every
      // required fact present; method-specific receiver condition included.
      if (!proofId) return false;
      if (!recipient) return false;
      if (!receiverName.trim()) return false;
      if (!namespace.trim() || !eventRef.trim() || !eventAt) return false;
      if (method === 'BANK_TRANSFER' && proofScope !== 'RECEIVER_CONFIRMED') return false;
      if (method === 'CASH') {
        if (acknowledgement !== 'ACKNOWLEDGED') return false;
        if (!voucherNumber.trim() || voucherNumber.trim() !== eventRef.trim()) return false;
      }
    }
    return true;
  }, [isAccountant, payable, grossNum, outcome, note, proofId, recipient,
      receiverName, namespace, eventRef, eventAt, method, proofScope,
      acknowledgement, voucherNumber]);

  if (!workflow || !payable) return null;

  const buildEvidence = () => {
    if (!proofId) return [];
    const values: Record<string, string | number | null> = {
      amount_vnd: grossNum, currency: 'VND', payer_side: senderSide,
      payee_ref: payeeRef, event_at: eventAt || null,
      receiver_outcome: outcome || null,
      event_namespace: namespace.trim() || null,
      event_ref: eventRef.trim() || null, method,
      receiver_name: receiverName.trim() || null,
    };
    const fields = [...CORE_EVIDENCE_FIELDS];
    return fields.filter((f) => values[f] !== null && values[f] !== undefined)
      .map((f) => ({
        field: f, source_id: proofId, locator: f,
        raw: String(values[f]), value: values[f] as number | string,
        read_state: 'READ' as const, origin: 'HUMAN_SOURCE_REVIEW' as const,
      }));
  };

  const buildDetails = (): B3ReceiptDetails | null => {
    if (method === 'BANK_TRANSFER') {
      return {
        kind: 'BANK_TRANSFER', receiver_name: receiverName.trim() || null,
        sender_name: null, bank_name: null, sender_account: null,
        recipient_bank: null, recipient_account: null, bank_status_text: null,
        proof_scope: proofScope,
      };
    }
    return {
      kind: 'CASH', voucher_number: voucherNumber.trim() || null,
      cashbook_label: namespace.trim() || null,
      handed_by_name: handedBy.trim() || null,
      receiver_name: receiverName.trim() || null,
      acknowledgement,
    };
  };

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      await onAction('B3_ADVANCE_PROOF', async () => {
        const src = await api.uploadB3AdvanceProof(
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
      await onAction('B3_ADVANCE_EVENT', () =>
        api.recordB3Advance(view.id, {
          actor_id: actorId.trim(), demo_role: role,
          expected_case_version: view.case_version,
          decision_id: decision?.id ?? null,
          event_namespace: namespace.trim() || null,
          event_ref: eventRef.trim() || null,
          method, gross_vnd: grossNum,
          payer_side: senderSide,
          payee_ref: payeeRef,
          event_at: eventAt ? new Date(eventAt).toISOString() : null,
          reported_status: outcome as B3AdvanceReportedStatus,
          evidence: buildEvidence(),
          allocation_note: note.trim(),
          supersedes_event_id: null,
          receipt_details: buildDetails(),
        }));
    } finally {
      setSubmitting(false);
    }
  };

  const sourcesForProof = (): SourceView[] => view.sources;

  return (
    <div className="panel" id="b3-funding-panel" data-testid="b3-funding-panel">
      <h2>Ghi nhận tiền ứng thực nhận</h2>
      <p className="muted">
        Kế toán đọc chứng từ và ghi sự kiện tiền đã xảy ra. Hệ thống <strong>không</strong>
        chuyển tiền và không tự xác thực ngân hàng; phê duyệt không phải đã nhận.
      </p>

      {funding && (
        <ul className="reasons" data-testid="b3-funding-summary">
          <li><strong>Số ứng đã duyệt:</strong> {formatVnd(approved)}</li>
          <li><strong>Đã ghi nhận thực nhận:</strong> {formatVnd(funding.recorded_received_vnd)}</li>
          <li><strong>Thực hiện hợp lệ:</strong> {formatVnd(funding.fulfilled_vnd)}</li>
          <li><strong>Còn lại:</strong> {formatVnd(funding.remaining_vnd)}</li>
          <li><strong>Trạng thái quỹ:</strong> {funding.status}</li>
          {funding.pending_count > 0 && (
            <li>{funding.pending_count} sự kiện đang chờ (chưa tính vào thực nhận)</li>
          )}
        </ul>
      )}

      {funding && funding.incidents.length > 0 && (
        <div className="notice notice-warn" role="alert" data-testid="b3-funding-incidents">
          {funding.incidents.map((incident, index) => (
            <p key={index}>
              <strong>{incident.kind}</strong>
              {incident.amount_vnd !== null ? ` — ${formatVnd(incident.amount_vnd)}` : ''}
              {': '}{incident.reason}
            </p>
          ))}
        </div>
      )}

      {events.length > 0 && (
        <div className="field" data-testid="b3-advance-events">
          <h3>Sự kiện đã ghi</h3>
          <ul className="reasons">
            {events.map((event) => (
              <li key={event.id}>
                <code>{event.id}</code> · {event.reported_status} ·{' '}
                {formatVnd(event.gross_vnd)} · {event.method} ·{' '}
                {event.payee_ref ?? '—'} · {event.event_ref ?? '—'}
                {event.evidence_issues.length > 0 && (
                  <span className="pill-badge pill-badge-amber" style={{ marginLeft: 6 }}>
                    Chưa đủ căn cứ
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {isAccountant && (
        <div className="field">
          <h3>Chứng từ &amp; sự kiện</h3>

          <label htmlFor="b3-funding-method">Phương thức</label>
          <select id="b3-funding-method" value={method}
                  onChange={(e) => {
                    setMethod(e.target.value as 'BANK_TRANSFER' | 'CASH');
                    // Switching method drops a support attached to the old one.
                    setProofId(null);
                    setNamespace('');
                  }}>
            <option value="BANK_TRANSFER">Chuyển khoản</option>
            <option value="CASH">Tiền mặt</option>
          </select>

          <label htmlFor="b3-proof-file">Chứng từ ứng (biên nhận ngân hàng / phiếu chi)</label>
          <input id="b3-proof-file" type="file" disabled={uploading}
                 onChange={(e) => {
                   const file = e.target.files?.[0];
                   if (file) void handleUpload(file);
                 }} />
          {proofId && (
            <p className="muted">Đã đính kèm chứng từ <code>{proofId}</code></p>
          )}

          <label htmlFor="b3-funding-gross">Số tiền nguồn ghi (VND)</label>
          <input id="b3-funding-gross" type="number" min="0" value={gross}
                 onChange={(e) => setGross(e.target.value)} />

          <label htmlFor="b3-funding-outcome">Kết quả giao dịch (theo nguồn)</label>
          <select id="b3-funding-outcome" value={outcome}
                  onChange={(e) => setOutcome(
                    e.target.value as B3AdvanceReportedStatus)}>
            <option value="">— Chọn theo nguồn —</option>
            <option value="RECEIVED">Đã nhận (RECEIVED)</option>
            <option value="PENDING">Đang chờ (PENDING)</option>
            <option value="FAILED">Thất bại (FAILED)</option>
            <option value="CANCELLED">Đã hủy (CANCELLED)</option>
            <option value="UNCONFIRMED">Chưa xác định (UNCONFIRMED)</option>
          </select>

          <label htmlFor="b3-funding-recipient">Người nhận thực tế (đọc từ nguồn)</label>
          <select id="b3-funding-recipient" value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}>
            <option value="">— Chọn theo nguồn —</option>
            {people.map((p) => (
              <option key={p.actor_ref} value={p.actor_ref}>
                {p.name}
              </option>
            ))}
            <option value={OTHER_PAYEE}>Người khác</option>
            <option value={NONE_PAYEE}>Chưa xác định</option>
          </select>

          <label htmlFor="b3-funding-receiver-name">Tên người nhận (theo nguồn)</label>
          <input id="b3-funding-receiver-name" value={receiverName}
                 onChange={(e) => setReceiverName(e.target.value)}
                 placeholder="Giữ nguyên văn tên đọc được trên chứng từ" />

          <label htmlFor="b3-funding-sender">Bên chi (theo nguồn)</label>
          <select id="b3-funding-sender" value={senderSide}
                  onChange={(e) => setSenderSide(
                    e.target.value as 'COMPANY' | 'OTHER' | 'UNKNOWN')}>
            <option value="COMPANY">Công ty</option>
            <option value="OTHER">Người khác</option>
            <option value="UNKNOWN">Chưa rõ</option>
          </select>

          <label htmlFor="b3-funding-namespace">Nguồn chi (theo cấu hình)</label>
          <select id="b3-funding-namespace" value={namespace}
                  onChange={(e) => setNamespace(e.target.value)}>
            <option value="">— Chọn nguồn chi —</option>
            {methodSources.map((s) => (
              <option key={s.namespace} value={s.namespace}>{s.label}</option>
            ))}
          </select>
          {methodSources.length === 0 && (
            <p className="review-hint">
              Chưa cấu hình nguồn chi cho phương thức này; không ghi nhận mới.
            </p>
          )}

          <label htmlFor="b3-funding-ref">
            {method === 'CASH' ? 'Mã sự kiện / số phiếu (event_ref)' : 'Mã giao dịch (event_ref)'}
          </label>
          <input id="b3-funding-ref" value={eventRef}
                 onChange={(e) => setEventRef(e.target.value)} />

          <label htmlFor="b3-funding-time">Thời điểm giao dịch</label>
          <input id="b3-funding-time" type="datetime-local" value={eventAt}
                 onChange={(e) => setEventAt(e.target.value)} />

          {method === 'BANK_TRANSFER' ? (
            <>
              <label htmlFor="b3-funding-proof-scope">Phạm vi nguồn xác nhận</label>
              <select id="b3-funding-proof-scope" value={proofScope}
                      onChange={(e) => setProofScope(
                        e.target.value as B3BankReceiptDetails['proof_scope'])}>
                <option value="UNCONFIRMED">— Chưa rõ —</option>
                <option value="ORDER_ONLY">Lệnh mới tạo</option>
                <option value="SENDER_DEBIT">Chỉ trích nợ bên gửi</option>
                <option value="RECEIVER_CONFIRMED">Đủ căn cứ người hưởng nhận</option>
              </select>
            </>
          ) : (
            <>
              <label htmlFor="b3-funding-voucher">Số phiếu chi</label>
              <input id="b3-funding-voucher" value={voucherNumber}
                     onChange={(e) => setVoucherNumber(e.target.value)} />
              <label htmlFor="b3-funding-handed-by">Người giao tiền (theo nguồn)</label>
              <input id="b3-funding-handed-by" value={handedBy}
                     onChange={(e) => setHandedBy(e.target.value)} />
              <label htmlFor="b3-funding-ack">Kết quả giao/nhận tiền mặt</label>
              <select id="b3-funding-ack" value={acknowledgement}
                      onChange={(e) => setAcknowledgement(
                        e.target.value as B3CashReceiptDetails['acknowledgement'])}>
                <option value="UNCONFIRMED">— Chưa đủ căn cứ —</option>
                <option value="ACKNOWLEDGED">Đã giao, có xác nhận nhận tiền</option>
                <option value="NOT_HANDED">Chưa giao</option>
              </select>
            </>
          )}

          <label htmlFor="b3-funding-note">Ghi chú đối chiếu</label>
          <input id="b3-funding-note" value={note}
                 onChange={(e) => setNote(e.target.value)}
                 placeholder="Đối chiếu giao dịch với đúng quyết định/công việc." />

          <button className="btn btn-primary"
                  disabled={!canRecord || submitting || uploading}
                  onClick={() => void submit()}>
            Ghi nhận kết quả thực tế
          </button>
          <p className="review-hint">
            Không tự điền “đã nhận”: ghi theo nguồn. Chưa rõ thì để trống/UNCONFIRMED.
          </p>
          {sourcesForProof().length === 0 && (
            <p className="review-hint">
              Chưa có chứng từ đính kèm; hãy tải chứng từ ứng trước khi ghi.
            </p>
          )}
        </div>
      )}

      {!isAccountant && (
        <p className="muted">
          {funding?.status === 'FULFILLED'
            ? 'Đã ghi nhận ứng — chờ quyết toán.'
            : 'Đang chờ kế toán ghi nhận tiền ứng thực nhận.'}
        </p>
      )}
    </div>
  );
}
