import { useState } from 'react';
import type { CaseRecord, EvidenceRole, PayerType, Profile, PurposeType } from './types';
import { ApiError } from './api';

export interface CaseFormValues {
  profile: Profile;
  purpose_type: PurposeType;
  purpose: string;
  trip: string;
  attendees: string;
  payer_type: PayerType;
  amountText: string;
  files: { file: File; role: EvidenceRole }[];
}

interface CaseFormProps {
  onCreate: (form: FormData) => Promise<CaseRecord>;
  onCreated: (record: CaseRecord) => void;
}

const PROFILES: Profile[] = ['TRAVEL', 'CLIENT_MEAL', 'WORK_PURCHASE', 'OTHER'];
const PAYERS: PayerType[] = ['PERSONAL', 'COMPANY', 'ADVANCE', 'VENDOR', 'UNKNOWN'];
const ROLES: EvidenceRole[] = ['PRIMARY_BILL', 'GOODS_RECEIPT', 'CONTEXT'];

export function CaseForm({ onCreate, onCreated }: CaseFormProps) {
  const [profile, setProfile] = useState<Profile>('TRAVEL');
  const [purposeType, setPurposeType] = useState<PurposeType>('BUSINESS');
  const [purpose, setPurpose] = useState('');
  const [trip, setTrip] = useState('');
  const [attendees, setAttendees] = useState('');
  const [payer, setPayer] = useState<PayerType>('PERSONAL');
  const [amountText, setAmountText] = useState('');
  const [files, setFiles] = useState<{ file: File; role: EvidenceRole }[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function validate(): { amount: number } | null {
    const next: Record<string, string> = {};
    const digits = amountText.replace(/[^\d]/g, '');
    const amount = Number(digits);
    if (!digits) {
      next.amount = 'Cần nhập số tiền đề nghị.';
    } else if (!Number.isSafeInteger(amount) || amount <= 0) {
      next.amount = 'Số tiền phải là số nguyên dương (VND).';
    }
    if (!purpose.trim()) next.purpose = 'Cần nêu mục đích công việc.';
    if (profile === 'CLIENT_MEAL' && !attendees.trim()) {
      next.attendees = 'Tiếp khách cần nêu người tham dự.';
    }
    if (files.length === 0) next.files = 'Cần đính kèm ít nhất một chứng từ.';
    setErrors(next);
    return Object.keys(next).length === 0 ? { amount } : null;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const valid = validate();
    if (!valid) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append(
        'claim_json',
        JSON.stringify({
          employee_id: 'demo-employee',
          profile,
          purpose_type: purposeType,
          purpose: purpose.trim(),
          trip: trip.trim(),
          attendees: attendees ? attendees.split(',').map((a) => a.trim()).filter(Boolean) : [],
          requested_amount_vnd: valid.amount,
          payer_type: payer,
          received_full: profile === 'WORK_PURCHASE' ? true : null,
        }),
      );
      form.append('roles', JSON.stringify(files.map((f) => f.role)));
      files.forEach(({ file }) => form.append('files', file));
      const record = await onCreate(form);
      onCreated(record);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Tạo hồ sơ thất bại.';
      setErrors({ form: message });
    } finally {
      setBusy(false);
    }
  }

  function addFile(file: File | undefined) {
    if (!file) return;
    setFiles((prev) => [...prev, { file, role: 'PRIMARY_BILL' }]);
  }

  return (
    <section className="panel" aria-labelledby="form-heading">
      <h2 id="form-heading">Nộp hồ sơ hoàn ứng</h2>
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="profile">Loại chi phí</label>
          <select id="profile" value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
            {PROFILES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="purpose-type">Mục đích</label>
          <select
            id="purpose-type"
            value={purposeType}
            onChange={(e) => setPurposeType(e.target.value as PurposeType)}
          >
            <option value="BUSINESS">Công việc</option>
            <option value="PERSONAL">Cá nhân</option>
            <option value="UNKNOWN">Chưa rõ</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="purpose">
            Nội dung công việc <span aria-hidden="true">*</span>
          </label>
          <input
            id="purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            aria-invalid={errors.purpose ? true : undefined}
            aria-describedby={errors.purpose ? 'purpose-error' : undefined}
          />
          {errors.purpose && (
            <p id="purpose-error" className="field-error" role="alert">{errors.purpose}</p>
          )}
        </div>

        <div className="field">
          <label htmlFor="trip">Chuyến đi / ghi chú</label>
          <input id="trip" value={trip} onChange={(e) => setTrip(e.target.value)} />
        </div>

        {profile === 'CLIENT_MEAL' && (
          <div className="field">
            <label htmlFor="attendees">Người tham dự (phẩy phân cách)</label>
            <input
              id="attendees"
              value={attendees}
              onChange={(e) => setAttendees(e.target.value)}
              aria-invalid={errors.attendees ? true : undefined}
            />
            {errors.attendees && <p className="field-error" role="alert">{errors.attendees}</p>}
          </div>
        )}

        <div className="field">
          <label htmlFor="payer">Người đã trả</label>
          <select id="payer" value={payer} onChange={(e) => setPayer(e.target.value as PayerType)}>
            {PAYERS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="amount">
            Số tiền đề nghị (VND) <span aria-hidden="true">*</span>
          </label>
          <input
            id="amount"
            inputMode="numeric"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            aria-invalid={errors.amount ? true : undefined}
            aria-describedby={errors.amount ? 'amount-error' : 'amount-help'}
          />
          <p id="amount-help" className="helper">Nhập số nguyên đồng, ví dụ 1200000.</p>
          {errors.amount && <p id="amount-error" className="field-error" role="alert">{errors.amount}</p>}
        </div>

        <fieldset className="field">
          <legend>
            Chứng từ <span aria-hidden="true">*</span>
          </legend>
          <input
            id="files"
            type="file"
            multiple
            onChange={(e) => {
              addFile(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
          <ul className="file-list">
            {files.map((entry, index) => (
              <li key={index}>
                <span>{entry.file.name}</span>
                <label htmlFor={`role-${index}`} className="visually-hidden">
                  Vai trò của {entry.file.name}
                </label>
                <select
                  id={`role-${index}`}
                  value={entry.role}
                  onChange={(e) =>
                    setFiles((prev) =>
                      prev.map((item, i) =>
                        i === index ? { ...item, role: e.target.value as EvidenceRole } : item,
                      ),
                    )
                  }
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setFiles((prev) => prev.filter((_, i) => i !== index))}
                >
                  Bỏ
                </button>
              </li>
            ))}
          </ul>
          {errors.files && <p className="field-error" role="alert">{errors.files}</p>}
        </fieldset>

        {errors.form && <p className="field-error" role="alert">{errors.form}</p>}

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Đang nộp…' : 'Nộp hồ sơ'}
        </button>
      </form>
    </section>
  );
}
