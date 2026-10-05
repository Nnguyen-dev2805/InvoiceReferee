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
