const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

const timeFormat = new Intl.DateTimeFormat("es-CO", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dateFormat = new Intl.DateTimeFormat("es-CO", {
  weekday: "short",
  day: "numeric",
  month: "short",
});

export function formatTime(ms: number): string {
  return timeFormat.format(ms);
}

function startOfDay(ms: number): number {
  const date = new Date(ms);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

/** "hoy 18:29", "ayer 09:12" or "sáb, 17 oct · 09:12". */
export function formatDayTime(ms: number, now: number): string {
  const days = Math.round((startOfDay(now) - startOfDay(ms)) / (24 * HOUR));
  if (days === 0) return `hoy ${formatTime(ms)}`;
  if (days === 1) return `ayer ${formatTime(ms)}`;
  return `${dateFormat.format(ms)} · ${formatTime(ms)}`;
}

/** "Hoy", "Ayer" or "sáb, 17 oct". */
export function formatDayLabel(ms: number, now: number): string {
  const days = Math.round((startOfDay(now) - startOfDay(ms)) / (24 * HOUR));
  if (days === 0) return "Hoy";
  if (days === 1) return "Ayer";
  return dateFormat.format(ms);
}

/** "ahora", "hace 40 s", "hace 3 min", "hace 2 h", or the day for older moments. */
export function formatRelative(ms: number, now: number): string {
  const diff = Math.max(0, now - ms);
  if (diff < 10_000) return "ahora";
  if (diff < MINUTE) return `hace ${Math.floor(diff / 1000)} s`;
  if (diff < HOUR) return `hace ${Math.floor(diff / MINUTE)} min`;
  if (diff < 12 * HOUR) return `hace ${Math.floor(diff / HOUR)} h`;
  return formatDayTime(ms, now);
}

/** "45 s", "6 min", "1 h 12 min". */
export function formatDuration(ms: number): string {
  const safe = Math.max(0, ms);
  if (safe < MINUTE) return `${Math.max(1, Math.round(safe / 1000))} s`;
  if (safe < HOUR) return `${Math.round(safe / MINUTE)} min`;
  const hours = Math.floor(safe / HOUR);
  const minutes = Math.round((safe % HOUR) / MINUTE);
  return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
}

/** Elapsed clock for running work: "0:07", "1:42". */
export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

const numberFormat = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });

export function formatSignal(value: number, unit: "%" | "s"): string {
  if (unit === "%") {
    const rounded = value >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
    return `${numberFormat.format(rounded)} %`;
  }
  return `${numberFormat.format(Math.round(value * 100) / 100)} s`;
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
