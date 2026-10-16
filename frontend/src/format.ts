export function formatVnd(value: number): string {
  return `${new Intl.NumberFormat("vi-VN").format(value)} ₫`;
}

export function formatVndHint(value: number | string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const num = typeof value === "number" ? value : Number(String(value).replace(/[^0-9.-]/g, ""));
  if (Number.isNaN(num) || !Number.isFinite(num) || num <= 0) return null;
  return `${new Intl.NumberFormat("vi-VN").format(num)} ₫`;
}

export function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("vi-VN");
}

