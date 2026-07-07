export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

export function fmtNum(x: number | null | undefined, digits = 1): string {
  if (x == null) return '0';
  const r = Math.round(x * 10 ** digits) / 10 ** digits;
  return Number.isInteger(r) ? String(r) : String(r);
}

/** Local calendar date as YYYY-MM-DD (matches the API's family-timezone days). */
export function localDateString(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function fmtDateHeading(dateStr: string): string {
  const today = localDateString();
  if (dateStr === today) return 'Today';
  const yest = new Date();
  yest.setDate(yest.getDate() - 1);
  if (dateStr === localDateString(yest)) return 'Yesterday';
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export function addDays(dateStr: string, delta: number): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  return localDateString(dt);
}

/** "35 minutes ago" style label for the log screens' time chip. */
export function fmtRelative(date: Date): string {
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  return `${h}h ${mins % 60}m ago`;
}
