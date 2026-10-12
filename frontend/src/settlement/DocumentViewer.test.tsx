import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, test, expect } from 'vitest';
import { DocumentViewer } from './DocumentViewer';
import type { SourceView } from './types';

const MOCK_SOURCES: SourceView[] = [
  {
    id: 'src-1',
    filename: 'giay_de_nghi.png',
    media_type: 'image/png',
    sha256: 'abc123',
    size_bytes: 2048,
    status: 'ACCEPTED',
    uploader_actor_id: 'NV-01',
    received_at: '2026-10-10T09:00:00Z',
    supersedes_source_id: null,
    provenance: {},
  },
  {
    id: 'src-2',
    filename: 'du_toan.pdf',
    media_type: 'application/pdf',
    sha256: 'def456',
    size_bytes: 4096,
    status: 'ACCEPTED',
    uploader_actor_id: 'NV-01',
    received_at: '2026-10-10T09:01:00Z',
    supersedes_source_id: null,
    provenance: {},
  },
];

test('hiển thị thông báo khi chưa có tài liệu và hỗ trợ tải tệp', () => {
  const onUpload = vi.fn();
  render(
    <DocumentViewer
      sources={[]}
      selectedSourceId={null}
      onSelectSource={() => {}}
      onUpload={onUpload}
    />
  );
  expect(screen.getByText('Chưa có tài liệu đính kèm')).toBeInTheDocument();
  expect(screen.getByText(/Kéo thả hoặc bấm để tải lên tài liệu minh chứng/)).toBeInTheDocument();
});

test('hiển thị danh sách tab tài liệu và kích hoạt xem ảnh với nút zoom', () => {
  const onSelect = vi.fn();
  render(
    <DocumentViewer
      sources={MOCK_SOURCES}
      selectedSourceId="src-1"
      onSelectSource={onSelect}
    />
  );

  expect(screen.getByText('giay_de_nghi.png')).toBeInTheDocument();
  expect(screen.getByText('du_toan.pdf')).toBeInTheDocument();

  // Nút zoom hiện khi chọn ảnh
  expect(screen.getByTitle('Thu nhỏ')).toBeInTheDocument();
  expect(screen.getByTitle('Phóng to')).toBeInTheDocument();
  expect(screen.getByText('100%')).toBeInTheDocument();

  // Chuyển tab
  fireEvent.click(screen.getByText('du_toan.pdf'));
  expect(onSelect).toHaveBeenCalledWith('src-2');
});

test('tải lên tài liệu khi chọn tệp qua nút + Thêm tệp', async () => {
  const user = userEvent.setup();
  const onUpload = vi.fn();
  render(
    <DocumentViewer
      sources={MOCK_SOURCES}
      selectedSourceId="src-1"
      onSelectSource={() => {}}
      onUpload={onUpload}
    />
  );

  const file = new File(['dummy content'], 'hoa_don.png', { type: 'image/png' });
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(fileInput).not.toBeNull();

  await user.upload(fileInput, file);
  expect(onUpload).toHaveBeenCalledTimes(1);
});
