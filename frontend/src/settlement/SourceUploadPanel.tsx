// Source upload panel: the queue/upload/provenance/progress/error workflow for
// a case's retained sources. Owns only source-upload state; the parent keeps
// selected case/loading/navigation. Multi-upload is sequential with per-file
// idempotency (case_version is re-fetched after each success), and a partial
// failure keeps the files that were not uploaded so nothing is silently lost.
import { useState } from 'react';
import * as api from './api';
import { ApiError } from './api';
import type { CaseView, DemoRole } from './types';

const SOURCE_ERROR_CODES = new Set([
  'UNSUPPORTED_FORMAT',
  'FILE_TOO_LARGE',
  'SOURCE_LIMIT_REACHED',
]);

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

interface SourceUploadPanelProps {
  view: CaseView;
  role: DemoRole;
  actorId: string;
  onChanged: (caseId: string) => Promise<void>;
  onError: (message: string) => void;
}

export function SourceUploadPanel({
  view, role, actorId, onChanged, onError,
}: SourceUploadPanelProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState('');
  const [sourceError, setSourceError] = useState<string | null>(null);

  const addFiles = (incoming: FileList | File[] | null) => {
    if (!incoming) return;
    const list = Array.from(incoming);
    if (list.length === 0) return;
    setFiles((prev) => {
      const existing = new Set(prev.map((f) => `${f.name}-${f.size}`));
      const unique = list.filter((f) => !existing.has(`${f.name}-${f.size}`));
      return [...prev, ...unique];
    });
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const upload = async () => {
    if (files.length === 0 || uploading) return;
    setUploading(true);
    let currentCase = view;
    const remaining = [...files];
    try {
      for (const file of files) {
        const fileNote = note.trim()
          ? (files.length > 1 ? `${note.trim()} (${file.name})` : note.trim())
          : '';
        try {
          await api.addSource(
            currentCase.id, file, currentCase.case_version,
            actorId.trim(), role, fileNote);
          currentCase = await api.getCase(currentCase.id);
          remaining.shift();
        } catch (fileErr) {
          if (fileErr instanceof ApiError && SOURCE_ERROR_CODES.has(fileErr.code)) {
            setSourceError(
              `Tệp "${file.name}" bị từ chối kỹ thuật (${fileErr.code}): ${fileErr.message}`);
          } else {
            onError(
              `Tải lên tệp "${file.name}" không thành công: `
              + `${fileErr instanceof Error ? fileErr.message : String(fileErr)}.`);
          }
          break;
        }
      }
      // Keep whatever was not uploaded; only clear when everything succeeded.
      setFiles(remaining);
      if (remaining.length === 0) {
        setNote('');
        setSourceError(null);
      }
      await onChanged(currentCase.id);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Không tải lên được nguồn.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="panel" data-testid="source-upload-panel">
      <h2>Nguồn chứng từ ({view.sources.length})</h2>
      {sourceError && (
        <div className="notice notice-warn" role="alert">
          {sourceError} — đây là từ chối kỹ thuật của nguồn, không phải kết luận
          nghiệp vụ.
        </div>
      )}
      <div className="field">
        <label htmlFor="sources-file-input">
          Thêm nguồn (JPEG/PNG/PDF/CSV/TXT/MD, tối đa 20 MiB — chọn được nhiều tệp cùng lúc)
        </label>
        <input
          id="sources-file-input"
          data-testid="sources-file-input"
          type="file"
          multiple
          accept="image/*,application/pdf,.csv,.txt,.md"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {files.length > 0 && (
        <div className="selected-files-list" style={{ marginBottom: 'var(--space-3)' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '6px' }}>
            Đã chọn {files.length} tệp:
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {files.map((file, idx) => (
              <span
                key={`${file.name}-${idx}`}
                className="pill-badge"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '4px 8px',
                  background: 'var(--color-bg-subtle, #f1f5f9)',
                  border: '1px solid var(--color-border, #e2e8f0)',
                  borderRadius: '4px', fontSize: '0.82rem',
                }}
              >
                <span>{file.name} ({formatBytes(file.size)})</span>
                <button
                  type="button"
                  aria-label={`Xoá ${file.name}`}
                  style={{
                    border: 'none', background: 'transparent', cursor: 'pointer',
                    padding: 0, fontSize: '0.9rem',
                    color: 'var(--color-muted-foreground, #64748b)', lineHeight: 1,
                  }}
                  onClick={() => removeFile(idx)}
                >
                  ✕
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="field">
        <label htmlFor="upload-note">
          Ghi chú nguồn (bạn nói file lấy từ đâu — không tự xác thực issuer)
        </label>
        <input
          id="upload-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Ví dụ: sao kê do kế toán export"
        />
      </div>
      <button
        className="btn btn-primary"
        disabled={files.length === 0 || uploading}
        onClick={() => void upload()}
      >
        {uploading
          ? `Đang tải lên (${files.length} tệp)...`
          : files.length > 1
            ? `Tải lên ${files.length} nguồn`
            : 'Tải lên nguồn'}
      </button>
      {view.sources.length > 0 && (
        <table style={{ marginTop: 'var(--space-4)' }}>
          <thead>
            <tr>
              <th>File</th>
              <th>Loại</th>
              <th>Dung lượng</th>
              <th>Mở gốc</th>
            </tr>
          </thead>
          <tbody>
            {view.sources.map((s) => (
              <tr key={s.id}>
                <td title={s.sha256}><strong>{s.filename}</strong></td>
                <td>{s.media_type}</td>
                <td>{formatBytes(s.size_bytes)}</td>
                <td>
                  <a href={api.sourceContentUrl(s.id)} target="_blank"
                     rel="noreferrer">Xem</a>
                  {' · '}
                  <a href={api.sourceContentUrl(s.id, true)}>Tải xuống</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
