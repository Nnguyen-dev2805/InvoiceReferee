import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { HumanActions } from './HumanActions';
import { caseRecord, infoDecision } from './testBuilders';

it('offers the employee a declaration control for a factual question', () => {
  render(
    <HumanActions caseRecord={caseRecord()} decision={infoDecision()} onAction={vi.fn()} />,
  );
  expect(screen.getByRole('button', { name: /gửi/i })).toBeTruthy();
});

it('requires a reason before submitting an action', async () => {
  const onAction = vi.fn();
  render(
    <HumanActions caseRecord={caseRecord()} decision={infoDecision()} onAction={onAction} />,
  );
  await userEvent.click(screen.getByRole('button', { name: /gửi/i }));
  expect(onAction).not.toHaveBeenCalled();
  expect(screen.getByText(/cần lý do/i)).toBeTruthy();
});

it('lets the operator switch demo role and offers that role\'s actions', async () => {
  render(<HumanActions caseRecord={caseRecord()} decision={infoDecision()} onAction={vi.fn()} />);
  // Default role follows the issue owner (EMPLOYEE) -> employee actions.
  expect(screen.getByRole('option', { name: 'Bổ sung khai báo' })).toBeTruthy();
  // Switch to APPROVER -> the action list changes to approve/deny.
  await userEvent.selectOptions(screen.getByLabelText(/vai trò/i), 'APPROVER');
  expect(screen.getByRole('option', { name: 'Duyệt số tiền' })).toBeTruthy();
  expect(screen.queryByRole('option', { name: 'Bổ sung khai báo' })).toBeNull();
});

it('submits the selected role as the action mode', async () => {
  const onAction = vi.fn().mockResolvedValue(undefined);
  render(<HumanActions caseRecord={caseRecord()} decision={infoDecision()} onAction={onAction} />);
  await userEvent.selectOptions(screen.getByLabelText(/vai trò/i), 'REVIEWER');
  await userEvent.type(screen.getByLabelText(/lý do/i), 'Đã xem chứng từ gốc');
  await userEvent.click(screen.getByRole('button', { name: /gửi/i }));
  expect(onAction).toHaveBeenCalledTimes(1);
  expect(onAction.mock.calls[0][0].mode).toBe('REVIEWER');
});
