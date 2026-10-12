// B3 v1 intake form (b3-intake-v1): nơi đến/ngày/mục đích, số xin, hạn quyết
// toán và các dòng dự toán tách công ty/nhân viên. Form là lời khai — client
// chỉ hiển thị tổng preview; backend kiểm lại số liệu. Không nhập tự do
// người duyệt/mã nội bộ; persona và mã hồ sơ do hệ thống cấp.
import type { B3EstimateRow, B3Intake } from './types';
import { formatMoney } from './displayText';

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
  return formatMoney(value, { nullText: '— (chưa rõ)' });
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
    <div data-testid="b3-intake-form" className="swiss-intake-form">
      {/* PHẦN 1: Thông tin chuyến công tác */}
      <section className="swiss-form-section">
        <div className="swiss-section-header">
          <h3 className="swiss-section-title">1. Thông tin chuyến công tác</h3>
        </div>

        <div className="swiss-grid-2">
          <div className="swiss-field">
            <label htmlFor="b3-destination" className="swiss-label">Nơi đến</label>
            <input
              id="b3-destination"
              className="swiss-input"
              value={value.destination ?? ''}
              disabled={disabled}
              onChange={(e) => update({ destination: e.target.value })}
            />
          </div>
          <div className="swiss-field">
            <label htmlFor="b3-purpose" className="swiss-label">Mục đích công tác</label>
            <input
              id="b3-purpose"
              className="swiss-input"
              value={value.purpose ?? ''}
              disabled={disabled}
              onChange={(e) => update({ purpose: e.target.value })}
            />
          </div>
        </div>

        <div className="swiss-grid-2">
          <div className="swiss-field">
            <label htmlFor="b3-trip-start" className="swiss-label">Ngày đi</label>
            <input
              id="b3-trip-start"
              type="date"
              className="swiss-input"
              value={value.trip_start ?? ''}
              disabled={disabled}
              onChange={(e) => update({ trip_start: e.target.value || null })}
            />
          </div>
          <div className="swiss-field">
            <label htmlFor="b3-trip-end" className="swiss-label">Ngày về</label>
            <input
              id="b3-trip-end"
              type="date"
              className="swiss-input"
              value={value.trip_end ?? ''}
              disabled={disabled}
              onChange={(e) => update({ trip_end: e.target.value || null })}
            />
          </div>
        </div>
      </section>

      {/* PHẦN 2: Đề nghị tạm ứng & Thời hạn */}
      <section className="swiss-form-section">
        <div className="swiss-section-header">
          <h3 className="swiss-section-title">2. Đề nghị tạm ứng & Thời hạn</h3>
        </div>

        <div className="swiss-grid-2">
          <div className="swiss-field">
            <label htmlFor="b3-request-amount" className="swiss-label">Số tiền đề nghị tạm ứng</label>
            <div className="swiss-currency-wrap">
              <input
                id="b3-request-amount"
                type="number"
                min="0"
                className="swiss-input swiss-currency-input"
                value={numberField(value.request_amount_vnd)}
                disabled={disabled}
                onChange={(e) => update({ request_amount_vnd: parseAmount(e.target.value) })}
              />
              <span className="swiss-currency-badge">VND</span>
            </div>
            {value.request_amount_vnd !== null && value.request_amount_vnd > 0 && (
              <span className="swiss-field-hint" data-testid="b3-request-hint">
                {value.request_amount_vnd.toLocaleString('vi-VN')} đ
              </span>
            )}
          </div>
          <div className="swiss-field">
            <label htmlFor="b3-settlement-due" className="swiss-label">Hạn thanh toán tạm ứng</label>
            <input
              id="b3-settlement-due"
              type="date"
              className="swiss-input"
              value={value.settlement_due ?? ''}
              disabled={disabled}
              onChange={(e) => update({ settlement_due: e.target.value || null })}
            />
          </div>
        </div>

        <div className="swiss-field" style={{ marginTop: '8px' }}>
          <label htmlFor="b3-assignment-note" className="swiss-label">
            Ghi chú giao việc (không bắt buộc)
          </label>
          <input
            id="b3-assignment-note"
            className="swiss-input"
            value={value.assignment_note ?? ''}
            disabled={disabled}
            onChange={(e) => update({ assignment_note: e.target.value || null })}
          />
        </div>
      </section>

      {/* PHẦN 3: Bảng dự toán chi phí */}
      <section className="swiss-form-section">
        <div className="swiss-section-header-row">
          <div>
            <h3 className="swiss-section-title">3. Bảng dự toán chi phí</h3>
          </div>
          {!disabled && (
            <button
              className="swiss-btn swiss-btn-secondary swiss-btn-sm"
              type="button"
              onClick={() =>
                update({
                  estimate_rows: [
                    ...value.estimate_rows,
                    {
                      row_id: nextRowId(),
                      description: '',
                      basis: null,
                      company_vnd: null,
                      employee_vnd: null,
                    },
                  ],
                })
              }
            >
              <span aria-hidden="true">+</span> <span>Thêm dòng dự toán</span>
            </button>
          )}
        </div>

        <div className="swiss-table-wrap">
          <table data-testid="b3-estimate-rows" className="swiss-table">
            <thead>
              <tr>
                <th style={{ width: '35%' }}>Nội dung chi</th>
                <th style={{ width: '25%' }}>Cơ sở dự toán</th>
                <th className="text-right" style={{ width: '18%' }}>Công ty dự kiến trả</th>
                <th className="text-right" style={{ width: '18%' }}>Nhân viên dự kiến trả</th>
                {!disabled && <th style={{ width: '4%' }}></th>}
              </tr>
            </thead>
            <tbody>
              {value.estimate_rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={disabled ? 4 : 5}
                    className="swiss-table-empty"
                  >
                    Chưa có khoản dự toán nào.
                  </td>
                </tr>
              ) : (
                value.estimate_rows.map((row) => (
                  <tr key={row.row_id}>
                    <td>
                      <input
                        aria-label={`nội dung ${row.row_id}`}
                        className="swiss-table-input"
                        value={row.description}
                        disabled={disabled}
                        onChange={(e) =>
                          updateRow(row.row_id, { description: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`cơ sở ${row.row_id}`}
                        className="swiss-table-input"
                        value={row.basis ?? ''}
                        disabled={disabled}
                        onChange={(e) =>
                          updateRow(row.row_id, { basis: e.target.value || null })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`công ty ${row.row_id}`}
                        type="number"
                        min="0"
                        className="swiss-table-input text-right"
                        value={numberField(row.company_vnd)}
                        disabled={disabled}
                        onChange={(e) =>
                          updateRow(row.row_id, { company_vnd: parseAmount(e.target.value) })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`nhân viên ${row.row_id}`}
                        type="number"
                        min="0"
                        className="swiss-table-input text-right"
                        value={numberField(row.employee_vnd)}
                        disabled={disabled}
                        onChange={(e) =>
                          updateRow(row.row_id, { employee_vnd: parseAmount(e.target.value) })
                        }
                      />
                    </td>
                    {!disabled && (
                      <td className="text-center">
                        <button
                          className="swiss-btn-delete"
                          type="button"
                          aria-label={`xóa dòng ${row.row_id}`}
                          title="Xóa dòng"
                          onClick={() =>
                            update({
                              estimate_rows: value.estimate_rows.filter(
                                (r) => r.row_id !== row.row_id
                              ),
                            })
                          }
                        >
                          ✕
                        </button>
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
            {/* Integrated Accounting Summary TFoot */}
            <tfoot>
              <tr className="swiss-table-total-row" data-testid="b3-totals-preview">
                <td colSpan={2} className="swiss-total-label">
                  Tổng cộng dự kiến: <strong>{vnd(totalPreview)}</strong>
                  <span className="sr-only">
                    công ty {vnd(companyTotal)} · nhân viên {vnd(employeeTotal)} · tổng {vnd(totalPreview)} (chưa duyệt, backend kiểm lại)
                  </span>
                </td>
                <td className="text-right swiss-total-val" title="Công ty chi trả">
                  {vnd(companyTotal)}
                </td>
                <td className="text-right swiss-total-val" title="Nhân viên tự chi">
                  {vnd(employeeTotal)}
                </td>
                {!disabled && <td></td>}
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}
