// B3 v1 intake form (b3-intake-v1): nơi đến/ngày/mục đích, số xin, hạn quyết
// toán và các dòng dự toán tách công ty/nhân viên. Form là lời khai — client
// chỉ hiển thị tổng preview; backend kiểm lại số liệu. Không nhập tự do
// người duyệt/mã nội bộ; persona và mã hồ sơ do hệ thống cấp.
import type { B3EstimateRow, B3Intake } from './types';

interface B3IntakeFormProps {
  value: B3Intake;
  onChange: (next: B3Intake) => void;
  disabled: boolean;
}

function sum(rows: B3EstimateRow[], side: 'company_vnd' | 'employee_vnd'):
  number | null {
  let total = 0;
  for (const row of rows) {
    const amount = row[side];
    if (amount === null) return null; // dòng chưa rõ: tổng giữ unknown
    total += amount;
  }
  return total;
}

function vnd(value: number | null): string {
  return value === null ? '— (chưa rõ)' : `${value.toLocaleString('vi-VN')} VND`;
}

export function emptyB3Intake(intakeMethod: 'WEB' | 'IMPORT'): B3Intake {
  return {
    schema_version: 'b3-intake-v1',
    intake_method: intakeMethod,
    confirmed: false,
    destination: '',
    trip_start: null,
    trip_end: null,
    purpose: '',
    assignment_note: null,
    request_amount_vnd: null,
    settlement_due: null,
    estimate_rows: [],
  };
}

let rowCounter = 0;
function nextRowId(): string {
  rowCounter += 1;
  return `row-${rowCounter}`;
}

