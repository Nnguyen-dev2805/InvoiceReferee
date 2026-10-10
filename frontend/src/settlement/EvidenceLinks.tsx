import type { SourceView } from './types';
import { sourceContentUrl } from './api';

export interface EvidenceLinksProps {
  refs: string[];
  sources?: SourceView[];
  diagnostics?: boolean;
}

export function EvidenceLinks({ refs, sources = [], diagnostics = false }: EvidenceLinksProps) {
  if (!refs || refs.length === 0) return null;

  const sourceMap = new Map<string, SourceView>();
  for (const s of sources) {
    sourceMap.set(s.id, s);
  }

  const matchedSources = new Map<string, { source: SourceView; subRefs: string[] }>();
  const formRefs: string[] = [];
  const otherRefs: string[] = [];

  for (const ref of refs) {
    if (ref.startsWith('form:') || ref.startsWith('form')) {
      if (!formRefs.includes(ref)) formRefs.push(ref);
      continue;
    }

    let matchedSource: SourceView | undefined = sourceMap.get(ref);
    if (!matchedSource) {
      for (const s of sources) {
        if (
          ref === s.id ||
          ref.startsWith(`${s.id}-`) ||
          ref.startsWith(`${s.id}:`) ||
          ref.startsWith(`${s.id}#`)
        ) {
          if (!matchedSource || s.id.length > matchedSource.id.length) {
            matchedSource = s;
          }
        }
      }
    }

    if (matchedSource) {
      const existing = matchedSources.get(matchedSource.id);
      if (existing) {
        if (!existing.subRefs.includes(ref)) existing.subRefs.push(ref);
      } else {
        matchedSources.set(matchedSource.id, { source: matchedSource, subRefs: [ref] });
      }
    } else {
      if (!otherRefs.includes(ref)) otherRefs.push(ref);
    }
  }

  return (
    <span className="evidence-links-container" style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 'var(--space-1)', alignItems: 'center' }}>
      {Array.from(matchedSources.values()).map(({ source, subRefs }) => (
        <a
          key={source.id}
          href={sourceContentUrl(source.id)}
          target="_blank"
          rel="noreferrer"
          className="evidence-link"
          title={`Tài liệu: ${source.filename} (${source.id})${subRefs.length > 1 ? ` — ${subRefs.length} căn cứ` : ''}`}
        >
          {source.filename || source.id}
        </a>
      ))}
      {formRefs.length > 0 && (
        <span className="evidence-form-ref" title={formRefs.join(', ')}>
          Khai báo từ form
        </span>
      )}
      {otherRefs.map((ref) => (
        <code key={ref} className="evidence-other-ref" title={ref}>
          {ref}
        </code>
      ))}
      {diagnostics && refs.length > 0 && (
        <details className="meta-details" style={{ display: 'inline-block', marginLeft: 'var(--space-1)' }}>
          <summary title="Chi tiết căn cứ kỹ thuật">({refs.length} refs)</summary>
          <ul className="reasons" style={{ marginTop: 'var(--space-1)' }}>
            {refs.map((r, i) => (
              <li key={`${r}-${i}`}><code>{r}</code></li>
            ))}
          </ul>
        </details>
      )}
    </span>
  );
}
