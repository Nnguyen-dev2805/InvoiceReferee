import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EvidencePreviewModal } from './EvidencePreviewModal';
import type { EvidenceDto } from './types';

const mockImageEvidence: EvidenceDto = {
  id: 'ev-img-1',
  case_id: 'case-101',
  role: 'PRIMARY_BILL',
  original_name: 'hoa_don_an_uong.jpg',
  sha256: 'abc1234567890def',
  mime: 'image/jpeg',
  size: 250 * 1024,
};

const mockPdfEvidence: EvidenceDto = {
  id: 'ev-pdf-1',
  case_id: 'case-101',
  role: 'GOODS_RECEIPT',
  original_name: 'bien_ban_giao_hang.pdf',
  sha256: 'fed0987654321cba',
  mime: 'application/pdf',
  size: 1024 * 1024,
};

describe('EvidencePreviewModal', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(
      <EvidencePreviewModal
        isOpen={false}
        evidence={mockImageEvidence}
        caseId="case-101"
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders image preview and metadata correctly', () => {
    render(
      <EvidencePreviewModal
        isOpen={true}
        evidence={mockImageEvidence}
        caseId="case-101"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('hoa_don_an_uong.jpg')).toBeTruthy();
    expect(screen.getByText('Hoá đơn / Chứng từ chính')).toBeTruthy();
    const img = screen.getByRole('img', { name: 'hoa_don_an_uong.jpg' });
    expect(img).toBeTruthy();
    expect(img.getAttribute('src')).toBe('/api/cases/case-101/evidence/ev-img-1/content');
  });

  it('renders iframe for PDF documents', () => {
    render(
      <EvidencePreviewModal
        isOpen={true}
        evidence={mockPdfEvidence}
        caseId="case-101"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('bien_ban_giao_hang.pdf')).toBeTruthy();
    expect(screen.getByText('Phiếu giao / Biên bản nhập kho')).toBeTruthy();
    const iframe = screen.getByTitle('bien_ban_giao_hang.pdf');
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute('src')).toBe('/api/cases/case-101/evidence/ev-pdf-1/content');
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    render(
      <EvidencePreviewModal
        isOpen={true}
        evidence={mockImageEvidence}
        caseId="case-101"
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByLabelText('Đóng cửa sổ xem trước'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape key is pressed', () => {
    const onClose = vi.fn();
    render(
      <EvidencePreviewModal
        isOpen={true}
        evidence={mockImageEvidence}
        caseId="case-101"
        onClose={onClose}
      />,
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
