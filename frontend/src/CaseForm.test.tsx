import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { CaseForm } from './CaseForm';
import { caseRecord } from './testBuilders';

it('renders form inputs correctly', () => {
  render(<CaseForm onCreate={vi.fn()} onCreated={vi.fn()} />);
  expect(screen.getByRole('heading', { name: 'Nộp hồ sơ hoàn ứng' })).toBeTruthy();
  expect(screen.getByLabelText(/nội dung công việc/i)).toBeTruthy();
  expect(screen.getByLabelText(/số tiền đề nghị/i)).toBeTruthy();
  expect(screen.getByLabelText(/chứng từ/i)).toBeTruthy();
});

it('shows accessible error summary when submitting empty form', async () => {
  render(<CaseForm onCreate={vi.fn()} onCreated={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: /nộp hồ sơ/i }));
  const summaryHeading = await screen.findByText(/thông tin chưa hợp lệ/i);
  expect(summaryHeading).toBeTruthy();
  expect(screen.getAllByText('Cần nêu mục đích công việc.')).toHaveLength(2);
  expect(screen.getAllByText('Cần nhập số tiền đề nghị.')).toHaveLength(2);
  expect(screen.getAllByRole('alert').length).toBeGreaterThan(1);
});

it('formats amount input while typing with thousands separator', async () => {
  render(<CaseForm onCreate={vi.fn()} onCreated={vi.fn()} />);
  const amountInput = screen.getByLabelText(/số tiền đề nghị/i);
  await userEvent.type(amountInput, '1500000');
  // Should format into Vietnamese currency notation with thousands separator
  expect(amountInput).toHaveValue('1.500.000');
});

it('supports uploading multiple files at once', async () => {
  render(<CaseForm onCreate={vi.fn()} onCreated={vi.fn()} />);
  const file1 = new File(['content1'], 'bill1.pdf', { type: 'application/pdf' });
  const file2 = new File(['content2'], 'receipt2.png', { type: 'image/png' });

  const fileInput = screen.getByLabelText(/chứng từ/i, { selector: 'input' });
  await userEvent.upload(fileInput, [file1, file2]);

  expect(screen.getByText('bill1.pdf')).toBeTruthy();
  expect(screen.getByText('receipt2.png')).toBeTruthy();
  expect(screen.getAllByRole('button', { name: 'Bỏ' })).toHaveLength(2);
});

it('submits form successfully with parsed integer VND and files', async () => {
  const onCreate = vi.fn().mockResolvedValue(caseRecord());
  const onCreated = vi.fn();
  render(<CaseForm onCreate={onCreate} onCreated={onCreated} />);

  await userEvent.type(screen.getByLabelText(/nội dung công việc/i), 'Chi phí công tác');
  await userEvent.type(screen.getByLabelText(/số tiền đề nghị/i), '2000000');

  const file = new File(['bill'], 'invoice.pdf', { type: 'application/pdf' });
  const fileInput = screen.getByLabelText(/chứng từ/i, { selector: 'input' });
  await userEvent.upload(fileInput, [file]);

  await userEvent.click(screen.getByRole('button', { name: /nộp hồ sơ/i }));

  expect(onCreate).toHaveBeenCalledTimes(1);
  const formData = onCreate.mock.calls[0][0] as FormData;
  const claimJson = JSON.parse(formData.get('claim_json') as string);
  expect(claimJson.requested_amount_vnd).toBe(2000000);
  expect(claimJson.purpose).toBe('Chi phí công tác');
  expect(formData.getAll('files')).toHaveLength(1);
});
