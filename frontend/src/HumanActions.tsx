import { useEffect, useMemo, useRef, useState } from 'react';
import type { CaseRecord, Decision, DemoMode, HumanAction, HumanActionKind } from './types';
import { formatCurrencyInput, formatVnd, MODE_LABEL, MODE_ORDER } from './format';

interface HumanActionsProps {
  caseRecord: CaseRecord;
  decision: Decision;
  onAction: (action: HumanAction) => Promise<void>;
  currentRole?: DemoMode;
  onRoleChange?: (mode: DemoMode) => void;
}

// Which action kinds each demo mode may perform. This mirrors the backend's
// role/scope contract for presentation only — the backend still validates.
const MODE_KINDS: Record<DemoMode, HumanActionKind[]> = {
  EMPLOYEE: ['SUPPLY_DECLARATION', 'ADD_EVIDENCE', 'PROPOSE_CORRECTION'],
  REVIEWER: ['CONFIRM_FIELD', 'CONFIRM_MAPPING'],
  APPROVER: ['APPROVE_AMOUNT', 'DENY'],
};

const KIND_LABEL: Record<HumanActionKind, string> = {
  SUPPLY_DECLARATION: 'Bổ sung khai báo',
  ADD_EVIDENCE: 'Bổ sung chứng từ',
  PROPOSE_CORRECTION: 'Đề xuất chỉnh sửa',
  CONFIRM_FIELD: 'Xác nhận dữ kiện',
  CONFIRM_MAPPING: 'Xác nhận đối chiếu dòng hàng',
  APPROVE_AMOUNT: 'Duyệt số tiền',
  DENY: 'Từ chối',
  STOP: 'Dừng',
  OVERRIDE: 'Ghi đè',
};

export function HumanActions({
  caseRecord,
  decision,
  onAction,
  currentRole,
  onRoleChange,
}: HumanActionsProps) {
  const openIssue = decision.issues.find((issue) => issue.status === 'OPEN') ?? decision.issues[0];
  const issueOwner = openIssue?.owner_mode;
  // Default to current selected role if given, or the role the backend assigned to the issue.
  const [mode, setMode] = useState<DemoMode>(currentRole ?? issueOwner ?? 'EMPLOYEE');

  // Keep in sync with parent role if parent updates it
  useEffect(() => {
    if (currentRole && currentRole !== mode) {
      setMode(currentRole);
      setKind(MODE_KINDS[currentRole][0]);
    }
  }, [currentRole]);

  const kinds = MODE_KINDS[mode];
  const [kind, setKind] = useState<HumanActionKind>(kinds[0]);
  const [reason, setReason] = useState('');
  const [value, setValue] = useState('');
  const [field, setField] = useState('total');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  function changeMode(next: DemoMode) {
    setMode(next);
    setKind(MODE_KINDS[next][0]); // the current kind may not exist for the new role
    setError(null);
    onRoleChange?.(next);
  }

  const needsAmount = kind === 'APPROVE_AMOUNT';
  const needsField = kind === 'CONFIRM_FIELD' || kind === 'PROPOSE_CORRECTION';

  const payload = useMemo<Record<string, unknown>>(() => {
    if (needsAmount) {
      const parsed = Number(value.replace(/[^\d]/g, ''));
      return {
        amount_vnd: Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 0,
        profile: caseRecord.claim.profile,
        purpose: caseRecord.claim.purpose,
        policy_version: '',
      };
    }
    if (needsField) {
      return { field, value, refs: [] };
    }
    return {};
  }, [kind, value, field, caseRecord, needsAmount, needsField]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!reason.trim()) {
      setError('Cần lý do để thực hiện hành động.');
      setTimeout(() => errorRef.current?.focus(), 50);
      return;
    }
    if (needsAmount) {
      const amount = payload.amount_vnd;
      if (typeof amount !== 'number' || !Number.isSafeInteger(amount) || amount <= 0) {
        setError('Số tiền phải là số nguyên dương (VND).');
        setTimeout(() => errorRef.current?.focus(), 50);
        return;
      }
    }
    setError(null);
    setBusy(true);
    try {
      await onAction({
        case_version: caseRecord.case_version,
        issue_id: openIssue?.id ?? null,
        mode,
        kind,
        payload,
        reason: reason.trim(),
      });
      setReason('');
      setValue('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gửi hành động thất bại.');
      setTimeout(() => errorRef.current?.focus(), 50);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="actions-heading">
      <h2 id="actions-heading">Xử lý hồ sơ</h2>
      <p className="muted">
        Đăng nhập demo — một người có thể chuyển vai trò. Hệ thống vẫn kiểm tra
        quyền của từng hành động.
        {issueOwner && issueOwner !== mode && ` Vấn đề hiện thuộc ${MODE_LABEL[issueOwner]}.`}
      </p>
      {!openIssue && (
        <p className="muted">
          Hồ sơ hiện không có câu hỏi mở. Chỉ nên dùng hành động khi có vấn đề cần
          xử lý; hành động không hợp lệ sẽ bị hệ thống từ chối.
        </p>
      )}

      {decision.accepted_amount_vnd !== null && (
        <p className="muted">Số tiền đang xem xét: {formatVnd(decision.accepted_amount_vnd)}</p>
      )}

      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="action-mode">Vai trò (demo)</label>
          <select
            id="action-mode"
            value={mode}
            onChange={(event) => changeMode(event.target.value as DemoMode)}
          >
            {MODE_ORDER.map((option) => (
              <option key={option} value={option}>
                {MODE_LABEL[option]}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="action-kind">Hành động</label>
          <select
            id="action-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as HumanActionKind)}
          >
            {kinds.map((option) => (
              <option key={option} value={option}>
                {KIND_LABEL[option]}
              </option>
            ))}
          </select>
        </div>

        {needsAmount && (
          <div className="field">
            <label htmlFor="action-amount">Số tiền (VND)</label>
            <input
              id="action-amount"
              inputMode="numeric"
              value={value}
              onChange={(event) => setValue(formatCurrencyInput(event.target.value))}
              aria-describedby="action-amount-help"
              placeholder="0"
            />
            <p id="action-amount-help" className="helper">
              Nhập số nguyên đồng, ví dụ 2.000.000₫.
            </p>
          </div>
        )}

        {needsField && (
          <>
            <div className="field">
              <label htmlFor="action-field">Trường dữ kiện</label>
              <input
                id="action-field"
                value={field}
                onChange={(event) => setField(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="action-value">Giá trị xác nhận</label>
              <input
                id="action-value"
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="action-reason">
            Lý do <span aria-hidden="true">*</span>
          </label>
          <textarea
            id="action-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-describedby="action-reason-help"
            aria-invalid={error ? true : undefined}
          />
          <p id="action-reason-help" className="helper">
            Lý do được lưu vào nhật ký kiểm toán.
          </p>
        </div>

        {error && (
          <div
            ref={errorRef}
            tabIndex={-1}
            className="notice notice-error"
            role="alert"
            style={{ marginBottom: 'var(--space-3)' }}
          >
            <p className="field-error" style={{ margin: 0 }}>
              {error}
            </p>
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Đang gửi…' : 'Gửi'}
        </button>
      </form>
    </section>
  );
}
