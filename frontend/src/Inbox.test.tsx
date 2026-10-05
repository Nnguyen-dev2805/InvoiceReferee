import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Inbox } from './Inbox';
import { caseRecord, completedRun, needsInfoRun } from './testBuilders';

it('shows a case in the inbox of the role that owns its open issue', () => {
  const reviewCase = caseRecord({ id: 'case-r', open_owner_modes: ['REVIEWER'] });
  render(
    <Inbox
      cases={[reviewCase]}
      role="REVIEWER"
      runsByCase={{ 'case-r': needsInfoRun() }}
      onOpen={vi.fn()}
    />,
  );
  expect(screen.getByText('Công tác Hà Nội')).toBeTruthy();
  expect(screen.getByText('1 việc')).toBeTruthy();
});

it('hides a case from a role that does not own its open issue', () => {
  const reviewCase = caseRecord({ id: 'case-r', open_owner_modes: ['REVIEWER'] });
  render(
    <Inbox
      cases={[reviewCase]}
      role="APPROVER"
      runsByCase={{ 'case-r': needsInfoRun() }}
      onOpen={vi.fn()}
    />,
  );
  expect(screen.queryByText('Công tác Hà Nội')).toBeNull();
  expect(screen.getByText(/không có việc cần xử lý/i)).toBeTruthy();
});

it('shows a still-processing case in the shared "Đang xử lý" section', () => {
  const running = caseRecord({ id: 'case-p', open_owner_modes: [] });
  const runningRun = { ...completedRun(), status: 'RUNNING' as const, result: null };
  render(
    <Inbox
      cases={[running]}
      role="EMPLOYEE"
      runsByCase={{ 'case-p': runningRun }}
      onOpen={vi.fn()}
    />,
  );
  expect(screen.getByRole('heading', { name: 'Đang xử lý' })).toBeTruthy();
  expect(screen.getByText('Công tác Hà Nội')).toBeTruthy();
});

it('opens the selected case', async () => {
  const onOpen = vi.fn();
  const reviewCase = caseRecord({ id: 'case-r', open_owner_modes: ['REVIEWER'] });
  render(
    <Inbox
      cases={[reviewCase]}
      role="REVIEWER"
      runsByCase={{ 'case-r': needsInfoRun() }}
      onOpen={onOpen}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: /công tác hà nội/i }));
  expect(onOpen).toHaveBeenCalledWith('case-r');
});
