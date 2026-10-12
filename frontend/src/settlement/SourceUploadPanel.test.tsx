import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { SourceUploadPanel } from './SourceUploadPanel';
import * as api from './api';
import { ApiError } from './api';
import type { CaseView } from './types';

function makeView(overrides: Partial<CaseView> = {}): CaseView {
  return {
    id: 'C-01', job: 'B3', case_version: 1, input_revision: 1, control_epoch: 1,
    stop_active: false, stage: 'CHECKING', current_run_id: null,
    submission: {
      employee_ref: 'NV-01', work_ref: 'WORK-01', job: 'B3',
      money_as_of: '2026-10-10T02:00:00Z',
      knowledge_cutoff: '2026-10-10T02:00:00Z', form: {},
    },
    sources: [], allowed_actions: [],
    money_summary: { approved_vnd: null, received_vnd: null, remaining_vnd: null,
                     pending_events: 0, incidents: [] },
    created_at: '2026-10-10T02:00:00Z', updated_at: '2026-10-10T02:00:00Z',
    ...overrides,
  };
}

const source = (id: string, filename: string) => ({
  id, filename, media_type: 'application/pdf', sha256: 'x', size_bytes: 10,
  status: 'ACCEPTED' as const, uploader_actor_id: 'NV-01',
  received_at: '2026-10-10T02:00:00Z', supersedes_source_id: null,
  provenance: {},
});

beforeEach(() => vi.restoreAllMocks());

test('partial failure giữ lại file chưa tải và báo lỗi', async () => {
  const addSpy = vi.spyOn(api, 'addSource')
    .mockResolvedValueOnce(source('S-1', 'a.pdf'))
    .mockRejectedValueOnce(new ApiError('FILE_TOO_LARGE', 'quá lớn', 413));
  vi.spyOn(api, 'getCase').mockResolvedValue(makeView({ case_version: 2 }));
  const onChanged = vi.fn().mockResolvedValue(undefined);
  const onError = vi.fn();

  render(<SourceUploadPanel view={makeView()} role="EMPLOYEE" actorId="NV-01"
    onChanged={onChanged} onError={onError} />);
  const input = screen.getByTestId('sources-file-input') as HTMLInputElement;
  const f1 = new File(['a'], 'a.pdf', { type: 'application/pdf' });
  const f2 = new File(['b'], 'b.pdf', { type: 'application/pdf' });
  fireEvent.change(input, { target: { files: [f1, f2] } });
  expect(screen.getByText(/Đã chọn 2 tệp/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Tải lên 2 nguồn' }));
  await waitFor(() => expect(addSpy).toHaveBeenCalledTimes(2));
  // File chưa tải (b.pdf) vẫn còn trong queue, không bị mất.
  await waitFor(() => expect(screen.getByText(/Đã chọn 1 tệp/)).toBeTruthy());
  expect(screen.getByLabelText('Xoá b.pdf')).toBeTruthy();
  expect(onChanged).toHaveBeenCalledWith('C-01');
});

test('tải thành công tất cả thì xoá queue', async () => {
  const addSpy = vi.spyOn(api, 'addSource')
    .mockResolvedValue(source('S-1', 'a.pdf'));
  vi.spyOn(api, 'getCase').mockResolvedValue(makeView({ case_version: 2 }));
  render(<SourceUploadPanel view={makeView()} role="EMPLOYEE" actorId="NV-01"
    onChanged={vi.fn().mockResolvedValue(undefined)} onError={vi.fn()} />);
  const input = screen.getByTestId('sources-file-input') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['a'], 'a.pdf',
    { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: 'Tải lên nguồn' }));
  await waitFor(() => expect(addSpy).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByText(/Đã chọn/)).toBeNull());
});

test('đổi case reset queue: không giữ file của case cũ', async () => {
  const { rerender } = render(
    <SourceUploadPanel key="C-01" view={makeView()} role="EMPLOYEE"
      actorId="NV-01" onChanged={vi.fn().mockResolvedValue(undefined)}
      onError={vi.fn()} />);
  const input = screen.getByTestId('sources-file-input') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['a'], 'a.pdf',
    { type: 'application/pdf' })] } });
  expect(screen.getByText(/Đã chọn 1 tệp/)).toBeTruthy();
  // Parent keyed the panel by case id → a new case remounts and resets state.
  rerender(
    <SourceUploadPanel key="C-02" view={makeView({ id: 'C-02' })} role="EMPLOYEE"
      actorId="NV-01" onChanged={vi.fn().mockResolvedValue(undefined)}
      onError={vi.fn()} />);
  expect(screen.queryByText(/Đã chọn/)).toBeNull();
});
