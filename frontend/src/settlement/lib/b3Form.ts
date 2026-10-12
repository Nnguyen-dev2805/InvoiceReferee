// Pure helpers for the B3 intake form display (no React state).
// Extracted from App.tsx; behavior unchanged.

export function isB3V1Form(form: Record<string, unknown> | undefined): boolean {
  return form?.schema_version === 'b3-intake-v1';
}

export function formatTripDates(startStr?: unknown, endStr?: unknown): string | null {
  if (!startStr && !endStr) return null;
  const parseYMD = (s: string) => {
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return null;
    return { y: m[1], m: m[2], d: m[3] };
  };
  const start = typeof startStr === 'string' ? parseYMD(startStr) : null;
  const end = typeof endStr === 'string' ? parseYMD(endStr) : null;

  if (start && end) {
    if (start.y === end.y && start.m === end.m) {
      if (start.d === end.d) {
        return `${start.d}/${start.m}/${start.y}`;
      }
      return `${start.d}–${end.d}/${start.m}/${start.y}`;
    }
    if (start.y === end.y) {
      return `${start.d}/${start.m} – ${end.d}/${end.m}/${start.y}`;
    }
    return `${start.d}/${start.m}/${start.y} – ${end.d}/${end.m}/${end.y}`;
  }
  if (start) return `${start.d}/${start.m}/${start.y}`;
  if (end) return `${end.d}/${end.m}/${end.y}`;
  return null;
}
