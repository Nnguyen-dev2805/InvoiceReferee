// B6→B7 company context panel (Task 2).
//
// The accountant records the source-backed company packet (whole-work
// coverage + actual events/expenses) that closes A/RA/P/RP. The employee sees
// a readonly card. This panel never edits budget/rights and never fabricates a
// row; absence is unknown, not zero.
import { useState } from 'react';
import * as api from './api';
import type { CaseView, DemoRole } from './types';

interface B7CompanyContextProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  onAction: (label: string, run: () => Promise<unknown>) => Promise<void>;
}

const DEFAULT_PACKET = {
  schema_version: 'b7-company-packet-v1',
  coverage: {
    employee_ref: '', work_ref: null,
    from: '2026-10-01T00:00:00+07:00', to: '2026-10-14T23:59:59+07:00',
    complete_prior_history: false,
    groups: ['ADVANCE', 'ADVANCE_RETURN', 'REIMBURSEMENT_RECEIVED',
             'REIMBURSEMENT_RETURN', 'COMPANY_DIRECT', 'DUPLICATE_CLAIMS'],
    methods: ['CASH', 'BANK_TRANSFER', 'OTHER_COMPANY_CHANNELS'],
    missing_ranges: [], owner_ref: '', origin: '', ref: '',
  },
  events: [], expenses: [], refs: [], reading_note: '',
};

export function B7CompanyContextPanel({
  view, role, actorId, onAction,
}: B7CompanyContextProps) {
  const link = view.linked_b7 ?? null;
  const [json, setJson] = useState('');
  const [busy, setBusy] = useState(false);
  if (!link) return null;

  const isAccountant = role === 'ACCOUNTANT';

  const record = () => {
    let packet: unknown;
    try {
      packet = JSON.parse(json);
    } catch {
      return; // invalid JSON: do nothing, keep the text for the user to fix
    }
    setBusy(true);
    void onAction('B7_COMPANY_CONTEXT', () =>
      api.recordB7CompanyPacket(view.id, {
        actor_id: actorId.trim(), demo_role: role,
        expected_case_version: view.case_version, packet,
      })).finally(() => setBusy(false));
  };

  return (
    <div className="panel" id="b7-company-context-panel" data-testid="b7-company-context">
      <h2>Dữ liệu công ty (coverage &amp; thực tế)</h2>
      <p className="muted">
        Kế toán cung cấp nguồn sổ công ty cho toàn công việc: coverage tới mốc
        quyết toán, các sự kiện tiền và chi phí thực tế có căn cứ. Vắng dòng là
        <strong> chưa rõ</strong>, không phải 0. Không sửa ngân sách/quyền ở đây.
      </p>
      <ul className="reasons" data-testid="b7-context-status">
        <li><strong>Coverage hiện hành:</strong> {link.context_current ? 'Đã cập nhật' : 'Chưa có / cần làm mới'}</li>
        <li><strong>Ứng đã ghi nhận (managed):</strong> {link.managed_advance_subtotal_vnd === null ? '—' : `${link.managed_advance_subtotal_vnd.toLocaleString('vi-VN')} đ`}</li>
      </ul>

      {isAccountant ? (
        <div className="field">
          <label htmlFor="b7-packet-json">
            Company packet (JSON có nhãn nghiệp vụ — demo import)
          </label>
          <textarea id="b7-packet-json" rows={8} value={json}
                    placeholder={JSON.stringify(DEFAULT_PACKET, null, 2)}
                    onChange={(e) => setJson(e.target.value)} />
          <button className="btn btn-primary" disabled={busy || !json.trim()}
                  onClick={record}>
            Ghi company context
          </button>
        </div>
      ) : (
        <p className="muted">
          Dữ liệu công ty do kế toán cung cấp; nhân viên chỉ xem.
        </p>
      )}
    </div>
  );
}
