import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { EvidenceLinks } from './EvidenceLinks';
import type { SourceView } from './types';

const SOURCE_1: SourceView = {
  id: 'S-doc',
  filename: 'de-nghi.pdf',
  media_type: 'application/pdf',
  sha256: 'abc123',
  size_bytes: 1024,
  status: 'ACCEPTED',
  uploader_actor_id: 'NV-01',
  received_at: '2026-10-10T09:00:00Z',
  supersedes_source_id: null,
  provenance: {},
};

const SOURCE_2: SourceView = {
  id: 'S-du-toan',
  filename: 'bang_du_toan.xlsx',
  media_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  sha256: 'def456',
  size_bytes: 2048,
  status: 'ACCEPTED',
  uploader_actor_id: 'NV-01',
  received_at: '2026-10-10T09:00:00Z',
  supersedes_source_id: null,
  provenance: {},
};

describe('EvidenceLinks', () => {
  test('dedups multiple refs of the same source and links to source content', () => {
    render(
      <EvidenceLinks
        refs={['S-doc', 'S-doc-p1-field-1', 'S-doc', 'S-doc-p1-field-1']}
        sources={[SOURCE_1]}
      />,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toContain('/api/sources/S-doc/content');
    expect(links[0].textContent).toContain('de-nghi.pdf');
  });

  test('renders links for multiple distinct sources', () => {
    render(
      <EvidenceLinks
        refs={['S-doc', 'S-du-toan']}
        sources={[SOURCE_1, SOURCE_2]}
      />,
    );
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(2);
    expect(links[0].textContent).toContain('de-nghi.pdf');
    expect(links[1].textContent).toContain('bang_du_toan.xlsx');
  });

  test('handles form refs without creating broken links', () => {
    render(
      <EvidenceLinks
        refs={['form:1:request_amount_vnd']}
        sources={[SOURCE_1]}
      />,
    );
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Khai báo từ form')).toBeInTheDocument();
  });

  test('renders empty when refs is empty', () => {
    const { container } = render(<EvidenceLinks refs={[]} sources={[SOURCE_1]} />);
    expect(container.textContent).toBe('');
  });
});
