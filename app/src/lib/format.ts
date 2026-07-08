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

/** The family's current "day": before day_start (e.g. 08:00) it's still
 * yesterday's date. */
export function effectiveDayString(dayStart: string): string {
  const [h, m] = (dayStart || '00:00').split(':').map(Number);
  const now = new Date();
  const cutoff = new Date(now);
  cutoff.setHours(h || 0, m || 0, 0, 0);
  if (now < cutoff) {
    const d = new Date(now);
    d.setDate(d.getDate() - 1);
    return localDateString(d);
  }
  return localDateString(now);
}

export function fmtDateHeading(dateStr: string, effectiveToday?: string): string {
  const today = effectiveToday ?? localDateString();
  if (dateStr === today) return 'Today';
  const [y0, m0, d0] = today.split('-').map(Number);
  const yest = new Date(y0, m0 - 1, d0);
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
