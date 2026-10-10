// Task 4: B3IntakeForm — fields render, disabled mode, totals preview với
// null-propagation (dòng chưa rõ giữ unknown, không suy bằng 0).
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { B3IntakeForm, emptyB3Intake } from './B3Intake';
import type { B3Intake } from './types';

function intakeWith(rows: B3Intake['estimate_rows']): B3Intake {
  return {...emptyB3Intake('WEB'), estimate_rows: rows};
}

test('render đầy đủ trường nghiệp vụ B3', () => {
  render(<B3IntakeForm value={emptyB3Intake('WEB')} onChange={() => {}} disabled={false} />);
  expect(screen.getByLabelText('Nơi đến')).toBeTruthy();
  expect(screen.getByLabelText('Ngày đi')).toBeTruthy();
  expect(screen.getByLabelText('Ngày về')).toBeTruthy();
  expect(screen.getByLabelText(/Số tiền đề nghị tạm ứng|Số xin ứng/)).toBeTruthy();
  expect(screen.getByLabelText(/Hạn thanh toán tạm ứng|Hạn quyết toán/)).toBeTruthy();
  expect(screen.getByLabelText(/Ghi chú giao việc/)).toBeTruthy();
  expect(screen.getByTestId('b3-estimate-rows')).toBeTruthy();
});

test('disabled khóa mọi input', () => {
  render(<B3IntakeForm value={emptyB3Intake('WEB')} onChange={() => {}} disabled={true} />);
  expect((screen.getByLabelText('Nơi đến') as HTMLInputElement).disabled).toBe(true);
  expect(screen.queryByText('Thêm dòng dự toán')).not.toBeInTheDocument();
});

test('totals preview cộng đúng và dòng null giữ "chưa rõ"', () => {
  const intake = intakeWith([
    {row_id: 'flight', description: 'Vé máy bay', basis: null,
     company_vnd: 3_000_000, employee_vnd: 0},
    {row_id: 'hotel', description: 'Khách sạn', basis: null,
     company_vnd: 0, employee_vnd: 3_000_000},
    {row_id: 'other', description: 'Chi khác', basis: null,
     company_vnd: null, employee_vnd: null},
  ]);
  render(<B3IntakeForm value={intake} onChange={() => {}} disabled={false} />);
  const preview = screen.getByTestId('b3-totals-preview').textContent ?? '';
  expect(preview).toContain('chưa rõ'); // không suy tổng một phần thành số
  expect(preview).toContain('backend kiểm lại');
});

test('totals preview cộng khi đủ dòng', () => {
  const intake = intakeWith([
    {row_id: 'flight', description: 'Vé máy bay', basis: null,
     company_vnd: 3_000_000, employee_vnd: 0},
    {row_id: 'hotel', description: 'Khách sạn', basis: null,
     company_vnd: 0, employee_vnd: 3_000_000},
  ]);
  render(<B3IntakeForm value={intake} onChange={() => {}} disabled={false} />);
  const preview = screen.getByTestId('b3-totals-preview').textContent ?? '';
  expect(preview).toContain('3.000.000');
  expect(preview).toContain('tổng 6.000.000');
});

test('onChange nhận bản intake đầy đủ khi sửa dòng', async () => {
  const user = userEvent.setup();
  function Harness() {
    const [intake, setIntake] = useState(emptyB3Intake('WEB'));
    return (
      <div>
        <B3IntakeForm value={intake} onChange={setIntake} disabled={false} />
        <pre data-testid="last-intake">{JSON.stringify(intake)}</pre>
      </div>
    );
  }
  render(<Harness />);
  await user.type(screen.getByLabelText('Nơi đến'), 'Hà Nội');
  await user.click(screen.getByText('Thêm dòng dự toán'));
  await user.type(screen.getByLabelText('nội dung row-1'), 'Vé máy bay');
  await user.type(screen.getByLabelText('nhân viên row-1'), '3000000');
  const parsed = JSON.parse(
    screen.getByTestId('last-intake').textContent ?? '{}');
  expect(parsed.destination).toBe('Hà Nội');
  expect(parsed.estimate_rows).toHaveLength(1);
  expect(parsed.estimate_rows[0].description).toBe('Vé máy bay');
  expect(parsed.estimate_rows[0].employee_vnd).toBe(3_000_000);
  expect(parsed.estimate_rows[0].company_vnd).toBeNull();
});