export function B3IntakeForm({ value, onChange, disabled }: B3IntakeFormProps) {
  const update = (patch: Partial<B3Intake>) =>
    onChange({ ...value, ...patch });

  const updateRow = (rowId: string, patch: Partial<B3EstimateRow>) =>
    update({estimate_rows: value.estimate_rows.map((row) =>
      row.row_id === rowId ? { ...row, ...patch } : row)});

  const numberField = (amount: number | null): string =>
    amount === null ? '' : String(amount);

  const parseAmount = (text: string): number | null =>
    text.trim() === '' ? null : Number(text);

  const companyTotal = sum(value.estimate_rows, 'company_vnd');
  const employeeTotal = sum(value.estimate_rows, 'employee_vnd');
  const totalPreview = companyTotal !== null && employeeTotal !== null
    ? companyTotal + employeeTotal : null;

  return (
    <div data-testid="b3-intake-form" className="b3-intake-container">
      {/* SECTION 1: Thông tin chuyến công tác */}
      <div className="b3-form-section">
        <div className="b3-section-header">
          <div className="b3-section-title-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
            <div>
              <span className="b3-section-title">Thông tin chuyến công tác</span>
              <span className="b3-section-desc">Địa điểm và mục đích chuyến công tác cần tạm ứng</span>
            </div>
          </div>
          <span className="b3-section-badge">Hành trình</span>
        </div>

        <div className="form-grid-2">
          <div className="field">
            <label htmlFor="b3-destination">Nơi đến</label>
            <input id="b3-destination" value={value.destination ?? ''}
                   disabled={disabled}
                   onChange={(e) => update({destination: e.target.value})}
                   placeholder="Ví dụ: Hà Nội, Đà Nẵng, TP.HCM..." />
          </div>
          <div className="field">
            <label htmlFor="b3-purpose">Mục đích công tác</label>
            <input id="b3-purpose" value={value.purpose ?? ''} disabled={disabled}
                   onChange={(e) => update({purpose: e.target.value})}
                   placeholder="Ví dụ: Đi khảo sát yêu cầu và thống nhất phạm vi dự án..." />
          </div>
        </div>

        <div className="form-grid-2">
          <div className="field">
            <label htmlFor="b3-trip-start">Ngày đi</label>
            <input id="b3-trip-start" type="date" value={value.trip_start ?? ''}
                   disabled={disabled}
                   onChange={(e) => update({trip_start: e.target.value || null})} />
          </div>
          <div className="field">
            <label htmlFor="b3-trip-end">Ngày về</label>
            <input id="b3-trip-end" type="date" value={value.trip_end ?? ''}
                   disabled={disabled}
                   onChange={(e) => update({trip_end: e.target.value || null})} />
          </div>
        </div>
      </div>

      {/* SECTION 2: Đề nghị tạm ứng & Quyết toán */}
      <div className="b3-form-section">
        <div className="b3-section-header">
          <div className="b3-section-title-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <line x1="2" y1="10" x2="22" y2="10" />
            </svg>
            <div>
              <span className="b3-section-title">Đề nghị tạm ứng & Thời hạn</span>
              <span className="b3-section-desc">Số tiền xin ứng và kế hoạch hoàn ứng sau công tác</span>
            </div>
          </div>
          <span className="b3-section-badge">Tài chính</span>
        </div>

        <div className="form-grid-2">
          <div className="field">
            <label htmlFor="b3-request-amount">Số tiền đề nghị tạm ứng</label>
            <div className="currency-input-wrapper">
              <input id="b3-request-amount" type="number" min="0"
                     value={numberField(value.request_amount_vnd)} disabled={disabled}
                     onChange={(e) => update({request_amount_vnd: parseAmount(e.target.value)})}
                     placeholder="0" />
              <span className="currency-suffix">VND</span>
            </div>
            <span className="helper">Số tiền bạn đang xin, chưa phải tiền đã nhận</span>
            {value.request_amount_vnd !== null && value.request_amount_vnd > 0 && (
              <span className="field-hint" data-testid="b3-request-hint">
                {value.request_amount_vnd.toLocaleString('vi-VN')} đ
              </span>
            )}
          </div>
          <div className="field">
            <label htmlFor="b3-settlement-due">Hạn thanh toán tạm ứng</label>
            <input id="b3-settlement-due" type="date"
                   value={value.settlement_due ?? ''} disabled={disabled}
                   onChange={(e) => update({settlement_due: e.target.value || null})} />
            <span className="helper">Ngày dự kiến nộp chứng từ và xử lý tiền ứng</span>
          </div>
        </div>

        <div className="field" style={{ marginTop: 'var(--space-2)' }}>
          <label htmlFor="b3-assignment-note">
            Ghi chú giao việc (không bắt buộc)
          </label>
          <input id="b3-assignment-note" value={value.assignment_note ?? ''}
                 disabled={disabled}
                 placeholder="Ví dụ: Giao việc qua điện thoại, phân công công tác theo dự án..."
                 onChange={(e) => update({assignment_note: e.target.value || null})} />
        </div>
      </div>

      {/* SECTION 3: Bảng dự toán chi phí */}
      <div className="b3-form-section">
        <div className="b3-section-header">
          <div className="b3-section-title-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            <div>
              <span className="b3-section-title">Bảng dự toán chi phí</span>
              <span className="b3-section-desc">Phân tách chi tiết nguồn chi trả theo quy định tài chính</span>
            </div>
          </div>
          {!disabled && (
            <button className="btn btn-sm btn-outline-primary" type="button"
                    onClick={() => update({estimate_rows: [...value.estimate_rows, {
                      row_id: nextRowId(), description: '', basis: null,
                      company_vnd: null, employee_vnd: null,
                    }]})}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>Thêm dòng dự toán</span>
            </button>
          )}
        </div>

        <div className="table-responsive">
          <table data-testid="b3-estimate-rows" className="estimate-table estimate-table-modern">
            <thead>
              <tr>
                <th style={{ width: '34%' }}>Nội dung chi</th>
                <th style={{ width: '24%' }}>Cơ sở dự toán</th>
                <th className="text-right" style={{ width: '19%' }}>Công ty dự kiến trả</th>
                <th className="text-right" style={{ width: '19%' }}>Nhân viên dự kiến trả</th>
                {!disabled && <th style={{ width: '4%' }}></th>}
              </tr>
            </thead>
            <tbody>
              {value.estimate_rows.length === 0 ? (
                <tr>
                  <td colSpan={disabled ? 4 : 5} style={{ textAlign: 'center', padding: '24px 12px', color: 'var(--color-muted-foreground)' }}>
                    Chưa có dòng dự toán nào. {!disabled && 'Nhấn "Thêm dòng dự toán" ở trên để kê khai.'}
                  </td>
                </tr>
              ) : (
                value.estimate_rows.map((row) => (
                  <tr key={row.row_id}>
                    <td>
                      <input aria-label={`nội dung ${row.row_id}`}
                             value={row.description} disabled={disabled}
                             placeholder="Ví dụ: Vé máy bay khứ hồi..."
                             onChange={(e) => updateRow(row.row_id,
                               {description: e.target.value})} />
                    </td>
                    <td>
                      <input aria-label={`cơ sở ${row.row_id}`}
                             value={row.basis ?? ''} disabled={disabled}
                             placeholder="Theo báo giá đại lý..."
                             onChange={(e) => updateRow(row.row_id,
                               {basis: e.target.value || null})} />
                    </td>
                    <td>
                      <input aria-label={`công ty ${row.row_id}`} type="number"
                             min="0" value={numberField(row.company_vnd)}
                             disabled={disabled}
                             className="number-cell"
                             placeholder="0"
                             onChange={(e) => updateRow(row.row_id,
                               {company_vnd: parseAmount(e.target.value)})} />
                    </td>
                    <td>
                      <input aria-label={`nhân viên ${row.row_id}`} type="number"
                             min="0" value={numberField(row.employee_vnd)}
                             disabled={disabled}
                             className="number-cell"
                             placeholder="0"
                             onChange={(e) => updateRow(row.row_id,
                               {employee_vnd: parseAmount(e.target.value)})} />
                    </td>
                    {!disabled && (
                      <td style={{ textAlign: 'center' }}>
                        <button className="btn-icon-delete" type="button"
                                aria-label={`xóa dòng ${row.row_id}`}
                                title="Xóa dòng này"
                                onClick={() => update({estimate_rows:
                                  value.estimate_rows.filter((r) =>
                                    r.row_id !== row.row_id)})}>
                          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                          </svg>
                          <span className="visually-hidden">Xóa</span>
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Enterprise Financial Summary Card */}
        <div className="b3-totals-summary-bar" data-testid="b3-totals-preview">
          <div className="b3-totals-header">
            <div className="b3-totals-title-group">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              <span>Tổng hợp dự toán chi phí</span>
            </div>
            <span className="b3-totals-audit-badge">Tổng hợp dự toán kê khai (chưa phê duyệt, chưa chi tiền)</span>
          </div>

          <div className="b3-totals-cards">
            <div className="b3-totals-card">
              <span className="b3-totals-card-label">Công ty dự kiến</span>
              <span className="b3-totals-card-val">{vnd(companyTotal)}</span>
            </div>
            <div className="b3-totals-card">
              <span className="b3-totals-card-label">Nhân viên dự kiến</span>
              <span className="b3-totals-card-val">{vnd(employeeTotal)}</span>
            </div>
            <div className="b3-totals-card b3-totals-card-highlight">
              <span className="b3-totals-card-label">Tổng cộng dự toán</span>
              <span className="b3-totals-card-val">{vnd(totalPreview)}</span>
            </div>
          </div>

          <div className="b3-totals-inline-summary">
            công ty {vnd(companyTotal)} · nhân viên {vnd(employeeTotal)} · tổng {vnd(totalPreview)} (chưa duyệt, backend kiểm lại)
          </div>
        </div>
      </div>
    </div>
  );
}
