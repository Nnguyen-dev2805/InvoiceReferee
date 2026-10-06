import { useRef, useState } from 'react';
import type { CaseRecord, EvidenceRole, PayerType, Profile, PurposeType } from './types';
import { ApiError } from './api';
import { formatCurrencyInput } from './format';
import { SpinnerIcon, UploadCloudIcon } from './icons';

export interface CaseFormValues {
  profile: Profile;
  purpose_type: PurposeType;
  purpose: string;
  trip: string;
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

const PROFILE_LABELS: Record<Profile, string> = {
  TRAVEL: 'Công tác / Đi lại (TRAVEL)',
  CLIENT_MEAL: 'Tiếp khách / Ăn uống (CLIENT_MEAL)',
  WORK_PURCHASE: 'Mua sắm công việc (WORK_PURCHASE)',
  OTHER: 'Chi phí khác (OTHER)',
};

const PAYER_LABELS: Record<PayerType, string> = {
  PERSONAL: 'Cá nhân chi trả trước (PERSONAL)',
  COMPANY: 'Công ty chi trực tiếp (COMPANY)',
  ADVANCE: 'Tạm ứng công ty (ADVANCE)',
  VENDOR: 'Nhà cung cấp xuất nợ (VENDOR)',
  UNKNOWN: 'Chưa xác định (UNKNOWN)',
};

const ROLE_LABELS: Record<EvidenceRole, string> = {
  PRIMARY_BILL: 'Hoá đơn chính (PRIMARY_BILL)',
  GOODS_RECEIPT: 'Phiếu giao / Biên bản (GOODS_RECEIPT)',
  CONTEXT: 'Tài liệu bối cảnh (CONTEXT)',
};

export function CaseForm({ onCreate, onCreated }: CaseFormProps) {
  const [profile, setProfile] = useState<Profile>('TRAVEL');
  const [purposeType, setPurposeType] = useState<PurposeType>('BUSINESS');
  const [purpose, setPurpose] = useState('');
  const [trip, setTrip] = useState('');
  const [payer, setPayer] = useState<PayerType>('PERSONAL');
  const [amountText, setAmountText] = useState('');
  const [files, setFiles] = useState<{ file: File; role: EvidenceRole }[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const errorSummaryRef = useRef<HTMLDivElement>(null);

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
    if (files.length === 0) next.files = 'Cần đính kèm ít nhất một chứng từ.';
    setErrors(next);
    if (Object.keys(next).length > 0) {
      setTimeout(() => errorSummaryRef.current?.focus(), 50);
      return null;
    }
    return { amount };
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
      setTimeout(() => errorSummaryRef.current?.focus(), 50);
    } finally {
      setBusy(false);
    }
  }

  function addFiles(fileList: FileList | null | undefined) {
    if (!fileList || fileList.length === 0) return;
    const newItems: { file: File; role: EvidenceRole }[] = [];
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      if (file) {
        newItems.push({ file, role: 'PRIMARY_BILL' });
      }
    }
    setFiles((prev) => [...prev, ...newItems]);
  }

  return (
    <section className="panel" aria-labelledby="form-heading">
      <h2 id="form-heading">Nộp hồ sơ hoàn ứng</h2>
      <form onSubmit={submit} noValidate>
        {Object.keys(errors).length > 0 && (
          <div
            ref={errorSummaryRef}
            tabIndex={-1}
            className="notice notice-error error-summary"
            role="alert"
            aria-labelledby="error-summary-heading"
          >
            <div>
              <strong id="error-summary-heading">Thông tin chưa hợp lệ ({Object.keys(errors).length})</strong>
              <ul className="error-summary-list">
                {errors.purpose && <li><a href="#purpose">{errors.purpose}</a></li>}
                {errors.amount && <li><a href="#amount">{errors.amount}</a></li>}
                {errors.files && <li><a href="#files">{errors.files}</a></li>}
                {errors.form && <li>{errors.form}</li>}
              </ul>
            </div>
          </div>
        )}

        <div className="field">
          <label htmlFor="profile">Loại chi phí</label>
          <select id="profile" value={profile} onChange={(e) => setProfile(e.target.value as Profile)}>
            {PROFILES.map((p) => (
              <option key={p} value={p}>{PROFILE_LABELS[p]}</option>
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
            <option value="BUSINESS">Công việc (BUSINESS)</option>
            <option value="PERSONAL">Cá nhân (PERSONAL)</option>
            <option value="UNKNOWN">Chưa xác định (UNKNOWN)</option>
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

        <div className="field">
          <label htmlFor="payer">Người đã trả</label>
          <select id="payer" value={payer} onChange={(e) => setPayer(e.target.value as PayerType)}>
            {PAYERS.map((p) => (
              <option key={p} value={p}>{PAYER_LABELS[p]}</option>
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
            onChange={(e) => setAmountText(formatCurrencyInput(e.target.value))}
            aria-invalid={errors.amount ? true : undefined}
            aria-describedby={errors.amount ? 'amount-error' : 'amount-help'}
            placeholder="Ví dụ: 1.500.000"
          />
          <p id="amount-help" className="helper">Nhập số nguyên đồng, ví dụ 1.200.000₫.</p>
          {errors.amount && <p id="amount-error" className="field-error" role="alert">{errors.amount}</p>}
        </div>

        <fieldset className="field">
          <legend>
            Chứng từ <span aria-hidden="true">*</span>
          </legend>
          <div
            className={`dropzone ${isDragging ? 'dropzone-active' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              addFiles(e.dataTransfer.files);
            }}
          >
            <input
              id="files"
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              aria-label="Chứng từ"
              className="dropzone-input"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <div className="dropzone-inner">
              <span className="dropzone-icon" aria-hidden="true">
                <UploadCloudIcon size={32} />
              </span>
              <p className="dropzone-text">
                <strong>Nhấn để chọn tệp</strong> hoặc kéo thả tệp vào đây
              </p>
              <p className="helper" style={{ margin: 'var(--space-1) 0 0' }}>
                Hỗ trợ PDF, PNG, JPG, WEBP (nhiều tệp cùng lúc)
              </p>
            </div>
          </div>
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
                    <option key={r} value={r}>{ROLE_LABELS[r]}</option>
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
          {busy ? (
            <>
              <SpinnerIcon size={16} />
              <span>Đang nộp…</span>
            </>
          ) : (
            'Nộp hồ sơ'
          )}
        </button>
      </form>
    </section>
  );
}
