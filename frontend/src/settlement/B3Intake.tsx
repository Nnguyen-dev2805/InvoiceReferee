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
    <div data-testid="b3-intake-form">
      <div className="form-grid-2">
        <div className="field">
          <label htmlFor="b3-destination">Nơi đến</label>
          <input id="b3-destination" value={value.destination ?? ''}
                 disabled={disabled}
                 onChange={(e) => update({destination: e.target.value})}
                 placeholder="Hà Nội" />
        </div>
        <div className="field">
          <label htmlFor="b3-settlement-due">Hạn quyết toán</label>
          <input id="b3-settlement-due" type="date"
                 value={value.settlement_due ?? ''} disabled={disabled}
                 onChange={(e) => update({settlement_due: e.target.value || null})} />
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

      <div className="field">
        <label htmlFor="b3-purpose">Mục đích công tác</label>
        <input id="b3-purpose" value={value.purpose ?? ''} disabled={disabled}
               onChange={(e) => update({purpose: e.target.value})}
               placeholder="Khảo sát yêu cầu và thống nhất phạm vi dự án" />
      </div>

      <div className="field">
        <label htmlFor="b3-request-amount">Số xin ứng (VND, lời khai — không phải actual)</label>
        <input id="b3-request-amount" type="number" min="0"
               value={numberField(value.request_amount_vnd)} disabled={disabled}
               onChange={(e) => update({request_amount_vnd: parseAmount(e.target.value)})}
               placeholder="2000000" />
        {value.request_amount_vnd !== null && value.request_amount_vnd > 0 && (
          <span className="field-hint" data-testid="b3-request-hint">
            ≈ {value.request_amount_vnd.toLocaleString('vi-VN')} VND
          </span>
        )}
      </div>

      <div className="field">
        <label htmlFor="b3-assignment-note">
          Ghi chú giao việc (không bắt buộc)
        </label>
        <input id="b3-assignment-note" value={value.assignment_note ?? ''}
               disabled={disabled}
               placeholder="Giao việc bằng lời; không đính kèm giấy lệnh"
               onChange={(e) => update({assignment_note: e.target.value || null})} />
      </div>

      <h4>Dự toán chi phí</h4>
      <div className="table-responsive">
        <table data-testid="b3-estimate-rows" className="estimate-table">
          <thead>
            <tr>
              <th>Nội dung chi</th>
              <th>Cơ sở</th>
              <th className="text-right">Công ty trả</th>
              <th className="text-right">Nhân viên trả</th>
              {!disabled && <th></th>}
            </tr>
          </thead>
        <tbody>
          {value.estimate_rows.map((row) => (
            <tr key={row.row_id}>
              <td>
                <input aria-label={`nội dung ${row.row_id}`}
                       value={row.description} disabled={disabled}
                       onChange={(e) => updateRow(row.row_id,
                         {description: e.target.value})} />
              </td>
              <td>
                <input aria-label={`cơ sở ${row.row_id}`}
                       value={row.basis ?? ''} disabled={disabled}
                       onChange={(e) => updateRow(row.row_id,
                         {basis: e.target.value || null})} />
              </td>
              <td>
                <input aria-label={`công ty ${row.row_id}`} type="number"
                       min="0" value={numberField(row.company_vnd)}
                       disabled={disabled}
                       onChange={(e) => updateRow(row.row_id,
                         {company_vnd: parseAmount(e.target.value)})} />
              </td>
              <td>
                <input aria-label={`nhân viên ${row.row_id}`} type="number"
                       min="0" value={numberField(row.employee_vnd)}
                       disabled={disabled}
                       onChange={(e) => updateRow(row.row_id,
                         {employee_vnd: parseAmount(e.target.value)})} />
              </td>
              {!disabled && (
                <td>
                  <button className="btn btn-ghost" type="button"
                          aria-label={`xóa dòng ${row.row_id}`}
                          onClick={() => update({estimate_rows:
                            value.estimate_rows.filter((r) =>
                              r.row_id !== row.row_id)})}>
                    Xóa
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {!disabled && (
        <button className="btn" type="button"
                onClick={() => update({estimate_rows: [...value.estimate_rows, {
                  row_id: nextRowId(), description: '', basis: null,
                  company_vnd: null, employee_vnd: null,
                }]})}>
          Thêm dòng dự toán
        </button>
      )}
      <p data-testid="b3-totals-preview">
        <strong>Preview (backend kiểm lại):</strong>{' '}
        công ty {vnd(companyTotal)} · nhân viên {vnd(employeeTotal)} ·{' '}
        tổng {vnd(totalPreview)}
      </p>
    </div>
  );
}
