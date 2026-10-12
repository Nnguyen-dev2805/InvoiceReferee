import React, { useState, useRef } from 'react';
import type { SourceView } from './types';
import { sourceContentUrl } from './api';

interface DocumentViewerProps {
  sources: SourceView[];
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
  onUpload?: (files: FileList | File[]) => void;
  isUploading?: boolean;
  onToggleFormOnly?: () => void;
}

export function DocumentViewer({
  sources,
  selectedSourceId,
  onSelectSource,
  onUpload,
  isUploading = false,
  onToggleFormOnly,
}: DocumentViewerProps) {
  const [zoom, setZoom] = useState(1);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Default to first source if none selected
  const activeSource = sources.find((s) => s.id === selectedSourceId) || sources[0] || null;

  const isImage = (s: SourceView) =>
    s.media_type?.startsWith('image/') || /\.(png|jpe?g|webp|gif)$/i.test(s.filename);
  const isPdf = (s: SourceView) =>
    s.media_type === 'application/pdf' || /\.pdf$/i.test(s.filename);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0 && onUpload) {
      onUpload(e.target.files);
      e.target.value = '';
    }
  };

  return (
    <div className="doc-viewer-container" data-testid="document-viewer">
      {/* Header bar: Document selector tabs & zoom controls */}
      <div className="doc-viewer-header">
        <div className="doc-viewer-tabs">
          {sources.length > 0 ? (
            sources.map((s, idx) => (
              <button
                key={s.id}
                type="button"
                className={`doc-tab-btn ${activeSource?.id === s.id ? 'active' : ''}`}
                onClick={() => {
                  onSelectSource(s.id);
                  setZoom(1);
                }}
                title={s.filename}
              >
                <span className="doc-tab-index">{idx + 1}.</span>
                <span className="doc-tab-name">{s.filename}</span>
              </button>
            ))
          ) : (
            <span className="doc-viewer-empty-label">Chưa có tài liệu đính kèm</span>
          )}
        </div>

        <div className="doc-viewer-actions">
          {activeSource && (
            <>
              {isImage(activeSource) && (
                <div className="doc-zoom-controls">
                  <button
                    type="button"
                    className="btn-icon-subtle"
                    onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
                    title="Thu nhỏ"
                    aria-label="Thu nhỏ"
                  >
                    -
                  </button>
                  <span className="zoom-level">{Math.round(zoom * 100)}%</span>
                  <button
                    type="button"
                    className="btn-icon-subtle"
                    onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
                    title="Phóng to"
                    aria-label="Phóng to"
                  >
                    +
                  </button>
                </div>
              )}
              <a
                href={sourceContentUrl(activeSource.id)}
                target="_blank"
                rel="noreferrer"
                className="btn-link-subtle"
                title="Mở trong tab mới"
              >
                Mở tệp ↗
              </a>
            </>
          )}

          {onUpload && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: 'none' }}
                onChange={handleFileChange}
                accept=".pdf,.png,.jpg,.jpeg,.csv,.txt"
              />
              <button
                type="button"
                className="btn-add-doc"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                title="Tải thêm tài liệu"
              >
                {isUploading ? 'Đang tải...' : '+ Thêm tệp'}
              </button>
            </>
          )}

          {onToggleFormOnly && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={onToggleFormOnly}
              title="Ẩn cột tài liệu để chỉ xem toàn bộ biểu mẫu"
              style={{ padding: '3px 8px', fontSize: '0.75rem', color: '#64748b' }}
            >
              Chỉ xem biểu mẫu ⛶
            </button>
          )}
        </div>
      </div>

      {/* Main View Area */}
      <div className="doc-viewer-body">
        {activeSource ? (
          <div className="doc-preview-wrapper">
            {isImage(activeSource) ? (
              <div className="doc-image-viewport">
                <img
                  src={sourceContentUrl(activeSource.id)}
                  alt={activeSource.filename}
                  style={{ transform: `scale(${zoom})`, transformOrigin: 'top center' }}
                  className="doc-preview-image"
                />
              </div>
            ) : isPdf(activeSource) ? (
              <iframe
                src={sourceContentUrl(activeSource.id)}
                title={activeSource.filename}
                className="doc-preview-iframe"
              />
            ) : (
              <div className="doc-fallback-preview">
                <div className="doc-fallback-icon">📄</div>
                <div className="doc-fallback-name">{activeSource.filename}</div>
                <div className="doc-fallback-meta">
                  {(activeSource.size_bytes / 1024).toFixed(1)} KB · {activeSource.media_type}
                </div>
                <a
                  href={sourceContentUrl(activeSource.id, true)}
                  className="btn btn-secondary btn-sm"
                  download={activeSource.filename}
                >
                  Tải về tệp này
                </a>
              </div>
            )}
          </div>
        ) : (
          <div
            className="doc-empty-dropzone"
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click();
            }}
          >
            <div className="doc-dropzone-icon">📁</div>
            <div className="doc-dropzone-title">Kéo thả hoặc bấm để tải lên tài liệu minh chứng</div>
            <div className="doc-dropzone-desc">Hỗ trợ: Giấy đề nghị tạm ứng, Bảng dự toán, Hóa đơn (PDF, Ảnh)</div>
          </div>
        )}
      </div>
    </div>
  );
}
