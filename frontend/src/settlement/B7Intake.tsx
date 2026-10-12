// B6→B7 linked settlement intake panel (b7-linked-intake-v1).
//
// The employee declares ACTUAL expenses for a linked B7 child of their B3
// work. Declarations are statements, never payment facts; the panel never
// prefills a forecast as actual. Work/employee/link are readonly server facts.
import { useState } from 'react';
import * as api from './api';
import type {
  B7ClaimRow, B7DeclaredPayer, B7LinkedIntake, CaseView, DemoRole, Report,
} from './types';

function formatVnd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value.toLocaleString('vi-VN')} đ`;
}

let claimSeq = 0;
function newClaimId(): string {
  claimSeq += 1;
  return `CL-${Date.now().toString(36)}-${claimSeq}`;
}

interface B7IntakeProps {
  view: CaseView;
  report: Report | null;
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
  // Runs the actual reconciliation. Confirming intake only saves the
  // declaration; it must not imply an automatic run that does not exist.
  onRunCheck?: () => Promise<void>;
}

function emptyIntake(): B7LinkedIntake {
  return { schema_version: 'b7-linked-intake-v1', confirmed: false,
           expense_rows: [], note: null };
}

export function B7IntakePanel({ view, report, role, actorId, onAction, onRunCheck }: B7IntakeProps) {
  const link = view.linked_b7 ?? null;
  const form = view.submission.form as unknown as B7LinkedIntake;
  const [intake, setIntake] = useState<B7LinkedIntake>(
    form?.schema_version === 'b7-linked-intake-v1' ? form : emptyIntake());
  const [saving, setSaving] = useState(false);

  if (!link) return null;

  const isEmployee = role === 'EMPLOYEE'
    && actorId.trim() === view.submission.employee_ref;
  const confirmed = intake.confirmed;

  const addRow = () => {
    setIntake((prev) => ({
      ...prev,
      expense_rows: [...prev.expense_rows, {
        claim_id: newClaimId(), description: '', expense_date: null,
        declared_amount_vnd: null, purpose: '', declared_payer: 'UNKNOWN',
        source_ids: [], payment_statement: null,
      }],
    }));
  };
  const removeRow = (claimId: string) => {
    setIntake((prev) => ({
      ...prev,
      expense_rows: prev.expense_rows.filter((r) => r.claim_id !== claimId),
    }));
  };
  const updateRow = (claimId: string, patch: Partial<B7ClaimRow>) => {
    setIntake((prev) => ({
      ...prev,
      expense_rows: prev.expense_rows.map((r) =>
        r.claim_id === claimId ? { ...r, ...patch } : r),
    }));
  };

  const amountNum = (raw: string): number | null => {
    if (raw.trim() === '') return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  };

  const save = (confirm: boolean) => {
    setSaving(true);
    const next: B7LinkedIntake = { ...intake, confirmed: confirm };
    void onAction(confirm ? 'B7_CONFIRM' : 'B7_SAVE', () =>
      api.reviseLinkedB7(view.id, {
        actor_id: actorId.trim(), demo_role: role,
        expected_case_version: view.case_version, intake: next,
      })).finally(() => setSaving(false));
  };

  const canConfirm = isEmployee && !saving
    && intake.expense_rows.length > 0
    && intake.expense_rows.every((r) => r.description.trim() !== '');

  return (
    <div className="panel" data-testid="b7-intake-panel">
      <h2>Quyết toán liên kết — {view.submission.employee_ref}</h2>
      <div className="review-summary-card" data-testid="b7-origin-link">
        <div className="review-summary-line">
          Công việc <code>{link.origin.work_ref}</code> · hồ sơ gốc{' '}
          <code>{link.origin.origin_case_id}</code> · ứng đã ghi nhận{' '}
          {formatVnd(link.managed_advance_subtotal_vnd)}
        </div>
      </div>
      <p className="muted">
        Khai chi phí <strong>thực tế</strong> đã phát sinh. Số dự toán và số ứng
        đã duyệt không tự thành chi phí thực tế; khai báo không phải bằng chứng
        thanh toán.
      </p>

      {confirmed && (
        <div className="notice notice-info" role="status">
          <p style={{ margin: 0 }}>
            Đã xác nhận nộp. {report ? 'Report đã có.' : 'Chưa chạy đối soát.'}
          </p>
          {isEmployee && !report && onRunCheck && (
            <button className="btn btn-primary btn-sm" style={{ marginTop: 'var(--space-2)' }}
                    onClick={() => void onRunCheck()}>
              Chạy kiểm tra đối soát
            </button>
          )}
        </div>
      )}

      <div className="field" data-testid="b7-claim-rows">
        <h3>Khoản chi thực tế ({intake.expense_rows.length})</h3>
        {intake.expense_rows.map((row) => (
          <div key={row.claim_id} className="b7-claim-row"
               data-testid={`claim-row-${row.claim_id}`}
               style={{ borderTop: '1px solid var(--color-border, #e2e8f0)',
                        paddingTop: 'var(--space-2)',
                        marginTop: 'var(--space-2)' }}>
            <label htmlFor={`desc-${row.claim_id}`}>Nội dung</label>
            <input id={`desc-${row.claim_id}`} value={row.description}
                   disabled={!isEmployee || confirmed}
                   onChange={(e) => updateRow(row.claim_id,
                     { description: e.target.value })} />
            <label htmlFor={`amt-${row.claim_id}`}>Số khai (VND)</label>
            <input id={`amt-${row.claim_id}`} type="number" min="0"
                   value={row.declared_amount_vnd ?? ''}
                   disabled={!isEmployee || confirmed}
                   onChange={(e) => updateRow(row.claim_id,
                     { declared_amount_vnd: amountNum(e.target.value) })} />
            <label htmlFor={`payer-${row.claim_id}`}>Bên trả (khai báo)</label>
            <select id={`payer-${row.claim_id}`}
                    value={row.declared_payer}
                    disabled={!isEmployee || confirmed}
                    onChange={(e) => updateRow(row.claim_id,
                      { declared_payer: e.target.value as B7DeclaredPayer })}>
              <option value="PERSONAL">Cá nhân tự trả</option>
              <option value="COMPANY">Công ty trả</option>
              <option value="UNKNOWN">Chưa rõ</option>
            </select>
            <label htmlFor={`purpose-${row.claim_id}`}>Mục đích/phạm vi</label>
            <input id={`purpose-${row.claim_id}`} value={row.purpose}
                   disabled={!isEmployee || confirmed}
                   onChange={(e) => updateRow(row.claim_id,
                     { purpose: e.target.value })} />
            {isEmployee && !confirmed && (
              <button className="btn btn-sm"
                      onClick={() => removeRow(row.claim_id)}>Xóa dòng</button>
            )}
          </div>
        ))}
        {isEmployee && !confirmed && (
          <button className="btn" onClick={addRow}
                  style={{ marginTop: 'var(--space-2)' }}>
            Thêm khoản chi
          </button>
        )}
      </div>

      {isEmployee && !confirmed && (
        <div style={{ display: 'flex', gap: 'var(--space-2)',
                      marginTop: 'var(--space-2)' }}>
          <button className="btn" disabled={saving}
                  onClick={() => save(false)}>
            Lưu nháp
          </button>
          <button className="btn btn-primary" disabled={!canConfirm}
                  onClick={() => save(true)}>
            Xác nhận nộp
          </button>
        </div>
      )}
      {!isEmployee && (
        <p className="muted">
          Chỉ nhân viên <strong>{view.submission.employee_ref}</strong> khai báo
          chi phí thực tế của mình.
        </p>
      )}
    </div>
  );
}
