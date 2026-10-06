import { useEffect } from 'react';
import type { EvidenceDto, EvidenceRole } from './types';
import { getEvidenceContentUrl } from './api';

const ROLE_LABEL_MAP: Record<EvidenceRole, string> = {
  PRIMARY_BILL: 'Hoá đơn / Chứng từ chính',
  GOODS_RECEIPT: 'Phiếu giao / Biên bản nhập kho',
  CONTEXT: 'Tài liệu bối cảnh',
};

interface EvidencePreviewModalProps {
  isOpen: boolean;
  evidence: EvidenceDto | null;
  caseId: string;
  onClose: () => void;
}

export function EvidencePreviewModal({
  isOpen,
  evidence,
  caseId,
  onClose,
}: EvidencePreviewModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !evidence) return null;

  const contentUrl = getEvidenceContentUrl(caseId, evidence.id);
  const isImage = evidence.mime.startsWith('image/');
  const isPdf = evidence.mime === 'application/pdf';
  const roleText = ROLE_LABEL_MAP[evidence.role] || evidence.role;
  const sizeKb = Math.ceil(evidence.size / 1024);

  return (
    <div
      className="modal-backdrop"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="modal-container preview-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="preview-modal-title"
      >
        <div className="modal-header">
          <div>
            <h3 id="preview-modal-title" className="preview-modal-title">
              {evidence.original_name}
            </h3>
            <div className="preview-modal-meta">
              <span className={`badge badge-role-${evidence.role.toLowerCase()}`}>
                {roleText}
              </span>
              <span className="muted">
                {sizeKb} KB · {evidence.mime} · Mã hash: <code>{evidence.sha256.slice(0, 10)}…</code>
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost modal-close-btn"
            onClick={onClose}
            aria-label="Đóng cửa sổ xem trước"
          >
            ✕
          </button>
        </div>

        <div className="modal-body preview-modal-body">
          {isImage ? (
            <div className="preview-media-wrapper">
              <img
                src={contentUrl}
                alt={evidence.original_name}
                className="preview-image"
                loading="lazy"
              />
            </div>
          ) : isPdf ? (
            <div className="preview-media-wrapper">
              <iframe
                src={contentUrl}
                title={evidence.original_name}
                className="preview-iframe"
              />
            </div>
          ) : (
            <div className="preview-unsupported">
              <p>Định dạng tệp này ({evidence.mime}) chưa hỗ trợ xem trực tiếp.</p>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <a
            href={contentUrl}
            target="_blank"
            rel="noopener noreferrer"
            download={evidence.original_name}
            className="btn btn-secondary"
          >
            Tải về tệp gốc
          </a>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
