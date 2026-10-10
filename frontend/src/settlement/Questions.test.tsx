import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, test, vi } from 'vitest';
import { QuestionsPanel } from './Questions';
import type { QuestionView, SourceView } from './types';

const SOURCE: SourceView = {
  id: 'src-1',
  filename: 'bang_ke_chi_tiet.pdf',
  media_type: 'application/pdf',
  sha256: 'abc123',
  size_bytes: 1024,
  status: 'ACCEPTED',
  uploader_actor_id: 'NV-01',
  received_at: '2026-10-10T09:00:00Z',
  supersedes_source_id: null,
  provenance: {},
};

const QUESTION: QuestionView = {
  id: 'Q-01',
  case_id: 'C-01',
  issue_id: 'I-01',
  owner: 'EMPLOYEE',
  status: 'OPEN',
  message: 'Cần bổ sung hóa đơn tiền phòng khách sạn.',
  refs: ['src-1'],
  blocked: null,
  created_at: '2026-10-10T09:00:00Z',
  origin_run_id: null,
  answered_at: null,
  resolved_run_id: null,
};

describe('QuestionsPanel', () => {
  test('renders question with friendly filename and EvidenceLinks', () => {
    const onResponded = vi.fn();
    render(
      <QuestionsPanel
        questions={[QUESTION]}
        caseVersion={1}
        sourceIds={['src-1']}
        sources={[SOURCE]}
        role="EMPLOYEE"
        onResponded={onResponded}
      />,
    );

    expect(screen.getByText('Cần bổ sung hóa đơn tiền phòng khách sạn.')).toBeInTheDocument();
    expect(screen.getByText('bang_ke_chi_tiet.pdf (src-1)')).toBeInTheDocument();
  });

  test('calls onResponded with drafted content and selected sourceIds', async () => {
    const user = userEvent.setup();
    const onResponded = vi.fn();
    render(
      <QuestionsPanel
        questions={[QUESTION]}
        caseVersion={1}
        sourceIds={['src-1']}
        sources={[SOURCE]}
        role="EMPLOYEE"
        onResponded={onResponded}
      />,
    );

    const input = screen.getByLabelText('Trả lời');
    await user.type(input, 'Đã đính kèm bảng kê có xác nhận của khách sạn');
    const checkbox = screen.getByLabelText(/bang_ke_chi_tiet\.pdf/);
    await user.click(checkbox);

    const submitBtn = screen.getByRole('button', { name: /Gửi trả lời/ });
    await user.click(submitBtn);

    expect(onResponded).toHaveBeenCalledWith('Q-01', {
      content: 'Đã đính kèm bảng kê có xác nhận của khách sạn',
      sourceIds: ['src-1'],
    });
  });

  test('displays empty message when no questions', () => {
    const onResponded = vi.fn();
    render(
      <QuestionsPanel
        questions={[]}
        caseVersion={1}
        sourceIds={[]}
        role="EMPLOYEE"
        onResponded={onResponded}
      />,
    );

    expect(screen.getByText('Chưa có câu hỏi nào cho hồ sơ này.')).toBeInTheDocument();
  });
});
