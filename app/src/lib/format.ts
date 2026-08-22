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

/** Which family-day (YYYY-MM-DD) a timestamp belongs to, honoring day_start
 * (a 3am feed belongs to the previous day when the day starts at 8am). */
export function effectiveDayOf(iso: string, dayStart: string): string {
  const [h, m] = (dayStart || '00:00').split(':').map(Number);
  const d = new Date(iso);
  const cutoff = new Date(d);
  cutoff.setHours(h || 0, m || 0, 0, 0);
  if (d < cutoff) d.setDate(d.getDate() - 1);
  return localDateString(d);
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

const G_PER_OZ = 28.349523125;

/** Grams → "6 lb 6 oz" (storage stays metric; lb/oz is display-only). */
export function fmtLbOz(g: number): string {
  const totalOz = g / G_PER_OZ;
  let lb = Math.floor(totalOz / 16);
  let oz = Math.round((totalOz - lb * 16) * 10) / 10;
  if (oz >= 16) {
    lb += 1;
    oz = 0;
  }
  return oz > 0 ? `${lb} lb ${fmtNum(oz)} oz` : `${lb} lb`;
}

/** Grams → "3.75 kg" (the metabolic team doses and weighs in kg). */
export function fmtKg(g: number): string {
  return `${fmtNum(g / 1000, 2)} kg`;
}

/** Both units, lb/oz first (how the parents read it) then kg (how the clinic
 * reads it): "8 lb 4.4 oz · 3.75 kg". */
export function fmtWeight(g: number): string {
  return `${fmtLbOz(g)} · ${fmtKg(g)}`;
}

/** kg → (lb, oz) for the two-way entry steppers. */
export function kgToLbOz(kg: number): { lb: number; oz: number } {
  const totalOz = (kg * 1000) / G_PER_OZ;
  let lb = Math.floor(totalOz / 16);
  let oz = Math.round((totalOz - lb * 16) * 10) / 10;
  if (oz >= 16) {
    lb += 1;
    oz = 0;
  }
  return { lb: Math.max(0, lb), oz: Math.max(0, oz) };
}

export function lbOzToG(lb: number, oz: number): number {
  return Math.round((lb * 16 + oz) * G_PER_OZ);
}

export function gToOz(g: number): number {
  return g / G_PER_OZ;
}

/** Newborn-style age from a YYYY-MM-DD birth date: "6 d", "7 wk 2 d",
 * then "3 mo 1 wk" once weeks stop being how parents count. */
export function fmtAge(dob: string, onDate?: string): string {
  const [y, m, d] = dob.split('-').map(Number);
  const birth = new Date(y, m - 1, d);
  const ref = onDate
    ? (() => {
        const [ry, rm, rd] = onDate.split('-').map(Number);
        return new Date(ry, rm - 1, rd);
      })()
    : new Date();
  ref.setHours(0, 0, 0, 0);
  const days = Math.floor((ref.getTime() - birth.getTime()) / 86400000);
  if (days < 0) return '';
  if (days < 7) return `${days} d`;
  const weeks = Math.floor(days / 7);
  if (weeks < 14) {
    const rest = days % 7;
    return rest ? `${weeks} wk ${rest} d` : `${weeks} wk`;
  }
  let months =
    (ref.getFullYear() - birth.getFullYear()) * 12 + (ref.getMonth() - birth.getMonth());
  if (ref.getDate() < birth.getDate()) months -= 1;
  const anchor = new Date(birth);
  anchor.setMonth(anchor.getMonth() + months);
  const restWeeks = Math.floor((ref.getTime() - anchor.getTime()) / (7 * 86400000));
  return restWeeks ? `${months} mo ${restWeeks} wk` : `${months} mo`;
}

/** "35 minutes ago" style label for the log screens' time chip. */
export function fmtRelative(date: Date): string {
  const mins = Math.round((Date.now() - date.getTime()) / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m ago`;
  const h = Math.floor(mins / 60);
  return `${h}h ${mins % 60}m ago`;
}
