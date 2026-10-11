// B5 advance-receipt panel (b3-intake-v1).
//
// The accountant records an ACTUAL advance money event with human-source
// evidence — approval is not receipt. This panel never transfers money and
// never derives "received" from approval; it only captures the accountant's
// source-read fields. The backend owns classification/sums/stage.
import { useMemo, useState } from 'react';
import * as api from './api';
import type {
  B3AdvanceReportedStatus, CaseView, DemoRole, SourceView,
} from './types';

function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('vi-VN')} đ`;
}

const EVIDENCE_FIELDS = [
  'amount_vnd', 'currency', 'payer_side', 'payee_ref', 'event_at',
  'receiver_outcome', 'event_namespace', 'event_ref', 'method',
] as const;

interface B3FundingProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
}

export function B3FundingPanel({ view, role, actorId, onAction }: B3FundingProps) {
  const workflow = view.b3_workflow ?? null;
  const decision = workflow?.decision ?? null;
  const funding = workflow?.funding ?? null;
  const events = workflow?.advance_events ?? [];
  const approved = decision?.advance_vnd ?? null;

  const [gross, setGross] = useState('');
  const [method, setMethod] =
    useState<'BANK_TRANSFER' | 'CASH'>('BANK_TRANSFER');
  const [outcome, setOutcome] = useState<B3AdvanceReportedStatus | ''>('');
  const [payee, setPayee] = useState('');
  const [namespace, setNamespace] = useState('');
  const [eventRef, setEventRef] = useState('');
  const [eventAt, setEventAt] = useState('');
  const [note, setNote] = useState('');
  const [proofId, setProofId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isAccountant = role === 'ACCOUNTANT';
  const payable = decision?.outcome === 'APPROVE';

  const grossNum = gross.trim() === '' ? null : Number(gross);
  const canRecord = useMemo(() => {
    if (!isAccountant || !payable) return false;
    if (grossNum === null || !Number.isFinite(grossNum) || grossNum <= 0) return false;
    if (outcome === '') return false;
    if (!note.trim()) return false;
    // RECEIVED needs the core source facts to be meaningful.
    if (outcome === 'RECEIVED') {
      if (!payee.trim() || !namespace.trim() || !eventRef.trim()) return false;
    }
    return true;
  }, [isAccountant, payable, grossNum, outcome, note, payee, namespace,
      eventRef]);

  if (!workflow || !payable) return null;

  const evidence = () => {
    if (!proofId) return [];
    const values: Record<string, string | number | null> = {
      amount_vnd: grossNum, currency: 'VND', payer_side: 'COMPANY',
      payee_ref: payee.trim() || null, event_at: eventAt || null,
      receiver_outcome: outcome || null,
      event_namespace: namespace.trim() || null,
      event_ref: eventRef.trim() || null, method,
    };
    return EVIDENCE_FIELDS.filter((f) => values[f] !== null
      && values[f] !== undefined).map((f) => ({
      field: f, source_id: proofId, locator: f,
      raw: String(values[f]), value: values[f] as number | string,
      read_state: 'READ' as const, origin: 'HUMAN_SOURCE_REVIEW' as const,
    }));
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
          payer_side: 'COMPANY',
          payee_ref: payee.trim() || null,
          event_at: eventAt ? new Date(eventAt).toISOString() : null,
          reported_status: outcome as B3AdvanceReportedStatus,
          evidence: evidence(),
          allocation_note: note.trim(),
          supersedes_event_id: null,
        }));
    } finally {
      setSubmitting(false);
    }
  };

  const sourcesForProof = (): SourceView[] => view.sources;

  return (
    <div className="panel" data-testid="b3-funding-panel">
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
              </li>
            ))}
          </ul>
        </div>
      )}

      {isAccountant && (
        <div className="field">
          <h3>Chứng từ &amp; sự kiện</h3>
          <label htmlFor="b3-proof-file">Chứng từ ứng (biên nhận ngân hàng / biên nhận cash)</label>
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

          <label htmlFor="b3-funding-method">Phương thức</label>
          <select id="b3-funding-method" value={method}
                  onChange={(e) => setMethod(
                    e.target.value as 'BANK_TRANSFER' | 'CASH')}>
            <option value="BANK_TRANSFER">Chuyển khoản</option>
            <option value="CASH">Tiền mặt</option>
          </select>

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

          <label htmlFor="b3-funding-payee">Người nhận thực tế (đọc từ nguồn)</label>
          <input id="b3-funding-payee" value={payee}
                 onChange={(e) => setPayee(e.target.value)}
                 placeholder="Điền đúng như nguồn, không mặc định theo nhân viên" />

          <label htmlFor="b3-funding-namespace">Không gian giao dịch (namespace)</label>
          <input id="b3-funding-namespace" value={namespace}
                 onChange={(e) => setNamespace(e.target.value)}
                 placeholder="BANK:DEMO-ACCOUNT" />

          <label htmlFor="b3-funding-ref">Mã giao dịch (event_ref)</label>
          <input id="b3-funding-ref" value={eventRef}
                 onChange={(e) => setEventRef(e.target.value)} />

          <label htmlFor="b3-funding-time">Thời điểm giao dịch</label>
          <input id="b3-funding-time" type="datetime-local" value={eventAt}
                 onChange={(e) => setEventAt(e.target.value)} />

          <label htmlFor="b3-funding-note">Ghi chú đối chiếu</label>
          <input id="b3-funding-note" value={note}
                 onChange={(e) => setNote(e.target.value)}
                 placeholder="Đối chiếu giao dịch với đúng quyết định/công việc." />

          <button className="btn btn-primary"
                  disabled={!canRecord || submitting || uploading}
                  onClick={() => void submit()}>
            Ghi nhận sự kiện ứng
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
